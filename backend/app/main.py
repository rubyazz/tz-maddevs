"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api import api_router
from app.config import settings
from app.db import make_engine, make_sessionmaker
from app.seed import seed_demo_data

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        timeout=httpx.Timeout(35.0),  # upper bound; each check sets its own timeout
    )
    if settings.seed_demo:
        async with app.state.sessionmaker() as session:
            await seed_demo_data(session)
        logger.info("demo seed complete")
    yield
    await app.state.http_client.aclose()
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title="Pulse API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/api/health")
async def health(request: Request) -> dict:
    heartbeat = await request.app.state.redis.get("scheduler:heartbeat")
    return {"status": "ok", "scheduler_heartbeat": heartbeat}
