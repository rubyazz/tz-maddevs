"""Integration tests against a real PostgreSQL (marked `db`, see conftest).

These cover the cross-column/cross-table behavior that unit tests can't:
claim atomicity, the full result→incident→email cycle, maintenance
suppression with the delayed notification pass, and history bucketing.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.checks import runner
from app.db import utcnow
from app.models import AlertEmail, Check, CheckResult, EmailOutbox, Group, Incident, MaintenanceWindow, User
from app.queries import history_rows
from tests.conftest import requires_db

pytestmark = [pytest.mark.asyncio, requires_db]

FAIL = runner.Outcome(ok=False, status_code=None, response_time_ms=5000, error="timeout after 5s")
OK = runner.Outcome(ok=True, status_code=200, response_time_ms=120, error=None)


async def _seed_check(session: AsyncSession, *, threshold: int = 3) -> tuple[User, Group, Check]:
    user = User(email="t@example.com", password_hash=hash_password("password123"))
    session.add(user)
    await session.flush()
    group = Group(owner_id=user.id, name="G")
    session.add(group)
    await session.flush()
    session.add(AlertEmail(group_id=group.id, email="alerts@example.com"))
    check = Check(
        group_id=group.id,
        name="c",
        url="http://localhost:9/whatever",
        interval_seconds=30,
        timeout_seconds=5,
        failure_threshold=threshold,
    )
    session.add(check)
    await session.commit()
    return user, group, check


async def _letters(session: AsyncSession, kind: str | None = None) -> list[EmailOutbox]:
    stmt = select(EmailOutbox)
    if kind is not None:
        stmt = stmt.where(EmailOutbox.kind == kind)
    return list((await session.execute(stmt)).scalars())


async def test_claim_is_exclusive(db_session):
    _, _, check = await _seed_check(db_session)
    first = await runner.claim_check(db_session, check.id, timeout_seconds=check.timeout_seconds)
    assert first is not None
    second = await runner.claim_check(db_session, check.id, timeout_seconds=check.timeout_seconds)
    assert second is None  # in-flight guard holds
    await runner.release_check(db_session, check.id)
    third = await runner.claim_check(db_session, check.id, timeout_seconds=check.timeout_seconds)
    assert third is not None  # and releases


async def test_claim_reschedules_atomically(db_session):
    _, _, check = await _seed_check(db_session)
    claimed = await runner.claim_check(
        db_session, check.id, timeout_seconds=5, reschedule_interval=30
    )
    assert claimed is not None
    await db_session.refresh(check)
    assert check.next_run_at is not None
    delta = (check.next_run_at - utcnow()).total_seconds()
    assert 25 < delta <= 30


async def test_full_incident_cycle_one_down_one_up_email(db_session):
    _, group, check = await _seed_check(db_session, threshold=3)

    for _ in range(3):
        await runner.process_result(db_session, None, check, FAIL)
        await db_session.refresh(check)

    assert check.state == "down"
    assert len(list((await db_session.execute(select(Incident))).scalars())) == 1
    assert len(await _letters(db_session, "down")) == 1  # exactly one DOWN per incident

    # more failures — still one letter
    await runner.process_result(db_session, None, check, FAIL)
    await runner.process_result(db_session, None, check, FAIL)
    assert len(await _letters(db_session, "down")) == 1

    # recovery closes the incident and sends exactly one UP
    await runner.process_result(db_session, None, check, OK)
    await db_session.refresh(check)
    assert check.state == "up"
    open_rows = (
        await db_session.execute(select(Incident).where(Incident.ended_at.is_(None)))
    ).scalars()
    assert list(open_rows) == []
    assert len(await _letters(db_session, "up")) == 1


async def test_maintenance_suppresses_then_window_end_sends(db_session):
    user, group, check = await _seed_check(db_session)

    now = utcnow()
    session_window = MaintenanceWindow(
        owner_id=user.id,
        group_id=group.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(hours=1),
        note="planned",
    )
    db_session.add(session_window)
    await db_session.commit()

    for _ in range(3):
        await runner.process_result(db_session, None, check, FAIL)

    rows = await _letters(db_session)
    assert len(rows) == 1
    assert rows[0].status == "suppressed"
    assert rows[0].suppress_reason == "maintenance_window"

    # incident exists but unnotified; the window-end pass must not send yet
    assert await runner.send_pending_down_notifications(db_session) == 0

    session_window.ends_at = utcnow() - timedelta(seconds=1)
    await db_session.commit()

    assert await runner.send_pending_down_notifications(db_session) == 1
    sent_down = [
        row for row in await _letters(db_session, "down") if row.status == "sent"
    ]
    assert len(sent_down) == 1


async def test_history_buckets_and_summary(db_session):
    _, _, check = await _seed_check(db_session)
    # one result per 5-minute bucket, timestamps aligned to bucket edges
    now = utcnow()
    aligned = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % 5)
    base = aligned - timedelta(minutes=5 * 29)
    for i in range(30):
        db_session.add(
            CheckResult(
                check_id=check.id,
                checked_at=base + timedelta(minutes=5 * i),
                ok=i % 15 != 0,  # 2 failures out of 30
                status_code=200 if i % 15 != 0 else None,
                response_time_ms=100 + i,
                error=None if i % 15 != 0 else "timeout after 5s",
            )
        )
    await db_session.commit()

    buckets, summary = await history_rows(db_session, check.id, "day")
    assert len(buckets) == 289  # 24h of 5-minute buckets + 1
    assert summary["checks"] == 30
    assert summary["ok"] == 28
    assert summary["uptime"] == round(28 / 30, 4)
    assert summary["p95_response_ms"] is not None
    nonzero = [bucket for bucket in buckets if bucket["count"] > 0]
    assert len(nonzero) == 30
    assert all(bucket["count"] == 1 for bucket in nonzero)
