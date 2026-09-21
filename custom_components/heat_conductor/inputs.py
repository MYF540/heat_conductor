"""Read Home Assistant states into engine inputs.

Used for live evaluation and for replaying recorded history (simulation). In
replay mode every reading counts as reported "now", because the recorder does
not keep last_reported.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.components.climate import ATTR_CURRENT_TEMPERATURE, HVACMode
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_HOME,
    STATE_IDLE,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_ON,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import State
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    CONF_BOILER_FLOW_TEMPERATURE,
    CONF_BOILER_RETURN_TEMPERATURE,
    CONF_BOILER_SWITCH,
    CONF_BOILER_WINTER_MODE,
    CONF_BURNER_LOCK,
    CONF_BURNER_SENSOR,
    CONF_CLIMATES,
    CONF_COMPENSATION,
    CONF_CURVE_REFERENCE,
    CONF_DUTY_CYCLE,
    CONF_FLOW_SETPOINT,
    CONF_FLOW_TEMPERATURE,
    CONF_GAS_FLOW,
    CONF_GAS_METER,
    CONF_OUTDOOR_SENSORS,
    CONF_PRESENCE,
    CONF_PUMP_SENSOR,
    CONF_RELAY_FEEDBACK,
    CONF_RETURN_TEMPERATURE,
    CONF_ROOM_KIND,
    CONF_ROOM_TEMPERATURE,
    CONF_SCHEDULE,
    CONF_SLEEP_SENSOR,
    CONF_SOLAR_GAIN,
    CONF_SOLAR_POWER,
    CONF_USAGE_ENTITIES,
    CONF_VALVES,
    CONF_WATCHDOG_URL,
    CONF_WEATHER,
    CONF_WEIGHT,
    CONF_WINDOWS,
    SUBENTRY_ROOM,
)
from .core.demand import RoomInput
from .core.engine import EngineSnapshot, RoomControlInput
from .core.models import MISSING, OperatingMode, Reading, RoomKind
from .core.setpoint import TrvInput

type StateGetter = Callable[[str], State | None]

_VOLUME_FACTORS: dict[str | None, float] = {
    UnitOfVolume.CUBIC_METERS: 1.0,
    UnitOfVolume.LITERS: 0.001,
}
_FLOW_FACTORS: dict[str | None, float] = {
    UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR: 1.0,
    UnitOfVolumeFlowRate.LITERS_PER_HOUR: 0.001,
    UnitOfVolumeFlowRate.LITERS_PER_MINUTE: 0.06,
}
# A media player that is merely idle or on standby does not make a room "in use".
_IDLE_STATES: frozenset[str] = frozenset(
    {STATE_OFF, STATE_NOT_HOME, STATE_IDLE, STATE_STANDBY, STATE_UNAVAILABLE, STATE_UNKNOWN}
)
_POWER_FACTORS: dict[str | None, float] = {
    UnitOfPower.WATT: 0.001,
    UnitOfPower.KILO_WATT: 1.0,
}


@dataclass(frozen=True, slots=True)
class RoomConfig:
    """Entity configuration of one room (from a config subentry)."""

    room_id: str
    name: str
    kind: RoomKind
    weight: float
    climates: tuple[str, ...]
    valves: tuple[str, ...]
    room_temperature: str | None
    windows: tuple[str, ...] = field(default=())
    schedule: str | None = None
    compensation: bool = True
    solar_gain: bool = False
    usage_entities: tuple[str, ...] = field(default=())
    curve_reference: bool = True

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> RoomConfig:
        """Build from a room subentry."""
        data = subentry.data
        return cls(
            room_id=subentry.subentry_id,
            name=subentry.title,
            kind=RoomKind(data.get(CONF_ROOM_KIND, RoomKind.REGULATED)),
            weight=float(data.get(CONF_WEIGHT, 1.0)),
            climates=tuple(data.get(CONF_CLIMATES, [])),
            valves=tuple(data.get(CONF_VALVES, [])),
            room_temperature=data.get(CONF_ROOM_TEMPERATURE) or None,
            windows=tuple(data.get(CONF_WINDOWS, [])),
            schedule=data.get(CONF_SCHEDULE) or None,
            compensation=bool(data.get(CONF_COMPENSATION, True)),
            solar_gain=bool(data.get(CONF_SOLAR_GAIN, False)),
            usage_entities=tuple(data.get(CONF_USAGE_ENTITIES, [])),
            curve_reference=bool(data.get(CONF_CURVE_REFERENCE, True)),
        )

    @property
    def entity_ids(self) -> set[str]:
        """All entities this room depends on."""
        ids = {*self.climates, *self.valves, *self.windows, *self.usage_entities}
        for entity_id in (self.room_temperature, self.schedule):
            if entity_id:
                ids.add(entity_id)
        return ids


@dataclass(frozen=True, slots=True)
class EntityConfig:
    """Central entities and rooms of an installation."""

    rooms: tuple[RoomConfig, ...]
    boiler_switch: str | None = None
    flow_temperature: str | None = None
    return_temperature: str | None = None
    gas_flow: str | None = None
    gas_meter: str | None = None
    burner_sensor: str | None = None
    outdoor_sensors: tuple[str, ...] = ()
    weather: str | None = None
    watchdog_url: str | None = None
    presence: tuple[str, ...] = ()
    duty_cycle: str | None = None
    flow_setpoint: str | None = None
    solar_power: str | None = None
    relay_feedback: str | None = None
    burner_lock: str | None = None
    boiler_winter_mode: str | None = None
    pump: str | None = None
    boiler_flow_temperature: str | None = None
    boiler_return_temperature: str | None = None
    sleep_sensor: str | None = None

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> EntityConfig:
        """Read from options and subentries."""
        options = entry.options

        def one(key: str) -> str | None:
            return options.get(key) or None

        return cls(
            rooms=tuple(
                RoomConfig.from_subentry(s)
                for s in entry.subentries.values()
                if s.subentry_type == SUBENTRY_ROOM
            ),
            boiler_switch=one(CONF_BOILER_SWITCH),
            flow_temperature=one(CONF_FLOW_TEMPERATURE),
            return_temperature=one(CONF_RETURN_TEMPERATURE),
            gas_flow=one(CONF_GAS_FLOW),
            gas_meter=one(CONF_GAS_METER),
            burner_sensor=one(CONF_BURNER_SENSOR),
            outdoor_sensors=tuple(options.get(CONF_OUTDOOR_SENSORS, [])),
            weather=one(CONF_WEATHER),
            watchdog_url=one(CONF_WATCHDOG_URL),
            presence=tuple(options.get(CONF_PRESENCE, [])),
            duty_cycle=one(CONF_DUTY_CYCLE),
            flow_setpoint=one(CONF_FLOW_SETPOINT),
            solar_power=one(CONF_SOLAR_POWER),
            relay_feedback=one(CONF_RELAY_FEEDBACK),
            burner_lock=one(CONF_BURNER_LOCK),
            boiler_winter_mode=one(CONF_BOILER_WINTER_MODE),
            pump=one(CONF_PUMP_SENSOR),
            boiler_flow_temperature=one(CONF_BOILER_FLOW_TEMPERATURE),
            boiler_return_temperature=one(CONF_BOILER_RETURN_TEMPERATURE),
            sleep_sensor=one(CONF_SLEEP_SENSOR),
        )

    @property
    def has_gas_source(self) -> bool:
        """Whether gas consumption can be measured."""
        return self.gas_flow is not None or self.gas_meter is not None

    @property
    def tracked_entities(self) -> set[str]:
        """All input entities."""
        ids: set[str] = {*self.outdoor_sensors, *self.presence}
        for entity_id in (
            self.boiler_switch,
            self.flow_temperature,
            self.return_temperature,
            self.gas_flow,
            self.gas_meter,
            self.burner_sensor,
            self.weather,
            self.duty_cycle,
            self.flow_setpoint,
            self.solar_power,
            self.relay_feedback,
            self.burner_lock,
            self.boiler_winter_mode,
            self.pump,
            self.boiler_flow_temperature,
            self.boiler_return_temperature,
            self.sleep_sensor,
        ):
            if entity_id:
                ids.add(entity_id)
        for room in self.rooms:
            ids |= room.entity_ids
        return ids


@dataclass(frozen=True, slots=True)
class ControlState:
    """User settings that enter an evaluation."""

    mode: OperatingMode
    automation_enabled: bool
    actuator_active: bool
    room_control_enabled: bool
    learned_schedule_enabled: bool
    vacation_active: bool
    forecast_6h: float | None = None
    forecast_12h: float | None = None


class InputReader:
    """Converts states to readings."""

    def __init__(self, get_state: StateGetter, replay_time: datetime | None = None) -> None:
        self._get = get_state
        self._replay_time = replay_time

    def state(self, entity_id: str) -> State | None:
        """State if available."""
        state = self._get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state

    def _reported(self, state: State) -> datetime:
        return self._replay_time or state.last_reported

    def _reading(self, state: State, value: float | None) -> Reading:
        return Reading(value, self._reported(state)) if value is not None else MISSING

    def number(self, entity_id: str, factors: dict[str | None, float] | None = None) -> Reading:
        """Numeric state, optionally unit converted."""
        state = self.state(entity_id)
        if state is None:
            return MISSING
        value = _to_float(state.state)
        if value is not None and factors is not None:
            value *= factors.get(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT), 1.0)
        return self._reading(state, value)

    def temperature(self, entity_id: str) -> Reading:
        """Temperature in °C."""
        state = self.state(entity_id)
        if state is None:
            return MISSING
        value = _to_float(state.state)
        if (
            value is not None
            and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.FAHRENHEIT
        ):
            value = TemperatureConverter.convert(
                value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        return self._reading(state, value)

    def valve(self, entity_id: str) -> Reading:
        """Valve position as a fraction 0..1."""
        state = self.state(entity_id)
        if state is None:
            return MISSING
        value = _to_float(state.state)
        if value is None:
            return MISSING
        if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE or value > 1:
            value /= 100
        return self._reading(state, min(max(value, 0.0), 1.0))

    def binary(self, entity_id: str) -> bool | None:
        """On/off state."""
        state = self.state(entity_id)
        if state is None:
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return None

    def weather_temperature(self, entity_id: str) -> Reading:
        """Current temperature of a weather entity in °C."""
        state = self.state(entity_id)
        if state is None:
            return MISSING
        value = _to_float(state.attributes.get(ATTR_TEMPERATURE))
        if (
            value is not None
            and state.attributes.get("temperature_unit") == UnitOfTemperature.FAHRENHEIT
        ):
            value = TemperatureConverter.convert(
                value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        return self._reading(state, value)

    def climate_attribute(self, state: State | None, attribute: str) -> Reading:
        """Numeric climate attribute."""
        if state is None:
            return MISSING
        return self._reading(state, _to_float(state.attributes.get(attribute)))

    def activity(self, entity_ids: tuple[str, ...]) -> bool | None:
        """Is the room in use? None if nothing is configured or known."""
        known = [s for e in entity_ids if (s := self.state(e)) is not None]
        if not known:
            return None
        return any(s.state not in _IDLE_STATES for s in known)

    def presence(self, entity_ids: tuple[str, ...]) -> bool | None:
        """Anyone at home? None if nothing is configured or known."""
        known = [s for e in entity_ids if (s := self.state(e)) is not None]
        if not known:
            return None
        return any(s.state in (STATE_HOME, STATE_ON) for s in known)

    def schedule(self, entity_id: str | None) -> tuple[bool | None, datetime | None]:
        """(currently on, next start of an 'on' period)."""
        if entity_id is None:
            return None, None
        state = self.state(entity_id)
        if state is None:
            return None, None
        on = state.state == STATE_ON
        next_event = _to_datetime(state.attributes.get("next_event"))
        return on, (next_event if not on else None)


def build_snapshot(
    config: EntityConfig, reader: InputReader, now: datetime, control: ControlState
) -> EngineSnapshot:
    """Assemble all inputs of one evaluation."""
    rooms: list[RoomInput] = []
    controls: list[RoomControlInput] = []
    for room in config.rooms:
        climate_states = [reader.state(e) for e in room.climates]
        rooms.append(
            RoomInput(
                room_id=room.room_id,
                name=room.name,
                kind=room.kind,
                weight=room.weight,
                room_temperature=reader.temperature(room.room_temperature)
                if room.room_temperature
                else None,
                thermostat_temperatures=tuple(
                    reader.climate_attribute(s, ATTR_CURRENT_TEMPERATURE) for s in climate_states
                ),
                targets=tuple(_target(reader, s) for s in climate_states),
                valves=tuple(reader.valve(e) for e in room.valves),
                windows_open=tuple(reader.binary(e) for e in room.windows),
            )
        )
        if room.kind is RoomKind.REGULATED:
            schedule_on, next_on = reader.schedule(room.schedule)
            controls.append(
                RoomControlInput(
                    room_id=room.room_id,
                    schedule_on=schedule_on,
                    next_schedule_on=next_on,
                    trvs=tuple(
                        TrvInput(
                            entity_id=entity_id,
                            available=state is not None,
                            current_target=_to_float(state.attributes.get(ATTR_TEMPERATURE))
                            if state
                            else None,
                            current_temperature=_to_float(
                                state.attributes.get(ATTR_CURRENT_TEMPERATURE)
                            )
                            if state
                            else None,
                            hvac_mode=state.state if state else None,
                        )
                        for entity_id, state in zip(room.climates, climate_states, strict=True)
                    ),
                    compensation=room.compensation,
                    solar_gain=room.solar_gain,
                    activity=reader.activity(room.usage_entities),
                    curve_reference=room.curve_reference,
                )
            )

    return EngineSnapshot(
        now=now,
        rooms=tuple(rooms),
        outdoor_sensors=tuple(reader.temperature(e) for e in config.outdoor_sensors),
        weather_temperature=reader.weather_temperature(config.weather) if config.weather else None,
        flow_temperature=reader.temperature(config.flow_temperature)
        if config.flow_temperature
        else None,
        return_temperature=reader.temperature(config.return_temperature)
        if config.return_temperature
        else None,
        gas_flow=reader.number(config.gas_flow, _FLOW_FACTORS) if config.gas_flow else None,
        gas_meter=reader.number(config.gas_meter, _VOLUME_FACTORS) if config.gas_meter else None,
        burner_on=reader.binary(config.burner_sensor) if config.burner_sensor else None,
        relay_on=reader.binary(config.boiler_switch) if config.boiler_switch else None,
        mode=control.mode,
        automation_enabled=control.automation_enabled,
        actuator_active=control.actuator_active,
        room_control_enabled=control.room_control_enabled,
        learned_schedule_enabled=control.learned_schedule_enabled,
        vacation_active=control.vacation_active,
        present=reader.presence(config.presence),
        room_controls=tuple(controls),
        duty_cycle=reader.number(config.duty_cycle) if config.duty_cycle else None,
        flow_setpoint=reader.temperature(config.flow_setpoint) if config.flow_setpoint else None,
        solar_power=reader.number(config.solar_power, _POWER_FACTORS)
        if config.solar_power
        else None,
        forecast_6h=control.forecast_6h,
        forecast_12h=control.forecast_12h,
        relay_feedback=reader.binary(config.relay_feedback) if config.relay_feedback else None,
        burner_lock=reader.number(config.burner_lock) if config.burner_lock else None,
        boiler_winter_mode=reader.binary(config.boiler_winter_mode)
        if config.boiler_winter_mode
        else None,
        pump_on=reader.binary(config.pump) if config.pump else None,
        boiler_flow_temperature=reader.temperature(config.boiler_flow_temperature)
        if config.boiler_flow_temperature
        else None,
        boiler_return_temperature=reader.temperature(config.boiler_return_temperature)
        if config.boiler_return_temperature
        else None,
        sleep_sensor=reader.binary(config.sleep_sensor) if config.sleep_sensor else None,
    )


def _target(reader: InputReader, state: State | None) -> Reading:
    if state is None or state.state == HVACMode.OFF:
        return MISSING
    return reader.climate_attribute(state, ATTR_TEMPERATURE)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return dt_util.parse_datetime(value)
    return None
