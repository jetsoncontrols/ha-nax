"""Nax Media Players."""

from __future__ import annotations

import logging
from typing import Any

from cresnextws import DataEventManager
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
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
    """Set up NAX media player entities for a config entry."""

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
            zone_outputs,
        ]
    ):
        _LOGGER.error("Could not retrieve required NAX device information")
        raise ConfigEntryNotReady("NAX device not available")

    entities_to_add = [
        NaxMediaPlayer(
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

    async_add_entities(entities_to_add)


class NaxMediaPlayer(NaxEntity, MediaPlayerEntity):
    """Representation of a NAX Media Player."""

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
        """Initialize the media player."""
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
        stopping here for today
        self._attr_unique_id = f"{format_mac(mac_address)}_media_player"
        self.entity_id = f"media_player.{format_mac(mac_address)}_nax_player"
        self._attr_name = f"{nax_device_name} Media Player"
        self._attr_icon = "mdi:audio-video"

        # Initialize media player attributes
        self._attr_state = MediaPlayerState.IDLE
        self._attr_supported_features = (
            MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )
        self._attr_source_list = [
            source_inputs[key].get("Name", key) for key in source_inputs
        ]
        self._attr_source = None
        self._attr_volume_level = 0.5
        self._attr_is_volume_muted = False

        # Subscribe to relevant events
        api.subscribe(
            "/Device/InputSources/CurrentInput",
            self._current_input_update,
        )
        api.subscribe(
            "/Device/Volume/Level",
            self._volume_level_update,
        )
        api.subscribe(
            "/Device/Volume/Mute",
            self._volume_mute_update,
        )

    @callback
    def _current_input_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the current input."""
        if message in self._source_inputs:
            source_name = self._source_inputs[message].get("Name", message)
            self._attr_source = source_name
            # Update state based on signal presence if available
            is_signal_present = self._source_inputs[message].get(
                "IsSignalPresent", False
            )
            self._attr_state = (
                MediaPlayerState.PLAYING if is_signal_present else MediaPlayerState.IDLE
            )
        self.async_write_ha_state()

    @callback
    def _volume_level_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the volume level."""
        # Assuming volume is in range 0-100, convert to 0.0-1.0
        if isinstance(message, (int, float)):
            self._attr_volume_level = message / 100.0
        self.async_write_ha_state()

    @callback
    def _volume_mute_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the mute state."""
        self._attr_is_volume_muted = bool(message)
        self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        # Find the key for the source name
        source_key = None
        for key, data in self._source_inputs.items():
            if data.get("Name", key) == source:
                source_key = key
                break

        if source_key:
            await self.api.client.ws_post(
                {"path": "/Device/InputSources/CurrentInput", "value": source_key}
            )

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        # Convert from 0.0-1.0 to 0-100
        volume_level = int(volume * 100)
        await self.api.client.ws_post(
            {"path": "/Device/Volume/Level", "value": volume_level}
        )

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (True) or unmute (False) the media player."""
        await self.api.client.ws_post({"path": "/Device/Volume/Mute", "value": mute})

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        # Update current input
        await self.api.client.ws_get("/Device/InputSources/CurrentInput")
        # Update volume information
        await self.api.client.ws_get("/Device/Volume/Level")
        await self.api.client.ws_get("/Device/Volume/Mute")
        # Update input source information
        for source_key in self._source_inputs:
            await self.api.client.ws_get(
                f"/Device/InputSources/Inputs/{source_key}/IsSignalPresent"
            )
