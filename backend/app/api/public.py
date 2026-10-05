"""Public status page: no auth, only what the owner published (CONTRACT §4)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.checks.logic import group_status
from app.events import CHANNEL
from app.models import Check, Group
from app.queries import uptime_24h_map
from app.schemas import PublicCheckOut, PublicGroupOut, PublicOut

router = APIRouter(prefix="/public", tags=["public"])

HEARTBEAT_SECONDS = 15.0


async def _public_group(slug: str, session: AsyncSession) -> tuple[Group, list[Check]]:
    group = (
        await session.execute(select(Group).where(Group.public_slug == slug))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such status page")
    checks = list(
        (
            await session.execute(
                select(Check)
                .where(Check.group_id == group.id, Check.show_on_public.is_(True))
                .order_by(Check.created_at)
            )
        ).scalars()
    )
    return group, checks


@router.get("/{slug}", response_model=PublicOut)
async def public_status(slug: str, session: AsyncSession = Depends(get_db)) -> PublicOut:
    group, checks = await _public_group(slug, session)
    uptimes = await uptime_24h_map(session, [c.id for c in checks])
    return PublicOut(
        group=PublicGroupOut(name=group.name, description=group.description),
        status=group_status([c.state for c in checks]),
        checks=[
            PublicCheckOut(
                id=c.id,
                name=c.name,
                state="paused" if c.paused else c.state,
                last_checked_at=c.last_checked_at,
                uptime_24h=uptimes.get(c.id),
            )
            for c in checks
        ],
    )


@router.get("/{slug}/events")
async def public_events(slug: str, request: Request) -> StreamingResponse:
    async def stream():
        pubsub = request.app.state.redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
                )
                if message is None:
                    yield ": ping\n\n"
                    continue
                event = json.loads(message["data"])
                if event.get("show_on_public") and event.get("public_slug") == slug:
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
