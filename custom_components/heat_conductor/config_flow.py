"""Config flow for HeatConductor: central setup, options and room subentries."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    ALL_DEFAULTS,
    CONF_BOILER_FLOW_TEMPERATURE,
    CONF_BOILER_RETURN_TEMPERATURE,
    CONF_BOILER_SWITCH,
    CONF_BOILER_WINTER_MODE,
    CONF_BURNER_FLOW_THRESHOLD,
    CONF_BURNER_LOCK,
    CONF_BURNER_MAX_POWER,
    CONF_BURNER_SENSOR,
    CONF_CALORIFIC_VALUE,
    CONF_CLIMATES,
    CONF_COMPENSATION,
    CONF_CONDENSING_RETURN_LIMIT,
    CONF_CURVE_REFERENCE,
    CONF_DEFICIT_FULL_SCALE,
    CONF_DUTY_CYCLE,
    CONF_FLOW_SETPOINT,
    CONF_FLOW_TEMPERATURE,
    CONF_FROST_LIMIT,
    CONF_GAS_FLOW,
    CONF_GAS_METER,
    CONF_HEATING_LIMIT,
    CONF_IMMEDIATE_DEFICIT,
    CONF_MANUAL_OVERRIDE,
    CONF_MAX_FLOW_TEMPERATURE,
    CONF_MAX_STARTS,
    CONF_MIN_PAUSE,
    CONF_MIN_RUN,
    CONF_OUTDOOR_SENSORS,
    CONF_OUTDOOR_SMOOTHING,
    CONF_PRESENCE,
    CONF_PUMP_SENSOR,
    CONF_RELAY_FEEDBACK,
    CONF_RETURN_TEMPERATURE,
    CONF_ROOM_KIND,
    CONF_ROOM_TEMPERATURE,
    CONF_SCHEDULE,
    CONF_SOLAR_GAIN,
    CONF_SOLAR_POWER,
    CONF_STALE_AFTER,
    CONF_START_CONFIRM,
    CONF_START_THRESHOLD,
    CONF_STOP_THRESHOLD,
    CONF_USAGE_ENTITIES,
    CONF_VALVES,
    CONF_WATCHDOG_URL,
    CONF_WEATHER,
    CONF_WEIGHT,
    CONF_WINDOWS,
    CONF_Z_FACTOR,
    DOMAIN,
    ENERGY_DEFAULTS,
    PARAMETER_DEFAULTS,
    SUBENTRY_ROOM,
)
from .core.models import RoomKind
from .params import PARAMS

ENTITY_KEYS = (
    CONF_BOILER_SWITCH,
    CONF_FLOW_TEMPERATURE,
    CONF_RETURN_TEMPERATURE,
    CONF_GAS_FLOW,
    CONF_GAS_METER,
    CONF_BURNER_SENSOR,
    CONF_OUTDOOR_SENSORS,
    CONF_WEATHER,
    CONF_WATCHDOG_URL,
    CONF_PRESENCE,
    CONF_DUTY_CYCLE,
    CONF_FLOW_SETPOINT,
    CONF_SOLAR_POWER,
    CONF_RELAY_FEEDBACK,
    CONF_BURNER_LOCK,
    CONF_BOILER_WINTER_MODE,
    CONF_PUMP_SENSOR,
    CONF_BOILER_FLOW_TEMPERATURE,
    CONF_BOILER_RETURN_TEMPERATURE,
)


def _entity(
    domain: str | list[str], device_class: str | None = None, *, multiple: bool = False
) -> selector.EntitySelector:
    config = selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    if device_class:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def _number(
    minimum: float, maximum: float, step: float | str, unit: str | None = None
) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


ENTITIES_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_BOILER_SWITCH): _entity(["switch", "input_boolean"]),
        vol.Optional(CONF_OUTDOOR_SENSORS, default=[]): _entity(
            "sensor", SensorDeviceClass.TEMPERATURE, multiple=True
        ),
        vol.Optional(CONF_WEATHER): _entity("weather"),
        vol.Optional(CONF_FLOW_TEMPERATURE): _entity("sensor", SensorDeviceClass.TEMPERATURE),
        vol.Optional(CONF_RETURN_TEMPERATURE): _entity("sensor", SensorDeviceClass.TEMPERATURE),
        vol.Optional(CONF_GAS_METER): _entity("sensor"),
        vol.Optional(CONF_GAS_FLOW): _entity("sensor"),
        vol.Optional(CONF_BURNER_SENSOR): _entity("binary_sensor"),
        vol.Optional(CONF_WATCHDOG_URL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
        vol.Optional(CONF_PRESENCE, default=[]): _entity(
            ["person", "device_tracker", "binary_sensor", "input_boolean"], multiple=True
        ),
        vol.Optional(CONF_DUTY_CYCLE): _entity("sensor"),
        vol.Optional(CONF_FLOW_SETPOINT): _entity("sensor", SensorDeviceClass.TEMPERATURE),
        vol.Optional(CONF_SOLAR_POWER): _entity("sensor", SensorDeviceClass.POWER),
        vol.Optional(CONF_RELAY_FEEDBACK): _entity("binary_sensor"),
        vol.Optional(CONF_BURNER_LOCK): _entity("sensor"),
        vol.Optional(CONF_BOILER_WINTER_MODE): _entity("binary_sensor"),
        vol.Optional(CONF_PUMP_SENSOR): _entity("binary_sensor"),
        vol.Optional(CONF_BOILER_FLOW_TEMPERATURE): _entity(
            "sensor", SensorDeviceClass.TEMPERATURE
        ),
        vol.Optional(CONF_BOILER_RETURN_TEMPERATURE): _entity(
            "sensor", SensorDeviceClass.TEMPERATURE
        ),
    }
)

PARAMETERS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_START_THRESHOLD): _number(1, 100, 1, "%"),
        vol.Required(CONF_START_CONFIRM): _number(0, 60, 1, "min"),
        vol.Required(CONF_STOP_THRESHOLD): _number(0, 100, 1, "%"),
        vol.Required(CONF_IMMEDIATE_DEFICIT): _number(0.2, 5, 0.1, "K"),
        vol.Required(CONF_DEFICIT_FULL_SCALE): _number(0.2, 5, 0.1, "K"),
        vol.Required(CONF_MIN_RUN): _number(0, 120, 1, "min"),
        vol.Required(CONF_MIN_PAUSE): _number(0, 120, 1, "min"),
        vol.Required(CONF_MAX_STARTS): _number(1, 20, 1, "1/h"),
        vol.Required(CONF_HEATING_LIMIT): _number(5, 30, 0.5, "°C"),
        vol.Required(CONF_FROST_LIMIT): _number(2, 12, 0.5, "°C"),
        vol.Required(CONF_MAX_FLOW_TEMPERATURE): _number(40, 90, 1, "°C"),
        vol.Required(CONF_STALE_AFTER): _number(15, 1440, 5, "min"),
        vol.Required(CONF_MANUAL_OVERRIDE): _number(5, 1440, 5, "min"),
        vol.Required(CONF_OUTDOOR_SMOOTHING): _number(1, 72, 1, "h"),
        vol.Required(CONF_BURNER_FLOW_THRESHOLD): _number(0, 5, 0.05, "m³/h"),
    }
)


ENERGY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CALORIFIC_VALUE): _number(8, 13, 0.001, "kWh/m³"),
        vol.Required(CONF_Z_FACTOR): _number(0.8, 1.1, "any"),
        vol.Required(CONF_BURNER_MAX_POWER): _number(0, 200, 0.1, "kW"),
        vol.Required(CONF_CONDENSING_RETURN_LIMIT): _number(30, 70, 1, "°C"),
    }
)


def _group_schema(group: str) -> vol.Schema:
    """Options form generated from the parameter metadata."""
    fields: dict[Any, Any] = {}
    for meta in PARAMS:
        if meta.group != group:
            continue
        if meta.boolean:
            fields[vol.Required(meta.key)] = selector.BooleanSelector()
        else:
            assert meta.minimum is not None and meta.maximum is not None and meta.step is not None
            fields[vol.Required(meta.key)] = _number(
                meta.minimum, meta.maximum, meta.step, meta.unit
            )
    return vol.Schema(fields)


def _validate_entities(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not user_input.get(CONF_OUTDOOR_SENSORS) and not user_input.get(CONF_WEATHER):
        errors["base"] = "outdoor_required"
    return errors


def _merge_entities(options: dict[str, Any], user_input: dict[str, Any]) -> dict[str, Any]:
    """Replace entity options; cleared optional selectors are removed."""
    merged = {k: v for k, v in options.items() if k not in ENTITY_KEYS}
    merged.update({k: v for k, v in user_input.items() if v not in (None, "", [])})
    return merged


class HeatConductorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup of HeatConductor."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose name and central entities."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        schema = vol.Schema({vol.Required(CONF_NAME, default="HeatConductor"): str}).extend(
            ENTITIES_SCHEMA.schema
        )
        if user_input is not None:
            errors = _validate_entities(user_input)
            if not errors:
                name = user_input.pop(CONF_NAME)
                options = _merge_entities(dict(ALL_DEFAULTS), user_input)
                return self.async_create_entry(title=name, data={}, options=options)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Options: entities and control parameters."""
        return HeatConductorOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Rooms are subentries."""
        return {SUBENTRY_ROOM: RoomSubentryFlow}


class HeatConductorOptionsFlow(OptionsFlow):
    """Edit entities and parameters."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose what to edit."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "entities",
                "parameters",
                "energy",
                "room_control",
                "usage",
                "vacation",
                "learning",
            ],
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit central entities."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_entities(user_input)
            if not errors:
                return self.async_create_entry(
                    data=_merge_entities(dict(self.config_entry.options), user_input)
                )
        return self.async_show_form(
            step_id="entities",
            data_schema=self.add_suggested_values_to_schema(
                ENTITIES_SCHEMA, user_input or dict(self.config_entry.options)
            ),
            errors=errors,
        )

    async def async_step_parameters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit control parameters."""
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        current = {**PARAMETER_DEFAULTS, **self.config_entry.options}
        return self.async_show_form(
            step_id="parameters",
            data_schema=self.add_suggested_values_to_schema(PARAMETERS_SCHEMA, current),
        )

    async def async_step_energy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit gas and boiler constants."""
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        current = {**ENERGY_DEFAULTS, **self.config_entry.options}
        return self.async_show_form(
            step_id="energy",
            data_schema=self.add_suggested_values_to_schema(ENERGY_SCHEMA, current),
        )

    async def async_step_room_control(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit room control parameters."""
        return await self._group_step("room_control", user_input)

    async def async_step_usage(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit usage based heating parameters."""
        return await self._group_step("usage", user_input)

    async def async_step_vacation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit automatic vacation parameters."""
        return await self._group_step("vacation", user_input)

    async def async_step_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit learning and anticipation parameters."""
        return await self._group_step("learning", user_input)

    async def _group_step(self, group: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        current = {**ALL_DEFAULTS, **self.config_entry.options}
        return self.async_show_form(
            step_id=group,
            data_schema=self.add_suggested_values_to_schema(_group_schema(group), current),
        )


ROOM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_ROOM_KIND, default=RoomKind.REGULATED.value): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[k.value for k in RoomKind],
                translation_key="room_kind",
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(CONF_CLIMATES, default=[]): _entity("climate", multiple=True),
        vol.Optional(CONF_VALVES, default=[]): _entity("sensor", multiple=True),
        vol.Optional(CONF_ROOM_TEMPERATURE): _entity("sensor", SensorDeviceClass.TEMPERATURE),
        vol.Optional(CONF_WINDOWS, default=[]): _entity("binary_sensor", multiple=True),
        vol.Optional(CONF_SCHEDULE): _entity("schedule"),
        vol.Optional(CONF_USAGE_ENTITIES, default=[]): _entity(
            ["binary_sensor", "media_player", "switch", "input_boolean", "light", "device_tracker"],
            multiple=True,
        ),
        vol.Required(CONF_COMPENSATION, default=True): selector.BooleanSelector(),
        vol.Required(CONF_SOLAR_GAIN, default=False): selector.BooleanSelector(),
        vol.Required(CONF_CURVE_REFERENCE, default=True): selector.BooleanSelector(),
        vol.Required(CONF_WEIGHT, default=1.0): _number(0.1, 10, 0.1),
    }
)


def _validate_room(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    kind = user_input.get(CONF_ROOM_KIND)
    if kind == RoomKind.REGULATED and not (
        user_input.get(CONF_CLIMATES) or user_input.get(CONF_VALVES)
    ):
        errors["base"] = "regulated_needs_inputs"
    if kind == RoomKind.MONITOR and not (
        user_input.get(CONF_ROOM_TEMPERATURE) or user_input.get(CONF_CLIMATES)
    ):
        errors["base"] = "monitor_needs_temperature"
    return errors


def _room_data(user_input: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    data = {k: v for k, v in user_input.items() if k != CONF_NAME and v not in (None, "")}
    return user_input[CONF_NAME].strip(), data


class RoomSubentryFlow(ConfigSubentryFlow):
    """Add or edit a room."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add a room."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_room(user_input)
            if not errors:
                title, data = _room_data(user_input)
                return self.async_create_entry(title=title, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(ROOM_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit a room."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_room(user_input)
            if not errors:
                title, data = _room_data(user_input)
                return self.async_update_and_abort(
                    self._get_entry(), subentry, title=title, data=data
                )
        current = user_input or {CONF_NAME: subentry.title, **subentry.data}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(ROOM_SCHEMA, current),
            errors=errors,
        )
