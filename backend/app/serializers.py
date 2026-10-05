"""ORM → response-model builders."""

from __future__ import annotations

from app.checks.logic import group_status
from app.models import Check, EmailOutbox, Group, Incident, MaintenanceWindow
from app.schemas import (
    CheckDetailOut,
    CheckOut,
    GroupBrief,
    IncidentBrief,
    IncidentOut,
    MailboxItem,
    MaintenanceOut,
)
from app.queries import PERIODS
from datetime import timedelta


def incident_brief(incident: Incident | None) -> IncidentBrief | None:
    if incident is None:
        return None
    return IncidentBrief(id=incident.id, started_at=incident.started_at)


def check_to_out(
    check: Check, open_incident: Incident | None = None, uptime_24h: float | None = None
) -> CheckOut:
    return CheckOut(
        id=check.id,
        group_id=check.group_id,
        name=check.name,
        url=check.url,
        interval_seconds=check.interval_seconds,
        timeout_seconds=check.timeout_seconds,
        expected_status=check.expected_status,
        expected_body=check.expected_body,
        failure_threshold=check.failure_threshold,
        paused=check.paused,
        show_on_public=check.show_on_public,
        state=check.state,
        consecutive_failures=check.consecutive_failures,
        last_checked_at=check.last_checked_at,
        last_ok=check.last_ok,
        last_status_code=check.last_status_code,
        last_response_time_ms=check.last_response_time_ms,
        last_error=check.last_error,
        open_incident=incident_brief(open_incident),
        uptime_24h=uptime_24h,
    )


def incident_to_out(incident: Incident) -> IncidentOut:
    return IncidentOut(
        id=incident.id,
        started_at=incident.started_at,
        ended_at=incident.ended_at,
        duration_s=(
            int((incident.ended_at - incident.started_at).total_seconds())
            if incident.ended_at
            else None
        ),
        last_error=incident.last_error,
    )


def check_to_detail(
    check: Check,
    group: Group,
    incidents: list[Incident],
    open_incident: Incident | None = None,
    uptime_24h: float | None = None,
) -> CheckDetailOut:
    return CheckDetailOut(
        **check_to_out(check, open_incident, uptime_24h).model_dump(),
        group=GroupBrief(id=group.id, name=group.name),
        incidents=[incident_to_out(i) for i in incidents],
    )


def maintenance_to_out(
    window: MaintenanceWindow, check_name: str | None, group_name: str | None
) -> MaintenanceOut:
    return MaintenanceOut(
        id=window.id,
        check_id=window.check_id,
        group_id=window.group_id,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        note=window.note,
        check_name=check_name,
        group_name=group_name,
    )


def mailbox_item(row: EmailOutbox) -> MailboxItem:
    return MailboxItem(
        id=row.id,
        group_id=row.group_id,
        check_id=row.check_id,
        to_email=row.to_email,
        subject=row.subject,
        body=row.body,
        kind=row.kind,
        status=row.status,
        suppress_reason=row.suppress_reason,
        created_at=row.created_at,
    )


def compute_group_status(checks: list[Check]) -> str:
    """Group status over non-paused checks (CONTRACT §3.6)."""
    return group_status([c.state for c in checks if not c.paused])


def period_window(period: str) -> timedelta:
    return PERIODS[period][0]
