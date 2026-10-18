from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.models.auth import Token, TokenPayload, UserCreate
from app.db.models.user import User
from app.db.repositories.user_repository import UserRepository


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_DUMMY_HASH = _pwd_context.hash("viescanner-dummy-password")
_TOKEN_INVALID_MSG = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_access_token(
    *,
    user_id: str,
    expires_minutes: int | None = None,
) -> str:
    expire_min = expires_minutes or settings.jwt_access_expire_min
    exp = datetime.now(UTC) + timedelta(minutes=expire_min)
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError(_TOKEN_INVALID_MSG, code="auth_token_invalid") from exc

    try:
        token_payload = TokenPayload.model_validate(payload)
    except ValidationError as exc:
        raise AuthenticationError(_TOKEN_INVALID_MSG, code="auth_token_invalid") from exc
    if token_payload.type != "access":
        raise AuthenticationError(_TOKEN_INVALID_MSG, code="auth_token_invalid")
    return token_payload


async def register_user(session: AsyncSession, data: UserCreate) -> User:
    repo = UserRepository(session)
    existing = await repo.get_by_email(str(data.email).lower())
    if existing is not None:
        raise ConflictError("Email đã được đăng ký.", code="email_exists")

    try:
        user = await repo.create_user(
            email=str(data.email).lower(),
            password_hash=hash_password(data.password),
            full_name=data.full_name,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("Email đã được đăng ký.", code="email_exists") from exc
    return user


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    repo = UserRepository(session)
    user = await repo.get_by_email(email.lower())
    # Vẫn băm khi email không tồn tại để thời gian phản hồi không lộ email nào đã đăng ký.
    password_hash = user.password_hash if user is not None else _DUMMY_HASH
    if not verify_password(password, password_hash) or user is None:
        raise AuthenticationError("Email hoặc mật khẩu không đúng.", code="auth_invalid")
    if not user.is_active:
        raise AuthenticationError("Tài khoản đã bị khóa.", code="auth_inactive")
    return user


def build_token_response(user: User) -> Token:
    return Token(access_token=create_access_token(user_id=user.id))


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "register_user",
    "authenticate_user",
    "build_token_response",
]

