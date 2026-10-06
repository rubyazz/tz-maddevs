"""Fixtures for DB-marked tests.

IMPORTANT: the env override below must run BEFORE any `from app...` import
in this file (and test modules import after conftest): app.config.Settings
reads env at import time. Otherwise a local run with only TEST_DATABASE_URL
set would point the app's engine at the default dev DB.
"""

from __future__ import annotations

import asyncio
import os

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["SEED_DEMO"] = "0"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.db import Base, make_engine  # noqa: E402

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set (run via `make test`)"
)


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = make_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()
