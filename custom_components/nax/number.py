"""Nax Number Entities."""

from __future__ import annotations

import logging
from typing import Any

from cresnextws import DataEventManager
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    """Set up NAX number entities for a config entry."""

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

    tone_generator = safe_get(
        await api.client.http_get("/Device/ToneGenerator") or {},
        "content", "Device", "ToneGenerator", default={}
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
        return

    if not all([source_inputs, zone_outputs, tone_generator]):
        return

    entities_to_add = [
        NaxToneGeneratorFrequencyNumber(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
            tone_generator_data=tone_generator,
        )
    ]

    entities_to_add.extend(
        [
            NaxInputCompensationNumber(
                api=api,
                mac_address=mac_address,
                nax_device_name=nax_device_name,
                nax_device_manufacturer=nax_device_manufacturer,
                nax_device_model=nax_device_model,
                nax_device_firmware_version=nax_device_firmware_version,
                nax_device_serial_number=nax_device_serial_number,
                source_input_key=source_input,
                source_input_data=source_inputs[source_input],
            )
            for source_input in source_inputs
        ]
    )

    entities_to_add.extend(
        [
            NaxZoneDefaultVolumeNumber(
                api=api,
                mac_address=mac_address,
                nax_device_name=nax_device_name,
                nax_device_manufacturer=nax_device_manufacturer,
                nax_device_model=nax_device_model,
                nax_device_firmware_version=nax_device_firmware_version,
                nax_device_serial_number=nax_device_serial_number,
                zone_output_key=zone_output,
                zone_output_data=zone_outputs[zone_output],
            )
            for zone_output in zone_outputs
        ]
    )

    entities_to_add.extend(
        [
            NaxZoneMinVolumeNumber(
                api=api,
                mac_address=mac_address,
                nax_device_name=nax_device_name,
                nax_device_manufacturer=nax_device_manufacturer,
                nax_device_model=nax_device_model,
                nax_device_firmware_version=nax_device_firmware_version,
                nax_device_serial_number=nax_device_serial_number,
                zone_output_key=zone_output,
                zone_output_data=zone_outputs[zone_output],
            )
            for zone_output in zone_outputs
        ]
    )

    entities_to_add.extend(
        [
            NaxZoneMaxVolumeNumber(
                api=api,
                mac_address=mac_address,
                nax_device_name=nax_device_name,
                nax_device_manufacturer=nax_device_manufacturer,
                nax_device_model=nax_device_model,
                nax_device_firmware_version=nax_device_firmware_version,
                nax_device_serial_number=nax_device_serial_number,
                zone_output_key=zone_output,
                zone_output_data=zone_outputs[zone_output],
            )
            for zone_output in zone_outputs
        ]
    )

    entities_to_add.extend(
        [
            NaxZoneTestToneVolumeNumber(
                api=api,
                mac_address=mac_address,
                nax_device_name=nax_device_name,
                nax_device_manufacturer=nax_device_manufacturer,
                nax_device_model=nax_device_model,
                nax_device_firmware_version=nax_device_firmware_version,
                nax_device_serial_number=nax_device_serial_number,
                zone_output_key=zone_output,
                zone_output_data=zone_outputs[zone_output],
            )
            for zone_output in zone_outputs
        ]
    )

    async_add_entities(entities_to_add)


class NaxInputCompensationNumber(NaxEntity, NumberEntity):
    """Representation of a NAX Input Compensation Number Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -10.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.CONFIG

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
        """Initialize the number entity."""
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
            f"{mac_address.replace(":", "_").replace(".", "_")}_{source_input_key}_compensation"
        )
        self._attr_icon = "mdi:tune"
        self._attr_native_unit_of_measurement = "dB"

        # Initialize number entity attributes
        source_audio = source_input_data.get("SourceAudio", {})
        self._compensation_update(
            event_name="", message=source_audio.get("Compensation", 0)
        )
        self._input_name_update(
            event_name="", message=source_input_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/InputSources/Inputs/{self._source_input_key}/SourceAudio/Compensation",
            self._compensation_update,
        )
        api.subscribe(
            f"/Device/InputSources/Inputs/{self._source_input_key}/Name",
            self._input_name_update,
        )

    @callback
    def _compensation_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the compensation."""
        # Convert from device value to dB (device stores in tenths)
        self._attr_native_value = message / 10.0
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _input_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the input name."""
        self._attr_name = f"{message} Compensation"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the compensation."""
        # Convert from dB to device value (device stores in tenths)
        device_value = int(value * 10)
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "InputSources": {
                        "Inputs": {
                            self._source_input_key: {
                                "SourceAudio": {
                                    "Compensation": device_value
                                }
                            }
                        }
                    }
                }
            }
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/InputSources/Inputs/{self._source_input_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/InputSources/Inputs/{self._source_input_key}/SourceAudio/Compensation"
        )


class NaxZoneDefaultVolumeNumber(NaxEntity, NumberEntity):
    """Representation of a NAX Zone Default Volume Number Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.CONFIG

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
        """Initialize the number entity."""
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
            f"{mac_address.replace(":", "_").replace(".", "_")}_{zone_output_key}_default_volume"
        )
        self._attr_icon = "mdi:volume-high"
        self._attr_native_unit_of_measurement = "%"

        # Initialize number entity attributes
        zone_audio = zone_output_data.get("ZoneAudio", {})
        self._default_volume_update(
            event_name="", message=zone_audio.get("DefaultVolume", 0)
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/DefaultVolume",
            self._default_volume_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _default_volume_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the default volume."""
        # Convert from 0-1000 range to 0-100 percentage
        self._attr_native_value = message / 10.0
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Default Volume"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the default volume."""
        # Convert from 0-100 percentage to 0-1000 range
        device_value = int(value * 10)
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {
                                    "DefaultVolume": device_value
                                }
                            }
                        }
                    }
                }
            }
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/DefaultVolume"
        )


class NaxZoneMinVolumeNumber(NaxEntity, NumberEntity):
    """Representation of a NAX Zone Minimum Volume Number Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 50
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.CONFIG

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
        """Initialize the number entity."""
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
            f"{mac_address.replace(":", "_").replace(".", "_")}_{zone_output_key}_min_volume"
        )
        self._attr_icon = "mdi:volume-low"
        self._attr_native_unit_of_measurement = "%"

        # Initialize number entity attributes
        zone_audio = zone_output_data.get("ZoneAudio", {})
        self._min_volume_update(
            event_name="", message=zone_audio.get("MinVolume", 0)
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/MinVolume",
            self._min_volume_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _min_volume_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the minimum volume."""
        # Convert from 0-500 range to 0-50 percentage
        self._attr_native_value = message / 10.0
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Minimum Volume"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the minimum volume."""
        # Convert from 0-50 percentage to 0-500 range
        device_value = int(value * 10)
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {
                                    "MinVolume": device_value
                                }
                            }
                        }
                    }
                }
            }
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/MinVolume"
        )


class NaxZoneMaxVolumeNumber(NaxEntity, NumberEntity):
    """Representation of a NAX Zone Maximum Volume Number Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 70
    _attr_native_max_value = 100
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.CONFIG

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
        """Initialize the number entity."""
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
            f"{mac_address.replace(":", "_").replace(".", "_")}_{zone_output_key}_max_volume"
        )
        self._attr_icon = "mdi:volume-high"
        self._attr_native_unit_of_measurement = "%"

        # Initialize number entity attributes
        zone_audio = zone_output_data.get("ZoneAudio", {})
        self._max_volume_update(
            event_name="", message=zone_audio.get("MaxVolume", 1000)
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/MaxVolume",
            self._max_volume_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _max_volume_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the maximum volume."""
        # Convert from 700-1000 range to 70-100 percentage
        self._attr_native_value = message / 10.0
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Maximum Volume"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the maximum volume."""
        # Convert from 70-100 percentage to 700-1000 range
        device_value = int(value * 10)
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {
                                    "MaxVolume": device_value
                                }
                            }
                        }
                    }
                }
            }
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/MaxVolume"
        )


class NaxToneGeneratorFrequencyNumber(NaxEntity, NumberEntity):
    """Representation of a NAX Tone Generator Frequency Number Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 20.0
    _attr_native_max_value = 20000.0
    _attr_native_step = 1.0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
        tone_generator_data: dict,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._attr_unique_id = f"{mac_address.replace(":", "_").replace(".", "_")}_tone_generator_frequency"
        self._attr_icon = "mdi:sine-wave"
        self._attr_native_unit_of_measurement = "Hz"
        self._attr_name = f"{nax_device_name} Tone Generator Frequency"

        # Initialize number entity attributes
        self._frequency_update(
            event_name="", message=tone_generator_data.get("FrequencyInHz", 1000)
        )

        # Subscribe to relevant events
        api.subscribe(
            "/Device/ToneGenerator/FrequencyInHz",
            self._frequency_update,
        )

    @callback
    def _frequency_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the frequency."""
        self._attr_native_value = float(message)
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the tone generator frequency."""
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ToneGenerator": {
                        "FrequencyInHz": int(value)
                    }
                }
            }
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get("/Device/ToneGenerator/FrequencyInHz")


class NaxZoneTestToneVolumeNumber(NaxEntity, NumberEntity):
    """Representation of a NAX Zone Test Tone Volume Number Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 0.1
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        """Initialize the number entity."""
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
            f"{mac_address.replace(":", "_").replace(".", "_")}_{zone_output_key}_test_tone_volume"
        )
        self._attr_icon = "mdi:sine-wave"
        self._attr_native_unit_of_measurement = "%"

        # Initialize number entity attributes
        zone_audio = zone_output_data.get("ZoneAudio", {})
        self._test_tone_volume_update(
            event_name="", message=zone_audio.get("TestToneVolume", 300)
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/TestToneVolume",
            self._test_tone_volume_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _test_tone_volume_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the test tone volume."""
        # Convert from 0-1000 range to 0-100 percentage
        self._attr_native_value = message / 10.0
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Test Tone Volume"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the test tone volume."""
        # Convert from 0-100 percentage to 0-1000 range
        device_value = int(value * 10)
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {
                                    "TestToneVolume": device_value
                                }
                            }
                        }
                    }
                }
            }
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/TestToneVolume"
        )
