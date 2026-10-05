"""Mailbox: the emulated email outbox, newest first."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import EmailOutbox, User
from app.serializers import mailbox_item

router = APIRouter(prefix="/mailbox", tags=["mailbox"])


@router.get("", response_model=dict)
async def list_mailbox(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await session.execute(
            select(EmailOutbox)
            .where(EmailOutbox.owner_id == user.id)
            .order_by(EmailOutbox.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return {"items": [mailbox_item(r).model_dump(mode="json") for r in rows]}
