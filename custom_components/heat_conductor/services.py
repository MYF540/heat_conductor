"""Domain services of HeatConductor."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import DOMAIN
from .coordinator import HeatConductorCoordinator
from .core.setpoint import MAX_TEMPERATURE, MIN_TEMPERATURE

SERVICE_SET_VACATION = "set_vacation"
SERVICE_CLEAR_VACATION = "clear_vacation"
SERVICE_RESET_LEARNING = "reset_learning"

ATTR_START = "start"
ATTR_END = "end"
ATTR_TEMPERATURE = "temperature"
ATTR_ROOM = "room"

VACATION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_START): cv.datetime,
        vol.Required(ATTR_END): cv.datetime,
        vol.Optional(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_TEMPERATURE, max=MAX_TEMPERATURE)
        ),
    }
)
RESET_SCHEMA = vol.Schema({vol.Optional(ATTR_ROOM): cv.string})


def get_coordinator(hass: HomeAssistant) -> HeatConductorCoordinator:
    """The coordinator of the (single) loaded entry."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return entries[0].runtime_data


def _local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_util.get_default_time_zone())
    return value


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services."""

    async def set_vacation(call: ServiceCall) -> None:
        coordinator = get_coordinator(hass)
        start = _local(call.data[ATTR_START]) if ATTR_START in call.data else None
        end = _local(call.data[ATTR_END])
        if start is not None and start >= end:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="vacation_order"
            )
        await coordinator.async_set_vacation(start, end, call.data.get(ATTR_TEMPERATURE))

    async def clear_vacation(call: ServiceCall) -> None:
        await get_coordinator(hass).async_clear_vacation()

    async def reset_learning(call: ServiceCall) -> None:
        coordinator = get_coordinator(hass)
        room = call.data.get(ATTR_ROOM)
        room_id = None
        if room:
            match = next((r for r in coordinator.rooms if room in (r.room_id, r.name)), None)
            if match is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unknown_room",
                    translation_placeholders={"room": room},
                )
            room_id = match.room_id
        await coordinator.async_reset_learning(room_id)

    hass.services.async_register(DOMAIN, SERVICE_SET_VACATION, set_vacation, VACATION_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_VACATION, clear_vacation)
    hass.services.async_register(DOMAIN, SERVICE_RESET_LEARNING, reset_learning, RESET_SCHEMA)
