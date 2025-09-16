"""NAX base entity class for Home Assistant integration."""

from collections.abc import Callable
from typing import Any

from cresnextws import ConnectionStatus, DataEventManager
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac
from homeassistant.helpers.entity import Entity


class NaxEntity(Entity):
    """Nax base entity class."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
    ) -> None:
        """Initialize the entity.

        Args:
            api: The DataEventManager instance
            mac_address: MAC address of the device
            subscriptions: List of tuples containing (path, callback) for data subscriptions
        """
        self.api = api
        self.mac_address = mac_address
        self._attr_should_poll = False
        self._attr_entity_registry_visible_default = False
        self.api.client.add_connection_status_handler(
            self._device_connection_status_update
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to Home Assistant."""

    @callback
    def _device_name_update(self, path: str, data: Any) -> None:
        if self._attr_device_info:
            self._attr_device_info["name"] = data
            self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _generic_update(self, path: str, data: Any) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _device_connection_status_update(self, status: ConnectionStatus) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Could the resource be accessed during the last update call."""
        return self.api.client.connected
