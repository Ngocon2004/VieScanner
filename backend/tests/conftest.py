from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

# Phải đặt trước khi import app: test dùng `TestClient(app)` không override `get_db`, và ghi scan chạy nền
# dùng thẳng `SessionLocal`, nên trước đây mỗi lần chạy pytest đều ghi scan/hồ sơ giả vào DB dev.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="viescanner-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TEST_DB_DIR / 'app.db').as_posix()}"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.db.models import cccd_record, correction, scan, user  # noqa: E402, F401
from main import app  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def _app_test_database() -> Generator[None, None, None]:
    engine = create_engine(f"sqlite:///{(_TEST_DB_DIR / 'app.db').as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()
    yield
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
def db_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)

