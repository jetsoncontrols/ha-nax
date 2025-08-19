"""The NAX integration."""

import asyncio
import logging
from typing import Any

from httpx import RemoteProtocolError

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
        Platform.SENSOR,  # something is wrong here, seems to error on 4ZSA
        Platform.SWITCH,
        Platform.BUTTON,
        Platform.SELECT,
    ]
)

# Group retryable setup exceptions
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RemoteProtocolError,
    asyncio.TimeoutError,  # Prefer asyncio variant
    OSError,
    ConnectionError,
)


# https://github.com/home-assistant/example-custom-config/blob/master/custom_components/detailed_hello_world_push
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load a config entry."""
    api = NaxApi(
        ip=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        http_fallback=True,
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
        # _LOGGER.error("Data update for %s", entry.title or entry.entry_id)
        asyncio.get_event_loop().create_task(
            hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        )
        api.unsubscribe_data_updates("Device.ZoneOutputs.Zones", on_zones_data_update)

    api.subscribe_data_updates(
        "Device.ZoneOutputs.Zones", on_zones_data_update, trigger_current_value=True
    )

    # def on_connection_update(connected: bool) -> None:
    #     async def _delayed_forward() -> None:
    #         await asyncio.sleep(1)
    #         await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    #     hass.async_create_task(_delayed_forward())

    # api.subscribe_connection_updates(on_connection_update)

    # try:
    #     connected, connect_message = await api.http_login()
    #     if connected:
    #         ws_connected, ws_message = await api.async_upgrade_websocket()
    #         if not ws_connected:
    #             _LOGGER.error("Websocket connection failed: %s", ws_message)
    #             raise ConfigEntryNotReady(f"Could not connect to NAX: {ws_message}")
    #         _LOGGER.warning("Setting up Nax entities for %s", entry.title)
    #         # asyncio.get_event_loop().create_task(
    #         #     hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    #         # )
    #         api.get_all_zone_outputs()
    #         return ws_connected
    # except Exception as e:
    #     _LOGGER.error("Error setting up NAX: %s", e)
    #     raise ConfigEntryNotReady(f"Could not connect to NAX: {connect_message}")

    try:

        def _raise_not_ready(reason: str) -> None:
            """Raise standardized not-ready error."""
            raise ConfigEntryNotReady(f"Could not connect to NAX: {reason}")

        connected, connect_message = await api.http_login()
        if not connected:
            _LOGGER.error("%s HTTP login failed: %s", entry.title, connect_message)
            _raise_not_ready(connect_message)
        ws_connected, ws_message = await api.async_upgrade_websocket()
        if not ws_connected:
            _LOGGER.error("%s Websocket connection failed: %s", entry.title, ws_message)
            _raise_not_ready(ws_message)

        # _LOGGER.warning("Setting up Nax entities for %s", entry.title)
        api.get_device()
        # await asyncio.get_event_loop().create_task(
        # Schedule fetching all zone outputs after 10 seconds without blocking setup.
        # def _delayed_get_zone_outputs() -> None:
        #     async def _run() -> None:
        #         await hass.async_add_executor_job(api.get_all_zone_outputs)

        #     hass.async_create_task(_run(), name="nax_get_all_zone_outputs")

        # hass.loop.call_later(10, _delayed_get_zone_outputs)

    except RETRYABLE_EXCEPTIONS as exc:
        reason = str(exc)
        _LOGGER.error("Error setting up NAX: %s", reason)
        _raise_not_ready(reason)
    else:
        return ws_connected


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

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to Home Assistant."""
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
