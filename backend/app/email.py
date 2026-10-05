"""Alert email building and delivery.

Delivery is emulated by default: every email is recorded in `email_outbox`
(status `sent`) and shown in the Mailbox UI. Suppressed notifications
(maintenance windows) are recorded with status `suppressed` and a reason —
proof of the suppression behavior. When SMTP_HOST is configured, an actual
SMTP attempt is made via aiosmtplib in addition to the outbox row.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import utcnow
from app.models import Check, EmailOutbox, Group, Incident

logger = logging.getLogger(__name__)

NOREPLY = "noreply@pulse.local"


def build_down_email(check: Check, group: Group, incident: Incident) -> tuple[str, str]:
    subject = f"[Pulse] DOWN: {check.name}"
    body = (
        f"Check \"{check.name}\" is DOWN.\n\n"
        f"URL: {check.url}\n"
        f"Group: {group.name}\n"
        f"Down since: {incident.started_at.isoformat()}\n"
        f"Error: {incident.last_error or 'unknown'}\n\n"
        f"— Pulse uptime monitor"
    )
    return subject, body


def build_up_email(check: Check, group: Group, incident: Incident) -> tuple[str, str]:
    ended = incident.ended_at or utcnow()
    duration = ended - incident.started_at
    minutes = int(duration.total_seconds() // 60)
    subject = f"[Pulse] UP: {check.name}"
    body = (
        f"Check \"{check.name}\" has RECOVERED.\n\n"
        f"URL: {check.url}\n"
        f"Group: {group.name}\n"
        f"Was down: {incident.started_at.isoformat()} → {ended.isoformat()} "
        f"({minutes} min)\n\n"
        f"— Pulse uptime monitor"
    )
    return subject, body


def build_test_email(group: Group) -> tuple[str, str]:
    subject = f"[Pulse] Test alert for group \"{group.name}\""
    body = (
        f"This is a test notification for group \"{group.name}\".\n"
        f"If you received this, alerting works.\n\n— Pulse uptime monitor"
    )
    return subject, body


async def deliver(
    session: AsyncSession,
    *,
    owner_id,
    group: Group,
    check: Check | None,
    kind: str,
    subject: str,
    body: str,
    recipient_emails: list[str],
    suppress_reason: str | None = None,
) -> None:
    """Write outbox rows (one per recipient) and attempt SMTP if configured."""
    emails = recipient_emails or [NOREPLY]
    if not recipient_emails:
        body = body + f"\n\n(note: group \"{group.name}\" has no alert emails; recorded for {NOREPLY})"

    for to_email in emails:
        row = EmailOutbox(
            owner_id=owner_id,
            group_id=group.id,
            check_id=check.id if check else None,
            to_email=to_email,
            subject=subject,
            body=body,
            kind=kind,
            status="suppressed" if suppress_reason else "sent",
            suppress_reason=suppress_reason,
        )
        session.add(row)

    if suppress_reason or not settings.smtp_host:
        return

    message = EmailMessage()
    message["From"] = settings.mail_from
    message["Subject"] = subject
    message.set_content(body)
    for to_email in emails:
        message["To"] = to_email
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_password or None,
                start_tls=True,
            )
        except Exception:  # noqa: BLE001 — alerting must not take down the check pipeline
            logger.exception("SMTP delivery to %s failed (kept in outbox)", to_email)
