"""Hình học thẻ CCCD: kiểm tra tứ giác 4 góc có giống thẻ không + tìm thẻ bằng đường viền.

YOLO `model_crop.pt` dò từng góc riêng lẻ nên hay hụt góc hoặc gán nhầm góc với thẻ bo tròn.
Trên 63 ảnh thật, thêm bước này vào aligner: ảnh OCR được 42 -> 61, lỗi căn thẻ 19 -> 2,
6 ảnh căn méo đọc được nhiều trường hơn, không ảnh nào mất; ~30 ms/ảnh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.ocr.interfaces import BBox

if TYPE_CHECKING:
    import numpy as np

CARD_ASPECT = 85.6 / 54  # ISO/IEC 7810 ID-1
_MAX_ANGLE_DEVIATION_DEG = 30.0
_MAX_OPPOSITE_SIDE_RATIO = 1.4
_MAX_ASPECT_ERROR = 0.35
_CONTOUR_WORK_SIDE_PX = 800
_MIN_CARD_AREA_RATIO = 0.2
_MAX_CARD_AREA_RATIO = 0.98
# Tứ giác có >= 2 góc sát mép ảnh thường là chính khung ảnh: ảnh nhiễu/không có thẻ cũng ra kết
# quả này khi tỉ lệ khung gần tỉ lệ thẻ, nên quality gate không coi là bằng chứng có thẻ. Aligner
# vẫn dùng được (warp gần như giữ nguyên ảnh): trên 63 ảnh thật đây là phần lớn ảnh được cứu.
_BORDER_MARGIN_RATIO = 0.02


def is_card_like(quad: "np.ndarray") -> bool:
    """Tứ giác (TL, TR, BR, BL) có góc gần vuông, cạnh đối gần bằng nhau, tỉ lệ gần thẻ ID-1.

    Ngưỡng nới rộng để chấp nhận ảnh chụp nghiêng (phối cảnh) và thẻ xoay dọc.
    """
    import numpy as np

    pts = np.asarray(quad, dtype=np.float64).reshape(4, 2)
    sides = [float(np.linalg.norm(pts[i] - pts[(i + 1) % 4])) for i in range(4)]
    if min(sides) <= 1:
        return False
    for i in range(4):
        v1, v2 = pts[i - 1] - pts[i], pts[(i + 1) % 4] - pts[i]
        cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
        if abs(math.degrees(math.acos(max(-1.0, min(1.0, cos)))) - 90) > _MAX_ANGLE_DEVIATION_DEG:
            return False
    opposite = max(
        max(sides[0], sides[2]) / min(sides[0], sides[2]),
        max(sides[1], sides[3]) / min(sides[1], sides[3]),
    )
    aspect = max(sides[0], sides[2]) / max(sides[1], sides[3])
    aspect_error = min(abs(aspect / CARD_ASPECT - 1), abs(aspect * CARD_ASPECT - 1))
    return opposite <= _MAX_OPPOSITE_SIDE_RATIO and aspect_error <= _MAX_ASPECT_ERROR


def _order_quad(pts: "np.ndarray") -> "np.ndarray":
    """Xếp theo góc quanh tâm (chiều kim đồng hồ trên ảnh), bắt đầu từ góc gần gốc toạ độ nhất.

    Không dùng argmin(x+y)/argmin(y-x): với thẻ xoay ~45° hai góc có thể bị chọn trùng.
    """
    import numpy as np

    center = pts.mean(axis=0)
    clockwise = pts[np.argsort(np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0]))]
    return np.float32(np.roll(clockwise, -int(np.argmin(clockwise.sum(axis=1))), axis=0))


def _hugs_frame(quad: "np.ndarray", shape: tuple[int, ...]) -> bool:
    h, w = shape[:2]
    margin = _BORDER_MARGIN_RATIO * max(h, w)
    near = sum(1 for x, y in quad if x <= margin or y <= margin or x >= w - 1 - margin or y >= h - 1 - margin)
    return near >= 2


def _work_image(image: "np.ndarray") -> tuple["np.ndarray", float]:
    import cv2  # type: ignore[import-untyped]

    scale = min(1.0, _CONTOUR_WORK_SIDE_PX / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    return small, scale


def _gray(small: "np.ndarray") -> "np.ndarray":
    import cv2  # type: ignore[import-untyped]

    gray = small if small.ndim == 2 else cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def _gray_masks(gray: "np.ndarray") -> tuple["np.ndarray", ...]:
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    return (
        cv2.dilate(cv2.Canny(gray, 30, 100), np.ones((5, 5), np.uint8), iterations=2),
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
    )


def _contour_quad(contour: "np.ndarray") -> "np.ndarray":
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    for epsilon in (0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(hull, epsilon * perimeter, True)
        if len(approx) == 4:
            return _order_quad(approx.reshape(4, 2).astype(np.float32))
    # Góc bo tròn làm approxPolyDP không ra 4 đỉnh: dùng hình chữ nhật xoay bao ngoài.
    return _order_quad(cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32))


def find_card_quad(image: "np.ndarray", *, allow_frame: bool = False) -> "np.ndarray | None":
    """Tứ giác (TL, TR, BR, BL, toạ độ ảnh gốc) của vùng lớn nhất trông giống thẻ, hoặc None.

    Thử 3 mặt nạ (cạnh Canny, Otsu sáng, Otsu tối) vì thẻ có thể sáng hơn hoặc tối hơn nền.
    `allow_frame`: chấp nhận cả tứ giác sát khung ảnh (dùng để căn, không dùng để xác nhận có thẻ).
    """
    import cv2  # type: ignore[import-untyped]

    if image is None or getattr(image, "ndim", 0) < 2 or image.size == 0:
        return None
    small, scale = _work_image(image)
    gray = _gray(small)
    image_area = gray.shape[0] * gray.shape[1]
    best, best_area = None, 0.0
    for mask in _gray_masks(gray):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(contour)
            if not _MIN_CARD_AREA_RATIO * image_area <= area <= _MAX_CARD_AREA_RATIO * image_area:
                continue
            quad = _contour_quad(contour)
            if area > best_area and is_card_like(quad) and (allow_frame or not _hugs_frame(quad, gray.shape)):
                best, best_area = quad, area
    return None if best is None else best / scale


# Nhiều thẻ trong 1 ảnh: thẻ trên giấy trắng có viền quá mờ cho Canny/Otsu nên thêm mặt nạ màu
# (nền thẻ CCCD có độ bão hòa, giấy trắng và mặt bàn tối thì không). Mỗi thẻ >= 4% ảnh và cỡ tương
# đương thẻ lớn nhất, để ảnh chân dung/QR bên trong một thẻ không bị coi là thẻ khác.
# Trên 63 ảnh thật: đúng 2 ảnh ra 2 thẻ, không ảnh 1 thẻ nào bị tách.
_MULTI_MIN_CARD_AREA_RATIO = 0.04
_MULTI_MIN_RELATIVE_AREA = 0.4
_MULTI_MAX_OVERLAP = 0.3


def find_card_quads(image: "np.ndarray") -> list["np.ndarray"]:
    """Mọi thẻ nằm trọn trong ảnh (TL, TR, BR, BL, toạ độ ảnh gốc), lớn trước; thẻ bị cắt mép bị bỏ."""
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    if image is None or getattr(image, "ndim", 0) != 3 or image.size == 0:
        return []
    small, scale = _work_image(image)
    gray = _gray(small)
    image_area = gray.shape[0] * gray.shape[1]
    hsv = cv2.cvtColor(cv2.GaussianBlur(small, (7, 7), 0), cv2.COLOR_BGR2HSV)
    colored = cv2.inRange(hsv, (0, 25, 90), (180, 255, 255))
    colored = cv2.morphologyEx(colored, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    colored = cv2.morphologyEx(colored, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    candidates: list[tuple[float, "np.ndarray"]] = []
    for mask in (colored, *_gray_masks(gray)):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if not _MULTI_MIN_CARD_AREA_RATIO * image_area <= area <= _MAX_CARD_AREA_RATIO * image_area:
                continue
            quad = _contour_quad(contour)
            if is_card_like(quad) and not _hugs_frame(quad, gray.shape):
                candidates.append((area, quad))
    kept: list[tuple[float, "np.ndarray"]] = []
    for area, quad in sorted(candidates, key=lambda c: -c[0]):
        if kept and area < _MULTI_MIN_RELATIVE_AREA * kept[0][0]:
            break
        if all(
            cv2.intersectConvexConvex(quad, other)[0] <= _MULTI_MAX_OVERLAP * min(area, other_area)
            for other_area, other in kept
        ):
            kept.append((area, quad))
    return [quad / scale for _, quad in kept]


# Thẻ nằm trong ảnh trang (bản photo, biểu mẫu): định vị theo dòng tiêu đề "Cộng hòa.../Căn cước..."
# vì viền thẻ trên bản photo quá mờ cho cách tìm đường viền. Tiêu đề rộng ~60% thẻ và lệch phải
# (bên trái là quốc huy/ảnh). Tiêu đề hẹp hơn 40% ảnh nghĩa là thẻ chỉ chiếm một phần ảnh.
_HEADER_CARD_WIDTH_RATIO = 0.6
_HEADER_CENTER_SHIFT = 0.15
_PAGE_HEADER_MAX_RATIO = 0.4


@dataclass(frozen=True, slots=True)
class CardRegion:
    box: tuple[int, int, int, int]  # x0, y0, x1, y1
    cards_on_page: int


def card_region_from_headers(headers: list[BBox], shape: tuple[int, ...]) -> CardRegion | None:
    """Khung thẻ đầu tiên suy từ các dòng tiêu đề, hoặc None nếu thẻ đã chiếm gần hết ảnh."""
    if not headers:
        return None
    height, width = shape[:2]
    headers = sorted(headers, key=lambda b: b.ymin)
    header_width = max(b.width for b in headers[:2])
    if header_width >= _PAGE_HEADER_MAX_RATIO * width:
        return None
    card_w = header_width / _HEADER_CARD_WIDTH_RATIO
    card_h = card_w / CARD_ASPECT
    first = headers[0]
    # Mỗi thẻ có 2 dòng tiêu đề sát nhau; tiêu đề cách xa hơn nửa thẻ thuộc thẻ khác.
    starts = [first.ymin]
    for b in headers[1:]:
        if b.ymin - starts[-1] > 0.5 * card_h:
            starts.append(b.ymin)
    y1 = first.ymin + card_h if len(starts) == 1 else min(first.ymin + card_h, starts[1] - 5)
    cx = (first.xmin + first.xmax) / 2 - _HEADER_CENTER_SHIFT * card_w
    box = (
        max(0, int(cx - 0.55 * card_w)),
        max(0, int(first.ymin - 0.08 * card_h)),
        min(width, int(cx + 0.55 * card_w)),
        min(height, int(y1)),
    )
    if box[2] - box[0] < 10 or box[3] - box[1] < 10:
        return None
    return CardRegion(box=box, cards_on_page=len(starts))


__all__ = [
    "CARD_ASPECT", "CardRegion", "card_region_from_headers", "find_card_quad", "find_card_quads", "is_card_like",
]
