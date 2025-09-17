"""Nax Media Players."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from cresnextws import DataEventManager
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

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
    store = config_entry.runtime_data

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

    matrix_routes = (
        (await api.client.http_get("/Device/AvMatrixRouting/Routes") or {})
        .get("content", {})
        .get("Device", {})
        .get("AvMatrixRouting", {})
        .get("Routes", {})
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
            matrix_routes is not None,  # If nothing is switched we get an empty list
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
            zone_matrix_data=matrix_routes.get(zone_output, {}),
            store=store,
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
        zone_matrix_data: dict,
        store: Store,
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
        self.store = store
        self._load_store_task = None
        self._save_store_task = None

        self._attr_unique_id = f"{format_mac(mac_address)}_{zone_output_key.lower()}"
        self.entity_id = (
            f"media_player.{format_mac(mac_address)}_{zone_output_key.lower()}"
        )
        self._attr_entity_registry_visible_default = True
        self._attr_icon = "mdi:audio-video"
        self._attr_volume_step = 0.1

        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER
        self._attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
        )

        # Initialize media player attributes
        self._zone_name_update(event_name="", message=zone_output_data.get("Name", ""))
        self._zone_matrix_audiosource_update(event_name="", message=zone_matrix_data)

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{zone_output_key}/Name",
            self._zone_name_update,
        )
        api.subscribe(
            f"/Device/AvMatrixRouting/Routes/{zone_output_key}",
            self._zone_matrix_audiosource_update,
            match_children=False,
        )

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} Media Player"
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_matrix_audiosource_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone matrix audio source."""
        zone_audio_source = message.get("AudioSource", "")
        if zone_audio_source != "":
            self._attr_state = MediaPlayerState.PLAYING
            self._attr_source = self.__mux_source_name(zone_audio_source)
            self._save_store_task = asyncio.create_task(
                self.async_save_store_last_input(zone_audio_source)
            )
        else:
            self._attr_state = MediaPlayerState.OFF
            self._attr_source = None
        if self.hass is not None:
            self.async_write_ha_state()

    @property
    def source_list(self) -> list[str] | None:
        """List of available input sources."""

    async def async_select_source(self, source: str) -> None:
        """Select input source."""

    async def async_turn_on(self) -> None:
        """Turn the media player on."""

    async def async_turn_off(self) -> None:
        """Turn the media player off."""

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""

    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""

    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""

    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command."""

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""

    @property
    def sound_mode_list(self) -> list[str] | None:
        """List of available sound modes."""
        return ["Off", "Classical", "Jazz", "Pop", "Rock", "SpokenWord"]

    async def async_select_sound_mode(self, sound_mode):
        """Select sound mode."""

    @property
    def sound_mode(self) -> str | None:
        """Return the current sound mode."""

    @property
    def media_content_type(self) -> MediaType | None:
        """Content type of current playing media."""

    # def __mux_source_name(self, input_source: str) -> str:
    #     # if not input_source:
    #     #     return ""
    #     # return f"{self.api.get_input_source_name(input_source)} ({input_source}, {self.api.get_aes67_address_for_input(input_source)})"

    # def __demux_source_name(self, source_name: str) -> str:
    #     # if not source_name:
    #     #     return ""
    #     # return source_name.split(" (", 1)[1][:-1].split(", ", 1)[0]

    # @callback
    # def _current_input_update(self, event_name: str, message: Any) -> None:
    #     """Handle updates to the current input."""
    #     if message in self._source_inputs:
    #         source_name = self._source_inputs[message].get("Name", message)
    #         self._attr_source = source_name
    #         # Update state based on signal presence if available
    #         is_signal_present = self._source_inputs[message].get(
    #             "IsSignalPresent", False
    #         )
    #         self._attr_state = (
    #             MediaPlayerState.PLAYING if is_signal_present else MediaPlayerState.IDLE
    #         )
    # add if self.hass is not None:
    #     self.async_write_ha_state()

    # @callback
    # def _volume_level_update(self, event_name: str, message: Any) -> None:
    #     """Handle updates to the volume level."""
    #     # Assuming volume is in range 0-100, convert to 0.0-1.0
    #     if isinstance(message, (int, float)):
    #         self._attr_volume_level = message / 100.0
    # add if self.hass is not None:
    #     self.async_write_ha_state()

    # @callback
    # def _volume_mute_update(self, event_name: str, message: Any) -> None:
    #     """Handle updates to the mute state."""
    #     self._attr_is_volume_muted = bool(message)
    # add if self.hass is not None:
    #     self.async_write_ha_state()

    # async def async_select_source(self, source: str) -> None:
    #     """Select input source."""
    #     # Find the key for the source name
    #     source_key = None
    #     for key, data in self._source_inputs.items():
    #         if data.get("Name", key) == source:
    #             source_key = key
    #             break

    #     if source_key:
    #         await self.api.client.ws_post(
    #             {"path": "/Device/InputSources/CurrentInput", "value": source_key}
    #         )

    # async def async_set_volume_level(self, volume: float) -> None:
    #     """Set volume level, range 0..1."""
    #     # Convert from 0.0-1.0 to 0-100
    #     volume_level = int(volume * 100)
    #     await self.api.client.ws_post(
    #         {"path": "/Device/Volume/Level", "value": volume_level}
    #     )

    # async def async_mute_volume(self, mute: bool) -> None:
    #     """Mute (True) or unmute (False) the media player."""
    #     await self.api.client.ws_post({"path": "/Device/Volume/Mute", "value": mute})

    # async def async_update(self) -> None:
    #     """Fetch new state data for this entity."""
    #     await super().async_update()
    #     # Update current input
    #     await self.api.client.ws_get("/Device/InputSources/CurrentInput")
    #     # Update volume information
    #     await self.api.client.ws_get("/Device/Volume/Level")
    #     await self.api.client.ws_get("/Device/Volume/Mute")
    #     # Update input source information
    #     for source_key in self._source_inputs:
    #         await self.api.client.ws_get(
    #             f"/Device/InputSources/Inputs/{source_key}/IsSignalPresent"
    #         )

    def __mux_source_name(self, input_source: str) -> str:
        if not input_source:
            return ""
        return f"{self.api.get_input_source_name(input_source)} ({input_source}, {self.api.get_aes67_address_for_input(input_source)})"

    async def async_save_store_last_input(self, last_input: str) -> None:
        """Save the last input source in storage if it changed."""
        storage_data = await self.store.async_load()
        if storage_data is None:
            storage_data = {}
        last_input_dict = storage_data.setdefault(STORAGE_LAST_INPUT_KEY, {})
        if last_input_dict.get(self.zone_output) != last_input:
            last_input_dict[self.zone_output] = last_input
            await self.store.async_save(storage_data)
