from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import Token, UserCreate, UserLogin, UserRead
from app.models.cccd import ErrorResponse
from app.db.models.user import User
from app.services.auth_service import (
    authenticate_user,
    build_token_response,
    register_user,
)

router = APIRouter(prefix="/auth")


@router.post(
    "/register",
    response_model=UserRead,
    responses={409: {"model": ErrorResponse}},
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    user = await register_user(db, payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token, responses={401: {"model": ErrorResponse}})
async def login(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = await authenticate_user(db, email=str(payload.email), password=payload.password)
    return build_token_response(user)


@router.get("/me", response_model=UserRead, responses={401: {"model": ErrorResponse}})
async def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/refresh", response_model=Token, responses={401: {"model": ErrorResponse}})
async def refresh(user: User = Depends(get_current_user)) -> Token:
    return build_token_response(user)

