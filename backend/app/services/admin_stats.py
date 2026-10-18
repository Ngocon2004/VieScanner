"""Số liệu cho trang quản trị: tổng quan lượt quét, chất lượng từng trường, người dùng.

Gom nhóm theo ngày làm ở Python (không dùng hàm ngày của SQL) để chạy giống nhau trên SQLite và
PostgreSQL. Chỉ trả số đếm/tỉ lệ và số CCCD đã che, không trả dữ liệu CCCD thô ra trang quản trị.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.correction import Correction
from app.db.models.job import Job, JobStatus
from app.db.models.scan import Scan, ScanStatus
from app.db.models.user import User
from app.models.admin import (
    AdminOverview,
    AdminScanItem,
    AdminUser,
    DailyScans,
    ErrorCount,
    FieldQuality,
    OverviewTotals,
)
from app.utils.privacy import mask_id_number

# Biểu đồ theo ngày dùng giờ Việt Nam: một lượt quét lúc 6h sáng không bị tính sang ngày hôm trước.
VN_TZ = timezone(timedelta(hours=7))
REVIEW_CONFIDENCE = 0.85
# Giới hạn số scan đọc vào bộ nhớ cho một lần tính: đủ cho quy mô hiện tại, tránh treo khi bảng lớn.
MAX_SCANS = 50_000
# Đúng 5 trường của danh sách xuất Excel (quê quán, quốc tịch, ngày hết hạn không còn được xuất).
FIELDS = ("full_name", "id_number", "dob", "gender", "residence")


def _percentile(sorted_values: list[int], q: float) -> int | None:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1))))
    return sorted_values[index]


def _as_utc(value: datetime) -> datetime:
    # SQLite trả datetime không kèm múi giờ cho cột timezone=True.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _confidence(confidences: dict, field: str) -> float:
    value = confidences.get(field)
    return float(value) if isinstance(value, (int, float)) else 0.0


async def build_overview(session: AsyncSession, *, days: int, now: datetime | None = None) -> AdminOverview:
    now = now or datetime.now(timezone.utc)
    # Kỳ = `days` ngày lịch theo giờ VN tính cả hôm nay, khớp đúng các cột của biểu đồ theo ngày.
    today = now.astimezone(VN_TZ).date()
    day_keys = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    since = datetime.combine(day_keys[0], time.min, VN_TZ).astimezone(timezone.utc)

    rows = (
        await session.execute(
            select(Scan.created_at, Scan.status, Scan.duration_ms, Scan.error_code, Scan.confidences)
            .where(Scan.created_at >= since)
            .order_by(Scan.created_at.desc())
            .limit(MAX_SCANS)
        )
    ).all()

    daily = {day: Counter() for day in day_keys}
    errors: Counter[str] = Counter()
    durations: list[int] = []
    field_read: Counter[str] = Counter()
    field_low: Counter[str] = Counter()
    for created_at, status, duration_ms, error_code, confidences in rows:
        day = _as_utc(created_at).astimezone(VN_TZ).date()
        ok = status == ScanStatus.SUCCESS
        if day in daily:
            daily[day]["success" if ok else "failed"] += 1
        if not ok:
            errors[error_code or "unknown"] += 1
            continue
        if duration_ms is not None:
            durations.append(duration_ms)
        for field in FIELDS:
            value = _confidence(confidences or {}, field)
            if value > 0:
                field_read[field] += 1
                field_low[field] += value < REVIEW_CONFIDENCE

    corrected = dict(
        (
            await session.execute(
                select(Correction.field_name, func.count())
                .join(Scan, Scan.id == Correction.scan_id)
                # Chỉ tính bản sửa của lượt quét đã đánh dấu xuất, khớp với mẫu số `exported_scans`.
                .where(Scan.created_at >= since, Scan.exported_at.is_not(None))
                .group_by(Correction.field_name)
            )
        ).all()
    )
    exported_scans = (
        await session.scalar(select(func.count()).where(Scan.created_at >= since, Scan.exported_at.is_not(None)))
    ) or 0

    # Tổng đếm bằng SQL để luôn đúng kể cả khi `rows` bị cắt ở MAX_SCANS.
    by_status = dict(
        (
            await session.execute(
                select(Scan.status, func.count()).where(Scan.created_at >= since).group_by(Scan.status)
            )
        ).all()
    )
    total_scans = sum(by_status.values())
    total_ok = by_status.get(ScanStatus.SUCCESS, 0)

    durations.sort()
    totals = OverviewTotals(
        scans=total_scans,
        succeeded=total_ok,
        failed=total_scans - total_ok,
        median_duration_ms=_percentile(durations, 0.5),
        p90_duration_ms=_percentile(durations, 0.9),
        users=(await session.scalar(select(func.count()).select_from(User))) or 0,
        new_users=(await session.scalar(select(func.count()).where(User.created_at >= since))) or 0,
        exported_scans=exported_scans,
        corrections=sum(corrected.values()),
        active_jobs=(
            await session.scalar(
                select(func.count()).where(Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]))
            )
        )
        or 0,
    )
    job_status = dict(
        (
            await session.execute(
                select(Job.status, func.count()).where(Job.created_at >= since).group_by(Job.status)
            )
        ).all()
    )

    return AdminOverview(
        days=days,
        totals=totals,
        daily=[
            DailyScans(date=day.isoformat(), success=daily[day]["success"], failed=daily[day]["failed"])
            for day in day_keys
        ],
        errors=[ErrorCount(code=code, count=count) for code, count in errors.most_common(8)],
        fields=[
            FieldQuality(
                field=field,
                read=field_read[field],
                read_rate=field_read[field] / total_ok if total_ok else 0.0,
                low_confidence=field_low[field],
                corrected=corrected.get(field, 0),
                corrected_rate=corrected.get(field, 0) / exported_scans if exported_scans else 0.0,
            )
            for field in FIELDS
        ],
        jobs={status.value: count for status, count in job_status.items()},
    )


async def list_users(
    session: AsyncSession, *, limit: int, offset: int, query: str | None = None, user_id: str | None = None
) -> list[AdminUser]:
    scans = select(Scan.user_id, func.count().label("n")).group_by(Scan.user_id).subquery()
    exported = (
        select(Scan.user_id, func.count().label("n"))
        .where(Scan.exported_at.is_not(None))
        .group_by(Scan.user_id)
        .subquery()
    )
    last_scan = select(Scan.user_id, func.max(Scan.created_at).label("at")).group_by(Scan.user_id).subquery()
    stmt = (
        select(User, scans.c.n, exported.c.n, last_scan.c.at)
        .outerjoin(scans, scans.c.user_id == User.id)
        .outerjoin(exported, exported.c.user_id == User.id)
        .outerjoin(last_scan, last_scan.c.user_id == User.id)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if user_id:
        stmt = stmt.where(User.id == user_id)
    if query:
        # Ký tự đại diện của LIKE trong ô tìm kiếm phải được hiểu là chữ thường.
        escaped = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            func.lower(User.email).like(pattern, escape="\\")
            | func.lower(User.full_name).like(pattern, escape="\\")
        )
    return [
        AdminUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            scans=scan_count or 0,
            exported_scans=exported_count or 0,
            last_scan_at=last_at,
        )
        for user, scan_count, exported_count, last_at in (await session.execute(stmt)).all()
    ]


async def list_scans(
    session: AsyncSession, *, limit: int, offset: int, status: ScanStatus | None
) -> list[AdminScanItem]:
    stmt = (
        select(Scan, User.email)
        .outerjoin(User, User.id == Scan.user_id)
        .order_by(Scan.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(Scan.status == status)
    items = []
    for scan, email in (await session.execute(stmt)).all():
        confidences = scan.confidences or {}
        id_number = (scan.raw_data or {}).get("id_number") if confidences.get("id_number") else None
        items.append(
            AdminScanItem(
                id=scan.id,
                created_at=scan.created_at,
                user_email=email,
                status=scan.status.value,
                ocr_engine=scan.ocr_engine,
                duration_ms=scan.duration_ms,
                error_code=scan.error_code,
                id_number_masked=mask_id_number(id_number) if id_number else None,
                fields_read=sum(1 for field in FIELDS if _confidence(confidences, field) > 0),
                low_confidence_fields=sum(
                    1 for field in FIELDS if 0 < _confidence(confidences, field) < REVIEW_CONFIDENCE
                ),
                from_job=scan.job_id is not None,
            )
        )
    return items


__all__ = ["build_overview", "list_scans", "list_users"]
