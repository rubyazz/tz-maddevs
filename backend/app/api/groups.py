"""Group and alert-email management."""

from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import email as email_mod
from app.api.deps import get_current_user, get_db, get_owned_group
from app.db import utcnow
from app.models import AlertEmail, EmailOutbox, Group, User
from app.schemas import AlertEmailIn, AlertEmailOut, GroupIn, GroupOut, GroupPatch, MailboxItem, PublicSlugOut
from app.serializers import mailbox_item

router = APIRouter(prefix="/groups", tags=["groups"])


def _generate_slug(length: int = 12) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    data: GroupIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupOut:
    group = Group(owner_id=user.id, name=data.name, description=data.description)
    session.add(group)
    await session.commit()
    return GroupOut(
        id=group.id, name=group.name, description=group.description, public_slug=group.public_slug
    )


@router.get("", response_model=list[GroupOut])
async def list_groups(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[GroupOut]:
    groups = (
        await session.execute(
            select(Group).where(Group.owner_id == user.id).order_by(Group.created_at)
        )
    ).scalars()
    return [
        GroupOut(id=g.id, name=g.name, description=g.description, public_slug=g.public_slug)
        for g in groups
    ]


@router.patch("/{group_id}", response_model=GroupOut)
async def patch_group(
    data: GroupPatch,
    group: Group = Depends(get_owned_group),
    session: AsyncSession = Depends(get_db),
) -> GroupOut:
    provided = data.model_fields_set
    if "name" in provided and data.name is not None:
        group.name = data.name
    if "description" in provided and data.description is not None:
        group.description = data.description
    if "public_slug" in provided:
        if data.public_slug is not None:
            clash = await session.execute(
                select(Group.id).where(Group.public_slug == data.public_slug)
            )
            if clash.first() is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Slug already in use")
        group.public_slug = data.public_slug  # None removes the group from the public page
    group.updated_at = utcnow()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already in use") from exc
    return GroupOut(
        id=group.id, name=group.name, description=group.description, public_slug=group.public_slug
    )


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group: Group = Depends(get_owned_group), session=Depends(get_db)) -> None:
    await session.delete(group)
    await session.commit()


@router.post("/{group_id}/emails", response_model=AlertEmailOut, status_code=status.HTTP_201_CREATED)
async def add_email(
    data: AlertEmailIn,
    group: Group = Depends(get_owned_group),
    session: AsyncSession = Depends(get_db),
) -> AlertEmailOut:
    existing = await session.execute(
        select(AlertEmail).where(
            AlertEmail.group_id == group.id, AlertEmail.email == data.email.lower()
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in group")
    row = AlertEmail(group_id=group.id, email=data.email.lower())
    session.add(row)
    await session.commit()
    return AlertEmailOut(id=row.id, email=row.email)


@router.delete("/{group_id}/emails/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email(
    email_id: str,
    group: Group = Depends(get_owned_group),
    session: AsyncSession = Depends(get_db),
) -> None:
    row = await session.get(AlertEmail, _uuid(email_id))
    if row is None or row.group_id != group.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")
    await session.delete(row)
    await session.commit()


@router.post("/{group_id}/public-slug/generate", response_model=PublicSlugOut)
async def generate_public_slug(
    group: Group = Depends(get_owned_group),
    session: AsyncSession = Depends(get_db),
) -> PublicSlugOut:
    group.public_slug = _generate_slug()
    await session.commit()
    return PublicSlugOut(public_slug=group.public_slug)


@router.post(
    "/{group_id}/emails/{email_id}/test", response_model=MailboxItem, status_code=status.HTTP_201_CREATED
)
async def send_test_email(
    email_id: str,
    group: Group = Depends(get_owned_group),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MailboxItem:
    row = await session.get(AlertEmail, _uuid(email_id))
    if row is None or row.group_id != group.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")
    subject, body = email_mod.build_test_email(group)
    await email_mod.deliver(
        session,
        owner_id=user.id,
        group=group,
        check=None,
        kind="test",
        subject=subject,
        body=body,
        recipient_emails=[row.email],
    )
    await session.commit()
    out = (
        await session.execute(
            select(EmailOutbox)
            .where(EmailOutbox.kind == "test", EmailOutbox.to_email == row.email)
            .order_by(EmailOutbox.created_at.desc())
            .limit(1)
        )
    ).scalar_one()
    return mailbox_item(out)


def _uuid(value: str):
    import uuid as _uuid_mod

    try:
        return _uuid_mod.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
