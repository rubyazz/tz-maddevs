"""Pydantic request/response schemas (CONTRACT §4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator

Period = Literal["day", "week", "month"]


def _require_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timezone-aware datetime required (ISO 8601 with offset)")
    return value


# --- Auth -----------------------------------------------------------------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr


class TokenOut(BaseModel):
    token: str
    user: UserOut


# --- Groups & alert emails --------------------------------------------------

class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)


class GroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    public_slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    public_slug: str | None


class AlertEmailIn(BaseModel):
    email: EmailStr


class AlertEmailOut(BaseModel):
    id: uuid.UUID
    email: EmailStr


class PublicSlugOut(BaseModel):
    public_slug: str


# --- Checks -----------------------------------------------------------------

class CheckIn(BaseModel):
    group_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    interval_seconds: int = Field(ge=30, le=3600)
    timeout_seconds: int = Field(ge=1, le=30)
    expected_status: int = Field(default=200, ge=100, le=599)
    expected_body: str | None = Field(default=None, max_length=1000)
    failure_threshold: int = Field(default=3, ge=1, le=10)
    show_on_public: bool = False


class CheckPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: HttpUrl | None = None
    interval_seconds: int | None = Field(default=None, ge=30, le=3600)
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    expected_body: str | None = Field(default=None, max_length=1000)
    failure_threshold: int | None = Field(default=None, ge=1, le=10)
    show_on_public: bool | None = None
    paused: bool | None = None
    group_id: uuid.UUID | None = None


class IncidentBrief(BaseModel):
    id: uuid.UUID
    started_at: datetime


class CheckOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    url: str
    interval_seconds: int
    timeout_seconds: int
    expected_status: int
    expected_body: str | None
    failure_threshold: int
    paused: bool
    show_on_public: bool
    state: str
    consecutive_failures: int
    last_checked_at: datetime | None
    last_ok: bool | None
    last_status_code: int | None
    last_response_time_ms: int | None
    last_error: str | None
    open_incident: IncidentBrief | None
    uptime_24h: float | None


class IncidentOut(BaseModel):
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    duration_s: int | None
    last_error: str | None


class GroupBrief(BaseModel):
    id: uuid.UUID
    name: str


class CheckDetailOut(CheckOut):
    group: GroupBrief
    incidents: list[IncidentOut]


class CheckResultOut(BaseModel):
    id: int
    checked_at: datetime
    ok: bool
    status_code: int | None
    response_time_ms: int | None
    error: str | None


class ResultsOut(BaseModel):
    items: list[CheckResultOut]
    next_before: datetime | None


# --- History ------------------------------------------------------------------

class HistoryBucket(BaseModel):
    ts: datetime
    count: int
    ok_count: int
    uptime_ratio: float | None
    avg_response_ms: float | None
    max_response_ms: int | None


class HistorySummary(BaseModel):
    checks: int
    ok: int
    uptime: float | None
    avg_response_ms: float | None
    p95_response_ms: float | None


class HistoryOut(BaseModel):
    period: Period
    buckets: list[HistoryBucket]
    summary: HistorySummary
    incidents: list[IncidentOut]


# --- Maintenance --------------------------------------------------------------

class MaintenanceIn(BaseModel):
    check_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    starts_at: datetime
    ends_at: datetime
    note: str = Field(default="", max_length=500)

    _tz_starts = field_validator("starts_at", mode="after")(_require_tz)
    _tz_ends = field_validator("ends_at", mode="after")(_require_tz)

    @model_validator(mode="after")
    def _exactly_one_target_and_order(self) -> "MaintenanceIn":
        if (self.check_id is None) == (self.group_id is None):
            raise ValueError("exactly one of check_id / group_id must be set")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class MaintenancePatch(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)

    _tz_starts = field_validator("starts_at", mode="after")(_require_tz)
    _tz_ends = field_validator("ends_at", mode="after")(_require_tz)


class MaintenanceOut(BaseModel):
    id: uuid.UUID
    check_id: uuid.UUID | None
    group_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    note: str
    check_name: str | None
    group_name: str | None


# --- Mailbox --------------------------------------------------------------------

class MailboxItem(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID | None
    check_id: uuid.UUID | None
    to_email: str
    subject: str
    body: str
    kind: str
    status: str
    suppress_reason: str | None
    created_at: datetime


# --- Public status page -----------------------------------------------------------

class PublicCheckOut(BaseModel):
    id: uuid.UUID
    name: str
    state: str
    last_checked_at: datetime | None
    uptime_24h: float | None


class PublicGroupOut(BaseModel):
    name: str
    description: str


class PublicOut(BaseModel):
    group: PublicGroupOut
    status: str
    checks: list[PublicCheckOut]
