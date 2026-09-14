"""Tests for gas energy, power, condensing share and degree days."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.heat_conductor.core.energy import (
    EnergyParams,
    EnergySnapshot,
    EnergyTracker,
)
from custom_components.heat_conductor.core.models import Reading

AGE = timedelta(hours=4)
PARAMS = EnergyParams(calorific_value=11.5, z_factor=0.96, burner_max_power=21.0)
KWH_PER_M3 = 11.5 * 0.96
T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def step(
    tracker: EnergyTracker,
    now: datetime,
    *,
    meter: float | None = None,
    flow: float | None = None,
    use_meter: bool = False,
    use_flow: bool = False,
    burner_on: bool | None = None,
    return_temperature: float | None = None,
    outdoor: float | None = None,
) -> EnergySnapshot:
    return tracker.update(
        now,
        meter=Reading(meter, now) if use_meter else None,
        flow=Reading(flow, now) if use_flow else None,
        burner_on=burner_on,
        burner_flow_threshold=0.2,
        return_temperature=return_temperature,
        outdoor=outdoor,
        max_age=AGE,
    )


def test_meter_total_is_converted_to_energy() -> None:
    tracker = EnergyTracker(PARAMS)
    step(tracker, at(0), meter=1000.00, use_meter=True)
    step(tracker, at(1), meter=1000.25, use_meter=True)
    snap = step(tracker, at(2), meter=1000.50, use_meter=True)
    assert snap.gas_volume == pytest.approx(0.5)
    assert snap.gas_energy == pytest.approx(0.5 * KWH_PER_M3)
    assert snap.gas_energy_today == pytest.approx(0.5 * KWH_PER_M3)


def test_meter_reset_and_replacement_are_not_counted() -> None:
    tracker = EnergyTracker(PARAMS)
    step(tracker, at(0), meter=1000.0, use_meter=True)
    step(tracker, at(1), meter=5.0, use_meter=True)  # reset
    step(tracker, at(2), meter=5.5, use_meter=True)
    snap = step(tracker, at(3), meter=900.0, use_meter=True)  # implausible jump
    assert snap.gas_volume == pytest.approx(0.5)


def test_meter_without_updates_still_counts_after_long_gap() -> None:
    tracker = EnergyTracker(PARAMS)
    step(tracker, at(0), meter=10.0, use_meter=True)
    snap = step(tracker, at(180), meter=12.0, use_meter=True)
    assert snap.gas_volume == pytest.approx(2.0)


def test_flow_is_derived_from_meter_window() -> None:
    tracker = EnergyTracker(PARAMS)
    step(tracker, at(0), meter=100.0, use_meter=True)
    assert step(tracker, at(1), meter=100.02, use_meter=True).gas_flow is None
    snap = step(tracker, at(3), meter=100.06, use_meter=True)
    assert snap.gas_flow == pytest.approx(1.2)
    assert snap.burner_active is True


def test_flow_is_integrated_when_no_meter() -> None:
    tracker = EnergyTracker(PARAMS)
    snap = None
    for minute in range(0, 31, 5):
        snap = step(tracker, at(minute), flow=1.2, use_flow=True)
    assert snap is not None
    assert snap.gas_volume == pytest.approx(0.6)
    assert snap.burner_power == pytest.approx(1.2 * KWH_PER_M3)


def test_long_gaps_are_not_integrated() -> None:
    tracker = EnergyTracker(PARAMS)
    step(tracker, at(0), flow=1.2, use_flow=True)
    snap = step(tracker, at(30), flow=1.2, use_flow=True)
    assert snap.gas_volume == 0.0


def test_modulation_relates_net_power_to_rated_load() -> None:
    tracker = EnergyTracker(PARAMS)
    snap = step(tracker, at(0), flow=1.0, use_flow=True)
    expected = 1.0 * KWH_PER_M3 / 1.11 / 21.0 * 100
    assert snap.burner_modulation == pytest.approx(expected)


def test_no_modulation_without_rated_load() -> None:
    tracker = EnergyTracker(EnergyParams())
    assert step(tracker, at(0), flow=1.0, use_flow=True).burner_modulation is None


def test_condensing_share_of_burner_runtime() -> None:
    tracker = EnergyTracker(PARAMS)
    step(tracker, at(0), burner_on=True, return_temperature=45.0)
    step(tracker, at(5), burner_on=True, return_temperature=45.0)
    step(tracker, at(10), burner_on=True, return_temperature=60.0)
    step(tracker, at(15), burner_on=False, return_temperature=60.0)
    snap = step(tracker, at(20), burner_on=False, return_temperature=40.0)
    assert snap.condensing is False
    assert snap.condensing_share_today == pytest.approx(200 / 3)


def test_degree_days_and_energy_per_degree_day() -> None:
    tracker = EnergyTracker(PARAMS)
    day_start = datetime(2026, 11, 2, 0, 0, tzinfo=UTC)
    meter = 0.0
    now = day_start
    while now < day_start + timedelta(days=1):
        step(tracker, now, meter=meter, use_meter=True, outdoor=5.0)
        now += timedelta(minutes=5)
        meter += 0.01
    snap = step(tracker, now, meter=meter, use_meter=True, outdoor=5.0)

    assert snap.degree_days_yesterday == pytest.approx(15.0)
    assert snap.gas_energy_yesterday == pytest.approx((meter - 0.01) * KWH_PER_M3)
    assert snap.energy_per_degree_day_yesterday == pytest.approx(snap.gas_energy_yesterday / 15.0)
    assert snap.gas_energy_today == pytest.approx(0.01 * KWH_PER_M3)


def test_warm_day_has_zero_degree_days_and_partial_day_none() -> None:
    tracker = EnergyTracker(PARAMS)
    start = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    now = start
    while now < start + timedelta(days=1):
        step(tracker, now, outdoor=18.0)
        now += timedelta(minutes=5)
    assert step(tracker, now, outdoor=18.0).degree_days_yesterday == 0.0

    partial = EnergyTracker(PARAMS)
    step(partial, datetime(2026, 6, 1, 22, 0, tzinfo=UTC), outdoor=5.0)
    step(partial, datetime(2026, 6, 1, 22, 5, tzinfo=UTC), outdoor=5.0)
    snap = step(partial, datetime(2026, 6, 2, 0, 1, tzinfo=UTC), outdoor=5.0)
    assert snap.degree_days_yesterday is None


def test_without_gas_source_energy_values_are_none() -> None:
    tracker = EnergyTracker(PARAMS)
    snap = step(tracker, at(0), burner_on=True, return_temperature=40.0)
    assert snap.gas_energy is None
    assert snap.burner_power is None
    assert snap.condensing is True


def test_persistence_roundtrip() -> None:
    tracker = EnergyTracker(PARAMS)
    step(tracker, at(0), meter=50.0, use_meter=True)
    step(tracker, at(1), meter=51.0, use_meter=True)

    restored = EnergyTracker(PARAMS)
    restored.restore(tracker.to_dict())
    assert restored.energy_total == pytest.approx(KWH_PER_M3)
    # Consumption while Home Assistant was down is still counted.
    snap = step(restored, at(60), meter=52.0, use_meter=True)
    assert snap.gas_volume == pytest.approx(2.0)
