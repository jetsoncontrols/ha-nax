"""The NAX integration."""

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

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


class NaxEntity(Entity):
    """Nax base entity class."""

    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the entity."""
        self._attr_unique_id = unique_id
        self._attr_should_poll = False
        self._attr_entity_registry_visible_default = False
        self.api = api
        self._attr_device_info = DeviceInfo(
            configuration_url=self.api.get_base_url(),
            connections={
                (
                    device_registry.CONNECTION_NETWORK_MAC,
                    self.api.get_device_mac_address(),
                )
            },
            # identifiers={(DOMAIN, self._attr_unique_id)},
            serial_number=self.api.get_device_serial_number(),
            manufacturer=self.api.get_device_manufacturer(),
            model=self.api.get_device_model(),
            sw_version=self.api.get_device_firmware_version(),
            name=self.api.get_device_name(),
        )
        self.__base_subscriptions()

    def __base_subscriptions(self) -> None:
        self.api.subscribe_connection_updates(self._update_connection)
        self.api.subscribe_data_updates(
            "Device.DeviceInfo.Name",
            self._device_name_update,
        )

    @callback
    def _device_name_update(self, path: str, data: Any) -> None:
        self._attr_device_info["name"] = data
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
