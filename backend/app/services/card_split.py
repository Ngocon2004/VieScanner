"""Tách ảnh chụp nhiều thẻ CCCD thành từng ảnh một thẻ trước khi OCR.

Pipeline OCR chỉ đọc một thẻ mỗi ảnh: ảnh nhiều thẻ trước đây cho ra trường trộn của nhiều người
và bỏ sót các thẻ còn lại. Mỗi thẻ cắt ra (kèm lề để aligner vẫn thấy viền thẻ) thành một item riêng
của job, nên kiểm tra chất lượng, OCR, cache và danh sách phía sau giữ nguyên.
"""

from __future__ import annotations

from app.core.logging import logger
from app.services.ocr.card_geometry import find_card_quads

_MARGIN_RATIO = 0.05
_JPEG_QUALITY = 92
_TARGET_LONG_SIDE_PX = 1200
_MAX_UPSCALE = 3.0
_MIN_CARD_SATURATION = 30.0


def _mean_saturation(image, quad) -> float:  # noqa: ANN001 – np.ndarray
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    mask = np.zeros(image.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)
    return float(cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[..., 1][mask > 0].mean())


def _is_portrait(quad) -> bool:  # noqa: ANN001 – np.ndarray (TL, TR, BR, BL)
    import numpy as np

    horizontal = np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])
    vertical = np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])
    return bool(vertical > horizontal)


def split_cards(data: bytes) -> list[bytes]:
    """Ảnh JPEG của từng thẻ theo thứ tự đọc (trên xuống, trái sang); [] nếu ảnh có ít hơn 2 thẻ."""
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return []
    quads = find_card_quads(image)
    # Vùng không có màu thì không phải thẻ chụp màu: 2 thẻ thật trong ảnh mẫu có độ bão hòa 61 và 66,
    # 2 ô trên trang giấy bị nhận nhầm là thẻ chỉ 17 và 22. Bản photo xám không tách, pipeline xử lý như trước.
    if len(quads) < 2 or any(_mean_saturation(image, quad) < _MIN_CARD_SATURATION for quad in quads):
        return []
    short_side = min(float(np.ptp(q[:, 1])) for q in quads)
    quads.sort(key=lambda q: (int(q[:, 1].mean() // short_side), float(q[:, 0].mean())))
    height, width = image.shape[:2]
    crops: list[bytes] = []
    for index, quad in enumerate(quads):
        x0, y0 = quad.min(axis=0)
        x1, y1 = quad.max(axis=0)
        margin = _MARGIN_RATIO * max(x1 - x0, y1 - y0)
        left, top = max(0, int(x0 - margin)), max(0, int(y0 - margin))
        right, bottom = min(width, int(x1 + margin)), min(height, int(y1 + margin))
        crop = image[top:bottom, left:right].copy()
        # Phần thẻ bên cạnh lọt vào lề sẽ làm aligner/OCR lẫn chữ của người khác -> tô trắng.
        for other_index, other in enumerate(quads):
            if other_index != index:
                cv2.fillConvexPoly(crop, (other - (left, top)).astype(np.int32), (255, 255, 255))
        # Thẻ dọc cắt riêng làm aligner/model hướng đọc sai (1/8 trường); xoay ngang thì đọc đủ 8/8.
        # Ngược 180 độ (nếu có) để model hướng của pipeline tự sửa.
        if _is_portrait(quad):
            crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        # Thẻ nhỏ trong ảnh (vài trăm px) cắt riêng thì chữ quá nhỏ cho detector -> phóng to.
        scale = min(_MAX_UPSCALE, _TARGET_LONG_SIDE_PX / max(crop.shape[:2]))
        if scale > 1:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        if not ok:
            return []
        crops.append(encoded.tobytes())
    logger.info("Tách ảnh nhiều thẻ | cards={}", len(crops))
    return crops


__all__ = ["split_cards"]
