from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.device_registry import format_mac, CONNECTION_NETWORK_MAC

from cresnextws import CresNextWSClient
from .const import DOMAIN


class NaxEntity(Entity):
    """Nax base entity class."""

    def __init__(self, api: CresNextWSClient, unique_id: str) -> None:
        """Initialize the entity."""
        self._attr_unique_id = unique_id
        self._attr_should_poll = False
        self._attr_entity_registry_visible_default = False
        self.api = api
        raw_mac = self.api.get_device_mac_address()
        formatted_mac = format_mac(raw_mac) if raw_mac else None

        connections: set[tuple[str, str]] = (
            {(CONNECTION_NETWORK_MAC, formatted_mac)} if formatted_mac else set()
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
        new_mac = format_mac(data)
        if new_mac == self._cached_mac:
            return
        self._cached_mac = new_mac
        if self._attr_device_info:
            self._attr_device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, new_mac)
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
