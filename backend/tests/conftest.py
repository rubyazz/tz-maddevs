"""Fixtures for DB-marked tests.

DB tests run only when TEST_DATABASE_URL points at a disposable PostgreSQL
(docker compose --profile test provides one). The schema is created/dropped
per test function.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import Base, make_engine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set (run via `make test`)"
)

if TEST_DATABASE_URL:
    # The app's Settings read env at import time — point them at the test DB
    # before any `from app...` import happens in test modules.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["SEED_DEMO"] = "0"


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
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
