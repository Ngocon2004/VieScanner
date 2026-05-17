from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.models.auth import Token, TokenPayload, UserCreate
from app.db.models.user import User
from app.db.repositories.user_repository import UserRepository


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
        raise AuthenticationError("Invalid or expired token.") from exc

    token_payload = TokenPayload.model_validate(payload)
    if token_payload.type != "access":
        raise AuthenticationError("Unsupported token type.")
    return token_payload


async def register_user(session: AsyncSession, data: UserCreate) -> User:
    repo = UserRepository(session)
    existing = await repo.get_by_email(str(data.email).lower())
    if existing is not None:
        raise ConflictError("Email already exists.", code="email_exists")

    user = await repo.create_user(
        email=str(data.email).lower(),
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    await session.commit()
    return user


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    repo = UserRepository(session)
    user = await repo.get_by_email(email.lower())
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password.", code="auth_invalid")
    if not user.is_active:
        raise AuthenticationError("User account is disabled.", code="auth_inactive")
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

