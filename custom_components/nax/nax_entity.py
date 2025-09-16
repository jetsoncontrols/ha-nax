"""NAX base entity class for Home Assistant integration."""

from typing import Any

from cresnextws import ConnectionStatus, DataEventManager
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class NaxEntity(Entity):
    """Nax base entity class."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
    ) -> None:
        """Initialize the entity.

        Args:
            api: The DataEventManager instance
            mac_address: MAC address of the device
            nax_device_name: Name of the device
            nax_device_manufacturer: Manufacturer of the device
            nax_device_model: Model of the device
        """
        self.api = api
        self.mac_address = mac_address
        self._attr_should_poll = False
        self._attr_entity_registry_visible_default = False

        # Create device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_address)},
            name=nax_device_name,
            manufacturer=nax_device_manufacturer,
            model=nax_device_model,
        )
        api.subscribe(
            "/Device/DeviceInfo/Name",
            self._nax_device_name_update,
        )
        self.api.client.add_connection_status_handler(
            self._device_connection_status_update
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to Home Assistant."""

    @callback
    def _nax_device_name_update(self, path: str, data: Any) -> None:
        """Update device name when it changes."""
        if self._attr_device_info:
            # Update the device info with new name, preserving existing info
            self._attr_device_info["name"] = data
            # self._attr_device_info = DeviceInfo(
            #     identifiers=self._attr_device_info.get(
            #         "identifiers", {(DOMAIN, self.mac_address)}
            #     ),
            #     name=data,
            #     manufacturer=self._attr_device_info.get("manufacturer", "Crestron"),
            #     model=self._attr_device_info.get("model", "NAX"),
            # )
            self.async_write_ha_state()

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
