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
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, safe_get
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

    nax_device_firmware_version = (
        (await api.client.http_get("/Device/DeviceInfo/DeviceVersion") or {})
        .get("content", {})
        .get("Device", {})
        .get("DeviceInfo", {})
        .get("DeviceVersion")
    )

    nax_device_serial_number = (
        (await api.client.http_get("/Device/DeviceInfo/SerialNumber") or {})
        .get("content", {})
        .get("Device", {})
        .get("DeviceInfo", {})
        .get("SerialNumber")
    )

    source_inputs = safe_get(
        await api.client.http_get("/Device/InputSources/Inputs") or {},
        "content", "Device", "InputSources", "Inputs", default={}
    )

    zone_outputs = safe_get(
        await api.client.http_get("/Device/ZoneOutputs/Zones") or {},
        "content", "Device", "ZoneOutputs", "Zones", default={}
    )

    if not all(
        [
            mac_address,
            nax_device_name,
            nax_device_manufacturer,
            nax_device_model,
            nax_device_firmware_version,
            nax_device_serial_number,
        ]
    ):
        _LOGGER.error("Could not retrieve required NAX device information")
        raise ConfigEntryNotReady("NAX device not available")

    device_params = {
        "api": api,
        "mac_address": mac_address,
        "nax_device_name": nax_device_name,
        "nax_device_manufacturer": nax_device_manufacturer,
        "nax_device_model": nax_device_model,
        "nax_device_firmware_version": nax_device_firmware_version,
        "nax_device_serial_number": nax_device_serial_number,
    }

    entities_to_add: list[BinarySensorEntity] = []

    if source_inputs:
        entities_to_add.extend(
            NaxInputSignalBinarySensor(
                **device_params,
                source_input_key=source_input,
                source_input_data=source_inputs[source_input],
            )
            for source_input in source_inputs
        )

        entities_to_add.extend(
            NaxInputClippingBinarySensor(
                **device_params,
                source_input_key=source_input,
                source_input_data=source_inputs[source_input],
            )
            for source_input in source_inputs
        )

    if zone_outputs:
        entities_to_add.extend(
            NaxZoneOutputSignalBinarySensor(
                **device_params,
                zone_output_key=zone_output,
                zone_output_data=zone_outputs[zone_output],
            )
            for zone_output in zone_outputs
        )

        entities_to_add.extend(
            NaxZoneOutputCastingBinarySensor(
                **device_params,
                zone_output_key=zone_output,
                zone_output_data=zone_outputs[zone_output],
            )
            for zone_output in zone_outputs
        )

        entities_to_add.extend(
            NaxZoneOutputSpeakerClippingBinarySensor(
                **device_params,
                zone_output_key=zone_output,
                zone_output_data=zone_outputs[zone_output],
            )
            for zone_output in zone_outputs
            if zone_outputs[zone_output].get("ZoneAudio", {}).get("IsAmplificationSupported", False)
        )

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
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
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
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._source_input_key = source_input_key
        self._attr_unique_id = (
            f"{mac_address.replace(":", "_").replace(".", "_")}_{source_input_key}_signal_present"
        )
        self._attr_icon = "mdi:waveform"

        # Initialize media player attributes
        self._is_signal_present_update(
            event_name="", message=source_input_data.get("IsSignalPresent", False)
        )
        self._input_name_update(
            event_name="", message=source_input_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
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
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _input_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the input name."""
        self._attr_name = f"{message} Signal Present"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/InputSources/Inputs/{self._source_input_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/InputSources/Inputs/{self._source_input_key}/IsSignalPresent"
        )


class NaxInputClippingBinarySensor(NaxEntity, BinarySensorEntity):
    """Representation of a NAX Input Clipping Sensor."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
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
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._source_input_key = source_input_key
        self._attr_unique_id = (
            f"{mac_address.replace(":", "_").replace(".", "_")}_{source_input_key}_clipping_detected"
        )
        self._attr_icon = "mdi:alert-octagon"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Initialize sensor attributes
        self._is_clipping_detected_update(
            event_name="", message=source_input_data.get("IsClippingDetected", False)
        )
        self._input_name_update(
            event_name="", message=source_input_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/InputSources/Inputs/{self._source_input_key}/IsClippingDetected",
            self._is_clipping_detected_update,
        )
        api.subscribe(
            f"/Device/InputSources/Inputs/{self._source_input_key}/Name",
            self._input_name_update,
        )

    @callback
    def _is_clipping_detected_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the clipping detection."""
        self._attr_is_on = message
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _input_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the input name."""
        self._attr_name = f"{message} Clipping Detected"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/InputSources/Inputs/{self._source_input_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/InputSources/Inputs/{self._source_input_key}/IsClippingDetected"
        )


class NaxZoneOutputSignalBinarySensor(NaxEntity, BinarySensorEntity):
    """Representation of a NAX Zone Output Signal Sensor."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
        zone_output_key: str,
        zone_output_data: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._zone_output_key = zone_output_key
        self._attr_unique_id = (
            f"{mac_address.replace(":", "_").replace(".", "_")}_{zone_output_key}_signal_detected"
        )
        self._attr_icon = "mdi:waveform"

        # Initialize sensor attributes
        self._is_signal_detected_update(
            event_name="", message=zone_output_data.get("IsSignalDetected", False)
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/IsSignalDetected",
            self._is_signal_detected_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _is_signal_detected_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the signal detection."""
        self._attr_is_on = message
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Signal Detected"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/IsSignalDetected"
        )


class NaxZoneOutputCastingBinarySensor(NaxEntity, BinarySensorEntity):
    """Representation of a NAX Zone Output Casting Sensor."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
        zone_output_key: str,
        zone_output_data: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._zone_output_key = zone_output_key
        self._attr_unique_id = (
            f"{mac_address.replace(":", "_").replace(".", "_")}_{zone_output_key}_casting_active"
        )
        self._attr_icon = "mdi:cast"

        # Initialize sensor attributes
        zone_based_providers = zone_output_data.get("ZoneBasedProviders", {})
        self._is_casting_active_update(
            event_name="", message=zone_based_providers.get("IsCastingActive", False)
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneBasedProviders/IsCastingActive",
            self._is_casting_active_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _is_casting_active_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the casting active status."""
        self._attr_is_on = message
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Casting Active"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneBasedProviders/IsCastingActive"
        )


class NaxZoneOutputSpeakerClippingBinarySensor(NaxEntity, BinarySensorEntity):
    """Representation of a NAX Zone Output Speaker Clipping Sensor."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
        zone_output_key: str,
        zone_output_data: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._zone_output_key = zone_output_key
        self._attr_unique_id = (
            f"{mac_address.replace(":", "_").replace(".", "_")}_{zone_output_key}_speaker_clipping_detected"
        )
        self._attr_icon = "mdi:alert-octagon"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Initialize sensor attributes
        zone_audio = zone_output_data.get("ZoneAudio", {})
        speaker_faults = zone_audio.get("Speaker", {}).get("Faults", {})
        self._is_clipping_detected_update(
            event_name="", message=speaker_faults.get("IsClippingDetected", False)
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/Speaker/Faults/IsClippingDetected",
            self._is_clipping_detected_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _is_clipping_detected_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the speaker clipping detection."""
        self._attr_is_on = message
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Speaker Clipping Detected"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/Speaker/Faults/IsClippingDetected"
        )
