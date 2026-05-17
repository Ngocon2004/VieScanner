from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, VieScannerError
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.cccd import ErrorResponse
from app.db.models.user import User
from app.models.scan import ScanListItem, ScanRead
from app.db.repositories.scan_repository import ScanRepository

router = APIRouter(prefix="/scans")


@router.get("", response_model=list[ScanListItem], responses={401: {"model": ErrorResponse}})
async def list_scans(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScanListItem]:
    repo = ScanRepository(db)
    scans = await repo.list_by_user(user_id=user.id, limit=limit, offset=offset)
    return [ScanListItem.model_validate(item) for item in scans]


@router.get("/{scan_id}", response_model=ScanRead, responses={401: {"model": ErrorResponse}})
async def get_scan(
    scan_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanRead:
    repo = ScanRepository(db)
    scan = await repo.get_by_id(scan_id)
    if scan is None:
        raise VieScannerError("Scan not found.", code="scan_not_found")
    if scan.user_id is not None and scan.user_id != user.id:
        raise AuthorizationError("You cannot access this scan.", code="scan_forbidden")
    return ScanRead.model_validate(scan)


@router.delete(
    "/{scan_id}",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_scan(
    scan_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    repo = ScanRepository(db)
    scan = await repo.get_by_id(scan_id)
    if scan is None:
        raise VieScannerError("Scan not found.", code="scan_not_found")
    await db.delete(scan)
    await db.commit()
    return {"status": "deleted"}

