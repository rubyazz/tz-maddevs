"""Check CRUD, manual run, history, raw results."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.checks import runner
from app.api.deps import get_current_user, get_db, get_owned_check, get_redis
from app.db import utcnow
from app.models import Check, Group, Incident, User
from app.queries import PERIODS, history_rows, incidents_in_window, open_incident_map, uptime_24h_map
from app.schemas import (
    CheckDetailOut,
    CheckIn,
    CheckOut,
    CheckPatch,
    CheckResultOut,
    HistoryBucket,
    HistoryOut,
    HistorySummary,
    IncidentOut,
    ResultsOut,
)
from app.serializers import check_to_detail, check_to_out, incident_to_out

router = APIRouter(prefix="/checks", tags=["checks"])


@router.post("", response_model=CheckOut, status_code=status.HTTP_201_CREATED)
async def create_check(
    data: CheckIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CheckOut:
    group = await session.get(Group, data.group_id)
    if group is None or group.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    check = Check(
        group_id=group.id,
        name=data.name,
        url=str(data.url),
        interval_seconds=data.interval_seconds,
        timeout_seconds=data.timeout_seconds,
        expected_status=data.expected_status,
        expected_body=data.expected_body,
        failure_threshold=data.failure_threshold,
        show_on_public=data.show_on_public,
        next_run_at=utcnow(),  # first run happens on the next scheduler tick
    )
    session.add(check)
    await session.commit()
    return check_to_out(check)


@router.get("", response_model=list[CheckOut])
async def list_checks(
    group_id: str | None = None,
    paused: bool | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[CheckOut]:
    stmt = (
        select(Check)
        .join(Group, Check.group_id == Group.id)
        .where(Group.owner_id == user.id)
        .order_by(Check.created_at)
    )
    if group_id is not None:
        stmt = stmt.where(Check.group_id == _uuid(group_id))
    if paused is not None:
        stmt = stmt.where(Check.paused.is_(paused))
    checks = list((await session.execute(stmt)).scalars())
    incidents = await open_incident_map(session, [c.id for c in checks])
    uptimes = await uptime_24h_map(session, [c.id for c in checks])
    return [check_to_out(c, incidents.get(c.id), uptimes.get(c.id)) for c in checks]


@router.get("/{check_id}", response_model=CheckDetailOut)
async def get_check(
    pair: tuple[Check, Group] = Depends(get_owned_check),
    session: AsyncSession = Depends(get_db),
) -> CheckDetailOut:
    check, group = pair
    incidents = list(
        (
            await session.execute(
                select(Incident)
                .where(Incident.check_id == check.id)
                .order_by(Incident.started_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    open_incident = next((i for i in incidents if i.ended_at is None), None)
    uptime = (await uptime_24h_map(session, [check.id])).get(check.id)
    return check_to_detail(check, group, incidents, open_incident, uptime)


@router.patch("/{check_id}", response_model=CheckOut)
async def patch_check(
    data: CheckPatch,
    pair: tuple[Check, Group] = Depends(get_owned_check),
    session: AsyncSession = Depends(get_db),
) -> CheckOut:
    check, group = pair
    provided = data.model_fields_set

    if "group_id" in provided and data.group_id is not None and data.group_id != check.group_id:
        target = await session.get(Group, data.group_id)
        if target is None or target.owner_id != group.owner_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Target group not found")
        check.group_id = data.group_id

    for field in (
        "name",
        "interval_seconds",
        "timeout_seconds",
        "expected_status",
        "failure_threshold",
        "show_on_public",
    ):
        if field in provided and getattr(data, field) is not None:
            setattr(check, field, getattr(data, field))

    if "url" in provided and data.url is not None:
        check.url = str(data.url)
    if "expected_body" in provided:  # explicit null clears the substring check
        check.expected_body = data.expected_body

    if "paused" in provided and data.paused is not None:
        if data.paused:
            check.paused = True
        elif check.paused:  # resume: schedule immediately
            check.paused = False
            check.next_run_at = utcnow()

    await session.commit()
    open_incident = await runner.get_open_incident(session, check.id)
    uptime = (await uptime_24h_map(session, [check.id])).get(check.id)
    return check_to_out(check, open_incident, uptime)


@router.delete("/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_check(pair: tuple[Check, Group] = Depends(get_owned_check), session=Depends(get_db)) -> None:
    check, _ = pair
    await session.delete(check)
    await session.commit()


@router.post("/{check_id}/run", response_model=CheckOut)
async def run_check(
    request: Request,
    pair: tuple[Check, Group] = Depends(get_owned_check),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> CheckOut:
    check, _ = pair
    if check.paused:
        raise HTTPException(status.HTTP_409_CONFLICT, "Check is paused; resume it first")
    try:
        updated = await runner.run_check_now(
            session, request.app.state.http_client, redis, check.id
        )
    except runner.CheckInProgress:
        raise HTTPException(status.HTTP_409_CONFLICT, "Check is already running")
    open_incident = await runner.get_open_incident(session, updated.id)
    uptime = (await uptime_24h_map(session, [updated.id])).get(updated.id)
    return check_to_out(updated, open_incident, uptime)


@router.post("/{check_id}/pause", response_model=CheckOut)
async def pause_check(
    pair: tuple[Check, Group] = Depends(get_owned_check),
    session: AsyncSession = Depends(get_db),
) -> CheckOut:
    check, _ = pair
    check.paused = True
    await session.commit()
    open_incident = await runner.get_open_incident(session, check.id)
    return check_to_out(check, open_incident)


@router.post("/{check_id}/resume", response_model=CheckOut)
async def resume_check(
    pair: tuple[Check, Group] = Depends(get_owned_check),
    session: AsyncSession = Depends(get_db),
) -> CheckOut:
    check, _ = pair
    check.paused = False
    check.next_run_at = utcnow()
    await session.commit()
    open_incident = await runner.get_open_incident(session, check.id)
    return check_to_out(check, open_incident)


@router.get("/{check_id}/history", response_model=HistoryOut)
async def get_history(
    period: str = Query(default="day", pattern="^(day|week|month)$"),
    pair: tuple[Check, Group] = Depends(get_owned_check),
    session: AsyncSession = Depends(get_db),
) -> HistoryOut:
    check, _ = pair
    buckets_raw, summary = await history_rows(session, check.id, period)
    window = PERIODS[period][0]
    end_ts = utcnow()
    incidents = await incidents_in_window(session, check.id, end_ts - window, end_ts)
    return HistoryOut(
        period=period,  # type: ignore[arg-type]
        buckets=[HistoryBucket(**b) for b in buckets_raw],
        summary=HistorySummary(**summary),
        incidents=[incident_to_out(i) for i in incidents],
    )


@router.get("/{check_id}/results", response_model=ResultsOut)
async def get_results(
    check_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = None,
    pair: tuple[Check, Group] = Depends(get_owned_check),
    session: AsyncSession = Depends(get_db),
) -> ResultsOut:
    from app.models import CheckResult
    from datetime import datetime as _dt

    stmt = (
        select(CheckResult)
        .where(CheckResult.check_id == pair[0].id)
        .order_by(CheckResult.checked_at.desc(), CheckResult.id.desc())
        .limit(limit + 1)
    )
    if before is not None:
        stmt = stmt.where(CheckResult.checked_at < _dt.fromisoformat(before))
    rows = list((await session.execute(stmt)).scalars())
    next_before = rows[limit].checked_at.isoformat() if len(rows) > limit else None
    items = [
        CheckResultOut(
            id=r.id,
            checked_at=r.checked_at,
            ok=r.ok,
            status_code=r.status_code,
            response_time_ms=r.response_time_ms,
            error=r.error,
        )
        for r in rows[:limit]
    ]
    return ResultsOut(items=items, next_before=next_before)


def _uuid(value: str):
    import uuid as _uuid_mod

    try:
        return _uuid_mod.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
