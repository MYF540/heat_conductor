"""Plausibility checks with feedback from the boiler electronics."""

from __future__ import annotations

from datetime import timedelta

from custom_components.heat_conductor.core.diagnosis import RELAY_FEEDBACK_DELAY, DiagnosisTracker

from .helpers import T0


def _update(tracker: DiagnosisTracker, now=T0, **kwargs):  # type: ignore[no-untyped-def]
    values = {
        "relay_on": True,
        "relay_feedback": True,
        "request_heat": True,
        "burner_on": None,
        "burner_lock": None,
        "winter_mode": None,
        "pump_on": None,
    }
    values.update(kwargs)
    return tracker.update(now, **values)


def test_relay_mismatch_only_after_the_delay() -> None:
    """The boiler needs a moment to report a switched relay."""
    tracker = DiagnosisTracker()
    assert not _update(tracker, relay_feedback=False).relay_mismatch
    later = T0 + RELAY_FEEDBACK_DELAY
    assert _update(tracker, later, relay_feedback=False).relay_mismatch


def test_matching_feedback_resets_the_mismatch() -> None:
    """Agreement in between restarts the timer."""
    tracker = DiagnosisTracker()
    _update(tracker, relay_feedback=False)
    _update(tracker, T0 + timedelta(minutes=1), relay_feedback=True)
    result = _update(tracker, T0 + RELAY_FEEDBACK_DELAY, relay_feedback=False)
    assert not result.relay_mismatch


def test_no_mismatch_without_feedback() -> None:
    """Without a feedback entity nothing is claimed."""
    tracker = DiagnosisTracker()
    _update(tracker, relay_feedback=None)
    assert not _update(tracker, T0 + timedelta(hours=1), relay_feedback=None).relay_mismatch


def test_burner_lock_explains_a_cold_burner() -> None:
    """A running lock time with the burner off counts as locked."""
    tracker = DiagnosisTracker()
    locked = _update(tracker, burner_on=False, burner_lock=4.0)
    assert locked.burner_locked
    assert locked.burner_lock_minutes == 4.0
    assert not _update(tracker, burner_on=False, burner_lock=0.0).burner_locked
    assert not _update(tracker, burner_on=True, burner_lock=4.0).burner_locked


def test_summer_mode_is_only_a_conflict_while_heat_is_needed() -> None:
    """Summer mode is fine as long as HeatConductor does not want heat."""
    tracker = DiagnosisTracker()
    assert _update(tracker, winter_mode=False, request_heat=True).summer_mode_conflict
    assert not _update(tracker, winter_mode=False, request_heat=False).summer_mode_conflict
    assert not _update(tracker, winter_mode=True, request_heat=True).summer_mode_conflict
    assert not _update(tracker, winter_mode=None, request_heat=True).summer_mode_conflict


def _flow(tracker: DiagnosisTracker, start, minutes: int, pipe: float, boiler: float, pump=True):  # type: ignore[no-untyped-def]
    """Feed flow readings every five minutes and return the last diagnosis."""
    result = None
    for step in range(0, minutes + 1, 5):
        result = _update(
            tracker,
            start + timedelta(minutes=step),
            pump_on=pump,
            pipe_flow=pipe,
            boiler_flow=boiler,
            pipe_return=40.0,
        )
    return result


def test_boiler_spread_uses_the_pipe_return_without_a_boiler_return() -> None:
    """The boiler has no return sensor, so the pipe return is used."""
    result = _update(DiagnosisTracker(), boiler_flow=55.0, pipe_return=41.0, pump_on=True)
    assert result.boiler_spread == 14.0
    assert (
        _update(DiagnosisTracker(), boiler_flow=55.0, pipe_return=41.0, pump_on=False).boiler_spread
        is None
    )


def test_constant_offset_is_learned_and_not_suspicious() -> None:
    """A pipe sensor 3 K below the boiler sensor is normal."""
    tracker = DiagnosisTracker()
    result = _flow(tracker, T0, 120, pipe=52.0, boiler=55.0)
    assert result.flow_deviation == -3.0
    assert result.flow_deviation_typical == -3.0
    assert not result.flow_sensor_suspect


def test_changed_offset_becomes_suspicious_after_a_while() -> None:
    """A clamp sensor that came loose reads far too low."""
    tracker = DiagnosisTracker()
    _flow(tracker, T0, 120, pipe=52.0, boiler=55.0)
    early = _flow(tracker, T0 + timedelta(minutes=125), 20, pipe=40.0, boiler=55.0)
    assert not early.flow_sensor_suspect
    late = _flow(tracker, T0 + timedelta(minutes=150), 30, pipe=40.0, boiler=55.0)
    assert late.flow_sensor_suspect
    # The faulty readings did not teach the offset.
    assert abs(late.flow_deviation_typical + 3.0) < 0.01


def test_no_learning_without_circulation() -> None:
    """With the pump off the pipe cools down, that is no sensor fault."""
    tracker = DiagnosisTracker()
    result = _flow(tracker, T0, 120, pipe=30.0, boiler=55.0, pump=False)
    assert result.flow_deviation_typical is None
    assert not result.flow_sensor_suspect


def test_learned_offset_survives_a_restart() -> None:
    """The offset is persisted."""
    tracker = DiagnosisTracker()
    _flow(tracker, T0, 120, pipe=52.0, boiler=55.0)
    restored = DiagnosisTracker()
    restored.restore(tracker.to_dict())
    assert restored.flow_offset == tracker.flow_offset
    assert restored.flow_offset_samples == tracker.flow_offset_samples
