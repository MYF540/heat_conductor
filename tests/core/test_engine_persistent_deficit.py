"""A single cold room starts the boiler although its share of the demand is small."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from custom_components.heat_conductor.core.engine import EngineSnapshot, HeatingEngine
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode, Reason

from .helpers import T0, fresh, room


def _snapshot(now: datetime, cold_deficit: float, *, window: bool = False) -> EngineSnapshot:
    rooms = [
        room(
            "Kalt",
            thermostat_temperatures=(fresh(21.0 - cold_deficit, now),),
            targets=(fresh(21.0, now),),
            valves=(fresh(1.0, now),),
            windows_open=(window,),
        )
    ]
    rooms += [
        room(
            f"Warm{i}",
            thermostat_temperatures=(fresh(21.0, now),),
            targets=(fresh(21.0, now),),
            valves=(fresh(0.0, now),),
        )
        for i in range(5)
    ]
    return EngineSnapshot(
        now=now,
        rooms=tuple(rooms),
        outdoor_sensors=(fresh(3.0, now),),
        weather_temperature=None,
        flow_temperature=None,
        return_temperature=None,
        gas_flow=None,
        gas_meter=None,
        burner_on=None,
        relay_on=None,
        mode=OperatingMode.AUTO,
        automation_enabled=True,
        actuator_active=False,
    )


def _run(engine: HeatingEngine, minutes: int, deficit: float, **kwargs: bool):
    """Evaluate once a minute; return the first minute with a start and its result."""
    for minute in range(minutes + 1):
        result = engine.evaluate(_snapshot(T0 + timedelta(minutes=minute), deficit, **kwargs))
        if result.decision.request_heat:
            return minute, result
    return None, result


def test_single_cold_room_starts_after_the_persistent_time() -> None:
    engine = HeatingEngine(ControlParams())
    minute, result = _run(engine, 120, 0.9)
    assert minute is not None
    assert 45 <= minute <= 47
    assert result.decision.reason is Reason.PERSISTENT_DEFICIT
    assert result.demand.persistent_deficit


def test_small_deficit_never_starts() -> None:
    engine = HeatingEngine(ControlParams())
    minute, result = _run(engine, 240, 0.3)
    assert minute is None
    assert result.decision.reason is Reason.NO_DEMAND
    assert not result.demand.persistent_deficit


def test_feature_is_off_with_time_zero() -> None:
    engine = HeatingEngine(replace(ControlParams(), persistent_deficit_time=timedelta(0)))
    minute, _ = _run(engine, 120, 0.9)
    assert minute is None


def test_open_window_does_not_count() -> None:
    engine = HeatingEngine(ControlParams())
    minute, _ = _run(engine, 120, 0.9, window=True)
    assert minute is None


def test_interruption_restarts_the_timer() -> None:
    engine = HeatingEngine(ControlParams())
    minute, _ = _run(engine, 40, 0.9)
    assert minute is None
    engine.evaluate(_snapshot(T0 + timedelta(minutes=41), 0.1))
    for m in range(42, 41 + 44):
        assert not engine.evaluate(_snapshot(T0 + timedelta(minutes=m), 0.9)).decision.request_heat


def test_hysteresis_keeps_a_starving_room_starving() -> None:
    engine = HeatingEngine(ControlParams())
    _, result = _run(engine, 120, 0.9)
    assert result.demand.persistent_deficit
    now = T0 + timedelta(minutes=130)
    # 0.3 K is below the 0.5 K limit but not below half of it: still starving.
    assert engine.evaluate(_snapshot(now, 0.3)).demand.persistent_deficit
    assert not engine.evaluate(_snapshot(now + timedelta(minutes=1), 0.2)).demand.persistent_deficit
