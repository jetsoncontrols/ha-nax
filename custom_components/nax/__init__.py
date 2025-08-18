"""The NAX integration."""

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
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

    store = Store[dict[str, Any]](hass, STORAGE_VERSION, DOMAIN + "_" + entry.entry_id)
    if not (storage_data := await store.async_load()):
        storage_data = {
            STORAGE_LAST_INPUT_KEY: dict[str, str](),
            STORAGE_LAST_AES67_STREAM_KEY: dict[str, str](),
        }
        await store.async_save(storage_data)
    entry.runtime_data = store

    def on_zones_data_update(path: str, data: Any) -> None:
        # add debug logging for data updates and what this device is called
        _LOGGER.error("Data update for %s", entry.title or entry.entry_id)
        asyncio.get_event_loop().create_task(
            hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        )
        api.unsubscribe_data_updates("Device.ZoneOutputs.Zones", on_zones_data_update)

    api.subscribe_data_updates(
        "Device.ZoneOutputs.Zones", on_zones_data_update, trigger_current_value=True
    )

    connected, connect_message = await api.http_login()
    if connected:
        ws_connected, ws_message = await api.async_upgrade_websocket()
        return ws_connected
    raise ConfigEntryNotReady(f"Could not connect to NAX: {connect_message}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(api.logout)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    _LOGGER.debug("Removing NAX config entry %s", entry.entry_id)


class NaxEntity(Entity):
    """Nax base entity class."""

    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the entity."""
        self._attr_unique_id = unique_id
        self._attr_should_poll = False
        self._attr_entity_registry_visible_default = False
        self.api = api
        raw_mac = self.api.get_device_mac_address()
        formatted_mac = dr.format_mac(raw_mac) if raw_mac else None

        connections: set[tuple[str, str]] = (
            {(dr.CONNECTION_NETWORK_MAC, formatted_mac)} if formatted_mac else set()
        )

        # Use a stable identifier (serial if available, else unique_id)
        stable_identifier = self.api.get_device_serial_number() or self._attr_unique_id

        device_info = DeviceInfo(
            configuration_url=self.api.get_base_url(),
            connections=connections,
            identifiers={(DOMAIN, stable_identifier)},
            serial_number=self.api.get_device_serial_number(),
            manufacturer=self.api.get_device_manufacturer(),
            model=self.api.get_device_model(),
            sw_version=self.api.get_device_firmware_version(),
            name=self.api.get_device_name(),
        )
        self._attr_device_info = device_info
        self._cached_mac = formatted_mac
        self.__base_subscriptions()

    def __base_subscriptions(self) -> None:
        self.api.subscribe_connection_updates(self._update_connection)
        self.api.subscribe_data_updates(
            "Device.DeviceInfo.Name",
            self._device_name_update,
        )
        # Subscribe to MAC updates if the device reports them dynamically
        self.api.subscribe_data_updates(
            "Device.DeviceInfo.MAC",
            self._device_mac_update,
        )

    @callback
    def _device_name_update(self, path: str, data: Any) -> None:
        if self._attr_device_info:
            self._attr_device_info["name"] = data
            self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _device_mac_update(self, path: str, data: Any) -> None:
        """Handle MAC address updates and refresh device connections."""
        if not data:
            return
        new_mac = dr.format_mac(data)
        if new_mac == self._cached_mac:
            return
        self._cached_mac = new_mac
        if self._attr_device_info:
            self._attr_device_info["connections"] = {
                (dr.CONNECTION_NETWORK_MAC, new_mac)
            }
            self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _generic_update(self, path: str, data: Any) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _update_connection(self, connected: bool) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @property
    def available(self) -> bool:
        """Could the resource be accessed during the last update call."""
        return self.api.get_websocket_connected()
