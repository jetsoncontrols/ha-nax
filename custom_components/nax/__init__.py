import logging
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.config_entries import ConfigEntry
from .nax.nax_api import NaxApi

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load a config entry."""
    api = NaxApi(
        ip=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = api

    async def on_hass_stop(event):
        await hass.async_add_executor_job(api.logout)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop)

    connected, connect_message = await hass.async_add_executor_job(api.login)
    if connected:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
    _LOGGER.error(f"Could not connect to NAX: {connect_message}")
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(api.logout)
    return unload_ok
