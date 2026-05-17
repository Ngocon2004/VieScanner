from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.session import get_db
from app.db.models.user import User
from app.db.repositories.user_repository import UserRepository
from app.services.auth_service import decode_token


_bearer = HTTPBearer(auto_error=False)


async def _load_user_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
    *,
    db: AsyncSession,
    required: bool,
) -> User | None:
    if credentials is None:
        if required:
            raise AuthenticationError("Missing bearer token.", code="auth_missing")
        return None

    token = credentials.credentials
    payload = decode_token(token)

    repo = UserRepository(db)
    user = await repo.get_by_id(payload.sub)
    if user is None:
        raise AuthenticationError("User not found for token.", code="auth_user_not_found")
    if not user.is_active:
        raise AuthenticationError("User is inactive.", code="auth_inactive")
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _load_user_from_credentials(credentials, db=db, required=True)
    assert user is not None
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    required = settings.auth_required
    return await _load_user_from_credentials(credentials, db=db, required=required)


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != "admin":
        raise AuthorizationError(code="admin_required")
    return user


__all__ = ["get_current_user", "get_optional_user", "require_admin"]

