"""Aligner – stage ① của pipeline.

- `MockAligner`: trả về ảnh gốc (dùng cho dev/test).
- `RealCardAligner`: dùng YOLO (model_crop.pt) detect 4 góc CCCD →
  perspective warp về ảnh thẳng; góc thiếu/tứ giác méo thì tìm thẻ theo đường viền
  (`card_geometry`). Port từ denghwee/OCR_Vietnamese_Read_CCCD
  với một số cải tiến:
    * Lazy-load model qua module-level cache (`_load_yolo_model`) để
      pipeline khởi tạo nhanh và share weight giữa các request.
    * Raise `OCRStageError` thay vì print + return None.
    * Estimate parallelogram chuẩn: tên góc nhất quán (`top_left/top_right/
      bot_right/bot_left`) – tránh bug typo trong code gốc.
    * Auto detect device (`auto` → cuda nếu sẵn).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import logger
from app.services.ocr.card_geometry import find_card_quad, is_card_like
from app.services.ocr.interfaces import OCRStageError

if TYPE_CHECKING:
    import numpy as np
    from ultralytics import YOLO  # type: ignore[import-untyped]


# Thứ tự 4 góc – tương ứng class names trong model_crop.pt của denghwee.
# LƯU Ý: tên dùng "bot_*" (3 ký tự), KHÔNG phải "bottom_*". Code gốc có bug
# trộn 2 cách viết – ta thống nhất theo class output thật của model.
_CORNER_NAMES = ("top_left", "top_right", "bot_right", "bot_left")


# ─────────────────────────────────────────────────────────────────────────────
# Mock
# ─────────────────────────────────────────────────────────────────────────────


class MockAligner:
    """Trả về ảnh gốc, không thay đổi gì. Dùng cho dev/test."""

    def align(self, image: "np.ndarray") -> "np.ndarray":
        logger.debug("MockAligner.align passthrough | shape={}", getattr(image, "shape", None))
        return image


# ─────────────────────────────────────────────────────────────────────────────
# Real – YOLO 4-corner detect + perspective warp
# ─────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=4)
def _load_yolo_model(model_path: str) -> "YOLO":
    """Load model_crop.pt 1 lần / process. Cache theo path để hỗ trợ test."""
    from ultralytics import YOLO  # type: ignore[import-untyped]

    path = Path(model_path)
    if not path.exists():
        raise OCRStageError(
            "aligner",
            f"Không tìm thấy model YOLO tại '{path}'. "
            "Hãy download model_crop.pt vào thư mục models/.",
        )
    logger.info("Loading YOLO aligner model | path={}", path)
    return YOLO(str(path))


def _resolve_device(device: str) -> str:
    """`auto` → 'cuda:0' nếu có CUDA, ngược lại 'cpu'. Còn lại trả về nguyên."""
    if device != "auto":
        return device
    try:
        import torch  # type: ignore[import-untyped]
    except ImportError:
        return "cpu"
    return "cuda:0" if torch.cuda.is_available() else "cpu"


class RealCardAligner:
    """Detect 4 góc CCCD bằng YOLO + perspective warp về ảnh thẳng.

    Args:
      model_path: đường dẫn `model_crop.pt`.
      img_size:   YOLO inference size (default 640).
      device:     'auto' | 'cpu' | 'cuda:0' | ...
      conf_threshold: confidence tối thiểu cho từng góc (filter noise).
      allow_estimate_one: nếu True, được phép nội suy 1 góc thiếu.
      contour_fallback: tìm thẻ bằng đường viền khi góc YOLO thiếu hoặc tứ giác méo.
    """

    def __init__(
        self,
        *,
        model_path: str,
        img_size: int = 640,
        device: str = "auto",
        conf_threshold: float = 0.25,
        allow_estimate_one: bool = True,
        retry_conf_thresholds: tuple[float, ...] = (0.15, 0.10, 0.05),
        contour_fallback: bool = True,
    ) -> None:
        self.model_path = model_path
        self.img_size = img_size
        self.device = _resolve_device(device)
        self.conf_threshold = conf_threshold
        self.allow_estimate_one = allow_estimate_one
        self.retry_conf_thresholds = retry_conf_thresholds
        self.contour_fallback = contour_fallback
        # Pre-warm model để fail-fast nếu thiếu file (không tốn nhiều RAM).
        _load_yolo_model(self.model_path)
        logger.info(
            "RealCardAligner ready | device={} | imgsz={} | conf={} | retries={} | model={}",
            self.device,
            self.img_size,
            self.conf_threshold,
            self.retry_conf_thresholds,
            self.model_path,
        )

    def align(self, image: "np.ndarray") -> "np.ndarray":
        """Ưu tiên: góc YOLO giống thẻ -> đường viền thẻ (OpenCV) -> góc YOLO dù méo -> lỗi."""
        if image is None or getattr(image, "size", 0) == 0:
            raise OCRStageError("aligner", "Ảnh đầu vào rỗng.")

        corners, tried = self._yolo_corners(image)
        if corners is not None and is_card_like(self._as_quad(corners)):
            try:
                return self._warp_perspective(image, corners)
            except OCRStageError as exc:  # vd 4 góc dính sát nhau -> thử đường viền.
                tried.append(f"warp_error={exc.message}")
                corners = None

        if self.contour_fallback:
            try:
                quad = find_card_quad(image, allow_frame=True)
            except Exception as exc:  # noqa: BLE001 – lỗi OpenCV chỉ làm mất đường dự phòng.
                logger.warning("Aligner: tìm đường viền thẻ lỗi: {}", exc)
                quad = None
            if quad is not None:
                logger.info(
                    "Aligner: {} -> căn theo đường viền thẻ.",
                    "tứ giác YOLO méo" if corners is not None else "YOLO không đủ góc",
                )
                return self._warp_perspective(
                    image, {name: (float(x), float(y)) for name, (x, y) in zip(_CORNER_NAMES, quad)}
                )

        if corners is not None:
            logger.warning("Aligner: tứ giác YOLO méo, không tìm được đường viền thẻ -> vẫn căn theo YOLO.")
            return self._warp_perspective(image, corners)

        # Chi tiết từng ngưỡng chỉ để debug: ghi log, không đưa vào thông báo hiển thị cho người dùng.
        logger.warning("Aligner: không đủ 4 góc | {}", " | ".join(tried))
        raise OCRStageError(
            "aligner",
            "Không tìm thấy đủ 4 góc thẻ CCCD. Vui lòng chụp lại ảnh sao cho thấy rõ cả 4 góc thẻ.",
        )

    def _yolo_corners(
        self, image: "np.ndarray"
    ) -> tuple[dict[str, tuple[int, int]] | None, list[str]]:
        """4 góc lồi đầu tiên tìm được qua các ngưỡng (nội suy tối đa 1 góc), kèm log các lần thử."""
        import cv2  # type: ignore[import-untyped]

        tried: list[str] = []
        best = self._best_corners(image)
        for conf in self._candidate_conf_thresholds():
            corners = {name: point for name, (score, point) in best.items() if score >= conf}
            missing = [name for name in _CORNER_NAMES if name not in corners]
            if len(missing) == 1 and self.allow_estimate_one:
                corners = self._estimate_missing_corner(corners, missing[0])
                logger.info("Aligner: thiếu góc {} ở conf={} – đã nội suy.", missing[0], conf)
            elif missing:
                tried.append(f"conf={conf}: missing={missing}")
                continue
            # YOLO gán nhầm lớp góc (hoặc nội suy sai) cho tứ giác tự cắt -> thử ngưỡng khác.
            if not cv2.isContourConvex(self._as_quad(corners).reshape(-1, 1, 2)):
                tried.append(f"conf={conf}: tứ giác không lồi")
                continue
            return corners, tried
        return None, tried

    @staticmethod
    def _as_quad(corners: dict[str, tuple[float, float]]) -> "np.ndarray":
        import numpy as np

        return np.float32([corners[name] for name in _CORNER_NAMES])

    def count_corners(self, image: "np.ndarray") -> int:
        """Đếm số góc CCCD YOLO phát hiện được (0-4). Dùng cho quality gate.

        Không raise: trả về 0 nếu ảnh rỗng hoặc inference lỗi để caller tự quyết.
        """
        if image is None or getattr(image, "size", 0) == 0:
            return 0
        try:
            return len(self._best_corners(image))
        except OCRStageError:
            return 0

    # ── internals ─────────────────────────────────────────────────────────

    def _best_corners(self, image: "np.ndarray") -> dict[str, tuple[float, tuple[int, int]]]:
        """YOLO 1 lần ở ngưỡng thấp nhất -> {góc: (độ tin cậy, tâm)} của box tốt nhất mỗi góc.

        Lọc theo từng ngưỡng sau đó cho kết quả y hệt chạy lại YOLO ở mỗi ngưỡng (NMS theo lớp không để
        box điểm thấp loại box điểm cao), trước đây tốn tới 4 lần chạy cho ảnh khó (2.7 lần/thẻ ở cổng
        chất lượng + 2.2 lần ở aligner, đo trên 61 thẻ thật).
        """
        conf = min(self._candidate_conf_thresholds())
        model = _load_yolo_model(self.model_path)
        try:
            results = model.predict(
                source=image,
                imgsz=self.img_size,
                device=self.device,
                conf=conf,
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001 – inference có thể fail nhiều lý do.
            raise OCRStageError(
                "aligner", f"YOLO inference lỗi: {exc}"
            ) from exc

        if not results:
            return {}
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            logger.warning("YOLO không detect được box nào (conf={}).", conf)
            return {}

        # Pull tensors về CPU 1 lần để tránh GPU↔CPU ping-pong trong loop.
        cls_arr = boxes.cls.cpu().numpy()
        conf_arr = boxes.conf.cpu().numpy()
        xyxy_arr = boxes.xyxy.cpu().numpy()
        names = model.names  # dict[int, str]

        corner_points: dict[str, tuple[float, tuple[int, int]]] = {}
        for corner in _CORNER_NAMES:
            indices = [i for i, c in enumerate(cls_arr) if names[int(c)] == corner]
            if not indices:
                logger.debug("YOLO: không thấy góc {} (conf={}).", corner, conf)
                continue
            best = max(indices, key=lambda i: float(conf_arr[i]))
            x1, y1, x2, y2 = xyxy_arr[best]
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            corner_points[corner] = (float(conf_arr[best]), (cx, cy))
        return corner_points

    def _candidate_conf_thresholds(self) -> tuple[float, ...]:
        """Danh sách threshold sẽ thử theo thứ tự, loại trùng và clamp [0,1]."""
        values = [self.conf_threshold, *self.retry_conf_thresholds]
        normalized: list[float] = []
        seen: set[float] = set()
        for v in values:
            conf = round(max(0.0, min(1.0, float(v))), 4)
            if conf in seen:
                continue
            seen.add(conf)
            normalized.append(conf)
        return tuple(normalized)

    @staticmethod
    def _estimate_missing_corner(
        corners: dict[str, tuple[int, int]], missing: str
    ) -> dict[str, tuple[int, int]]:
        """Nội suy 1 góc thiếu bằng tính chất hình bình hành.

        Cho hình bình hành ABCD: A = B + D - C (C là góc đối diện A).
        """
        # Map: missing → (adj1, adj2, opposite)
        opposite_map = {
            "top_left": ("top_right", "bot_left", "bot_right"),
            "top_right": ("top_left", "bot_right", "bot_left"),
            "bot_right": ("top_right", "bot_left", "top_left"),
            "bot_left": ("top_left", "bot_right", "top_right"),
        }
        adj1_name, adj2_name, opp_name = opposite_map[missing]
        adj1 = corners[adj1_name]
        adj2 = corners[adj2_name]
        opp = corners[opp_name]
        cx = adj1[0] + adj2[0] - opp[0]
        cy = adj1[1] + adj2[1] - opp[1]
        new_corners = dict(corners)
        new_corners[missing] = (cx, cy)
        logger.debug(
            "Estimate missing corner {} from {}+{}-{} = ({}, {})",
            missing, adj1_name, adj2_name, opp_name, cx, cy,
        )
        return new_corners

    @staticmethod
    def _warp_perspective(
        image: "np.ndarray", corners: dict[str, tuple[int, int]]
    ) -> "np.ndarray":
        import cv2  # type: ignore[import-untyped]
        import numpy as np

        pts_src = np.float32([
            corners["top_left"],
            corners["top_right"],
            corners["bot_right"],
            corners["bot_left"],
        ])
        # YOLO gán nhầm lớp góc (hoặc nội suy góc thiếu sai) cho tứ giác tự cắt -> warp ra ảnh
        # méo vô nghĩa mà không báo lỗi; coi là lỗi để aligner thử ngưỡng khác.
        if not cv2.isContourConvex(pts_src.reshape(-1, 1, 2)):
            raise OCRStageError(
                "aligner",
                "4 góc phát hiện không tạo thành tứ giác lồi (nhãn góc bị nhầm).",
            )

        # Width = max(top, bottom); Height = max(left, right). Tránh squash.
        width = int(max(
            np.linalg.norm(pts_src[0] - pts_src[1]),
            np.linalg.norm(pts_src[2] - pts_src[3]),
        ))
        height = int(max(
            np.linalg.norm(pts_src[0] - pts_src[3]),
            np.linalg.norm(pts_src[1] - pts_src[2]),
        ))
        if width <= 5 or height <= 5:
            raise OCRStageError(
                "aligner",
                f"Kích thước warp không hợp lệ (width={width}, height={height}). "
                "Có thể 4 góc detect bị overlap – ảnh quá nhỏ hoặc CCCD bị che.",
            )

        pts_dst = np.float32([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ])

        matrix = cv2.getPerspectiveTransform(pts_src, pts_dst)
        warped = cv2.warpPerspective(image, matrix, (width, height))
        if warped is None or warped.size == 0:
            raise OCRStageError("aligner", "cv2.warpPerspective trả về ảnh rỗng.")

        logger.debug(
            "RealCardAligner.align done | in={} out={}",
            getattr(image, "shape", None), warped.shape,
        )
        return warped


__all__ = ["MockAligner", "RealCardAligner"]
