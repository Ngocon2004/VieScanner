"""Há»‡ thá»‘ng exception táº­p trung cho VieScanner.

Má»i exception nghiá»‡p vá»¥ nÃªn káº¿ thá»«a `VieScannerError` Ä‘á»ƒ Ä‘Æ°á»£c handler
chuyá»ƒn thÃ nh response JSON nháº¥t quÃ¡n.
"""

from __future__ import annotations

from fastapi import status


class VieScannerError(Exception):
    """Base exception cho toÃ n bá»™ á»©ng dá»¥ng."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "CÃ³ lá»—i xáº£y ra. Vui lÃ²ng thá»­ láº¡i."

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message
        if code:
            self.code = code


class ImageValidationError(VieScannerError):
    """áº¢nh upload khÃ´ng há»£p lá»‡ (size, mime, magic bytes)."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "image_invalid"
    message = "áº¢nh upload khÃ´ng há»£p lá»‡."


class OCRFailedError(VieScannerError):
    """OCR engine xá»­ lÃ½ tháº¥t báº¡i."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "ocr_failed"
    message = "KhÃ´ng thá»ƒ trÃ­ch xuáº¥t thÃ´ng tin tá»« áº£nh."


class ExcelGenerationError(VieScannerError):
    """Lá»—i khi táº¡o file Excel."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "excel_failed"
    message = "KhÃ´ng thá»ƒ táº¡o file Excel."


class AuthenticationError(VieScannerError):
    """Invalid/missing auth credentials."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "auth_invalid"
    message = "Authentication failed."


class AuthorizationError(VieScannerError):
    """Authenticated but not allowed."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to perform this action."


class ConflictError(VieScannerError):
    """Resource already exists or in conflicting state."""

    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Conflict detected."

