"""Pure decision logic for check results → state / incidents / notifications.

No I/O here on purpose: the whole state machine is unit-testable without a
database. See docs/CONTRACT.md §3.3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Decision:
    """What the caller must do after processing one check result."""

    new_state: str
    failures: int
    failing_since_set_now: bool
    open_incident: bool = False
    close_incident: bool = False
    send_down: bool = False
    send_up: bool = False
    # Would have notified, but a maintenance window is active: record a
    # suppressed outbox row instead (visible in the Mailbox UI).
    suppress_down: bool = False
    suppress_up: bool = False


def decide(
    *,
    ok: bool,
    prev_state: str,
    consecutive_failures: int,
    failure_threshold: int,
    has_open_incident: bool,
    down_notified: bool,
    in_maintenance: bool,
) -> Decision:
    """Apply one check outcome to the check/incident state machine."""
    if ok:
        decision = Decision(new_state="up", failures=0, failing_since_set_now=False)
        if has_open_incident:
            decision = Decision(
                new_state="up",
                failures=0,
                failing_since_set_now=False,
                close_incident=True,
                send_up=not in_maintenance,
                suppress_up=in_maintenance,
            )
        return decision

    failures = consecutive_failures + 1
    first_failure_of_streak = consecutive_failures == 0
    threshold_reached = failures >= failure_threshold
    new_state = "down" if threshold_reached else prev_state

    if not has_open_incident and threshold_reached:
        # Incident opens at threshold; started_at is the streak's first failure.
        return Decision(
            new_state=new_state,
            failures=failures,
            failing_since_set_now=first_failure_of_streak,
            open_incident=True,
            send_down=not in_maintenance,
            suppress_down=in_maintenance,
        )

    if has_open_incident and not down_notified and not in_maintenance:
        # Opened during maintenance, window has ended, site is still down:
        # the delayed down-notification goes out on the next failing check.
        return Decision(
            new_state=new_state,
            failures=failures,
            failing_since_set_now=first_failure_of_streak,
            send_down=True,
        )

    return Decision(
        new_state=new_state,
        failures=failures,
        failing_since_set_now=first_failure_of_streak,
    )


def group_status(states: list[str]) -> str:
    """Compute group status from member check states (CONTRACT §3.6).

    paused checks are excluded by the caller.
    """
    if not states:
        return "operational"
    downs = states.count("down")
    if downs == 0:
        return "degraded" if "unknown" in states else "operational"
    return "major_outage" if downs == len(states) else "partial_outage"
