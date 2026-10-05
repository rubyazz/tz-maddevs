"""Maintenance windows CRUD (target: one check or one group)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db import utcnow
from app.models import Check, Group, MaintenanceWindow, User
from app.schemas import MaintenanceIn, MaintenanceOut, MaintenancePatch
from app.serializers import maintenance_to_out

router = APIRouter(prefix="/maintenance-windows", tags=["maintenance"])


async def _owned_window(window_id: str, user: User, session: AsyncSession) -> MaintenanceWindow:
    try:
        import uuid as _uuid

        row = await session.get(MaintenanceWindow, _uuid.UUID(window_id))
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
    if row is None or row.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance window not found")
    return row


async def _validate_target(data: MaintenanceIn, user: User, session: AsyncSession) -> None:
    if data.check_id is not None:
        check = await session.get(Check, data.check_id)
        if check is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Check not found")
        group = await session.get(Group, check.group_id)
        if group is None or group.owner_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Check not found")
    if data.group_id is not None:
        group = await session.get(Group, data.group_id)
        if group is None or group.owner_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")


@router.get("", response_model=list[MaintenanceOut])
async def list_windows(
    active: bool | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MaintenanceOut]:
    stmt = (
        select(MaintenanceWindow, Check.name, Group.name)
        .outerjoin(Check, MaintenanceWindow.check_id == Check.id)
        .outerjoin(Group, MaintenanceWindow.group_id == Group.id)
        .where(MaintenanceWindow.owner_id == user.id)
        .order_by(MaintenanceWindow.starts_at.desc())
    )
    now = utcnow()
    rows = (await session.execute(stmt)).all()
    out = []
    for window, check_name, group_name in rows:
        if active is not None and (window.starts_at <= now < window.ends_at) != active:
            continue
        out.append(maintenance_to_out(window, check_name, group_name))
    return out


@router.post("", response_model=MaintenanceOut, status_code=status.HTTP_201_CREATED)
async def create_window(
    data: MaintenanceIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaintenanceOut:
    await _validate_target(data, user, session)
    window = MaintenanceWindow(
        owner_id=user.id,
        check_id=data.check_id,
        group_id=data.group_id,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        note=data.note,
    )
    session.add(window)
    await session.commit()
    check_name = group_name = None
    if window.check_id:
        check = await session.get(Check, window.check_id)
        check_name = check.name if check else None
    if window.group_id:
        group = await session.get(Group, window.group_id)
        group_name = group.name if group else None
    return maintenance_to_out(window, check_name, group_name)


@router.patch("/{window_id}", response_model=MaintenanceOut)
async def patch_window(
    window_id: str,
    data: MaintenancePatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MaintenanceOut:
    window = await _owned_window(window_id, user, session)
    provided = data.model_fields_set
    if "starts_at" in provided and data.starts_at is not None:
        window.starts_at = data.starts_at
    if "ends_at" in provided and data.ends_at is not None:
        window.ends_at = data.ends_at
    if "note" in provided and data.note is not None:
        window.note = data.note
    if window.ends_at <= window.starts_at:
        await session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ends_at must be after starts_at")
    await session.commit()
    check_name = group_name = None
    if window.check_id:
        check = await session.get(Check, window.check_id)
        check_name = check.name if check else None
    if window.group_id:
        group = await session.get(Group, window.group_id)
        group_name = group.name if group else None
    return maintenance_to_out(window, check_name, group_name)


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_window(
    window_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    window = await _owned_window(window_id, user, session)
    await session.delete(window)
    await session.commit()
