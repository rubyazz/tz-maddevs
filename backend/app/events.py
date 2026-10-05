"""Redis pub/sub event publishing (SSE fan-out)."""

from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

CHANNEL = "pulse:events"


async def publish_event(redis: Redis, payload: dict[str, Any]) -> None:
    """Publish one domain event; SSE endpoints filter per subscriber."""
    try:
        await redis.publish(CHANNEL, json.dumps(payload, default=str))
    except Exception:  # noqa: BLE001 — realtime is best-effort, never fatal
        logger.exception("failed to publish event %s", payload.get("type"))
