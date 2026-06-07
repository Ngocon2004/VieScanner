"""Cổng kiểm tra chất lượng ảnh CCCD trước OCR.

Đánh giá 1 ảnh theo 4 nhóm tiêu chí và trả về `QualityReport`:
  ① Độ phân giải  (cạnh ngắn px)         – OpenCV thuần
  ② Độ nét        (variance Laplacian)   – OpenCV thuần
  ③ Độ sáng/lóa   (mean luma + % cháy)   – OpenCV thuần
  ④ Là thẻ CCCD   (số góc YOLO detect)   – chỉ khi OCR_ENGINE=real

Mỗi tiêu chí có ngưỡng "hard" (chặn OCR) và "soft" (vẫn OCR nhưng cảnh báo),
lấy từ `settings`. Hàm được thiết kế để **degrade gracefully**:
  - Thiếu OpenCV       -> trả report `accepted=True` (nhường pipeline xử lý).
  - Không decode được  -> trả report `accepted=True` (pipeline thật sẽ báo lỗi decode).
Nhờ vậy mock pipeline / ảnh test giả vẫn chạy bình thường.

Hàm sync (CPU/GPU-bound) -> controller gọi qua `asyncio.to_thread`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.logging import logger
from app.models.quality import QualityIssue, QualityReport

if TYPE_CHECKING:
    import numpy as np


def _passthrough(reason: str) -> QualityReport:
    logger.debug("quality check passthrough: {}", reason)
    return QualityReport(accepted=True, score=1.0, issues=[], metrics={})


@lru_cache(maxsize=1)
def _get_card_aligner() -> Any:
    """Build (cached) RealCardAligner để đếm góc CCCD. Chỉ gọi ở real mode."""
    from app.repositories import ModelWeightsRepository
    from app.services.ocr.stages import RealCardAligner

    weights = ModelWeightsRepository()
    return RealCardAligner(
        model_path=str(weights.require_path("card_aligner")),
        device=settings.ocr_device,
        conf_threshold=settings.ocr_aligner_conf_threshold,
        retry_conf_thresholds=tuple(settings.ocr_aligner_retry_conf_thresholds),
    )


def _count_card_corners(image: "np.ndarray") -> int | None:
    """Đếm số góc CCCD; trả None nếu không chạy được (coi như bỏ qua tiêu chí)."""
    try:
        return _get_card_aligner().count_corners(image)
    except Exception as exc:  # noqa: BLE001 – thiếu model/weights -> bỏ qua tiêu chí.
        logger.warning("card-presence check skipped: {}", exc)
        return None


def assess_image_quality(
    image_bytes: bytes,
    *,
    run_card_check: bool = False,
) -> QualityReport:
    """Đánh giá chất lượng ảnh. Xem docstring module để biết hành vi degrade."""
    if not settings.quality_check_enabled:
        return _passthrough("quality_check_disabled")

    try:
        import cv2  # type: ignore[import-untyped]
        import numpy as np
    except ImportError:
        return _passthrough("opencv_not_installed")

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or getattr(img, "size", 0) == 0:
        return _passthrough("undecodable_image")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]

    issues: list[QualityIssue] = []
    metrics: dict[str, float] = {}

    # ① Độ phân giải -------------------------------------------------------
    min_side = int(min(h, w))
    metrics["min_side_px"] = float(min_side)
    metrics["width_px"] = float(w)
    metrics["height_px"] = float(h)
    if min_side < settings.quality_min_side_hard_px:
        issues.append(QualityIssue(
            code="low_resolution", severity="hard",
            message=f"Ảnh có độ phân giải quá thấp (cạnh ngắn {min_side}px). Hãy dùng ảnh nét và lớn hơn.",
            metric=float(min_side), threshold=float(settings.quality_min_side_hard_px),
        ))
    elif min_side < settings.quality_min_side_soft_px:
        issues.append(QualityIssue(
            code="low_resolution", severity="soft",
            message=f"Độ phân giải hơi thấp (cạnh ngắn {min_side}px) có thể làm giảm độ chính xác.",
            metric=float(min_side), threshold=float(settings.quality_min_side_soft_px),
        ))

    # ② Độ nét (Laplacian variance) ----------------------------------------
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    metrics["blur_var"] = round(blur_var, 2)
    if blur_var < settings.quality_blur_var_hard:
        issues.append(QualityIssue(
            code="blur", severity="hard",
            message="Ảnh bị mờ/nhòe nặng. Hãy giữ máy chắc tay và lấy nét lại.",
            metric=round(blur_var, 2), threshold=float(settings.quality_blur_var_hard),
        ))
    elif blur_var < settings.quality_blur_var_soft:
        issues.append(QualityIssue(
            code="blur", severity="soft",
            message="Ảnh hơi mờ, kết quả nhận dạng có thể kém chính xác.",
            metric=round(blur_var, 2), threshold=float(settings.quality_blur_var_soft),
        ))

    # ③ Độ sáng + lóa ------------------------------------------------------
    brightness = float(gray.mean())
    metrics["brightness"] = round(brightness, 2)
    if brightness < settings.quality_dark_hard:
        issues.append(QualityIssue(
            code="too_dark", severity="hard",
            message="Ảnh quá tối. Hãy chụp ở nơi đủ sáng.",
            metric=round(brightness, 2), threshold=float(settings.quality_dark_hard),
        ))
    elif brightness < settings.quality_dark_soft:
        issues.append(QualityIssue(
            code="too_dark", severity="soft",
            message="Ảnh hơi tối, nên tăng độ sáng khi chụp.",
            metric=round(brightness, 2), threshold=float(settings.quality_dark_soft),
        ))
    elif brightness > settings.quality_bright_hard:
        issues.append(QualityIssue(
            code="too_bright", severity="hard",
            message="Ảnh quá sáng/cháy sáng. Hãy giảm độ sáng hoặc tránh đèn flash.",
            metric=round(brightness, 2), threshold=float(settings.quality_bright_hard),
        ))
    elif brightness > settings.quality_bright_soft:
        issues.append(QualityIssue(
            code="too_bright", severity="soft",
            message="Ảnh hơi sáng, có thể mất chi tiết ở vùng chữ.",
            metric=round(brightness, 2), threshold=float(settings.quality_bright_soft),
        ))

    # Lóa / cháy sáng: tỉ lệ pixel gần trắng (>=250)
    glare_ratio = float((gray >= 250).mean())
    metrics["glare_ratio"] = round(glare_ratio, 4)
    if glare_ratio > settings.quality_glare_hard:
        issues.append(QualityIssue(
            code="glare", severity="hard",
            message="Ảnh bị lóa/chói sáng nhiều. Hãy tránh ánh sáng phản chiếu trên bề mặt thẻ.",
            metric=round(glare_ratio, 4), threshold=float(settings.quality_glare_hard),
        ))
    elif glare_ratio > settings.quality_glare_soft:
        issues.append(QualityIssue(
            code="glare", severity="soft",
            message="Có hiện tượng lóa nhẹ trên thẻ, có thể che mất một phần thông tin.",
            metric=round(glare_ratio, 4), threshold=float(settings.quality_glare_soft),
        ))

    # ④ Là thẻ CCCD (YOLO) -------------------------------------------------
    if run_card_check:
        corners = _count_card_corners(img)
        if corners is not None:
            metrics["card_corners"] = float(corners)
            if corners == 0:
                issues.append(QualityIssue(
                    code="not_cccd", severity="hard",
                    message="Không phát hiện thẻ CCCD trong ảnh. Hãy chụp đúng mặt trước thẻ, rõ cả 4 góc.",
                    metric=0.0, threshold=1.0,
                ))
            elif corners < 4:
                issues.append(QualityIssue(
                    code="card_partial", severity="soft",
                    message=f"Chỉ thấy {corners}/4 góc thẻ. Hãy chụp thẳng và đủ 4 góc để kết quả tốt hơn.",
                    metric=float(corners), threshold=4.0,
                ))

    accepted = not any(i.severity == "hard" for i in issues)
    score = _compute_score(issues)

    logger.info(
        "quality assessed | accepted={} | score={} | issues={} | metrics={}",
        accepted, score, [i.code for i in issues], metrics,
    )
    return QualityReport(accepted=accepted, score=score, issues=issues, metrics=metrics)


def _compute_score(issues: list[QualityIssue]) -> float:
    """Điểm chất lượng đơn giản: 1.0 trừ phạt theo mức độ vấn đề."""
    score = 1.0
    for issue in issues:
        score -= 0.35 if issue.severity == "hard" else 0.12
    return round(max(0.0, min(1.0, score)), 3)


__all__ = ["assess_image_quality"]
