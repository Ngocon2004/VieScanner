from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# SQLite trả cột DateTime(timezone=True) về dạng không kèm múi giờ (dù lưu UTC). JSON thiếu múi giờ bị
# trình duyệt hiểu là giờ địa phương -> lệch 7 tiếng ở VN. Mọi thời gian trong response dùng kiểu này.
UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]

__all__ = ["UTCDateTime"]
