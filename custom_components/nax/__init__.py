import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .nax.nax_api import NaxApi

_LOGGER = logging.getLogger(__name__)
PLATFORMS = sorted(
    [
        Platform.MEDIA_PLAYER,
        Platform.SENSOR,
        Platform.SWITCH,
        Platform.BUTTON,
        Platform.SELECT,
    ]
)


# https://github.com/home-assistant/example-custom-config/blob/master/custom_components/detailed_hello_world_push
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load a config entry."""
    api = NaxApi(
        ip=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        http_fallback=False,
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

    connected, connect_message = await hass.async_add_executor_job(api.http_login)
    if connected:
        await api.async_upgrade_websocket()
        return True
    _LOGGER.error(f"Could not connect to NAX: {connect_message}")  # noqa: G004
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(api.logout)
    return unload_ok
