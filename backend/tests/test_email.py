"""Email building/deliver tests (in-memory models, no DB)."""

from datetime import datetime, timezone
from uuid import uuid4

from app import email as email_mod
from app.models import Check, EmailOutbox, Group, Incident


class Recorder:
    """Minimal AsyncSession stand-in: records added objects."""

    def __init__(self):
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)


def _fixtures():
    group = Group(id=uuid4(), owner_id=uuid4(), name="Production")
    check = Check(
        id=uuid4(), group_id=group.id, name="Main site", url="http://demo-sites:8090/site/main"
    )
    started = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)
    incident = Incident(id=uuid4(), check_id=check.id, started_at=started, last_error="timeout after 10s")
    return group, check, incident


async def test_down_email_content():
    group, check, incident = _fixtures()
    subject, body = email_mod.build_down_email(check, group, incident)
    assert subject == "[Pulse] DOWN: Main site"
    assert check.url in body
    assert "timeout after 10s" in body


async def test_up_email_content():
    group, check, incident = _fixtures()
    incident.ended_at = datetime(2026, 10, 6, 10, 7, tzinfo=timezone.utc)
    subject, body = email_mod.build_up_email(check, group, incident)
    assert subject == "[Pulse] UP: Main site"
    assert "7 min" in body


async def test_deliver_writes_row_per_recipient():
    group, check, _ = _fixtures()
    session = Recorder()
    await email_mod.deliver(
        session,
        owner_id=group.owner_id,
        group=group,
        check=check,
        kind="down",
        subject="s",
        body="b",
        recipient_emails=["a@example.com", "b@example.com"],
    )
    assert len(session.added) == 2
    assert all(isinstance(row, EmailOutbox) for row in session.added)
    assert {row.to_email for row in session.added} == {"a@example.com", "b@example.com"}
    assert all(row.status == "sent" for row in session.added)


async def test_deliver_without_recipients_falls_back_to_noreply():
    group, check, _ = _fixtures()
    session = Recorder()
    await email_mod.deliver(
        session,
        owner_id=group.owner_id,
        group=group,
        check=check,
        kind="down",
        subject="s",
        body="b",
        recipient_emails=[],
    )
    assert len(session.added) == 1
    assert session.added[0].to_email == email_mod.NOREPLY
    assert "no alert emails" in session.added[0].body


async def test_deliver_suppressed_records_reason():
    group, check, _ = _fixtures()
    session = Recorder()
    await email_mod.deliver(
        session,
        owner_id=group.owner_id,
        group=group,
        check=check,
        kind="down",
        subject="s",
        body="b",
        recipient_emails=["a@example.com"],
        suppress_reason="maintenance_window",
    )
    row = session.added[0]
    assert row.status == "suppressed"
    assert row.suppress_reason == "maintenance_window"
