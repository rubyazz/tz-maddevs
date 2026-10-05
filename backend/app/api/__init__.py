"""API router aggregation."""

from fastapi import APIRouter

from app.api import auth, checks, events, groups, mailbox, maintenance, overview, public

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(auth.router_me)
api_router.include_router(overview.router)
api_router.include_router(groups.router)
api_router.include_router(checks.router)
api_router.include_router(maintenance.router)
api_router.include_router(mailbox.router)
api_router.include_router(events.router)
api_router.include_router(public.router)
