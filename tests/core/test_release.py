"""The relay releases the boiler; the boiler decides about the burner itself."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.heat_conductor.core.boiler_fsm import BoilerController, BoilerInputs
from custom_components.heat_conductor.core.demand import DemandSummary
from custom_components.heat_conductor.core.diagnosis import DiagnosisTracker
from custom_components.heat_conductor.core.models import (
    BoilerState,
    ControlParams,
    OperatingMode,
    Reason,
)

from .helpers import T0, demand

PARAMS = ControlParams()
LOW = demand(0.05, max_deficit=0.2)  # below the stop threshold
MARGINAL = demand(0.2, max_deficit=0.3)  # between stop and start threshold
HIGH = demand(0.5, max_deficit=0.5)  # above the start threshold


def at(m: float) -> datetime:
    return T0 + timedelta(minutes=m)


def step(
    fsm: BoilerController,
    m: float,
    summary: DemandSummary,
    *,
    burner: bool | None,
    relay: bool = True,
    actuator: bool = True,
):
    return fsm.step(
        BoilerInputs(
            now=at(m),
            demand=summary,
            outdoor_smoothed=5.0,
            flow_temperature=None,
            mode=OperatingMode.AUTO,
            automation_enabled=True,
            actuator_active=actuator,
            relay_on=relay if actuator else None,
            burner_on=burner,
        )
    )


def released(params: ControlParams = PARAMS) -> BoilerController:
    """A controller that took over the relay and released the boiler at minute 1."""
    fsm = BoilerController(params)
    step(fsm, 0, demand(0.0), burner=False, relay=False)
    started = step(fsm, 1, demand(1.0, max_deficit=2.0), burner=False, relay=False)
    assert started.request_heat
    fsm.note_command(True)
    return fsm


def test_running_burner_is_not_cut() -> None:
    """Demand gone while the burner fires: the burner cycle is finished first."""
    fsm = released()
    step(fsm, 2, HIGH, burner=True)
    finishing = step(fsm, 25, LOW, burner=True)
    assert finishing.reason is Reason.BURNER_FINISHING
    assert finishing.request_heat
    assert finishing.state is BoilerState.HEATING

    done = step(fsm, 28, LOW, burner=False)
    assert done.reason is Reason.DEMAND_SATISFIED
    assert not done.request_heat


def test_finishing_has_a_timeout() -> None:
    """A burner that keeps firing does not hold the release forever."""
    fsm = released()
    step(fsm, 2, HIGH, burner=True)
    step(fsm, 25, LOW, burner=True)
    still = step(fsm, 54, LOW, burner=True)
    assert still.reason is Reason.BURNER_FINISHING
    stopped = step(fsm, 56, LOW, burner=True)
    assert stopped.reason is Reason.DEMAND_SATISFIED
    assert not stopped.request_heat


def test_release_ends_after_the_burner_cycle_when_demand_is_marginal() -> None:
    """The boiler would fire again after its lock time for a demand below the start."""
    fsm = released()
    step(fsm, 2, HIGH, burner=True)
    during = step(fsm, 15, MARGINAL, burner=True)
    assert during.reason is Reason.DEMAND_CONTINUES
    held = step(fsm, 18, MARGINAL, burner=False)
    assert held.reason is Reason.MIN_RUNTIME  # the minimum release time still applies
    done = step(fsm, 22, MARGINAL, burner=False)
    assert done.reason is Reason.BURNER_CYCLE_DONE
    assert not done.request_heat


def test_release_continues_after_the_burner_cycle_when_demand_is_high() -> None:
    """With real demand the boiler may fire again within the release."""
    fsm = released()
    step(fsm, 2, HIGH, burner=True)
    step(fsm, 15, HIGH, burner=False)
    later = step(fsm, 30, HIGH, burner=False)
    assert later.reason is Reason.DEMAND_CONTINUES
    assert later.request_heat


def test_no_cycle_end_before_the_burner_has_fired() -> None:
    """Right after the release the boiler may still be locked: that is no cycle end."""
    fsm = released()
    waiting = step(fsm, 25, MARGINAL, burner=False)
    assert waiting.reason is Reason.DEMAND_CONTINUES


def test_burner_starts_are_counted_per_release() -> None:
    """Every ignition within the release counts."""
    fsm = released()
    step(fsm, 2, HIGH, burner=True)
    step(fsm, 10, HIGH, burner=False)
    decision = step(fsm, 30, HIGH, burner=True)
    assert decision.release_burner_starts == 2


def test_observation_mode_ignores_the_burner() -> None:
    """The virtual boiler cannot know the real burner, so the rules stay off."""
    fsm = BoilerController(PARAMS)
    step(fsm, 0, demand(1.0, max_deficit=2.0), burner=None, actuator=False)
    step(fsm, 5, demand(1.0, max_deficit=2.0), burner=True, actuator=False)
    stopped = step(fsm, 25, LOW, burner=True, actuator=False)
    assert stopped.reason is Reason.DEMAND_SATISFIED
    assert not stopped.request_heat


def test_rules_can_be_switched_off() -> None:
    """Both rules are optional."""
    params = ControlParams(finish_burner_cycle=False, end_after_burner_cycle=False)
    fsm = released(params)
    step(fsm, 2, HIGH, burner=True)
    assert step(fsm, 25, LOW, burner=True).reason is Reason.DEMAND_SATISFIED

    fsm = released(params)
    step(fsm, 2, HIGH, burner=True)
    step(fsm, 15, MARGINAL, burner=False)
    assert step(fsm, 25, MARGINAL, burner=False).reason is Reason.DEMAND_CONTINUES


def test_hard_stops_do_not_wait_for_the_burner() -> None:
    """Mode off switches off at once, even with a running burner."""
    fsm = released()
    step(fsm, 2, HIGH, burner=True)
    off = fsm.step(
        BoilerInputs(
            now=at(25),
            demand=HIGH,
            outdoor_smoothed=5.0,
            flow_temperature=None,
            mode=OperatingMode.OFF,
            automation_enabled=True,
            actuator_active=True,
            relay_on=True,
            burner_on=True,
        )
    )
    assert off.reason is Reason.MODE_OFF
    assert not off.request_heat


# -- diagnosis: released, but the boiler does not heat ----------------------


def _diag(tracker: DiagnosisTracker, m: float, **kwargs):  # type: ignore[no-untyped-def]
    values = {
        "relay_on": True,
        "relay_feedback": None,
        "request_heat": True,
        "burner_on": False,
        "burner_lock": 0.0,
        "winter_mode": True,
        "pump_on": True,
        "boiler_flow": 25.0,
        "flow_setpoint": 40.0,
    }
    values.update(kwargs)
    return tracker.update(at(m), **values)


def test_release_without_burner_is_reported() -> None:
    """Thirty minutes released, burner never lit, water far below target."""
    tracker = DiagnosisTracker()
    assert not _diag(tracker, 0).not_heating
    assert not _diag(tracker, 29).not_heating
    assert _diag(tracker, 31).not_heating


def test_no_alarm_while_the_boiler_is_locked_or_warm() -> None:
    """A running lock time or water near the setpoint are no fault."""
    tracker = DiagnosisTracker()
    _diag(tracker, 0)
    assert not _diag(tracker, 31, burner_lock=5.0).not_heating
    assert not _diag(tracker, 32, boiler_flow=38.0).not_heating


def test_a_burner_start_clears_the_suspicion() -> None:
    """Once the burner lit in this release everything is fine."""
    tracker = DiagnosisTracker()
    _diag(tracker, 0)
    _diag(tracker, 5, burner_on=True)
    assert not _diag(tracker, 40).not_heating


def test_no_alarm_without_a_burner_signal() -> None:
    """Without burner information nothing is claimed."""
    tracker = DiagnosisTracker()
    _diag(tracker, 0, burner_on=None)
    assert not _diag(tracker, 60, burner_on=None).not_heating
