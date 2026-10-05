"""Check execution: HTTP probe, atomic claim, result processing, notifications.

Used by both the scheduler loop and the manual "run now" API endpoint —
one code path, so behavior cannot drift between them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app import email as email_mod
from app import events
from app.checks.logic import Decision, decide
from app.db import utcnow
from app.models import AlertEmail, Check, CheckResult, Group, Incident, MaintenanceWindow

logger = logging.getLogger(__name__)


class CheckInProgress(Exception):
    """Raised when the check is already being executed (claim failed)."""


@dataclass(slots=True)
class Outcome:
    ok: bool
    status_code: int | None
    response_time_ms: int | None
    error: str | None


async def perform_http_check(
    client: httpx.AsyncClient,
    url: str,
    timeout_seconds: int,
    expected_status: int,
    expected_body: str | None,
) -> Outcome:
    """Probe one URL. Never raises: every failure mode becomes an Outcome."""
    started = time.monotonic()
    status_code: int | None = None
    error: str | None = None
    try:
        response = await client.get(
            url, timeout=timeout_seconds, follow_redirects=True
        )
        status_code = response.status_code
        if response.status_code != expected_status:
            error = f"unexpected status {response.status_code} (expected {expected_status})"
        elif expected_body is not None and expected_body not in response.text:
            error = "expected body substring not found"
    except httpx.TimeoutException:
        error = f"timeout after {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001 — any transport error is a failed check
        error = f"{type(exc).__name__}: {exc}"

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return Outcome(
        ok=error is None,
        status_code=status_code,
        response_time_ms=elapsed_ms,
        error=error,
    )


async def claim_check(
    session: AsyncSession,
    check_id,
    *,
    timeout_seconds: int,
    reschedule_interval: int | None = None,
) -> Check | None:
    """Atomically claim a check for execution (CONTRACT §3.2).

    Returns the fresh Check row on success, None if someone else holds the
    claim (or the check is paused). Optionally reschedules next_run_at in the
    same statement — the scheduler uses this so a dispatched check can never
    be picked twice, even if it runs longer than its interval.
    """
    now = utcnow()
    values: dict = {"in_flight_until": now + timedelta(seconds=timeout_seconds + 10)}
    if reschedule_interval is not None:
        values["next_run_at"] = now + timedelta(seconds=reschedule_interval)

    stmt = (
        update(Check)
        .where(
            Check.id == check_id,
            Check.paused.is_(False),
            or_(Check.in_flight_until.is_(None), Check.in_flight_until <= now),
        )
        .values(**values)
        .returning(Check)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one_or_none()


async def release_check(session: AsyncSession, check_id) -> None:
    await session.execute(
        update(Check)
        .where(Check.id == check_id)
        .values(in_flight_until=None)
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def get_open_incident(session: AsyncSession, check_id) -> Incident | None:
    stmt = (
        select(Incident)
        .where(Incident.check_id == check_id, Incident.ended_at.is_(None))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def in_maintenance(session: AsyncSession, *, check_id, group_id, now=None) -> bool:
    now = now or utcnow()
    stmt = select(MaintenanceWindow.id).where(
        or_(
            MaintenanceWindow.check_id == check_id,
            MaintenanceWindow.group_id == group_id,
        ),
        MaintenanceWindow.starts_at <= now,
        MaintenanceWindow.ends_at > now,
    )
    return (await session.execute(stmt)).first() is not None


async def process_result(
    session: AsyncSession,
    redis: Redis | None,
    check: Check,
    outcome: Outcome,
    now=None,
) -> Decision:
    """Apply one outcome: result row, state, incidents, emails, SSE events.

    Commits on success (single transaction); the caller should have no
    pending writes of its own.
    """
    now = now or utcnow()
    open_incident = await get_open_incident(session, check.id)
    maintenance = await in_maintenance(session, check_id=check.id, group_id=check.group_id, now=now)

    decision = decide(
        ok=outcome.ok,
        prev_state=check.state,
        consecutive_failures=check.consecutive_failures,
        failure_threshold=check.failure_threshold,
        has_open_incident=open_incident is not None,
        down_notified=bool(open_incident and open_incident.notified_down_at),
        in_maintenance=maintenance,
    )

    session.add(
        CheckResult(
            check_id=check.id,
            checked_at=now,
            ok=outcome.ok,
            status_code=outcome.status_code,
            response_time_ms=outcome.response_time_ms,
            error=outcome.error,
        )
    )

    check.consecutive_failures = decision.failures
    check.last_checked_at = now
    check.last_ok = outcome.ok
    check.last_status_code = outcome.status_code
    check.last_response_time_ms = outcome.response_time_ms
    check.last_error = outcome.error
    check.state = decision.new_state
    if decision.failing_since_set_now:
        check.failing_since = now

    group = await session.get(Group, check.group_id)

    if decision.open_incident:
        open_incident = Incident(
            check_id=check.id,
            started_at=check.failing_since or now,
            last_error=outcome.error,
        )
        session.add(open_incident)
        await session.flush()  # need incident.id for the event payload

    if decision.close_incident and open_incident is not None:
        open_incident.ended_at = now

    if any((decision.send_down, decision.suppress_down, decision.send_up, decision.suppress_up)):
        emails = [
            row.email
            for row in await session.execute(
                select(AlertEmail.email).where(AlertEmail.group_id == check.group_id)
            )
        ]
        if decision.send_down or decision.suppress_down:
            subject, body = email_mod.build_down_email(check, group, open_incident)
            await email_mod.deliver(
                session,
                owner_id=group.owner_id,
                group=group,
                check=check,
                kind="down",
                subject=subject,
                body=body,
                recipient_emails=emails,
                suppress_reason="maintenance_window" if decision.suppress_down else None,
            )
            if decision.send_down and open_incident is not None:
                open_incident.notified_down_at = now
        else:  # up notification
            subject, body = email_mod.build_up_email(check, group, open_incident)
            await email_mod.deliver(
                session,
                owner_id=group.owner_id,
                group=group,
                check=check,
                kind="up",
                subject=subject,
                body=body,
                recipient_emails=emails,
                suppress_reason="maintenance_window" if decision.suppress_up else None,
            )
            if decision.send_up and open_incident is not None:
                open_incident.notified_up_at = now

    await session.commit()

    if redis is not None:
        await _publish_check_update(redis, check, outcome, now, group)
        if decision.open_incident and open_incident is not None:
            await events.publish_event(
                redis,
                {
                    "type": "incident.opened",
                    "incident_id": str(open_incident.id),
                    "check_id": str(check.id),
                    "group_id": str(check.group_id),
                    "owner_id": str(group.owner_id),
                    "started_at": (check.failing_since or now).isoformat(),
                    "last_error": outcome.error,
                    "show_on_public": check.show_on_public,
                    "public_slug": group.public_slug,
                },
            )
        if decision.close_incident and open_incident is not None:
            await events.publish_event(
                redis,
                {
                    "type": "incident.closed",
                    "incident_id": str(open_incident.id),
                    "check_id": str(check.id),
                    "group_id": str(check.group_id),
                    "owner_id": str(group.owner_id),
                    "started_at": open_incident.started_at.isoformat(),
                    "ended_at": now.isoformat(),
                    "show_on_public": check.show_on_public,
                    "public_slug": group.public_slug,
                },
            )
    return decision


async def _publish_check_update(
    redis: Redis, check: Check, outcome: Outcome, now, group: Group
) -> None:
    await events.publish_event(
        redis,
        {
            "type": "check.update",
            "check_id": str(check.id),
            "group_id": str(check.group_id),
            "owner_id": str(group.owner_id),
            "state": check.state,
            "ok": outcome.ok,
            "status_code": outcome.status_code,
            "response_time_ms": outcome.response_time_ms,
            "checked_at": now.isoformat(),
            "paused": check.paused,
            "consecutive_failures": check.consecutive_failures,
            "failure_threshold": check.failure_threshold,
            "show_on_public": check.show_on_public,
            "public_slug": group.public_slug,
        },
    )


async def run_check_now(
    session: AsyncSession,
    client: httpx.AsyncClient,
    redis: Redis | None,
    check_id,
) -> Check:
    """Manual run from the API: claim → probe → process → release.

    Raises CheckInProgress if the check is already running somewhere.
    """
    check = await session.get(Check, check_id)
    if check is None:
        raise KeyError(check_id)
    claimed = await claim_check(session, check_id, timeout_seconds=check.timeout_seconds)
    if claimed is None:
        raise CheckInProgress(check_id)
    try:
        outcome = await perform_http_check(
            client,
            claimed.url,
            claimed.timeout_seconds,
            claimed.expected_status,
            claimed.expected_body,
        )
        await process_result(session, redis, claimed, outcome)
    finally:
        await release_check(session, check_id)
    refreshed = await session.get(Check, check_id)
    assert refreshed is not None
    return refreshed


async def send_pending_down_notifications(session: AsyncSession) -> int:
    """Window ended, incident still open, down-email never sent → send now.

    Runs as a periodic scheduler pass so the delayed email leaves within one
    tick, not on the check's next scheduled run (interval can be up to 1h).
    """
    now = utcnow()
    stmt = (
        select(Incident, Check, Group)
        .join(Check, Incident.check_id == Check.id)
        .join(Group, Check.group_id == Group.id)
        .where(Incident.ended_at.is_(None), Incident.notified_down_at.is_(None))
    )
    sent = 0
    for incident, check, group in (await session.execute(stmt)).all():
        if await in_maintenance(session, check_id=check.id, group_id=check.group_id, now=now):
            continue
        emails = [
            row.email
            for row in await session.execute(
                select(AlertEmail.email).where(AlertEmail.group_id == check.group_id)
            )
        ]
        subject, body = email_mod.build_down_email(check, group, incident)
        await email_mod.deliver(
            session,
            owner_id=group.owner_id,
            group=group,
            check=check,
            kind="down",
            subject=subject,
            body=body,
            recipient_emails=emails,
        )
        incident.notified_down_at = now
        sent += 1
    await session.commit()
    return sent
