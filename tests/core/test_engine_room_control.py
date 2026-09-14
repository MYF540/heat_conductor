"""Room control inside the engine pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.heat_conductor.core.engine import (
    EngineSnapshot,
    HeatingEngine,
    RoomControlInput,
)
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode, Reading
from custom_components.heat_conductor.core.setpoint import SetpointSource, TrvInput

from .helpers import T0, fresh, room


def snapshot(
    now: datetime,
    *,
    enabled: bool,
    trv_target: float = 18.0,
    schedule_on: bool = True,
    duty: float | None = None,
) -> EngineSnapshot:
    return EngineSnapshot(
        now=now,
        rooms=(
            room(
                "Bad",
                room_temperature=fresh(20.0, now),
                thermostat_temperatures=(fresh(21.0, now),),
                targets=(fresh(trv_target, now),),
                valves=(fresh(0.0, now),),
            ),
        ),
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
        room_control_enabled=enabled,
        room_controls=(
            RoomControlInput(
                room_id="bad",
                schedule_on=schedule_on,
                trvs=(TrvInput("climate.bad", True, trv_target, 21.0, "heat"),),
            ),
        ),
        duty_cycle=Reading(duty, now) if duty is not None else None,
    )


def test_setpoints_are_previewed_but_not_written_when_disabled() -> None:
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(snapshot(T0, enabled=False))
    assert result.setpoint("bad").source is SetpointSource.SCHEDULE_COMFORT
    assert result.trv_commands == ()
    assert result.room("bad").target == 18.0  # thermostat target still used


def test_room_control_writes_and_uses_effective_target() -> None:
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(snapshot(T0, enabled=True))
    assert result.room("bad").target == 21.0
    assert result.room("bad").deficit == 1.0
    assert len(result.trv_commands) == 1
    # comfort 21 + compensation offset (21 - 20 = 1)
    assert result.trv_commands[0].temperature == 22.0


def test_duty_cycle_limit_suppresses_writes() -> None:
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(snapshot(T0, enabled=True, duty=95.0))
    assert not result.duty_cycle_ok
    assert result.trv_commands == ()


def test_manual_thermostat_change_becomes_override() -> None:
    engine = HeatingEngine(ControlParams())
    engine.evaluate(snapshot(T0, enabled=True))  # writes 22.0
    later = T0 + timedelta(minutes=10)
    result = engine.evaluate(snapshot(later, enabled=True, trv_target=24.0))
    assert result.manual_overrides == ("bad",)
    following = engine.evaluate(
        snapshot(later + timedelta(minutes=1), enabled=True, trv_target=24.0)
    )
    assert following.setpoint("bad").source is SetpointSource.OVERRIDE
    assert following.setpoint("bad").target == 23.0  # 24 minus offset 1


def test_room_runtime_is_persisted() -> None:
    engine = HeatingEngine(ControlParams())
    engine.runtime("bad").comfort = 22.5
    engine.set_boost("bad", T0, timedelta(minutes=20), None)
    restored = HeatingEngine(ControlParams())
    restored.restore(engine.to_dict())
    assert restored.runtime("bad").comfort == 22.5
    assert restored.runtime("bad").boost_until == T0 + timedelta(minutes=20)
