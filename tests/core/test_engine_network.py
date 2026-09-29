"""Heat network inside the engine: thermostat writes, demand and restore."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.heat_conductor.core.engine import (
    EngineSnapshot,
    HeatingEngine,
    RoomControlInput,
)
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode
from custom_components.heat_conductor.core.network import NetworkParams, NetworkPhase
from custom_components.heat_conductor.core.setpoint import TrvInput

from .helpers import T0, fresh, room

OPEN = NetworkParams().opening_temperature


def snapshot(
    now: datetime,
    *,
    bad: float = 18.0,
    wohnzimmer: float = 21.0,
    wohnzimmer_valve: float = 0.0,
    wohnzimmer_trv: float = 21.0,
    network: bool = True,
    room_control: bool = True,
    actuator: bool = True,
    relay_on: bool = True,
) -> EngineSnapshot:
    """Bad is cold and starts a release, Wohnzimmer is at its target."""
    return EngineSnapshot(
        now=now,
        rooms=(
            room(
                "Bad",
                room_temperature=fresh(bad, now),
                targets=(fresh(21.0, now),),
                valves=(fresh(1.0 if bad < 21.0 else 0.0, now),),
            ),
            room(
                "Wohnzimmer",
                room_temperature=fresh(wohnzimmer, now),
                targets=(fresh(wohnzimmer_trv, now),),
                valves=(fresh(wohnzimmer_valve, now),),
            ),
        ),
        outdoor_sensors=(fresh(5.0, now),),
        weather_temperature=None,
        flow_temperature=None,
        return_temperature=None,
        gas_flow=None,
        gas_meter=None,
        burner_on=None,
        relay_on=relay_on,
        mode=OperatingMode.AUTO,
        automation_enabled=True,
        actuator_active=actuator,
        room_control_enabled=room_control,
        network_enabled=network,
        room_controls=(
            RoomControlInput(
                room_id="bad",
                schedule_on=True,
                trvs=(TrvInput("climate.bad", True, 21.0, bad, "heat"),),
                compensation=False,
            ),
            RoomControlInput(
                room_id="wohnzimmer",
                schedule_on=True,
                trvs=(TrvInput("climate.wohnzimmer", True, wohnzimmer_trv, wohnzimmer, "heat"),),
                compensation=False,
            ),
        ),
    )


def writes(result, entity_id: str) -> list[float]:  # type: ignore[no-untyped-def]
    return [c.temperature for c in result.trv_commands if c.entity_id == entity_id]


def test_co_heating_opens_the_thermostat_and_closes_it_at_the_goal() -> None:
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(snapshot(T0))
    assert result.decision.request_heat
    assert result.network.phase is NetworkPhase.RELEASE
    assert result.network.executing
    assert "wohnzimmer" in result.network.active_rooms()
    assert writes(result, "climate.wohnzimmer") == [OPEN]
    assert engine.runtime("wohnzimmer").co_heat_written

    # The open valve of the co-heated room is no demand of its own.
    later = T0 + timedelta(minutes=5)
    result = engine.evaluate(
        snapshot(later, wohnzimmer_valve=1.0, wohnzimmer_trv=OPEN, wohnzimmer=21.2)
    )
    assert result.room("wohnzimmer").demand == 0.0
    assert result.room("wohnzimmer").target == 21.0

    goal = result.network.room("wohnzimmer").goal
    assert goal is not None and 21.0 < goal <= 22.0
    done = later + timedelta(minutes=30)
    result = engine.evaluate(
        snapshot(done, wohnzimmer_valve=1.0, wohnzimmer_trv=OPEN, wohnzimmer=goal)
    )
    assert "wohnzimmer" not in result.network.active_rooms()
    assert writes(result, "climate.wohnzimmer") == [21.0]
    assert not engine.runtime("wohnzimmer").co_heat_written
    # The valve closes slowly: it still does not count right after the co-heat.
    assert result.room("wohnzimmer").demand == 0.0


def test_preview_writes_nothing() -> None:
    """With the switch off the plan is shown, the thermostats keep their target."""
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(snapshot(T0, network=False))
    assert result.network.blocked == "switch_off"
    assert "wohnzimmer" in result.network.active_rooms()
    assert writes(result, "climate.wohnzimmer") == []


def test_observation_mode_only_previews() -> None:
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(snapshot(T0, actuator=False, relay_on=False))
    assert result.network.blocked == "observation_mode"
    assert writes(result, "climate.wohnzimmer") == []


def test_room_control_off_restores_the_previous_target() -> None:
    """HeatConductor undoes its own opening even when it no longer controls rooms."""
    engine = HeatingEngine(ControlParams())
    engine.evaluate(snapshot(T0, wohnzimmer_trv=20.5))
    later = T0 + timedelta(minutes=5)
    result = engine.evaluate(
        snapshot(later, wohnzimmer_trv=OPEN, wohnzimmer_valve=1.0, room_control=False)
    )
    assert writes(result, "climate.wohnzimmer") == [20.5]
    assert not engine.runtime("wohnzimmer").co_heat_written


def test_restart_ends_co_heating() -> None:
    """After a restart without a release the opened thermostat gets its target back."""
    engine = HeatingEngine(ControlParams())
    engine.evaluate(snapshot(T0))
    restored = HeatingEngine(ControlParams())
    restored.restore(engine.to_dict())
    later = T0 + timedelta(minutes=2)
    result = restored.evaluate(
        snapshot(later, bad=21.5, wohnzimmer_trv=OPEN, wohnzimmer_valve=1.0, relay_on=False)
    )
    assert not result.decision.request_heat
    assert writes(result, "climate.wohnzimmer") == [21.0]


def test_excluded_room_is_never_co_heated() -> None:
    engine = HeatingEngine(ControlParams())
    engine.runtime("wohnzimmer").co_heat_enabled = False
    result = engine.evaluate(snapshot(T0))
    assert "wohnzimmer" not in result.network.active_rooms()
    assert writes(result, "climate.wohnzimmer") == []
