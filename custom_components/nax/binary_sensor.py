"""Nax Sensors."""

from __future__ import annotations

import logging
from typing import Any

from cresnextws import DataEventManager
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nax_entity import NaxEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NAX sensor entities for a config entry."""

    api: DataEventManager = hass.data[DOMAIN][config_entry.entry_id]

    mac_address = (
        (await api.client.http_get("/Device/DeviceInfo/MacAddress") or {})
        .get("content", {})
        .get("Device", {})
        .get("DeviceInfo", {})
        .get("MacAddress")
    )

    nax_device_name = (
        (await api.client.http_get("/Device/DeviceInfo/Name") or {})
        .get("content", {})
        .get("Device", {})
        .get("DeviceInfo", {})
        .get("Name")
    )

    nax_device_manufacturer = (
        (await api.client.http_get("/Device/DeviceInfo/Manufacturer") or {})
        .get("content", {})
        .get("Device", {})
        .get("DeviceInfo", {})
        .get("Manufacturer")
    )

    nax_device_model = (
        (await api.client.http_get("/Device/DeviceInfo/Model") or {})
        .get("content", {})
        .get("Device", {})
        .get("DeviceInfo", {})
        .get("Model")
    )

    source_inputs = (
        (await api.client.http_get("/Device/InputSources/Inputs") or {})
        .get("content", {})
        .get("Device", {})
        .get("InputSources", {})
        .get("Inputs", [])
    )

    if not mac_address or not source_inputs:
        _LOGGER.error("Could not retrieve NAX device MAC address or inputs")
        raise ConfigEntryNotReady("NAX device not available")

    entities_to_add = [
        NaxInputSignalBinarySensor(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            source_input_key=source_input,
            source_input_data=source_inputs[source_input],
        )
        for source_input in source_inputs
    ]

    async_add_entities(entities_to_add)


class NaxInputSignalBinarySensor(NaxEntity, BinarySensorEntity):
    """Representation of a NAX Input Signal Sensor."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        source_input_key: str,
        source_input_data: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
        )
        self._source_input_key = source_input_key
        self._attr_unique_id = (
            f"{format_mac(mac_address)}_{source_input_key}_signal_present"
        )
        self.entity_id = f"sensor.{format_mac(mac_address)}_{source_input_key.lower()}_signal_present"
        self._attr_name = f"{source_input_data.get('Name')} Signal Present"
        self._attr_is_on = source_input_data.get("IsSignalPresent")
        self._attr_icon = "mdi:waveform"

        api.subscribe(
            f"/Device/InputSources/Inputs/{self._source_input_key}/IsSignalPresent",
            self._is_signal_present_update,
        )
        api.subscribe(
            f"/Device/InputSources/Inputs/{self._source_input_key}/Name",
            self._input_name_update,
        )

    @callback
    def _is_signal_present_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the signal presence."""
        self._attr_is_on = message
        self.async_write_ha_state()

    @callback
    def _input_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the input name."""
        self._attr_name = f"{message} Signal Present"
        self.async_write_ha_state()
