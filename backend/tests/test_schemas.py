"""Schema validation tests (pydantic-level, no DB)."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas import CheckIn, MaintenanceIn

UTC = timezone.utc


class TestCheckIn:
    def _base(self, **overrides):
        data = dict(
            group_id="00000000-0000-0000-0000-000000000001",
            name="x",
            url="http://example.com",
            interval_seconds=60,
            timeout_seconds=10,
        )
        data.update(overrides)
        return data

    def test_interval_bounds(self):
        with pytest.raises(ValidationError):
            CheckIn(**self._base(interval_seconds=29))
        with pytest.raises(ValidationError):
            CheckIn(**self._base(interval_seconds=3601))
        CheckIn(**self._base(interval_seconds=30))
        CheckIn(**self._base(interval_seconds=3600))

    def test_timeout_bounds(self):
        with pytest.raises(ValidationError):
            CheckIn(**self._base(timeout_seconds=0))
        with pytest.raises(ValidationError):
            CheckIn(**self._base(timeout_seconds=31))

    def test_url_must_be_http(self):
        with pytest.raises(ValidationError):
            CheckIn(**self._base(url="ftp://example.com"))


class TestMaintenanceIn:
    def _base(self, **overrides):
        start = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
        data = dict(
            group_id="00000000-0000-0000-0000-000000000002",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        data.update(overrides)
        return data

    def test_valid(self):
        window = MaintenanceIn(**self._base())
        assert window.note == ""

    def test_requires_exactly_one_target(self):
        with pytest.raises(ValidationError):
            MaintenanceIn(**self._base(group_id=None))
        both = self._base(check_id="00000000-0000-0000-0000-000000000003")
        with pytest.raises(ValidationError):
            MaintenanceIn(**both)

    def test_ends_after_starts(self):
        start = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
        with pytest.raises(ValidationError):
            MaintenanceIn(**self._base(ends_at=start - timedelta(minutes=1)))

    def test_naive_datetimes_rejected(self):
        start = datetime(2026, 10, 6, 12, 0)
        with pytest.raises(ValidationError):
            MaintenanceIn(**self._base(starts_at=start))
