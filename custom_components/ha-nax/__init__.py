
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

PLATFORMS: list[Platform] = ["sensor", "switch"]

async def async_setup_entry(home_assistant: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up WattBox from a config entry."""
    api = NaxApi(
        ip=config_entry.data[CONF_HOST],
        username=config_entry.data[CONF_USERNAME],
        password=config_entry.data[CONF_PASSWORD],
    )
    _LOGGER.error(f"Setting up NaxApi ip={config_entry.data[CONF_HOST]} username={config_entry.data[CONF_USERNAME]} password={config_entry.data[CONF_PASSWORD]}")

    return True
    # api = WattBoxApi(
    #     hass,
    #     entry,
    #     ip=entry.data[CONF_HOST],
    #     username=entry.data[CONF_USERNAME],
    #     password=entry.data[CONF_PASSWORD],
    # )
    # # await api.async_connect()
    # hass.data.setdefault(DOMAIN, {})[entry.entry_id] = api

    # async def on_hass_stop(event):
    #     """Stop push updates when hass stops."""
    #     await api.disconnect()

    # entry.async_on_unload(
    #     hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop)
    # )
    # # hass.async_create_task(
    # #     hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # # )

    # return api is not None