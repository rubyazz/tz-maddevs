"""Asyncio scheduler (CONTRACT §3.5).

Single leader process (Redis lock, renewed in background; lock loss kills the
process immediately — an in-flight check's claim self-expires by TTL, so a
hard exit is safe and prevents split-brain). Each tick:
  1. heartbeat,
  2. claim+dispatch due checks (atomic claim also reschedules — a check can
     never run in parallel with itself, and missed slots are skipped),
  3. every ~5s: send down-notifications delayed by maintenance windows,
  4. daily: prune raw results past the retention horizon.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import timedelta

import httpx
from redis.asyncio import Redis
from redis.exceptions import LockError, LockNotOwnedError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.checks import runner
from app.config import settings
from app.db import make_engine, make_sessionmaker, utcnow
from app.models import Check, CheckResult

logger = logging.getLogger("pulse.scheduler")

LEADER_KEY = "scheduler:leader"
HEARTBEAT_KEY = "scheduler:heartbeat"
HEARTBEAT_TTL = 10
WINDOW_PASS_INTERVAL = 5.0


async def run_one(
    maker: async_sessionmaker,
    client: httpx.AsyncClient,
    redis: Redis,
    job: runner.CheckJob,
) -> None:
    """Execute one claimed check end-to-end; never raises.

    The job carries plain values (an ORM instance returned by the claim would
    be merged into a fresh session with its pre-claim snapshot and clobber
    next_run_at back in time).
    """
    try:
        outcome = await runner.perform_http_check(
            client, job.url, job.timeout_seconds, job.expected_status, job.expected_body
        )
        async with maker() as session:
            check = await session.get(Check, job.id)
            if check is not None:
                await runner.process_result(session, redis, check, outcome)
    except Exception:  # noqa: BLE001 — one broken check must not stop the loop
        logger.exception("check %s failed to process", job.id)
    finally:
        try:
            async with maker() as session:
                await runner.release_check(session, job.id)
        except Exception:  # noqa: BLE001
            logger.exception("failed to release claim for check %s", job.id)


async def _renew_forever(lock) -> None:
    while True:
        await asyncio.sleep(10)
        try:
            await lock.renew()
        except (LockNotOwnedError, LockError):
            logger.fatal("lost scheduler leader lock — exiting immediately")
            os._exit(1)


async def prune_old_results(maker: async_sessionmaker) -> None:
    horizon = utcnow() - timedelta(days=settings.results_retention_days)
    async with maker() as session:
        result = await session.execute(delete(CheckResult).where(CheckResult.checked_at < horizon))
        await session.commit()
    if result.rowcount:
        logger.info(
            "pruned %s results older than %s days", result.rowcount, settings.results_retention_days
        )


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    engine = make_engine()
    maker = make_sessionmaker(engine)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        timeout=httpx.Timeout(35.0),
    )

    lock = redis.lock(LEADER_KEY, timeout=30)
    if not await lock.acquire(blocking=False):
        logger.fatal("another scheduler holds %s — exiting", LEADER_KEY)
        return
    renewal = asyncio.create_task(_renew_forever(lock))
    logger.info("acquired scheduler leader lock; scheduler started (tick=%.1fs)",
                settings.scheduler_tick_seconds)

    tasks: set[asyncio.Task] = set()
    last_window_pass = 0.0
    last_prune_day = ""

    try:
        while True:
            now = utcnow()
            await redis.set(HEARTBEAT_KEY, now.isoformat(), ex=HEARTBEAT_TTL)

            async with maker() as session:
                due = (
                    await session.execute(
                        select(Check).where(Check.paused.is_(False), Check.next_run_at <= now)
                    )
                ).scalars().all()
                for check in due:
                    claimed = await runner.claim_check(
                        session,
                        check.id,
                        timeout_seconds=check.timeout_seconds,
                        reschedule_interval=check.interval_seconds,
                    )
                    if claimed is None:
                        continue  # someone is already running it
                    job = runner.CheckJob(
                        id=claimed.id,
                        url=claimed.url,
                        timeout_seconds=claimed.timeout_seconds,
                        expected_status=claimed.expected_status,
                        expected_body=claimed.expected_body,
                    )
                    task = asyncio.create_task(run_one(maker, client, redis, job))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

            if time.monotonic() - last_window_pass > WINDOW_PASS_INTERVAL:
                last_window_pass = time.monotonic()
                try:
                    async with maker() as session:
                        sent = await runner.send_pending_down_notifications(session)
                        if sent:
                            logger.info("sent %s delayed down-notification(s)", sent)
                except Exception:  # noqa: BLE001
                    logger.exception("window-end notification pass failed")

            if now.date().isoformat() != last_prune_day:
                last_prune_day = now.date().isoformat()
                try:
                    await prune_old_results(maker)
                except Exception:  # noqa: BLE001
                    logger.exception("prune pass failed")

            await asyncio.sleep(settings.scheduler_tick_seconds)
    finally:
        renewal.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await lock.release()
        except (LockNotOwnedError, LockError):
            pass
        await client.aclose()
        await redis.aclose()
        await engine.dispose()
        logger.info("scheduler stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
