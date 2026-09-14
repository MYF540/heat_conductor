"""Tests for the boiler state machine."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.heat_conductor.core.boiler_fsm import BoilerController, BoilerInputs
from custom_components.heat_conductor.core.demand import DemandSummary
from custom_components.heat_conductor.core.models import (
    BoilerState,
    ControlParams,
    OperatingMode,
    Reason,
)

from .helpers import T0, demand

PARAMS = ControlParams()


def inputs(
    now: datetime,
    summary: DemandSummary,
    *,
    mode: OperatingMode = OperatingMode.AUTO,
    outdoor: float | None = 5.0,
    flow: float | None = None,
    automation: bool = True,
    actuator: bool = False,
    relay: bool | None = None,
) -> BoilerInputs:
    return BoilerInputs(
        now=now,
        demand=summary,
        outdoor_smoothed=outdoor,
        flow_temperature=flow,
        mode=mode,
        automation_enabled=automation,
        actuator_active=actuator,
        relay_on=relay,
    )


def minutes(m: float) -> datetime:
    return T0 + timedelta(minutes=m)


def test_start_requires_confirmation() -> None:
    fsm = BoilerController(PARAMS)
    first = fsm.step(inputs(minutes(0), demand(0.5)))
    assert first.reason is Reason.WAITING_CONFIRMATION
    assert not first.request_heat
    started = fsm.step(inputs(minutes(5), demand(0.5)))
    assert started.state is BoilerState.HEATING
    assert started.reason is Reason.DEMAND_START
    assert started.request_heat


def test_confirmation_resets_when_demand_drops() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(0.5)))
    assert fsm.step(inputs(minutes(3), demand(0.1))).reason is Reason.NO_DEMAND
    assert fsm.step(inputs(minutes(6), demand(0.5))).reason is Reason.WAITING_CONFIRMATION


def test_large_deficit_starts_immediately() -> None:
    fsm = BoilerController(PARAMS)
    decision = fsm.step(inputs(minutes(0), demand(0.1, max_deficit=1.5)))
    assert decision.reason is Reason.DEFICIT_START
    assert decision.request_heat


def test_min_runtime_and_min_pause() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(0.2, max_deficit=1.2)))
    held = fsm.step(inputs(minutes(10), demand(0.0)))
    assert held.reason is Reason.MIN_RUNTIME
    assert held.request_heat
    assert held.remaining == timedelta(minutes=10)

    stopped = fsm.step(inputs(minutes(20), demand(0.0)))
    assert stopped.reason is Reason.DEMAND_SATISFIED
    assert not stopped.request_heat

    waiting = fsm.step(inputs(minutes(25), demand(0.9, max_deficit=2.0)))
    assert waiting.reason is Reason.WAITING_MIN_PAUSE
    assert waiting.remaining == timedelta(minutes=10)
    assert fsm.step(inputs(minutes(35), demand(0.9, max_deficit=2.0))).request_heat


def test_max_starts_per_hour() -> None:
    params = ControlParams(min_run=timedelta(minutes=1), min_pause=timedelta(minutes=1))
    fsm = BoilerController(params)
    t = 0.0
    for _ in range(3):
        assert fsm.step(inputs(minutes(t), demand(1.0, max_deficit=2.0))).request_heat
        t += 2
        assert not fsm.step(inputs(minutes(t), demand(0.0))).request_heat
        t += 2
    blocked = fsm.step(inputs(minutes(t), demand(1.0, max_deficit=2.0)))
    assert blocked.reason is Reason.WAITING_MAX_STARTS
    assert fsm.step(inputs(minutes(61), demand(1.0, max_deficit=2.0))).request_heat


def test_no_data_after_startup_grace_is_failsafe() -> None:
    fsm = BoilerController(PARAMS)
    assert fsm.step(inputs(minutes(0), demand(None))).state is BoilerState.STARTING
    decision = fsm.step(inputs(minutes(3), demand(None)))
    assert decision.state is BoilerState.FAILSAFE
    assert decision.reason is Reason.NO_DATA


def test_failsafe_stops_immediately_ignoring_min_run() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(1.0, max_deficit=2.0)))
    decision = fsm.step(inputs(minutes(5), demand(None)))
    assert decision.state is BoilerState.FAILSAFE
    assert not decision.request_heat


def test_overtemperature_stops() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(1.0, max_deficit=2.0)))
    decision = fsm.step(inputs(minutes(1), demand(1.0, max_deficit=2.0), flow=85.0))
    assert decision.reason is Reason.OVERTEMPERATURE
    assert not decision.request_heat


def test_summer_mode_blocks_but_comfort_overrides() -> None:
    fsm = BoilerController(PARAMS)
    assert (
        fsm.step(inputs(minutes(0), demand(1.0, max_deficit=2.0), outdoor=18.0)).state
        is BoilerState.SUMMER
    )
    comfort = fsm.step(
        inputs(minutes(1), demand(1.0, max_deficit=2.0), outdoor=18.0, mode=OperatingMode.COMFORT)
    )
    assert comfort.request_heat


def test_frost_protection_even_when_mode_off() -> None:
    fsm = BoilerController(PARAMS)
    decision = fsm.step(
        inputs(minutes(0), demand(0.0, min_temperature=5.0), mode=OperatingMode.OFF)
    )
    assert decision.state is BoilerState.FROST_PROTECTION
    assert decision.request_heat
    still = fsm.step(inputs(minutes(30), demand(0.0, min_temperature=6.5), mode=OperatingMode.OFF))
    assert still.state is BoilerState.FROST_PROTECTION
    released = fsm.step(
        inputs(minutes(40), demand(0.0, min_temperature=7.2), mode=OperatingMode.OFF)
    )
    assert released.reason is Reason.MODE_OFF
    assert not released.request_heat


def test_mode_off_stops_immediately() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(1.0, max_deficit=2.0)))
    decision = fsm.step(inputs(minutes(1), demand(1.0, max_deficit=2.0), mode=OperatingMode.OFF))
    assert not decision.request_heat


def test_relay_unavailable_is_failsafe_without_command() -> None:
    fsm = BoilerController(PARAMS)
    decision = fsm.step(inputs(minutes(0), demand(1.0), actuator=True, relay=None))
    assert decision.reason is Reason.RELAY_UNAVAILABLE
    assert not decision.command_allowed


def test_manual_switching_is_detected_and_respected() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(0.0), actuator=True, relay=False))
    fsm.note_command(False)
    decision = fsm.step(inputs(minutes(1), demand(0.0), actuator=True, relay=True))
    assert decision.state is BoilerState.MANUAL
    assert decision.request_heat
    assert not decision.command_allowed
    resumed = fsm.step(inputs(minutes(62), demand(0.0), actuator=True, relay=True))
    assert resumed.reason is Reason.DEMAND_SATISFIED
    assert not resumed.request_heat


def test_commanded_switching_is_not_manual() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(0.0), actuator=True, relay=False))
    decision = fsm.step(
        inputs(minutes(1), demand(1.0, max_deficit=2.0), actuator=True, relay=False)
    )
    assert decision.request_heat
    fsm.note_command(True)
    following = fsm.step(
        inputs(minutes(2), demand(1.0, max_deficit=2.0), actuator=True, relay=True)
    )
    assert following.state is BoilerState.HEATING


def test_residual_heat_stops_when_all_rooms_above_target() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(1.0, max_deficit=2.0)))
    held = fsm.step(inputs(minutes(10), demand(0.2, max_deficit=-0.5)))
    assert held.reason is Reason.MIN_RUNTIME
    stopped = fsm.step(inputs(minutes(21), demand(0.2, max_deficit=-0.5)))
    assert stopped.reason is Reason.RESIDUAL_HEAT
    assert not stopped.request_heat


def test_forecast_of_cold_weather_overrides_summer_mode() -> None:
    fsm = BoilerController(PARAMS)
    summer = BoilerInputs(
        now=minutes(0),
        demand=demand(1.0, max_deficit=2.0),
        outdoor_smoothed=17.0,
        flow_temperature=None,
        mode=OperatingMode.AUTO,
        automation_enabled=True,
        actuator_active=False,
        relay_on=None,
        forecast_outdoor=17.0,
    )
    assert fsm.step(summer).state is BoilerState.SUMMER
    cold = BoilerInputs(
        now=minutes(1),
        demand=demand(1.0, max_deficit=2.0),
        outdoor_smoothed=17.0,
        flow_temperature=None,
        mode=OperatingMode.AUTO,
        automation_enabled=True,
        actuator_active=False,
        relay_on=None,
        forecast_outdoor=8.0,
    )
    assert fsm.step(cold).request_heat


def test_leaving_observation_adopts_relay_without_pause() -> None:
    fsm = BoilerController(PARAMS)
    assert fsm.step(inputs(minutes(0), demand(1.0, max_deficit=2.0))).request_heat
    fsm.step(inputs(minutes(30), demand(0.0)))
    decision = fsm.step(
        inputs(minutes(31), demand(1.0, max_deficit=2.0), actuator=True, relay=False)
    )
    assert decision.reason is Reason.DEFICIT_START
    assert decision.request_heat


def test_lagging_relay_does_not_reset_state() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(0.0), actuator=True, relay=False))
    assert fsm.step(
        inputs(minutes(1), demand(1.0, max_deficit=2.0), actuator=True, relay=False)
    ).request_heat
    fsm.note_command(True)
    still = fsm.step(inputs(minutes(2), demand(1.0, max_deficit=2.0), actuator=True, relay=False))
    assert still.request_heat
    assert still.state is BoilerState.HEATING


def test_restart_while_in_control_keeps_min_pause() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(0.0), actuator=True, relay=False))
    fsm.step(inputs(minutes(1), demand(1.0, max_deficit=2.0), actuator=True, relay=False))
    fsm.note_command(True)
    fsm.step(inputs(minutes(2), demand(1.0, max_deficit=2.0), actuator=True, relay=True))
    fsm.step(inputs(minutes(25), demand(0.0), actuator=True, relay=True))
    fsm.note_command(False)
    fsm.step(inputs(minutes(26), demand(0.0), actuator=True, relay=False))

    restarted = BoilerController(PARAMS)
    restarted.restore(fsm.to_dict())
    decision = restarted.step(
        inputs(minutes(30), demand(1.0, max_deficit=2.0), actuator=True, relay=False)
    )
    assert decision.reason is Reason.WAITING_MIN_PAUSE


def test_automation_disabled_never_commands() -> None:
    fsm = BoilerController(PARAMS)
    decision = fsm.step(
        inputs(minutes(0), demand(1.0, max_deficit=2.0), automation=False, relay=True)
    )
    assert decision.state is BoilerState.DISABLED
    assert not decision.command_allowed


def test_state_roundtrip() -> None:
    fsm = BoilerController(PARAMS)
    fsm.step(inputs(minutes(0), demand(1.0, max_deficit=2.0)))
    restored = BoilerController(PARAMS)
    restored.restore(fsm.to_dict())
    assert restored.is_on
    assert restored.on_since == minutes(0)
    assert len(restored.starts) == 1
