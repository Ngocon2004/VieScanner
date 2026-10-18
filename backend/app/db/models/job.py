from __future__ import annotations

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobSource(str, enum.Enum):
    UPLOAD = "upload"
    IMPORT_PDF = "import_pdf"
    CAMERA = "camera"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobItemStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = {JobStatus.COMPLETED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED}
TERMINAL_ITEM_STATUSES = {
    JobItemStatus.DONE,
    JobItemStatus.REJECTED,
    JobItemStatus.FAILED,
    JobItemStatus.CANCELLED,
}


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        values_callable=lambda members: [m.value for m in members],
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[JobSource] = mapped_column(_enum(JobSource, "job_source_enum"))
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status_enum"), default=JobStatus.QUEUED, index=True
    )
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    ocr_engine: Mapped[str] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["JobItem"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        # Thẻ tách ra từ 1 ảnh nhận seq cuối job: sắp theo file/trang để vẫn đứng cạnh nhau.
        order_by="[JobItem.upload_index, JobItem.page_number, JobItem.seq]",
    )


class JobItem(Base):
    __tablename__ = "job_items"
    __table_args__ = (UniqueConstraint("job_id", "seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    upload_index: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[JobItemStatus] = mapped_column(
        _enum(JobItemStatus, "job_item_status_enum"), default=JobItemStatus.QUEUED, index=True
    )
    scan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="items")


__all__ = [
    "Job",
    "JobItem",
    "JobItemStatus",
    "JobSource",
    "JobStatus",
    "TERMINAL_ITEM_STATUSES",
    "TERMINAL_JOB_STATUSES",
]
