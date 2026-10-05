"""Idempotent demo seed (CONTRACT §8). Runs on api startup when SEED_DEMO=1."""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.config import settings
from app.db import utcnow
from app.models import AlertEmail, Check, Group, MaintenanceWindow, User

logger = logging.getLogger(__name__)

DEMO_EMAIL = "demo@pulse.dev"
DEMO_PASSWORD = "demo1234"

INITIAL_MODES = {
    "main": {"mode": "ok"},
    "slow": {"mode": "slow", "delay_ms": 3000},
    "flaky": {"mode": "ok"},
    "dead": {"mode": "ok"},
}


async def _set_emulator_modes() -> None:
    """Best-effort: put demo-sites into known initial modes."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, payload in INITIAL_MODES.items():
                await client.post(f"{settings.demo_sites_url}/mode/{name}", json=payload)
    except Exception:  # noqa: BLE001 — emulator may not be up yet
        logger.warning("could not set demo-sites initial modes (will retry on next start)")


async def seed_demo_data(session: AsyncSession) -> None:
    user = (
        await session.execute(select(User).where(User.email == DEMO_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
        session.add(user)
        await session.flush()

    production = await _group(session, user.id, "Production", "Public-facing services")
    if production.public_slug is None:
        production.public_slug = "demo-status"
    internal = await _group(session, user.id, "Internal", "Internal infrastructure")

    await _alert_email(session, production.id, DEMO_EMAIL)

    await _check(session, production.id, "Main site", f"{settings.demo_sites_url}/site/main",
                 interval=60, timeout=10, threshold=3, public=True)
    await _check(session, production.id, "Slow API", f"{settings.demo_sites_url}/site/slow",
                 interval=60, timeout=5, threshold=2, public=True)
    await _check(session, production.id, "Flaky endpoint", f"{settings.demo_sites_url}/site/flaky",
                 interval=30, timeout=10, threshold=3, public=False)
    await _check(session, internal.id, "Legacy service", f"{settings.demo_sites_url}/site/dead",
                 interval=60, timeout=10, threshold=3, public=False)

    await _maintenance_window(session, user.id, internal.id)

    await session.commit()
    await _set_emulator_modes()


async def _group(session: AsyncSession, owner_id, name: str, description: str) -> Group:
    group = (
        await session.execute(
            select(Group).where(Group.owner_id == owner_id, Group.name == name)
        )
    ).scalar_one_or_none()
    if group is None:
        group = Group(owner_id=owner_id, name=name, description=description)
        session.add(group)
        await session.flush()
    return group


async def _alert_email(session: AsyncSession, group_id, email: str) -> None:
    existing = await session.execute(
        select(AlertEmail).where(AlertEmail.group_id == group_id, AlertEmail.email == email)
    )
    if existing.scalar_one_or_none() is None:
        session.add(AlertEmail(group_id=group_id, email=email))


async def _check(
    session: AsyncSession,
    group_id,
    name: str,
    url: str,
    *,
    interval: int,
    timeout: int,
    threshold: int,
    public: bool,
) -> None:
    existing = await session.execute(
        select(Check).where(Check.group_id == group_id, Check.name == name)
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(
        Check(
            group_id=group_id,
            name=name,
            url=url,
            interval_seconds=interval,
            timeout_seconds=timeout,
            expected_status=200,
            failure_threshold=threshold,
            show_on_public=public,
            next_run_at=utcnow(),
        )
    )


async def _maintenance_window(session: AsyncSession, owner_id, group_id) -> None:
    """One upcoming window on the Internal group: tomorrow 02:00–04:00 UTC."""
    upcoming = await session.execute(
        select(MaintenanceWindow).where(
            MaintenanceWindow.group_id == group_id, MaintenanceWindow.ends_at > utcnow()
        )
    )
    if upcoming.first() is not None:
        return
    tomorrow = (utcnow() + timedelta(days=1)).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    session.add(
        MaintenanceWindow(
            owner_id=owner_id,
            group_id=group_id,
            starts_at=tomorrow,
            ends_at=tomorrow + timedelta(hours=2),
            note="DB upgrade",
        )
    )
