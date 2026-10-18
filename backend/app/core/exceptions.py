"""Hệ thống exception tập trung cho VieScanner.

Mọi exception nghiệp vụ nên kế thừa `VieScannerError` để được handler
chuyển thành response JSON nhất quán.
"""

from __future__ import annotations

from fastapi import status

from app.core.config import settings


class VieScannerError(Exception):
    """Base exception cho toàn bộ ứng dụng."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "Có lỗi xảy ra. Vui lòng thử lại."

    details: list | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: list | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message
        if code:
            self.code = code
        if details is not None:
            self.details = details


class RequestTooLargeError(VieScannerError):
    """Tổng dung lượng request vượt `MAX_REQUEST_MB`."""

    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "request_too_large"

    def __init__(self) -> None:
        super().__init__(
            f"Tổng dung lượng gửi lên vượt quá {settings.max_request_mb}MB. "
            "Hãy chia thành nhiều lần gửi, mỗi lần ít file hơn."
        )


class ImageValidationError(VieScannerError):
    """Ảnh upload không hợp lệ (size, mime, magic bytes)."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "image_invalid"
    message = "Ảnh upload không hợp lệ."


class OCRFailedError(VieScannerError):
    """OCR engine xử lý thất bại."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "ocr_failed"
    message = "Không thể trích xuất thông tin từ ảnh."


class ImageQualityError(VieScannerError):
    """Ảnh không đạt tiêu chuẩn chất lượng (mờ, tối, lóa, độ phân giải thấp, không phải CCCD)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "image_quality_low"
    message = "Ảnh không đạt tiêu chuẩn để trích xuất. Vui lòng chụp lại."


class ExcelGenerationError(VieScannerError):
    """Lỗi khi tạo file Excel."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "excel_failed"
    message = "Không thể tạo file Excel."


class AuthenticationError(VieScannerError):
    """Invalid/missing auth credentials."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "auth_invalid"
    message = "Xác thực thất bại."


class AuthorizationError(VieScannerError):
    """Authenticated but not allowed."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "Bạn không có quyền thực hiện thao tác này."


class ConflictError(VieScannerError):
    """Resource already exists or in conflicting state."""

    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Dữ liệu bị trùng hoặc xung đột."



class NotFoundError(VieScannerError):
    """Resource does not exist (or is hidden from the caller)."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Không tìm thấy dữ liệu."
