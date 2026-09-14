"""Tests for daily counters and the engine pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.heat_conductor.core.engine import EngineSnapshot, HeatingEngine
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode, RoomKind
from custom_components.heat_conductor.core.stats import DailyRuntime

from .helpers import T0, fresh, room


def test_daily_runtime_counts_starts_and_time() -> None:
    stats = DailyRuntime()
    stats.update(T0, False)
    stats.update(T0 + timedelta(minutes=1), True)
    snap = stats.update(T0 + timedelta(minutes=31), False)
    assert snap.starts == 1
    assert snap.runtime == timedelta(minutes=30)


def test_daily_runtime_resets_at_midnight() -> None:
    stats = DailyRuntime()
    late = datetime(2026, 11, 2, 23, 50, tzinfo=UTC)
    stats.update(late, False)
    stats.update(late + timedelta(minutes=5), True)
    snap = stats.update(late + timedelta(minutes=20), True)
    assert snap.starts == 0
    assert snap.runtime == timedelta(minutes=10)


def _snapshot(now: datetime, valve: float) -> EngineSnapshot:
    return EngineSnapshot(
        now=now,
        rooms=(
            room(
                "Bad",
                thermostat_temperatures=(fresh(19.3, now),),
                targets=(fresh(21.0, now),),
                valves=(fresh(valve, now),),
            ),
            room("Schlafzimmer", kind=RoomKind.MONITOR, room_temperature=fresh(17.0, now)),
        ),
        outdoor_sensors=(fresh(3.0, now),),
        weather_temperature=None,
        flow_temperature=fresh(45.0, now),
        return_temperature=fresh(38.0, now),
        gas_flow=fresh(1.2, now),
        gas_meter=None,
        burner_on=None,
        relay_on=None,
        mode=OperatingMode.AUTO,
        automation_enabled=True,
        actuator_active=False,
    )


def test_engine_end_to_end_and_persistence() -> None:
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(_snapshot(T0, 1.0))
    assert result.decision.request_heat
    assert result.demand.total == 1.0
    assert result.spread == 7.0
    assert result.burner_active is True
    assert result.outdoor.value == 3.0
    assert result.room("schlafzimmer") is not None

    restored = HeatingEngine(ControlParams())
    restored.restore(engine.to_dict())
    assert restored.boiler.is_on
    assert restored.outdoor_smoother.value == 3.0
    assert result.energy.burner_power is not None
