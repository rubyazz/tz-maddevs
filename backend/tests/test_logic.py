"""Unit tests for the pure incident state machine (CONTRACT §3.3)."""

from app.checks.logic import decide, group_status


def d(**overrides):
    kwargs = dict(
        ok=False,
        prev_state="up",
        consecutive_failures=0,
        failure_threshold=3,
        has_open_incident=False,
        down_notified=False,
        in_maintenance=False,
    )
    kwargs.update(overrides)
    return decide(**kwargs)


class TestFailureStreak:
    def test_single_blip_is_not_downtime(self):
        decision = d(ok=False, consecutive_failures=0)
        assert decision.new_state == "up"  # still up below threshold
        assert not decision.open_incident
        assert decision.failures == 1
        assert decision.failing_since_set_now

    def test_second_failure_still_no_incident(self):
        decision = d(consecutive_failures=1)
        assert decision.new_state == "up"
        assert not decision.open_incident
        assert not decision.failing_since_set_now  # streak already started

    def test_threshold_opens_incident_and_sends_down(self):
        decision = d(consecutive_failures=2)
        assert decision.new_state == "down"
        assert decision.open_incident
        assert decision.send_down
        assert not decision.suppress_down

    def test_first_ever_failure_keeps_unknown_state(self):
        decision = d(prev_state="unknown", consecutive_failures=0)
        assert decision.new_state == "unknown"

    def test_threshold_lowered_mid_streak_opens_incident(self):
        # threshold was 5, streak at 4, threshold PATCHed to 3
        decision = d(consecutive_failures=3, failure_threshold=3)
        assert decision.open_incident


class TestOpenIncident:
    def test_repeated_failures_send_no_more_emails(self):
        decision = d(consecutive_failures=5, has_open_incident=True, down_notified=True)
        assert not decision.send_down
        assert not decision.open_incident  # already open
        assert decision.new_state == "down"

    def test_recovery_closes_and_sends_up(self):
        decision = d(ok=True, has_open_incident=True)
        assert decision.new_state == "up"
        assert decision.close_incident
        assert decision.send_up
        assert decision.failures == 0

    def test_recovery_without_incident_is_quiet(self):
        decision = d(ok=True, has_open_incident=False)
        assert not decision.close_incident
        assert not decision.send_up

    def test_opened_during_maintenance_window_ended(self):
        # incident open, down email never sent (was suppressed), window over
        decision = d(consecutive_failures=4, has_open_incident=True, down_notified=False,
                     in_maintenance=False)
        assert decision.send_down  # the delayed notification path
        assert not decision.open_incident


class TestMaintenanceSuppression:
    def test_opening_in_window_suppresses_down(self):
        decision = d(consecutive_failures=2, in_maintenance=True)
        assert decision.open_incident
        assert decision.suppress_down
        assert not decision.send_down

    def test_recovery_in_window_suppresses_up(self):
        decision = d(ok=True, has_open_incident=True, in_maintenance=True)
        assert decision.close_incident  # incident still tracked & closed
        assert decision.suppress_up
        assert not decision.send_up

    def test_still_in_window_no_late_send(self):
        decision = d(consecutive_failures=4, has_open_incident=True, down_notified=False,
                     in_maintenance=True)
        assert not decision.send_down  # waits for the window-end pass


class TestGroupStatus:
    def test_empty(self):
        assert group_status([]) == "operational"

    def test_all_up(self):
        assert group_status(["up", "up"]) == "operational"

    def test_any_unknown_degraded(self):
        assert group_status(["up", "unknown"]) == "degraded"

    def test_partial_outage(self):
        assert group_status(["up", "down"]) == "partial_outage"

    def test_major_outage(self):
        assert group_status(["down", "down"]) == "major_outage"
