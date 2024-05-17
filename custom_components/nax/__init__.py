import logging
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    Platform,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.config_entries import ConfigEntry
from .nax.nax_api import NaxApi
import asyncio

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
]


# https://github.com/home-assistant/example-custom-config/blob/master/custom_components/detailed_hello_world_push
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load a config entry."""
    _LOGGER.warning(f"Setting up NAX entry: {entry.entry_id}")
    api = NaxApi(
        ip=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = api

    def on_zones_data_update(path: str, data: any) -> None:
        asyncio.get_event_loop().create_task(
            hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        )
        api.unsubscribe_data_updates("Device.ZoneOutputs.Zones", on_zones_data_update)

    api.subscribe_data_updates(
        "Device.ZoneOutputs.Zones", on_zones_data_update, trigger_current_value=True
    )

    # async def on_hass_stop(event):
    #     await hass.async_add_executor_job(api.logout)

    # hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop)

    connected, connect_message = await hass.async_add_executor_job(api.http_login)
    if connected:
        await api.async_upgrade_websocket()
        return True
    _LOGGER.error(f"Could not connect to NAX: {connect_message}")
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an config entry."""
    _LOGGER.warning(f"Unloading NAX entry: {entry.entry_id}")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(api.logout)
    return unload_ok
