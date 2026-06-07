"""Pydantic schemas cho cổng kiểm tra chất lượng ảnh (pre-OCR).

Module này là "leaf" – KHÔNG import từ `models/cccd.py` để tránh circular import
(`cccd.py` import ngược `QualityReport` từ đây cho field tùy chọn).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QualityIssue(BaseModel):
    """Một vấn đề chất lượng phát hiện được trên ảnh."""

    code: str = Field(..., description="Mã vấn đề: blur | too_dark | too_bright | glare | low_resolution | not_cccd | card_partial")
    severity: Literal["hard", "soft"] = Field(..., description="hard = chặn OCR, soft = cảnh báo")
    message: str = Field(..., description="Mô tả tiếng Việt cho người dùng")
    metric: float | None = Field(default=None, description="Giá trị đo được")
    threshold: float | None = Field(default=None, description="Ngưỡng so sánh")


class QualityReport(BaseModel):
    """Kết quả đánh giá chất lượng 1 ảnh."""

    accepted: bool = Field(..., description="True nếu không có vấn đề 'hard'")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Điểm chất lượng tổng hợp 0-1")
    issues: list[QualityIssue] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict, description="Các chỉ số đo được (debug)")

    @property
    def has_hard_issue(self) -> bool:
        return any(issue.severity == "hard" for issue in self.issues)

    @property
    def has_soft_issue(self) -> bool:
        return any(issue.severity == "soft" for issue in self.issues)


__all__ = ["QualityIssue", "QualityReport"]
