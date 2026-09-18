"""Heating curve suggestion from steady heating periods."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.heat_conductor.core.curve_advice import (
    MIN_BAND_SAMPLES,
    SAMPLE_INTERVAL,
    STEADY_AFTER,
    CurveAdvisor,
    CurveRoomSample,
)

from .helpers import T0

NAMES = {"bad": "Bad", "wohnen": "Wohnzimmer"}


def _heat(
    advisor: CurveAdvisor,
    *,
    start: datetime = T0,
    outdoor: float,
    setpoint: float,
    valve: float,
    temperature: float = 21.0,
    target: float = 21.0,
    samples: int = MIN_BAND_SAMPLES,
    heating: bool = True,
) -> datetime:
    """Steady heating long enough for the given number of samples."""
    moment = start
    end = start + STEADY_AFTER + SAMPLE_INTERVAL * (samples - 1)
    while moment <= end:
        advisor.update(
            moment,
            heating=heating,
            outdoor=outdoor,
            flow_setpoint=setpoint,
            flow=setpoint - 3.0,  # pipe sensor a bit below the boiler setpoint
            return_temperature=setpoint - 13.0,
            pump_on=True,
            rooms=[
                CurveRoomSample("bad", temperature, target, valve),
                CurveRoomSample("wohnen", 21.0, 21.0, 0.2),
            ],
        )
        moment += timedelta(minutes=1)
    # A pause ends the steady phase, so the next call starts a new one.
    advisor.update(
        moment,
        heating=False,
        outdoor=None,
        flow_setpoint=None,
        flow=None,
        return_temperature=None,
        pump_on=True,
        rooms=[],
    )
    return moment + timedelta(hours=1)


def _summary(advisor: CurveAdvisor, **kwargs):  # type: ignore[no-untyped-def]
    values = {"current": (-1.0, 45.0), "target_valve": 0.85, "curve_setting": 1.4}
    values.update(kwargs)
    return advisor.summary(NAMES, **values)


def test_no_suggestion_without_enough_steady_heating() -> None:
    """A short burner run is not evidence."""
    advisor = CurveAdvisor()
    _heat(advisor, outdoor=5.0, setpoint=40.0, valve=0.4, samples=5)
    summary = _summary(advisor)
    assert not summary["ready"]
    assert summary["bands"][0]["recommended"] is None
    assert summary["bands"][0]["samples"] == 5


def test_nothing_is_collected_without_heating() -> None:
    """Idle periods are ignored completely."""
    advisor = CurveAdvisor()
    _heat(advisor, outdoor=5.0, setpoint=40.0, valve=0.4, heating=False)
    assert advisor.bands == {}


def test_throttled_valves_suggest_a_lower_curve() -> None:
    """All rooms warm, bottleneck valve only 40 % open: the flow can go down."""
    advisor = CurveAdvisor()
    _heat(advisor, outdoor=5.0, setpoint=45.0, valve=0.4)
    band = _summary(advisor)["bands"][0]
    assert band["bottleneck"] == "Bad"
    assert band["bottleneck_share"] == 1.0
    assert band["change"] < -3.0
    assert band["recommended"] < 45.0


def test_well_balanced_curve_stays() -> None:
    """At the target valve opening nothing changes."""
    advisor = CurveAdvisor()
    _heat(advisor, outdoor=5.0, setpoint=45.0, valve=0.85)
    assert abs(_summary(advisor)["bands"][0]["change"]) < 0.5


def test_open_valve_and_cold_room_suggest_a_higher_curve() -> None:
    """Valve fully open and still 1.5 K too cold: the curve is too low."""
    advisor = CurveAdvisor()
    _heat(advisor, outdoor=0.0, setpoint=45.0, valve=1.0, temperature=19.5, target=21.0)
    band = _summary(advisor)["bands"][0]
    assert band["too_cold_share"] == 1.0
    assert band["change"] > 1.0


def test_curve_fit_and_curve_number_over_several_bands() -> None:
    """Two bands give a straight line and a curve number for the controller."""
    advisor = CurveAdvisor()
    moment = _heat(advisor, outdoor=10.0, setpoint=35.0, valve=0.4)
    _heat(advisor, start=moment, outdoor=0.0, setpoint=45.0, valve=0.4)
    summary = _summary(advisor)

    assert summary["ready"]
    assert summary["suggested"] is not None
    assert summary["suggested"]["flow_at_0"] < 45.0
    assert summary["shift"] < 0
    assert summary["suggested_setting"] is not None
    assert summary["suggested_setting"] < 1.4


def test_no_curve_number_without_the_current_setting() -> None:
    """Without the set curve only flow temperatures are suggested."""
    advisor = CurveAdvisor()
    _heat(advisor, outdoor=5.0, setpoint=45.0, valve=0.4)
    summary = _summary(advisor, curve_setting=0.0)
    assert summary["ready"]
    assert summary["suggested_setting"] is None


def test_evidence_survives_a_restart() -> None:
    """Collected bands are persisted."""
    advisor = CurveAdvisor()
    _heat(advisor, outdoor=5.0, setpoint=45.0, valve=0.4)
    restored = CurveAdvisor.from_dict(advisor.to_dict())
    assert _summary(restored)["bands"] == _summary(advisor)["bands"]
