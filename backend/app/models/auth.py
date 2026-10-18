from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.common import UTCDateTime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    exp: int
    type: str = "access"


__all__ = [
    "UserCreate",
    "UserLogin",
    "UserRead",
    "Token",
    "TokenPayload",
]
