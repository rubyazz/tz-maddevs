"""SSE stream of domain events for authenticated clients (CONTRACT §5)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.auth import decode_token
from app.events import CHANNEL

router = APIRouter(tags=["events"])

HEARTBEAT_SECONDS = 15.0


@router.get("/events")
async def events_stream(request: Request, token: str = Query(...)) -> StreamingResponse:
    user_id = decode_token(token)  # 401 JSON before the stream starts

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
                if event.get("owner_id") == str(user_id):
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
