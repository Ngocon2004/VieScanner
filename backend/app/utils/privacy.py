"""Che dữ liệu cá nhân trước khi ghi log (log có thể được chia sẻ khi debug)."""

from __future__ import annotations


def mask_id_number(value: str | None) -> str:
    """'001202000123' -> '001******123'."""
    if not value:
        return "-"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}{'*' * (len(value) - 6)}{value[-3:]}"


__all__ = ["mask_id_number"]
