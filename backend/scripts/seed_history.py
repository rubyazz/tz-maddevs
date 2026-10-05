"""Synthetic history generator — proof of month-query performance.

Writes generated rows straight into `check_results` so that month-range
history/aggregation can be benchmarked on realistic volumes (~90k rows per
check for 30 days at a 30s interval). The data is SYNTHETIC and is meant for
local performance demonstration only — it is indistinguishable from real
results by design of the schema, so do not use it as incident evidence.

Usage (inside the api container):
    python scripts/seed_history.py --days 30 [--interval 30] [--check-name "Main site"]
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db import make_engine, make_sessionmaker, utcnow
from app.models import Check, CheckResult, Group


async def seed(checks: list[Check], days: int, interval: int, rng: random.Random) -> None:
    engine = make_engine()
    maker = make_sessionmaker(engine)
    now = utcnow()
    start = now - timedelta(days=days)
    total_seconds = int((now - start).total_seconds())

    async with maker() as session:
        for check in checks:
            base_ms = rng.randint(80, 300)
            rows: list[CheckResult] = []
            written = 0
            for offset in range(0, total_seconds, interval):
                # ~1.5% of the timeline is "server downtime" gaps: no rows at all
                if rng.random() < 0.015:
                    continue
                ok = rng.random() < 0.985
                checked_at = start + timedelta(seconds=offset)
                if ok:
                    response_ms = max(20, int(rng.gauss(base_ms, base_ms * 0.25)))
                    if rng.random() < 0.004:  # occasional latency spike
                        response_ms = int(response_ms * rng.uniform(4, 9))
                    rows.append(
                        CheckResult(
                            check_id=check.id,
                            checked_at=checked_at,
                            ok=True,
                            status_code=check.expected_status,
                            response_time_ms=response_ms,
                            error=None,
                        )
                    )
                else:
                    rows.append(
                        CheckResult(
                            check_id=check.id,
                            checked_at=checked_at,
                            ok=False,
                            status_code=None,
                            response_time_ms=(
                                int(rng.gauss(10_000, 500))
                                if check.timeout_seconds >= 10
                                else check.timeout_seconds * 1000
                            ),
                            error=(
                                f"timeout after {check.timeout_seconds}s"
                                if rng.random() < 0.8
                                else "ConnectError: connection refused"
                            ),
                        )
                    )
                if len(rows) >= 5_000:
                    session.add_all(rows)
                    await session.flush()
                    written += len(rows)
                    rows = []
            if rows:
                session.add_all(rows)
                written += len(rows)
            await session.commit()
            print(f"  {check.name}: +{written} synthetic results over {days} days")
    await engine.dispose()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--interval", type=int, default=30, help="seconds between results")
    parser.add_argument("--check-name", type=str, default=None, help="limit to one check")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    engine = make_engine()
    maker = make_sessionmaker(engine)
    async with maker() as session:
        stmt = select(Check).join(Group, Check.group_id == Group.id)
        if args.check_name:
            stmt = stmt.where(Check.name == args.check_name)
        checks = list((await session.execute(stmt)).scalars())
    await engine.dispose()

    if not checks:
        print("no checks matched")
        return
    rng = random.Random(args.seed)
    print(f"seeding {len(checks)} check(s) with {args.days} days of history at {args.interval}s …")
    started = time.monotonic()
    await seed(checks, args.days, args.interval, rng)
    print(f"done in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
