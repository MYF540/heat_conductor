"""Gas energy, burner power and modulation, condensing share and degree days."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .models import Reading

# Ratio of gross (Hs) to net (Hi) calorific value of natural gas. Type plates
# state the burner load on Hi basis, gas bills on Hs basis.
HS_HI_RATIO = 1.11

# Heating degree days according to VDI 3807: indoor 20 °C, heating limit 15 °C.
DEGREE_DAY_INDOOR = 20.0
DEGREE_DAY_LIMIT = 15.0

# Flow is only integrated across short gaps; longer gaps are lost rather than guessed.
MAX_INTEGRATION_GAP = timedelta(minutes=5)
# Flow derived from a meter total is averaged over this window.
METER_FLOW_WINDOW = timedelta(minutes=5)
MIN_METER_FLOW_WINDOW = timedelta(minutes=2)
# Meter jumps larger than this in one step are treated as a meter replacement.
MAX_METER_STEP = 50.0
# A day needs at least this share of outdoor coverage for degree days.
MIN_DAY_COVERAGE = 0.5
SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True, slots=True)
class EnergyParams:
    """Gas and boiler constants, user configurable."""

    calorific_value: float = 11.2  # Brennwert Hs in kWh/m³
    z_factor: float = 0.95  # Zustandszahl
    burner_max_power: float = 0.0  # kW (Hi), 0 = unknown
    condensing_return_limit: float = 55.0  # °C

    @property
    def kwh_per_m3(self) -> float:
        """Energy per operating cubic metre."""
        return self.calorific_value * self.z_factor


@dataclass(frozen=True, slots=True)
class EnergySnapshot:
    """Energy related results of one evaluation."""

    has_gas_source: bool
    kwh_per_m3: float
    gas_flow: float | None  # m³/h
    gas_volume: float | None  # m³ since tracking started
    gas_energy: float | None  # kWh since tracking started
    gas_energy_today: float | None
    gas_energy_yesterday: float | None
    burner_active: bool | None
    burner_power: float | None  # kW, gross (Hs)
    burner_modulation: float | None  # % of rated load
    condensing: bool | None
    condensing_share_today: float | None  # % of burner runtime
    outdoor_mean_today: float | None
    degree_days_yesterday: float | None
    energy_per_degree_day_yesterday: float | None  # kWh/Kd


class EnergyTracker:
    """Accumulates gas consumption and daily energy indicators."""

    def __init__(self, params: EnergyParams) -> None:
        self.params = params
        self.volume_total = 0.0
        self.energy_total = 0.0
        self.day: date | None = None
        self.energy_today = 0.0
        self.energy_yesterday: float | None = None
        self.burner_seconds_today = 0.0
        self.condensing_seconds_today = 0.0
        self.outdoor_sum_today = 0.0
        self.outdoor_seconds_today = 0.0
        self.degree_days_yesterday: float | None = None
        self.energy_per_degree_day_yesterday: float | None = None
        self.last_meter: float | None = None

        self._meter_samples: deque[tuple[datetime, float]] = deque()
        self._last_update: datetime | None = None
        self._last_flow: float | None = None
        self._last_burner: bool | None = None
        self._last_condensing: bool | None = None
        self._last_outdoor: float | None = None

    # -- main update ---------------------------------------------------------

    def update(
        self,
        now: datetime,
        *,
        meter: Reading | None,
        flow: Reading | None,
        burner_on: bool | None,
        burner_flow_threshold: float,
        return_temperature: float | None,
        outdoor: float | None,
        max_age: timedelta,
    ) -> EnergySnapshot:
        """Feed current inputs. now must be timezone-aware local time."""
        p = self.params
        self._roll_day(now)

        dt = (now - self._last_update).total_seconds() if self._last_update else 0.0
        gap_ok = 0 < dt <= MAX_INTEGRATION_GAP.total_seconds()

        # Time-weighted daily values use the state of the previous interval.
        if gap_ok:
            if self._last_burner:
                self.burner_seconds_today += dt
                if self._last_condensing:
                    self.condensing_seconds_today += dt
            if self._last_outdoor is not None:
                self.outdoor_sum_today += self._last_outdoor * dt
                self.outdoor_seconds_today += dt

        has_gas_source = meter is not None or flow is not None
        volume_delta = 0.0
        current_flow: float | None = None

        if meter is not None:
            volume_delta = self._meter_delta(meter)
            if meter.value is not None:
                self._meter_samples.append((now, meter.value))
            while self._meter_samples and now - self._meter_samples[0][0] > METER_FLOW_WINDOW:
                self._meter_samples.popleft()
            current_flow = self._meter_flow()

        if flow is not None:
            flow_value = flow.valid_value(now, max_age)
            if meter is None and gap_ok and self._last_flow is not None:
                volume_delta = max(self._last_flow, 0.0) * dt / 3600.0
            self._last_flow = flow_value
            # A dedicated flow sensor reacts faster than a meter-derived flow.
            if flow_value is not None:
                current_flow = max(flow_value, 0.0)

        if volume_delta > 0:
            self.volume_total += volume_delta
            energy = volume_delta * p.kwh_per_m3
            self.energy_total += energy
            self.energy_today += energy

        burner = burner_on
        if burner is None and current_flow is not None:
            burner = current_flow >= burner_flow_threshold

        power = current_flow * p.kwh_per_m3 if current_flow is not None else None
        modulation = None
        if power is not None and p.burner_max_power > 0:
            modulation = min(max(power / HS_HI_RATIO / p.burner_max_power * 100, 0.0), 100.0)

        condensing = None
        if burner is not None and return_temperature is not None:
            condensing = burner and return_temperature < p.condensing_return_limit

        self._last_update = now
        self._last_burner = burner
        self._last_condensing = condensing
        self._last_outdoor = outdoor

        return EnergySnapshot(
            has_gas_source=has_gas_source,
            kwh_per_m3=p.kwh_per_m3,
            gas_flow=current_flow,
            gas_volume=self.volume_total if has_gas_source else None,
            gas_energy=self.energy_total if has_gas_source else None,
            gas_energy_today=self.energy_today if has_gas_source else None,
            gas_energy_yesterday=self.energy_yesterday if has_gas_source else None,
            burner_active=burner,
            burner_power=power,
            burner_modulation=modulation,
            condensing=condensing,
            condensing_share_today=(
                self.condensing_seconds_today / self.burner_seconds_today * 100
                if self.burner_seconds_today > 0
                else None
            ),
            outdoor_mean_today=(
                self.outdoor_sum_today / self.outdoor_seconds_today
                if self.outdoor_seconds_today > 0
                else None
            ),
            degree_days_yesterday=self.degree_days_yesterday,
            energy_per_degree_day_yesterday=(
                self.energy_per_degree_day_yesterday if has_gas_source else None
            ),
        )

    # -- helpers -------------------------------------------------------------

    def _meter_delta(self, meter: Reading) -> float:
        """Consumption since the last meter reading (no staleness: meters idle for hours)."""
        value = meter.value
        if value is None:
            return 0.0
        previous = self.last_meter
        self.last_meter = value
        if previous is None:
            return 0.0
        delta = value - previous
        if delta < 0 or delta > MAX_METER_STEP:
            # Meter reset or replacement: rebase without counting.
            self._meter_samples.clear()
            return 0.0
        return delta

    def _meter_flow(self) -> float | None:
        if len(self._meter_samples) < 2:
            return None
        (t0, v0), (t1, v1) = self._meter_samples[0], self._meter_samples[-1]
        span = t1 - t0
        if span < MIN_METER_FLOW_WINDOW or v1 < v0:
            return None
        return (v1 - v0) / (span.total_seconds() / 3600.0)

    def _roll_day(self, now: datetime) -> None:
        today = now.date()
        if self.day == today:
            return
        if self.day is not None:
            self.energy_yesterday = self.energy_today
            coverage = self.outdoor_seconds_today / SECONDS_PER_DAY
            if coverage >= MIN_DAY_COVERAGE:
                mean = self.outdoor_sum_today / self.outdoor_seconds_today
                self.degree_days_yesterday = (
                    DEGREE_DAY_INDOOR - mean if mean < DEGREE_DAY_LIMIT else 0.0
                )
            else:
                self.degree_days_yesterday = None
            self.energy_per_degree_day_yesterday = (
                self.energy_yesterday / self.degree_days_yesterday
                if self.degree_days_yesterday
                else None
            )
        self.day = today
        self.energy_today = 0.0
        self.burner_seconds_today = 0.0
        self.condensing_seconds_today = 0.0
        self.outdoor_sum_today = 0.0
        self.outdoor_seconds_today = 0.0

    # -- persistence -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize state that must survive a restart."""
        return {
            "volume_total": self.volume_total,
            "energy_total": self.energy_total,
            "day": self.day.isoformat() if self.day else None,
            "energy_today": self.energy_today,
            "energy_yesterday": self.energy_yesterday,
            "burner_seconds_today": self.burner_seconds_today,
            "condensing_seconds_today": self.condensing_seconds_today,
            "outdoor_sum_today": self.outdoor_sum_today,
            "outdoor_seconds_today": self.outdoor_seconds_today,
            "degree_days_yesterday": self.degree_days_yesterday,
            "energy_per_degree_day_yesterday": self.energy_per_degree_day_yesterday,
            "last_meter": self.last_meter,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore state saved by to_dict."""

        def number(key: str, default: float | None = 0.0) -> float | None:
            value = data.get(key, default)
            return float(value) if isinstance(value, (int, float)) else default

        self.volume_total = number("volume_total") or 0.0
        self.energy_total = number("energy_total") or 0.0
        try:
            self.day = date.fromisoformat(data["day"]) if data.get("day") else None
        except TypeError, ValueError:
            self.day = None
        self.energy_today = number("energy_today") or 0.0
        self.energy_yesterday = number("energy_yesterday", None)
        self.burner_seconds_today = number("burner_seconds_today") or 0.0
        self.condensing_seconds_today = number("condensing_seconds_today") or 0.0
        self.outdoor_sum_today = number("outdoor_sum_today") or 0.0
        self.outdoor_seconds_today = number("outdoor_seconds_today") or 0.0
        self.degree_days_yesterday = number("degree_days_yesterday", None)
        self.energy_per_degree_day_yesterday = number("energy_per_degree_day_yesterday", None)
        self.last_meter = number("last_meter", None)
