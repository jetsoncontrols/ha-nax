"""Nax Switch Entities."""

from __future__ import annotations

import logging
from typing import Any

from cresnextws import DataEventManager
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nax_entity import NaxEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NAX switch entities for a config entry."""

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

    tone_generator = (
        (await api.client.http_get("/Device/ToneGenerator") or {})
        .get("content", {})
        .get("Device", {})
        .get("ToneGenerator", {})
    )

    zone_outputs = (
        (await api.client.http_get("/Device/ZoneOutputs/Zones") or {})
        .get("content", {})
        .get("Device", {})
        .get("ZoneOutputs", {})
        .get("Zones", [])
    )

    if not all(
        [
            mac_address,
            nax_device_name,
            nax_device_manufacturer,
            nax_device_model,
            nax_device_firmware_version,
            nax_device_serial_number,
            tone_generator is not None,
            zone_outputs,
        ]
    ):
        _LOGGER.error("Could not retrieve required NAX device information")
        return

    entities_to_add = [
        NaxToneGeneratorLeftChannelSwitch(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
            tone_generator_data=tone_generator,
        ),
        NaxToneGeneratorRightChannelSwitch(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
            tone_generator_data=tone_generator,
        ),
    ]

    # Add zone test tone switches
    entities_to_add.extend(
        [
            NaxZoneTestToneSwitch(
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


class NaxToneGeneratorLeftChannelSwitch(NaxEntity, SwitchEntity):
    """Representation of a NAX Tone Generator Left Channel Switch."""

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
        """Initialize the switch entity."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )

        # Initialize attributes
        self._attr_unique_id = (
            f"{mac_address.replace(":", "_")}_tone_generator_left_channel"
        )
        self.entity_id = f"switch.{self._attr_unique_id}"
        self._attr_name = f"{nax_device_name} Tone Generator Left Channel"
        self._attr_icon = "mdi:sine-wave"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._left_channel_update(
            event_name="",
            message=tone_generator_data.get("IsLeftChannelEnabled", True),
        )

        # Subscribe to relevant events
        api.subscribe(
            "/Device/ToneGenerator/IsLeftChannelEnabled",
            self._left_channel_update,
        )

    @callback
    def _left_channel_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the left channel state."""
        self._attr_is_on = message
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the left channel."""
        await self.api.client.ws_post(
            payload={"Device": {"ToneGenerator": {"IsLeftChannelEnabled": True}}}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the left channel."""
        await self.api.client.ws_post(
            payload={"Device": {"ToneGenerator": {"IsLeftChannelEnabled": False}}}
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get("/Device/ToneGenerator/IsLeftChannelEnabled")


class NaxToneGeneratorRightChannelSwitch(NaxEntity, SwitchEntity):
    """Representation of a NAX Tone Generator Right Channel Switch."""

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
        """Initialize the switch entity."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )

        # Initialize attributes
        self._attr_unique_id = (
            f"{mac_address.replace(":", "_")}_tone_generator_right_channel"
        )
        self.entity_id = f"switch.{self._attr_unique_id}"
        self._attr_name = f"{nax_device_name} Tone Generator Right Channel"
        self._attr_icon = "mdi:sine-wave"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._right_channel_update(
            event_name="",
            message=tone_generator_data.get("IsRightChannelEnabled", True),
        )

        # Subscribe to relevant events
        api.subscribe(
            "/Device/ToneGenerator/IsRightChannelEnabled",
            self._right_channel_update,
        )

    @callback
    def _right_channel_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the right channel state."""
        self._attr_is_on = message
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the right channel."""
        await self.api.client.ws_post(
            payload={"Device": {"ToneGenerator": {"IsRightChannelEnabled": True}}}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the right channel."""
        await self.api.client.ws_post(
            payload={"Device": {"ToneGenerator": {"IsRightChannelEnabled": False}}}
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get("/Device/ToneGenerator/IsRightChannelEnabled")


class NaxZoneTestToneSwitch(NaxEntity, SwitchEntity):
    """Representation of a NAX Zone Test Tone Switch."""

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
        """Initialize the switch entity."""
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

        # Initialize attributes
        self._attr_unique_id = f"{mac_address.replace(":", "_")}_{zone_output_key}_test_tone"
        self.entity_id = f"switch.{self._attr_unique_id}"
        self._attr_icon = "mdi:sine-wave"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
        zone_audio = zone_output_data.get("ZoneAudio", {})
        self._test_tone_update(
            event_name="",
            message=zone_audio.get("IsTestToneActive", False),
        )
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/IsTestToneActive",
            self._test_tone_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )

    @callback
    def _test_tone_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the test tone state."""
        self._attr_is_on = message
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Test Tone"
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the test tone."""
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {"IsTestToneActive": True}
                            }
                        }
                    }
                }
            }
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the test tone."""
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {"IsTestToneActive": False}
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
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/IsTestToneActive"
        )
