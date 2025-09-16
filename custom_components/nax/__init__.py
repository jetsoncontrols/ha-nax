"""Crestron NAX integration."""

import logging
from typing import Any

from cresnextws import ClientConfig, CresNextWSClient, DataEventManager
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    STORAGE_LAST_AES67_STREAM_KEY,
    STORAGE_LAST_INPUT_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = sorted(
    [
        Platform.MEDIA_PLAYER,
        # Platform.SELECT,
        Platform.BINARY_SENSOR,
    ]
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load a config entry."""
    client = CresNextWSClient(
        ClientConfig(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )
    )
    api = DataEventManager(client)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = api

    store = Store[dict[str, Any]](hass, STORAGE_VERSION, DOMAIN + "_" + entry.entry_id)
    if not (storage_data := await store.async_load()):
        storage_data = {
            STORAGE_LAST_INPUT_KEY: dict[str, str](),
            STORAGE_LAST_AES67_STREAM_KEY: dict[str, str](),
        }
        await store.async_save(storage_data)
    entry.runtime_data = store

    try:
        if not await api.client.connect():
            raise ConfigEntryNotReady("Could not connect to NAX")
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to connect to NAX: {err}") from err
    await api.start_monitoring()
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Successfully set up NAX entities for %s", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an config entry."""
    _LOGGER.debug("Unloading NAX config entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api: DataEventManager = hass.data[DOMAIN].pop(entry.entry_id, None)
        if api is not None:
            await api.stop_monitoring()
            await api.client.disconnect()
        else:
            _LOGGER.debug(
                "No API client found for entry %s during unload", entry.entry_id
            )
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    _LOGGER.debug("Removing NAX config entry %s", entry.entry_id)

    # Safely get and remove the API client if it exists
    api: DataEventManager = hass.data[DOMAIN].pop(entry.entry_id, None)

    if api is not None:
        await api.stop_monitoring()
        await api.client.disconnect()
    else:
        _LOGGER.debug("No API client found for entry %s during removal", entry.entry_id)
