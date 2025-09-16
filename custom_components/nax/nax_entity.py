"""NAX base entity class for Home Assistant integration."""

import logging

from cresnextws import ConnectionStatus, DataEventManager
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class NaxEntity(Entity):
    """Nax base entity class."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
    ) -> None:
        """Initialize the entity.

        Args:
            api: The DataEventManager instance
            mac_address: MAC address of the device
            nax_device_name: Name of the device
            nax_device_manufacturer: Manufacturer of the device
            nax_device_model: Model of the device
            nax_device_firmware_version: Firmware version of the device
            nax_device_serial_number: Serial number of the device
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
            sw_version=nax_device_firmware_version,
            serial_number=nax_device_serial_number,
            configuration_url=self.api.client.get_base_endpoint(),
        )
        self.api.client.add_connection_status_handler(
            self._device_connection_status_update
        )

    @callback
    def _device_connection_status_update(self, status: ConnectionStatus) -> None:
        if status == ConnectionStatus.CONNECTED:
            self._attr_available = True
            self.schedule_update_ha_state(force_refresh=True)
        else:
            self._attr_available = False
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        # We could retreive DeviceInfo here if needed in the future
