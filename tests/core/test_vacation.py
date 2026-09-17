"""Automatic vacation detection from presence."""

from __future__ import annotations

from datetime import timedelta

from custom_components.heat_conductor.core.vacation import AutoVacation, VacationParams

from .helpers import T0

PARAMS = VacationParams()


def _run(detector: AutoVacation, start, present: bool | None, hours: float) -> bool:
    """Feed one presence value for a number of hours, one sample every 10 minutes."""
    moment = start
    end = start + timedelta(hours=hours)
    active = detector.active
    while moment <= end:
        active = detector.update(moment, present, PARAMS)
        moment += timedelta(minutes=10)
    return active


def test_starts_after_two_days_without_anybody_home() -> None:
    """Nobody home for the configured absence starts the vacation."""
    detector = AutoVacation()
    assert _run(detector, T0, False, hours=47) is False
    assert _run(detector, T0 + timedelta(hours=47), False, hours=2) is True
    assert detector.since is not None


def test_short_presence_restarts_the_absence() -> None:
    """Somebody dropping by resets the timer."""
    detector = AutoVacation()
    _run(detector, T0, False, hours=40)
    _run(detector, T0 + timedelta(hours=40), True, hours=0.5)
    assert _run(detector, T0 + timedelta(hours=41), False, hours=40) is False


def test_ends_after_three_hours_at_home() -> None:
    """Being back for the configured time ends the vacation."""
    detector = AutoVacation()
    _run(detector, T0, False, hours=50)
    assert detector.active

    back = T0 + timedelta(hours=50)
    assert _run(detector, back, True, hours=2) is True  # still vacation
    assert _run(detector, back + timedelta(hours=2), True, hours=1.5) is False


def test_short_visit_does_not_end_it() -> None:
    """A brief visit keeps the vacation running."""
    detector = AutoVacation()
    _run(detector, T0, False, hours=50)
    visit = T0 + timedelta(hours=50)
    assert _run(detector, visit, True, hours=1) is True
    assert _run(detector, visit + timedelta(hours=1), False, hours=1) is True


def test_disabled_never_activates() -> None:
    """Switched off, nothing happens."""
    detector = AutoVacation()
    params = VacationParams(enabled=False)
    moment = T0
    for _ in range(600):
        assert detector.update(moment, False, params) is False
        moment += timedelta(minutes=10)


def test_unknown_presence_does_not_start_a_vacation() -> None:
    """Without presence entities absence cannot be claimed."""
    detector = AutoVacation()
    moment = T0
    for _ in range(600):
        assert detector.update(moment, None, PARAMS) is False
        moment += timedelta(minutes=10)


def test_manual_reset_requires_a_full_absence_again() -> None:
    """Ending it by hand does not let it come back right away."""
    detector = AutoVacation()
    _run(detector, T0, False, hours=50)
    assert detector.active

    reset_at = T0 + timedelta(hours=50)
    detector.reset(reset_at)
    assert detector.active is False
    assert _run(detector, reset_at, False, hours=47) is False
    assert _run(detector, reset_at + timedelta(hours=47), False, hours=2) is True


def test_survives_a_restart() -> None:
    """Timers and state are persisted."""
    detector = AutoVacation()
    _run(detector, T0, False, hours=30)
    restored = AutoVacation.from_dict(detector.to_dict())

    assert restored.absent_since == detector.absent_since
    assert restored.active is False
    assert _run(restored, T0 + timedelta(hours=30), False, hours=19) is True
