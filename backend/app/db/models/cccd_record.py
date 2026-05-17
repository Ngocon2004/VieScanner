from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CCCDRecord(Base):
    __tablename__ = "cccd_records"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    scan_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("scans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    id_number: Mapped[str] = mapped_column(String(12), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    dob: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(8))
    nationality: Mapped[str] = mapped_column(String(100))
    origin: Mapped[str] = mapped_column(Text)
    residence: Mapped[str] = mapped_column(Text)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    scan: Mapped["Scan | None"] = relationship(back_populates="record")
    user: Mapped["User | None"] = relationship(back_populates="records")


if TYPE_CHECKING:
    from app.db.models.scan import Scan
    from app.db.models.user import User


__all__ = ["CCCDRecord"]

