"""Plausibility checks with feedback from the boiler electronics.

Optional inputs, for example from the Vaillant X6 diagnostic interface:

- relay feedback: the room thermostat input as seen by the boiler (terminals 3-4-5)
- burner lock: remaining anti-cycling time of the boiler
- winter mode: heating enabled at the boiler
- pump: the boiler's heating pump
- boiler flow/return: the boiler's own sensors, to cross-check the pipe sensors

The pipe sensors sit behind the circulation pump, so a constant offset to the boiler
sensor is normal. It is learned while the pump runs; only a change of that offset is
suspicious (a loose clamp sensor, a failing probe).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

# The boiler and the diagnostic interface need some time to report a switched relay.
RELAY_FEEDBACK_DELAY = timedelta(minutes=2)
# Learning the normal offset between pipe and boiler sensor.
OFFSET_SAMPLE_INTERVAL = timedelta(minutes=5)
OFFSET_SMOOTHING = timedelta(hours=24)
OFFSET_MIN_SAMPLES = 12  # one hour of circulation
SUSPECT_DEVIATION = 5.0  # K away from the learned offset
SUSPECT_DELAY = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class BoilerDiagnosis:
    """What the boiler reports and which contradictions were found."""

    relay_feedback: bool | None = None
    relay_mismatch: bool = False
    burner_lock_minutes: float | None = None
    burner_locked: bool = False
    winter_mode: bool | None = None
    summer_mode_conflict: bool = False
    pump_on: bool | None = None
    boiler_flow: float | None = None
    boiler_return: float | None = None
    flow_deviation: float | None = None  # pipe flow minus boiler flow
    flow_deviation_typical: float | None = None
    return_deviation: float | None = None  # pipe return minus boiler return
    boiler_spread: float | None = None  # boiler flow minus return (boiler or pipe)
    flow_sensor_suspect: bool = False


class DiagnosisTracker:
    """Keeps timers and the learned offset between pipe and boiler sensor."""

    def __init__(self) -> None:
        self.mismatch_since: datetime | None = None
        self.flow_offset: float | None = None
        self.flow_offset_samples: int = 0
        self._offset_at: datetime | None = None
        self._suspect_since: datetime | None = None

    def update(
        self,
        now: datetime,
        *,
        relay_on: bool | None,
        relay_feedback: bool | None,
        request_heat: bool,
        burner_on: bool | None,
        burner_lock: float | None,
        winter_mode: bool | None,
        pump_on: bool | None,
        pipe_flow: float | None = None,
        pipe_return: float | None = None,
        boiler_flow: float | None = None,
        boiler_return: float | None = None,
    ) -> BoilerDiagnosis:
        """Evaluate the current feedback."""
        disagree = (
            relay_on is not None and relay_feedback is not None and relay_on != relay_feedback
        )
        if not disagree:
            self.mismatch_since = None
        elif self.mismatch_since is None:
            self.mismatch_since = now
        mismatch = (
            self.mismatch_since is not None and now - self.mismatch_since >= RELAY_FEEDBACK_DELAY
        )
        flow_deviation = _diff(pipe_flow, boiler_flow)
        circulating = pump_on is not False
        suspect = self._check_flow_offset(now, flow_deviation, circulating)
        return BoilerDiagnosis(
            relay_feedback=relay_feedback,
            relay_mismatch=mismatch,
            burner_lock_minutes=burner_lock,
            burner_locked=bool(burner_lock and burner_lock > 0 and burner_on is not True),
            winter_mode=winter_mode,
            # HeatConductor wants heat, but the boiler has heating switched off.
            summer_mode_conflict=request_heat and winter_mode is False,
            pump_on=pump_on,
            boiler_flow=boiler_flow,
            boiler_return=boiler_return,
            flow_deviation=flow_deviation,
            flow_deviation_typical=self.flow_offset
            if self.flow_offset_samples >= OFFSET_MIN_SAMPLES
            else None,
            return_deviation=_diff(pipe_return, boiler_return),
            boiler_spread=_diff(
                boiler_flow, boiler_return if boiler_return is not None else pipe_return
            )
            if circulating
            else None,
            flow_sensor_suspect=suspect,
        )

    def _check_flow_offset(self, now: datetime, deviation: float | None, circulating: bool) -> bool:
        """Learn the usual offset and report a lasting departure from it."""
        if deviation is None or not circulating:
            self._suspect_since = None
            return False
        learned = self.flow_offset_samples >= OFFSET_MIN_SAMPLES and self.flow_offset is not None
        off = learned and abs(deviation - self.flow_offset) > SUSPECT_DEVIATION
        if off:
            if self._suspect_since is None:
                self._suspect_since = now
        else:
            self._suspect_since = None
            # Only plausible values refine the offset, a failing sensor must not teach it.
            if self._offset_at is None or now - self._offset_at >= OFFSET_SAMPLE_INTERVAL:
                self._learn_offset(now, deviation)
        return self._suspect_since is not None and now - self._suspect_since >= SUSPECT_DELAY

    def _learn_offset(self, now: datetime, deviation: float) -> None:
        if self.flow_offset is None or self._offset_at is None:
            self.flow_offset = deviation
        else:
            dt = (now - self._offset_at).total_seconds()
            alpha = max(
                1.0 / (self.flow_offset_samples + 1),
                1.0 - math.exp(-dt / OFFSET_SMOOTHING.total_seconds()),
            )
            self.flow_offset += alpha * (deviation - self.flow_offset)
        self.flow_offset_samples += 1
        self._offset_at = now

    def to_dict(self) -> dict[str, float | int | None]:
        """Serialize the learned offset."""
        return {"flow_offset": self.flow_offset, "flow_offset_samples": self.flow_offset_samples}

    def restore(self, data: dict | None) -> None:
        """Restore the learned offset."""
        if not data:
            return
        offset = data.get("flow_offset")
        samples = data.get("flow_offset_samples")
        self.flow_offset = float(offset) if isinstance(offset, (int, float)) else None
        self.flow_offset_samples = int(samples) if isinstance(samples, int) else 0


def _diff(a: float | None, b: float | None) -> float | None:
    return a - b if a is not None and b is not None else None
