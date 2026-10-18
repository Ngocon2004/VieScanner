from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _create_engine(database_url: str, *, echo: bool) -> AsyncEngine:
    engine = create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )
    # SQLite mặc định TẮT khóa ngoại: mọi ondelete CASCADE/SET NULL bị bỏ qua và dữ liệu mồ côi.
    # Chỉ bật cho engine của app; engine Alembic giữ tắt vì batch migration DROP TABLE sẽ cascade xóa bảng con.
    if engine.dialect.name == "sqlite":
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine


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
