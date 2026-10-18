"""API trang quản trị: chỉ tài khoản role=admin gọi được (mọi route dùng `require_admin`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models.scan import ScanStatus
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.admin import AdminOverview, AdminScanItem, AdminSystem, AdminUser, AdminUserUpdate
from app.models.cccd import ErrorResponse
from app.services import admin_stats
from app.services.ocr.version import pipeline_version
from app.services.ocr_engine import is_ocr_engine_ready

router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_admin)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@router.get("/overview", response_model=AdminOverview)
async def overview(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> AdminOverview:
    return await admin_stats.build_overview(db, days=days)


@router.get("/system", response_model=AdminSystem)
async def system(request: Request) -> AdminSystem:
    worker = getattr(request.app.state, "job_worker", None)
    return AdminSystem(
        ocr_engine=settings.ocr_engine,
        engine_ready=is_ocr_engine_ready(),
        pipeline_version=pipeline_version(),
        queue_size=worker.qsize() if worker else 0,
        concurrency=settings.ocr_max_concurrency,
        qr_enabled=settings.ocr_qr_enabled,
        cache_enabled=settings.ocr_result_cache_enabled,
        cache_ttl_hours=settings.ocr_result_cache_ttl_seconds / 3600,
        scan_retention_days=settings.scan_retention_days,
        job_retention_days=settings.job_retention_days,
        auth_required=settings.auth_required,
    )


@router.get("/users", response_model=list[AdminUser])
async def users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=100),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUser]:
    return await admin_stats.list_users(db, limit=limit, offset=offset, query=q)


@router.patch("/users/{user_id}", response_model=AdminUser, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUser:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Không tìm thấy người dùng.", code="user_not_found")
    # Chặn tự hạ quyền/tự khóa: người thao tác luôn là 1 admin đang hoạt động, nên hệ thống không bao giờ mất admin cuối cùng.
    if user.id == admin.id and (payload.role == "user" or payload.is_active is False):
        raise ConflictError("Không thể tự hạ quyền hoặc tự khóa tài khoản đang dùng.", code="admin_self_change")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await db.commit()
    [item] = await admin_stats.list_users(db, limit=1, offset=0, user_id=user.id)
    return item


@router.get("/scans", response_model=list[AdminScanItem])
async def scans(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: ScanStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[AdminScanItem]:
    return await admin_stats.list_scans(db, limit=limit, offset=offset, status=status)
