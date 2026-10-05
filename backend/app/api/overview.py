"""Dashboard overview: groups with computed status, checks, alert emails."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import AlertEmail, Check, Group, User
from app.queries import open_incident_map, uptime_24h_map
from app.serializers import check_to_out, compute_group_status

router = APIRouter(tags=["overview"])


@router.get("/overview")
async def overview(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    groups = list(
        (
            await session.execute(
                select(Group).where(Group.owner_id == user.id).order_by(Group.created_at)
            )
        ).scalars()
    )
    checks = list(
        (
            await session.execute(
                select(Check)
                .join(Group, Check.group_id == Group.id)
                .where(Group.owner_id == user.id)
                .order_by(Check.created_at)
            )
        ).scalars()
    )
    emails = list(
        (
            await session.execute(
                select(AlertEmail)
                .join(Group, AlertEmail.group_id == Group.id)
                .where(Group.owner_id == user.id)
            )
        ).scalars()
    )

    incidents = await open_incident_map(session, [c.id for c in checks])
    uptimes = await uptime_24h_map(session, [c.id for c in checks])

    checks_by_group: dict = {g.id: [] for g in groups}
    for check in checks:
        if check.group_id in checks_by_group:
            checks_by_group[check.group_id].append(check)

    emails_by_group: dict = {g.id: [] for g in groups}
    for row in emails:
        if row.group_id in emails_by_group:
            emails_by_group[row.group_id].append({"id": str(row.id), "email": row.email})

    return {
        "groups": [
            {
                "id": str(group.id),
                "name": group.name,
                "description": group.description,
                "public_slug": group.public_slug,
                "status": compute_group_status(checks_by_group[group.id]),
                "alert_emails": emails_by_group[group.id],
                "checks": [
                    check_to_out(c, incidents.get(c.id), uptimes.get(c.id)).model_dump(mode="json")
                    for c in checks_by_group[group.id]
                ],
            }
            for group in groups
        ]
    }
