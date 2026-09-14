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
    CONF_BOILER_SWITCH,
    CONF_BURNER_FLOW_THRESHOLD,
    CONF_BURNER_SENSOR,
    CONF_CLIMATES,
    CONF_DEFICIT_FULL_SCALE,
    CONF_FLOW_TEMPERATURE,
    CONF_FROST_LIMIT,
    CONF_GAS_FLOW,
    CONF_HEATING_LIMIT,
    CONF_IMMEDIATE_DEFICIT,
    CONF_MANUAL_OVERRIDE,
    CONF_MAX_FLOW_TEMPERATURE,
    CONF_MAX_STARTS,
    CONF_MIN_PAUSE,
    CONF_MIN_RUN,
    CONF_OUTDOOR_SENSORS,
    CONF_OUTDOOR_SMOOTHING,
    CONF_RETURN_TEMPERATURE,
    CONF_ROOM_KIND,
    CONF_ROOM_TEMPERATURE,
    CONF_STALE_AFTER,
    CONF_START_CONFIRM,
    CONF_START_THRESHOLD,
    CONF_STOP_THRESHOLD,
    CONF_VALVES,
    CONF_WEATHER,
    CONF_WEIGHT,
    CONF_WINDOWS,
    DOMAIN,
    PARAMETER_DEFAULTS,
    SUBENTRY_ROOM,
)
from .core.models import RoomKind

ENTITY_KEYS = (
    CONF_BOILER_SWITCH,
    CONF_FLOW_TEMPERATURE,
    CONF_RETURN_TEMPERATURE,
    CONF_GAS_FLOW,
    CONF_BURNER_SENSOR,
    CONF_OUTDOOR_SENSORS,
    CONF_WEATHER,
)


def _entity(
    domain: str | list[str], device_class: str | None = None, *, multiple: bool = False
) -> selector.EntitySelector:
    config = selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    if device_class:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def _number(
    minimum: float, maximum: float, step: float, unit: str | None = None
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
        vol.Optional(CONF_GAS_FLOW): _entity("sensor"),
        vol.Optional(CONF_BURNER_SENSOR): _entity("binary_sensor"),
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
                options = _merge_entities(dict(PARAMETER_DEFAULTS), user_input)
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
        return self.async_show_menu(step_id="init", menu_options=["entities", "parameters"])

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
