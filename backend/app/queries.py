"""Reusable read-model queries (aggregations, lookups)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.models import Check, CheckResult, Group, Incident

# period → (window length, bucket size) — CONTRACT §3.7
PERIODS: dict[str, tuple[timedelta, timedelta]] = {
    "day": (timedelta(days=1), timedelta(minutes=5)),
    "week": (timedelta(days=7), timedelta(hours=1)),
    "month": (timedelta(days=30), timedelta(hours=6)),
}


async def open_incident_map(
    session: AsyncSession, check_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Incident]:
    if not check_ids:
        return {}
    stmt = select(Incident).where(
        Incident.check_id.in_(check_ids), Incident.ended_at.is_(None)
    )
    return {incident.check_id: incident for incident in (await session.execute(stmt)).scalars()}


async def uptime_24h_map(
    session: AsyncSession, check_ids: list[uuid.UUID]
) -> dict[uuid.UUID, float | None]:
    """ok/total over the last 24h per check; checks with no data map to None."""
    if not check_ids:
        return {}
    since = utcnow() - timedelta(hours=24)
    stmt = (
        select(
            CheckResult.check_id,
            func.count().label("total"),
            func.count().filter(CheckResult.ok.is_(True)).label("ok"),
        )
        .where(CheckResult.check_id.in_(check_ids), CheckResult.checked_at >= since)
        .group_by(CheckResult.check_id)
    )
    result: dict[uuid.UUID, float | None] = {cid: None for cid in check_ids}
    for check_id, total, ok in (await session.execute(stmt)).all():
        result[check_id] = round(ok / total, 4) if total else None
    return result


_HISTORY_SQL = text(
    """
    WITH bounds AS (
        SELECT date_bin(:bucket, :start_ts, timestamptz '2000-01-03 00:00:00+00') AS first_bucket,
               date_bin(:bucket, :end_ts,   timestamptz '2000-01-03 00:00:00+00') AS last_bucket
    ),
    series AS (
        SELECT generate_series(first_bucket, last_bucket, :bucket) AS bucket FROM bounds
    ),
    agg AS (
        SELECT date_bin(:bucket, checked_at, timestamptz '2000-01-03 00:00:00+00') AS bucket,
               count(*) AS count,
               count(*) FILTER (WHERE ok) AS ok_count,
               round(avg(response_time_ms)) AS avg_ms,
               max(response_time_ms) AS max_ms
        FROM check_results
        WHERE check_id = :check_id AND checked_at >= :start_ts AND checked_at < :end_ts
        GROUP BY 1
    )
    SELECT series.bucket,
           coalesce(agg.count, 0),
           coalesce(agg.ok_count, 0),
           agg.avg_ms,
           agg.max_ms
    FROM series LEFT JOIN agg ON series.bucket = agg.bucket
    ORDER BY series.bucket
    """
)

# date_bin origin must be a multiple of the bucket; 2000-01-03 is a Monday
# midnight UTC — aligned for 5m, 1h and 6h buckets.

_SUMMARY_SQL = text(
    """
    SELECT count(*) AS total,
           count(*) FILTER (WHERE ok) AS ok,
           round(avg(response_time_ms)) AS avg_ms,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY response_time_ms) AS p95_ms
    FROM check_results
    WHERE check_id = :check_id AND checked_at >= :start_ts AND checked_at < :end_ts
    """
)


async def history_rows(
    session: AsyncSession, check_id: uuid.UUID, period: str
) -> tuple[list[dict], dict]:
    """Bucketed aggregates + summary for a period. Buckets with no data come
    back with count=0 (a gap in history, not downtime)."""
    window, bucket = PERIODS[period]
    end_ts = utcnow().replace(microsecond=0)
    start_ts = end_ts - window
    bucket_seconds = int(bucket.total_seconds())

    raw = (
        await session.execute(
            _HISTORY_SQL,
            {
                "bucket": f"{bucket_seconds} seconds",
                "check_id": check_id,
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
        )
    ).all()

    buckets = [
        {
            "ts": row[0],
            "count": row[1],
            "ok_count": row[2],
            "uptime_ratio": (row[2] / row[1]) if row[1] else None,
            "avg_response_ms": row[3],
            "max_response_ms": row[4],
        }
        for row in raw
    ]

    total, ok, avg_ms, p95_ms = (
        await session.execute(
            _SUMMARY_SQL, {"check_id": check_id, "start_ts": start_ts, "end_ts": end_ts}
        )
    ).one()

    summary = {
        "checks": total,
        "ok": ok,
        "uptime": round(ok / total, 4) if total else None,
        "avg_response_ms": avg_ms,
        "p95_response_ms": round(p95_ms) if p95_ms is not None else None,
    }
    return buckets, summary


async def incidents_in_window(
    session: AsyncSession, check_id: uuid.UUID, start_ts: datetime, end_ts: datetime
) -> list[Incident]:
    """Incidents overlapping [start_ts, end_ts): started before end, ended
    (or still open) after start."""
    stmt = select(Incident).where(
        Incident.check_id == check_id,
        Incident.started_at < end_ts,
        (Incident.ended_at.is_(None)) | (Incident.ended_at > start_ts),
    ).order_by(Incident.started_at.desc())
    return list((await session.execute(stmt)).scalars())
