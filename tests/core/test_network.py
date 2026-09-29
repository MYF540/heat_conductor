"""Heat network: forecast, co-heating, residual heat, bundling and learning."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import math

import pytest

from custom_components.heat_conductor.core.boiler_fsm import BoilerController, BoilerInputs
from custom_components.heat_conductor.core.energy import EnergySnapshot
from custom_components.heat_conductor.core.learning import RoomLearner
from custom_components.heat_conductor.core.models import (
    BoilerState,
    ControlParams,
    OperatingMode,
    Reason,
)
from custom_components.heat_conductor.core.network import (
    DEFAULT_OVERSHOOT,
    VALVE_SETTLE,
    CoHeatEnd,
    CoHeatReason,
    HeatNetwork,
    KpiTracker,
    NetworkInputs,
    NetworkParams,
    NetworkPhase,
    NetworkRoom,
    SinkLearner,
    bundle_room,
    forecast_room,
    hold_temperature,
    need_in,
)

from .helpers import T0, demand

PARAMS = NetworkParams()
OUTDOOR = 10.0


def comfort_room(room_id: str, temperature: float, **kwargs) -> NetworkRoom:  # type: ignore[no-untyped-def]
    values = {
        "room_id": room_id,
        "temperature": temperature,
        "target": 21.0,
        "comfort": 21.0,
        "eligible": True,
        "comfort_like": True,
        "valve": 0.0,
        "tau": 40.0,
        **kwargs,
    }
    return NetworkRoom(**values)


def inputs(rooms, now=T0, *, release=True, blocked=None, **kwargs) -> NetworkInputs:  # type: ignore[no-untyped-def]
    forecasts = {r.room_id: forecast_room(r, now, OUTDOOR, PARAMS) for r in rooms}
    return NetworkInputs(
        now=now,
        rooms=tuple(rooms),
        forecasts=forecasts,
        release=release,
        enabled=True,
        blocked=blocked,
        **kwargs,
    )


# -- room model -------------------------------------------------------------------


def test_cooling_model() -> None:
    """Newton cooling towards the outdoor temperature."""
    need = need_in(21.8, 21.0, OUTDOOR, 40.0)
    assert need is not None
    assert need.total_seconds() / 3600 == pytest.approx(40 * math.log(11.8 / 11.0))
    assert need_in(20.5, 21.0, OUTDOOR, 40.0) == timedelta(0)
    assert need_in(21.5, 21.0, 22.0, 40.0) is None  # warmer outside: never
    assert hold_temperature(21.0, OUTDOOR, 40.0, timedelta(hours=3)) == pytest.approx(
        10 + 11 * math.exp(3 / 40)
    )


def test_soon_goal_lasts_the_horizon_and_is_capped() -> None:
    """A well insulated room needs a little, a fast cooling room hits the reserve."""
    slow = forecast_room(comfort_room("a", 21.0, tau=40.0), T0, OUTDOOR, PARAMS)
    fast = forecast_room(comfort_room("b", 21.0, tau=15.0), T0, OUTDOOR, PARAMS)
    assert slow.soon_goal == pytest.approx(10 + 11 * math.exp(3 / 40))
    assert fast.soon_goal == 22.0  # would need 23.4, capped at target + 1 K
    assert slow.candidate() is CoHeatReason.SOON
    assert fast.need_in is not None and slow.need_in is not None


def test_comfort_ending_soon_limits_the_goal() -> None:
    """No reserve beyond the end of the comfort period."""
    room = comfort_room("a", 21.0, comfort_ends=T0 + timedelta(minutes=30))
    forecast = forecast_room(room, T0, OUTDOOR, PARAMS)
    assert forecast.sink_goal is None
    assert forecast.soon_goal == pytest.approx(10 + 11 * math.exp(0.5 / 40))
    assert forecast.candidate() is None  # less than the minimum gain


def test_eco_room_is_preheated_only_shortly_before_its_own_preheat() -> None:
    """Comfort begins soon: heat along up to comfort, not above."""
    base = comfort_room(
        "a", 18.5, target=18.0, comfort_like=False, preheat_lead=timedelta(minutes=60)
    )
    soon = forecast_room(
        replace(base, comfort_starts=T0 + timedelta(minutes=90)), T0, OUTDOOR, PARAMS
    )
    assert soon.preheat_goal == 21.0
    assert soon.candidate() is CoHeatReason.PREHEAT
    assert soon.need_in == timedelta(minutes=30)
    later = forecast_room(
        replace(base, comfort_starts=T0 + timedelta(hours=3)), T0, OUTDOOR, PARAMS
    )
    assert later.preheat_goal is None
    assert later.candidate() is None


def test_demanding_and_ineligible_rooms_are_no_candidates() -> None:
    """Rooms below their target heat themselves; excluded rooms stay out."""
    below = forecast_room(comfort_room("a", 20.5, demanding=True), T0, OUTDOOR, PARAMS)
    excluded = forecast_room(comfort_room("b", 21.0, eligible=False), T0, OUTDOOR, PARAMS)
    assert below.candidate() is None
    assert excluded.candidate() is None
    assert excluded.soon_goal is None


# -- co-heating ---------------------------------------------------------------------


def test_release_co_heats_soon_rooms_and_fills_the_sink() -> None:
    """Rooms needing heat soon always join, further rooms only while the sink is small."""
    network = HeatNetwork()
    rooms = [
        comfort_room("soon", 21.0, tau=15.0),  # cools fast: needs heat soon
        comfort_room("warm1", 21.4, tau=200.0),  # lasts the horizon, reserve left
        comfort_room("warm2", 21.5, tau=200.0),
    ]
    state = network.step(inputs(rooms, sink=0.0, sink_needed=2.0), PARAMS)
    assert state.phase is NetworkPhase.RELEASE
    assert network.active["soon"].reason is CoHeatReason.SOON
    # One sink room is enough to reach two open radiators.
    sink_rooms = {rid for rid, a in network.active.items() if a.reason is CoHeatReason.SINK}
    assert len(sink_rooms) == 1
    assert state.started == 2
    assert network.masked_rooms(T0) == frozenset(network.active)


def test_no_co_heating_without_release() -> None:
    network = HeatNetwork()
    state = network.step(inputs([comfort_room("a", 21.0)], release=False), PARAMS)
    assert state.phase is NetworkPhase.IDLE
    assert not network.active


def test_co_heat_ends_at_goal_minus_after_heating() -> None:
    """The radiators keep heating, so the valve closes a bit earlier."""
    network = HeatNetwork()
    room = comfort_room("a", 21.0, tau=15.0)
    network.step(inputs([room]), PARAMS)
    later = T0 + timedelta(minutes=30)
    state = network.step(
        inputs([replace(room, temperature=22.0 - DEFAULT_OVERSHOOT)], later), PARAMS
    )
    assert state.ended == (("a", CoHeatEnd.REACHED),)
    # The valve still reports open for a while and must not count as demand.
    assert "a" in network.masked_rooms(later + VALVE_SETTLE - timedelta(minutes=1))
    assert "a" not in network.masked_rooms(later + VALVE_SETTLE)


def test_residual_heat_is_used_while_the_pump_runs() -> None:
    """After the release the open rooms take the heat left in boiler and pipes."""
    network = HeatNetwork()
    room = comfort_room("a", 21.0, tau=15.0)
    network.step(inputs([room]), PARAMS)
    t1 = T0 + timedelta(minutes=5)
    state = network.step(inputs([room], t1, release=False, pump_on=True, flow=45.0), PARAMS)
    assert state.phase is NetworkPhase.RESIDUAL
    assert "a" in network.active
    t2 = t1 + timedelta(minutes=3)
    state = network.step(inputs([room], t2, release=False, pump_on=False, flow=45.0), PARAMS)
    assert state.phase is NetworkPhase.IDLE
    assert state.ended == (("a", CoHeatEnd.RELEASE_ENDED),)


def test_residual_heat_opens_rooms_and_stops_when_the_flow_is_cold() -> None:
    network = HeatNetwork()
    room = comfort_room("a", 21.0, tau=15.0)
    network.step(inputs([replace(room, eligible=False)]), PARAMS)
    t1 = T0 + timedelta(minutes=5)
    network.step(inputs([room], t1, release=False, flow=40.0), PARAMS)
    assert "a" in network.active  # opened for the residual heat
    t2 = t1 + timedelta(minutes=2)
    state = network.step(inputs([room], t2, release=False, flow=25.0), PARAMS)
    assert state.phase is NetworkPhase.IDLE
    assert not network.active


def test_residual_heat_is_limited_in_time() -> None:
    network = HeatNetwork()
    room = comfort_room("a", 21.0, tau=15.0)
    network.step(inputs([room]), PARAMS)
    t1 = T0 + timedelta(minutes=5)
    network.step(inputs([room], t1, release=False), PARAMS)
    state = network.step(inputs([room], t1 + PARAMS.residual_max, release=False), PARAMS)
    assert state.phase is NetworkPhase.IDLE


def test_preview_does_not_mask_or_count() -> None:
    """In observation mode or with the switch off the plan is only shown."""
    network = HeatNetwork()
    state = network.step(inputs([comfort_room("a", 21.0, tau=15.0)], blocked="switch_off"), PARAMS)
    assert state.active_rooms() == {"a"}
    assert not state.executing
    assert network.masked_rooms(T0) == frozenset()
    assert state.room("a").today == 0


def test_leaving_execution_stops_everything() -> None:
    network = HeatNetwork()
    room = comfort_room("a", 21.0, tau=15.0)
    network.step(inputs([room]), PARAMS)
    state = network.step(
        inputs([room], T0 + timedelta(minutes=1), blocked="room_control_off"), PARAMS
    )
    assert ("a", CoHeatEnd.STOPPED) in state.ended


def test_daily_limit_and_restart_gap() -> None:
    """At most max_per_day co-heats per room, and not right after the last one."""
    network = HeatNetwork()
    params = replace(PARAMS, max_per_day=1)
    room = comfort_room("a", 21.0, tau=15.0)
    network.step(inputs([room]), params)
    t1 = T0 + timedelta(minutes=10)
    network.step(inputs([replace(room, temperature=21.8)], t1), params)  # reached
    t2 = t1 + timedelta(hours=1)
    network.step(inputs([room], t2), params)
    assert "a" not in network.active  # the only co-heat of the day is used up


def test_duty_cycle_reserve_blocks_new_co_heats() -> None:
    network = HeatNetwork()
    state = network.step(
        inputs([comfort_room("a", 21.0, tau=15.0)], duty_cycle=70.0, duty_cycle_limit=80.0),
        PARAMS,
    )
    assert state.started == 0


def test_ineligible_room_stops() -> None:
    network = HeatNetwork()
    room = comfort_room("a", 21.0, tau=15.0)
    network.step(inputs([room]), PARAMS)
    state = network.step(inputs([replace(room, eligible=False)], T0 + timedelta(minutes=1)), PARAMS)
    assert state.ended == (("a", CoHeatEnd.INELIGIBLE),)


# -- bundling -----------------------------------------------------------------------


def test_bundling_waits_for_a_room_that_joins_soon() -> None:
    joining = comfort_room("b", 21.05, tau=5.0)  # needs heat within minutes
    forecasts = {
        "a": forecast_room(comfort_room("a", 20.0, demanding=True, valve=1.0), T0, OUTDOOR, PARAMS),
        "b": forecast_room(joining, T0, OUTDOOR, PARAMS),
    }
    assert bundle_room(forecasts, sink=1.0, sink_needed=4.0, co_heating=False, params=PARAMS) == "b"
    # With co-heating the joining room is opened right away instead.
    assert bundle_room(forecasts, sink=1.0, sink_needed=2.0, co_heating=True, params=PARAMS) is None
    # Enough heating surface already: no reason to wait.
    assert (
        bundle_room(forecasts, sink=4.0, sink_needed=4.0, co_heating=False, params=PARAMS) is None
    )
    off = replace(PARAMS, bundle_wait=timedelta(0))
    assert bundle_room(forecasts, sink=1.0, sink_needed=4.0, co_heating=False, params=off) is None


def test_boiler_holds_a_start_for_bundling() -> None:
    params = ControlParams(start_confirm=timedelta(0))
    boiler = BoilerController(params)

    def step(now, deficit=0.5):  # type: ignore[no-untyped-def]
        return boiler.step(
            BoilerInputs(
                now=now,
                demand=demand(0.6, max_deficit=deficit),
                outdoor_smoothed=5.0,
                flow_temperature=None,
                mode=OperatingMode.AUTO,
                automation_enabled=True,
                actuator_active=False,
                relay_on=None,
                bundle_wait=timedelta(minutes=30),
            )
        )

    decision = step(T0)
    assert decision.reason is Reason.BUNDLING
    assert decision.state is BoilerState.OFF
    assert step(T0 + timedelta(minutes=30)).reason is Reason.DEMAND_START


def test_urgent_demand_is_never_held() -> None:
    boiler = BoilerController(ControlParams(start_confirm=timedelta(0)))
    decision = boiler.step(
        BoilerInputs(
            now=T0,
            demand=demand(0.6, max_deficit=2.0),
            outdoor_smoothed=5.0,
            flow_temperature=None,
            mode=OperatingMode.AUTO,
            automation_enabled=True,
            actuator_active=False,
            relay_on=None,
            bundle_wait=timedelta(minutes=30),
        )
    )
    assert decision.reason is Reason.DEFICIT_START


# -- learning -----------------------------------------------------------------------


def _feed_runs(learner: SinkLearner, runs: list[tuple[float, float]]) -> None:
    """Feed burner runs (sink, minutes) within one release."""
    now = T0
    learner.update(now, burner=False, release=True, sink=0.0)
    for sink, minutes in runs:
        now += timedelta(minutes=1)
        learner.update(now, burner=True, release=True, sink=sink)
        now += timedelta(minutes=minutes)
        learner.update(now, burner=False, release=True, sink=sink)


def test_sink_learner_finds_the_needed_heating_surface() -> None:
    """1/run = a - b * sink: from real-like runs to the surface for 10 min runs."""
    a, b = 1.19, 0.23
    runs = [(s, 1.0 / (a - b * s)) for s in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 2.2, 3.8, 4.2)]
    learner = SinkLearner()
    _feed_runs(learner, [(3.0, 2.0), *runs])  # the first run of a release is skipped
    assert learner.samples == len(runs)
    fit = learner.fit()
    assert fit is not None
    assert fit[0] == pytest.approx(a, rel=0.02)
    assert fit[1] == pytest.approx(b, rel=0.02)
    needed, learned = learner.needed(timedelta(minutes=10), 4.0)
    assert learned
    assert needed == pytest.approx((a - 0.1) / b, rel=0.03)
    restored = SinkLearner.from_dict(learner.to_dict())
    assert restored.needed(timedelta(minutes=10), 4.0) == pytest.approx((needed, True))


def test_sink_learner_needs_spread() -> None:
    """Without different heating surfaces there is no relation to learn."""
    learner = SinkLearner()
    _feed_runs(learner, [(3.0, 2.0)] * 10)
    assert learner.needed(timedelta(minutes=10), 4.0) == (4.0, False)


def test_after_heating_is_learned_per_room() -> None:
    learner = RoomLearner()
    for i in range(3):
        start = T0 + timedelta(hours=2 * i)
        learner.start_overshoot(start, 21.7)
        for minutes, temp in ((10, 21.9), (30, 22.1), (50, 22.0), (61, 21.9)):
            learner.update(
                start + timedelta(minutes=minutes),
                temperature=temp,
                outdoor=5.0,
                valve=0.0,
                heating=False,
                window_open=False,
            )
    assert learner.overshoot_value() == pytest.approx(0.4)


def test_daily_key_figures() -> None:
    tracker = KpiTracker()
    now = T0
    tracker.update(now, burner=False, release=False, co_heats=0, enabled=True, energy=None)
    for run in (2, 20):
        now += timedelta(minutes=5)
        tracker.update(now, burner=True, release=True, co_heats=1, enabled=True, energy=None)
        now += timedelta(minutes=run)
        tracker.update(now, burner=False, release=False, co_heats=0, enabled=True, energy=None)
    assert tracker.today.burner_starts == 2
    assert tracker.today.short_runs == 1
    assert tracker.today.releases == 2
    assert tracker.today.co_heats == 2

    energy = EnergySnapshot(
        has_gas_source=True,
        kwh_per_m3=10.0,
        gas_flow=None,
        gas_volume=None,
        gas_energy=None,
        gas_energy_today=0.0,
        gas_energy_yesterday=12.5,
        burner_active=False,
        burner_power=None,
        burner_modulation=None,
        condensing=None,
        condensing_share_today=None,
        outdoor_mean_today=None,
        degree_days_yesterday=8.0,
        energy_per_degree_day_yesterday=None,
    )
    tracker.update(
        now + timedelta(days=1),
        burner=False,
        release=False,
        co_heats=0,
        enabled=True,
        energy=energy,
    )
    day = tracker.history[-1]
    assert day["burner_starts"] == 2
    assert day["gas_kwh"] == 12.5
    assert day["degree_days"] == 8.0
    assert day["network"] is True
    restored = KpiTracker.from_dict(tracker.to_dict())
    assert list(restored.history) == list(tracker.history)
