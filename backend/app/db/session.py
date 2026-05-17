from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _create_engine(database_url: str, *, echo: bool) -> AsyncEngine:
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )


engine: AsyncEngine = _create_engine(settings.database_url, echo=settings.database_echo)
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def ping_database() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    await engine.dispose()


async def reset_engine_for_tests(database_url: str, *, echo: bool = False) -> None:
    """Rebind global engine/sessionmaker for test runtime.

    This keeps the production import path unchanged while allowing tests to
    use isolated sqlite databases.
    """

    global engine, SessionLocal
    await engine.dispose()
    engine = _create_engine(database_url, echo=echo)
    SessionLocal = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "ping_database",
    "dispose_engine",
    "reset_engine_for_tests",
]
