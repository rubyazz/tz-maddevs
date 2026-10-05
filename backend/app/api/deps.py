"""FastAPI dependencies: DB session, Redis, current user, ownership guards."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_token
from app.models import Check, Group, User

bearer = HTTPBearer(auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    maker = request.app.state.sessionmaker
    async with maker() as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_token(credentials.credentials)
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def get_owned_group(
    group_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Group:
    group = await session.get(Group, _parse_uuid(group_id))
    if group is None or group.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    return group


async def get_owned_check(
    check_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> tuple[Check, Group]:
    stmt = select(Check, Group).join(Group, Check.group_id == Group.id).where(Check.id == _parse_uuid(check_id))
    row = (await session.execute(stmt)).first()
    if row is None or row[1].owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Check not found")
    return row[0], row[1]


def _parse_uuid(value: str):
    import uuid as _uuid

    try:
        return _uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
