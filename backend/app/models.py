"""ORM models — mirror docs/CONTRACT.md §2 exactly."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

UUIDPk = UUID(as_uuid=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUIDPk, primary_key=True, server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(UUIDPk, primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    public_slug: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AlertEmail(Base):
    __tablename__ = "alert_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUIDPk, primary_key=True, server_default=text("gen_random_uuid()"))
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("group_id", "email", name="uq_alert_emails_group_email"),)


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (
        CheckConstraint("interval_seconds between 30 and 3600", name="ck_checks_interval"),
        CheckConstraint("timeout_seconds between 1 and 30", name="ck_checks_timeout"),
        CheckConstraint("failure_threshold between 1 and 10", name="ck_checks_threshold"),
        CheckConstraint("state in ('unknown','up','down')", name="ck_checks_state"),
        Index("ix_checks_group", "group_id"),
        # The scheduler's due-scan: partial index over schedulable rows only.
        Index("ix_checks_due", "next_run_at", postgresql_where=text("not paused")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDPk, primary_key=True, server_default=text("gen_random_uuid()"))
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("200"))
    expected_body: Mapped[str | None] = mapped_column(Text)
    failure_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    show_on_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Domain state, maintained by the scheduler/API manual runs.
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'unknown'"))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failing_since: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    in_flight_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # Denormalized last result: the status panel reads one row, no subqueries.
    last_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_response_time_ms: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (Index("ix_results_check_time", "check_id", "checked_at"),)

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True, autoincrement=True
    )
    check_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checks.id", ondelete="CASCADE"), nullable=False)
    checked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_check", "check_id", "started_at"),
        Index("ix_incidents_open", "check_id", postgresql_where=text("ended_at is null")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDPk, primary_key=True, server_default=text("gen_random_uuid()"))
    check_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checks.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notified_down_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notified_up_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    __table_args__ = (
        CheckConstraint("num_nonnulls(check_id, group_id) = 1", name="ck_maintenance_one_target"),
        CheckConstraint("ends_at > starts_at", name="ck_maintenance_period"),
        Index("ix_maintenance_active", "starts_at", "ends_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDPk, primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    check_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("checks.id", ondelete="CASCADE"))
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(UUIDPk, primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    check_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("checks.id", ondelete="CASCADE"))
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    suppress_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
