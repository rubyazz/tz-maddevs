"""Async engine/session wiring and shared SQLAlchemy base."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def utcnow() -> datetime:
    """Aware UTC now — the only clock the domain uses."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or settings.database_url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def new_id() -> uuid.UUID:
    """Client-side UUID default (portable; DB has gen_random_uuid() too)."""
    return uuid.uuid4()


async def session_scope(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """One-shot session with commit/rollback — used by the scheduler tasks."""
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
