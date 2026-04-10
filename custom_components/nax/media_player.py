"""Nax Media Players."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.util.dt import utcnow

import deepmerge

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
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_LAST_AES67_STREAM_KEY, STORAGE_LAST_INPUT_KEY
from .mp2 import NaxMP2Client
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

    input_sources = (
        (await api.client.http_get("/Device/InputSources/Inputs") or {})
        .get("content", {})
        .get("Device", {})
        .get("InputSources", {})
        .get("Inputs", {})
    )

    matrix_routes = (
        (await api.client.http_get("/Device/AvMatrixRouting/Routes") or {})
        .get("content", {})
        .get("Device", {})
        .get("AvMatrixRouting", {})
        .get("Routes", {})
    )

    nax_tx = (
        (await api.client.http_get("/Device/NaxAudio/NaxTx") or {})
        .get("content", {})
        .get("Device", {})
        .get("NaxAudio", {})
        .get("NaxTx", {})
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
            input_sources,
            matrix_routes is not None,  # If nothing is switched we get an empty list
            nax_tx,
        ]
    ):
        _LOGGER.error("Could not retrieve required NAX device information")
        return

    # Detect MP2 availability (gracefully returns None if not available)
    mp2_info = await NaxMP2Client.detect(api.client, zone_outputs, input_sources)

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
            input_sources_data=input_sources,
            zone_matrix_data=matrix_routes.get(zone_output, {}),
            nax_tx_data=nax_tx,
            store=store,
            mp2_player_id=(
                mp2_info["player_map"].get(zone_output) if mp2_info else None
            ),
            mp2_profile_key=(
                mp2_info["profile_key"] if mp2_info else None
            ),
            mp2_streaming_input_key=(
                mp2_info["streaming_input_map"].get(zone_output) if mp2_info else None
            ),
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
        input_sources_data: dict,
        zone_matrix_data: dict,
        nax_tx_data: dict,
        store: Store,
        mp2_player_id: str | None = None,
        mp2_profile_key: str | None = None,
        mp2_streaming_input_key: str | None = None,
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
        self._store = store
        self._load_store_task = None
        self._save_store_task = None
        self._input_sources = input_sources_data
        self._nax_tx = nax_tx_data

        # Initialize media player attributes
        self._attr_unique_id = f"{mac_address.replace(':', '_').replace('.', '_')}_{zone_output_key.lower()}"
        self._attr_entity_registry_visible_default = True
        self._attr_icon = "mdi:audio-video"
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
        self._attr_volume_step = 0.01
        # MP2 setup (must be before initial callback invocations)
        self._mp2: NaxMP2Client | None = None
        self._mp2_player_id = mp2_player_id
        self._mp2_streaming_input_key = mp2_streaming_input_key
        self._mp2_player_state: str | None = None
        self._mp2_stream_state: str | None = None
        self._current_audio_source: str = zone_matrix_data.get("AudioSource", "")

        if mp2_player_id and mp2_profile_key:
            self._mp2 = NaxMP2Client(api.client, mp2_player_id, mp2_profile_key)
            self._attr_supported_features |= (
                MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.NEXT_TRACK
                | MediaPlayerEntityFeature.PREVIOUS_TRACK
                | MediaPlayerEntityFeature.SEEK
            )

        # Initialize state from device data
        self._zone_name_update(event_name="", message=zone_output_data.get("Name", ""))
        self._zone_volume_update(
            event_name="",
            message=zone_output_data.get("ZoneAudio", {}).get("Volume", 0),
        )
        self._zone_mute_update(
            event_name="",
            message=zone_output_data.get("ZoneAudio", {}).get("IsMuted", False),
        )
        self._zone_sound_mode_update(
            event_name="",
            message=zone_output_data.get("ZoneAudio", {}).get("ToneProfile", "Off"),
        )
        self._zone_matrix_audiosource_update(event_name="", message=zone_matrix_data)
        self._input_sources_update(event_name="", message=None)  # None bypasses merge
        self._zone_aes67_receiver_key = zone_output_data.get("NaxRxStream", "")
        self._attr_sound_mode_list = [
            "Off",
            "Classical",
            "Jazz",
            "Pop",
            "Rock",
            "SpokenWord",
        ]

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{zone_output_key}/Name",
            self._zone_name_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{zone_output_key}/ZoneAudio/Volume",
            self._zone_volume_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{zone_output_key}/ZoneAudio/IsMuted",
            self._zone_mute_update,
        )
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{zone_output_key}/ZoneAudio/ToneProfile",
            self._zone_sound_mode_update,
        )
        api.subscribe(
            "/Device/InputSources/Inputs",
            self._input_sources_update,
            full_message=True,
        )
        api.subscribe(
            "/Device/NaxAudio/NaxTx",
            self._nax_tx_update,
            full_message=True,
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
    def _zone_volume_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone volume."""
        if isinstance(message, (int, float)):
            self._attr_volume_level = message / 1000.0
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_mute_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone mute state."""
        self._attr_is_volume_muted = bool(message)
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_sound_mode_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone sound mode."""
        if isinstance(message, str) and message in (self.sound_mode_list or []):
            self._attr_sound_mode = message
        else:
            self._attr_sound_mode = "Off"
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_matrix_audiosource_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone matrix audio source."""
        zone_audio_source_key = message.get("AudioSource", "")
        self._current_audio_source = zone_audio_source_key
        zone_audio_source_name, zone_audio_source_aes67_address = (
            self.__get_source_name_and_address_by_key(zone_audio_source_key)
        )

        if zone_audio_source_key and zone_audio_source_name:
            self._attr_source = self.__mux_source_name(
                input_source_key=zone_audio_source_key,
                input_source_name=zone_audio_source_name,
                input_source_aes67_address=zone_audio_source_aes67_address,
            )
            self._save_store_task = asyncio.create_task(
                self.__async_save_store_last_input(zone_audio_source_key)
            )
        else:
            self._attr_source = None

        self._update_state_from_context()

        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _input_sources_update(self, event_name: str, message: Any | None) -> None:
        """Handle updates to the input sources."""
        if message is not None:
            deepmerge.always_merger.merge(
                self._input_sources,
                message.get("Device", {}).get("InputSources", {}).get("Inputs", {}),
            )

        self._attr_source_list = [
            self.__mux_source_name(
                input_source_key=input_source,
                input_source_name=name,
                input_source_aes67_address=address,
            )
            for input_source in self._input_sources
            for name, address in [
                self.__get_source_name_and_address_by_key(input_source)
            ]
        ]

        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _nax_tx_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the NAX TX data."""
        if message is not None:
            deepmerge.always_merger.merge(
                self._nax_tx,
                message.get("Device", {}).get("NaxAudio", {}).get("NaxTx", {}),
            )
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _mp2_player_update(self, event_name: str, message: Any) -> None:
        """Handle push events from the MP2 player."""
        if message is None:
            return

        player_data = (
            message.get("Device", {})
            .get("MediaPlayerNeXt", {})
            .get("Players", {})
            .get(self._mp2_player_id, {})
        )
        if not player_data:
            return

        # Track player and stream state
        if "PlayerState" in player_data:
            self._mp2_player_state = player_data["PlayerState"]
        if "StreamState" in player_data:
            self._mp2_stream_state = player_data["StreamState"]

        # Extract NowPlayingData
        now_playing = player_data.get("Player", {}).get("NowPlayingData", {})
        if now_playing:
            title = now_playing.get("TrackTitle", "").strip()
            artist = now_playing.get("ArtistName", "").strip()
            album = now_playing.get("AlbumName", "").strip()
            art_url = now_playing.get("AlbumArtUrl", "").strip()
            duration = now_playing.get("Duration")
            elapsed = now_playing.get("ElapsedSec")

            self._attr_media_title = title if title else None
            self._attr_media_artist = artist if artist else None
            self._attr_media_album_name = album if album else None
            self._attr_media_image_url = art_url if art_url else None
            if isinstance(duration, (int, float)) and duration > 0:
                self._attr_media_duration = duration
            else:
                self._attr_media_duration = None
            if isinstance(elapsed, (int, float)):
                self._attr_media_position = elapsed
                self._attr_media_position_updated_at = utcnow()
            else:
                self._attr_media_position = None

        # Update entity state based on current audio source
        self._update_state_from_context()

        if self.hass is not None:
            self.async_write_ha_state()

    def _update_state_from_context(self) -> None:
        """Derive entity state from the current audio source and MP2 player state."""
        if not self._current_audio_source:
            # No input routed
            self._attr_state = MediaPlayerState.OFF
            self._attr_media_content_type = None
            return

        if (
            self._mp2
            and self._current_audio_source == self._mp2_streaming_input_key
        ):
            # Zone is on its streaming input — state follows MP2 player
            self._attr_media_content_type = MediaType.MUSIC
            if self._mp2_player_state == "playing":
                self._attr_state = MediaPlayerState.PLAYING
            elif self._mp2_player_state == "paused":
                self._attr_state = MediaPlayerState.PAUSED
            else:
                self._attr_state = MediaPlayerState.IDLE
        else:
            # Zone is on a non-streaming input — playing as before
            self._attr_state = MediaPlayerState.PLAYING
            self._attr_media_content_type = MediaType.MUSIC
            # Clear MP2 media attributes when not on streaming input
            self._attr_media_title = None
            self._attr_media_artist = None
            self._attr_media_album_name = None
            self._attr_media_image_url = None
            self._attr_media_duration = None
            self._attr_media_position = None

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "AvMatrixRouting": {
                        "Routes": {
                            self._zone_output_key: {
                                "AudioSource": self.__demux_source_name(source)
                            }
                        }
                    }
                }
            }
        )

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        last_input = await self.__async_load_store_last_input()
        last_aes67_stream = await self.__async_load_store_last_aes67_stream()
        if last_input:
            await self.__set_zone_audio_matrix_route(input_source_key=last_input)
            if (
                last_input == "Aes67"
                and last_aes67_stream
                and self._zone_aes67_receiver_key
            ):
                await self.__set_zone_aes67_stream(aes67_address=last_aes67_stream)
        elif self._input_sources:
            await self.__set_zone_audio_matrix_route(next(iter(self._input_sources)))

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self.__set_zone_audio_matrix_route(input_source_key="")

    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        if self.volume_level is None:
            return
        new_volume = min(self.volume_level + self._attr_volume_step, 1.0)
        await self.async_set_volume_level(new_volume)

    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        if self.volume_level is None:
            return
        new_volume = max(self.volume_level - self._attr_volume_step, 0.0)
        await self.async_set_volume_level(new_volume)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        # Convert from 0.0-1.0 to 0-1000
        volume_level = int(volume * 1000)
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {"Volume": volume_level}
                            }
                        }
                    }
                }
            }
        )

    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command."""
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {"ZoneAudio": {"IsMuted": mute}}
                        }
                    }
                }
            }
        )

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select sound mode."""
        if sound_mode not in (self.sound_mode_list or []):
            _LOGGER.error("Invalid sound mode selected: %s", sound_mode)
            return
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ZoneOutputs": {
                        "Zones": {
                            self._zone_output_key: {
                                "ZoneAudio": {
                                    "ToneProfile": sound_mode,
                                }
                            }
                        }
                    }
                }
            }
        )

    def _schedule_mp2_refresh(self, delay: float = 1.0) -> None:
        """Schedule a delayed MP2 state refresh via HTTP poll."""
        if not self._mp2 or not self._mp2_player_id or self.hass is None:
            return

        async def _do_refresh(_now=None) -> None:
            resp = await self.api.client.http_get(
                f"/Device/MediaPlayerNeXt/Players/{self._mp2_player_id}"
            )
            if resp:
                self._mp2_player_update(
                    event_name="",
                    message=resp.get("content", {}),
                )

        self.hass.loop.call_later(
            delay, lambda: asyncio.ensure_future(_do_refresh())
        )

    def _set_mp2_state_optimistic(self, state: str) -> None:
        """Optimistically set the MP2 player state and update entity."""
        self._mp2_player_state = state
        self._update_state_from_context()
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media from a URL."""
        if self._mp2 is None:
            _LOGGER.warning("MP2 not available for %s", self.name)
            return
        # Route zone to its streaming input if not already there
        if self._current_audio_source != self._mp2_streaming_input_key:
            await self.__set_zone_audio_matrix_route(self._mp2_streaming_input_key)
        await self._mp2.load_source(media_id)
        self._set_mp2_state_optimistic("playing")
        self._schedule_mp2_refresh(delay=2.0)

    async def async_media_play(self) -> None:
        """Send play command."""
        if self._mp2 is None:
            return
        await self._mp2.play()
        self._set_mp2_state_optimistic("playing")
        self._schedule_mp2_refresh()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        if self._mp2 is None:
            return
        await self._mp2.pause()
        self._set_mp2_state_optimistic("paused")
        self._schedule_mp2_refresh()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        if self._mp2 is None:
            return
        await self._mp2.next_track()
        self._set_mp2_state_optimistic("playing")
        self._schedule_mp2_refresh(delay=2.0)

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        if self._mp2 is None:
            return
        await self._mp2.previous_track()
        self._set_mp2_state_optimistic("playing")
        self._schedule_mp2_refresh(delay=2.0)

    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        if self._mp2 is None:
            return
        await self._mp2.seek(position)
        self._schedule_mp2_refresh()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/Volume"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/IsMuted"
        )
        await self.api.client.ws_get(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/ZoneAudio/ToneProfile"
        )
        await self.api.client.ws_get("/Device/InputSources/Inputs")
        await self.api.client.ws_get("/Device/NaxAudio/NaxTx")
        await self.api.client.ws_get(
            f"/Device/AvMatrixRouting/Routes/{self._zone_output_key}"
        )
        if self._mp2 and self._mp2_player_id:
            await self.api.client.ws_get(
                f"/Device/MediaPlayerNeXt/Players/{self._mp2_player_id}"
            )

    # Helper methods
    async def __set_zone_audio_matrix_route(self, input_source_key: str) -> None:
        """Set the audio matrix route for the zone."""
        if input_source_key is None:
            return
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "AvMatrixRouting": {
                        "Routes": {
                            self._zone_output_key: {"AudioSource": input_source_key}
                        }
                    }
                }
            }
        )

    async def __set_zone_aes67_stream(self, aes67_address: str) -> None:
        """Set the AES67 stream for the zone."""
        if not aes67_address or not self._zone_aes67_receiver_key:
            return
        await self.api.client.ws_post(
            payload={
                "Device": {
                    "NaxAudio": {
                        "NaxRx": {
                            "NaxRxStreams": {
                                self._zone_output_key: {
                                    "NetworkAddressRequested": aes67_address,
                                }
                            }
                        }
                    }
                }
            }
        )

    def __get_source_name_and_address_by_key(
        self, input_source_key: str
    ) -> tuple[str, str | None]:
        input_source_name = (
            self._input_sources.get(input_source_key, {}).get("Name", "")
            if input_source_key in self._input_sources
            else ""
        )
        input_source_aes67_stream_key = self._input_sources.get(
            input_source_key, {}
        ).get("NaxTxStream", "")
        input_source_aes67_address = (
            self._nax_tx.get("NaxTxStreams", {})
            .get(input_source_aes67_stream_key, {})
            .get("NetworkAddressStatus", None)
            if input_source_key in self._input_sources
            else None
        )
        return input_source_name, input_source_aes67_address

    def __mux_source_name(
        self,
        input_source_key: str,
        input_source_name: str,
        input_source_aes67_address: str | None,
    ) -> str:
        if not input_source_key or not input_source_name:
            return ""
        return f"{input_source_name} ({input_source_key}, {input_source_aes67_address})"

    def __demux_source_name(self, source_name: str) -> str:
        if not source_name:
            return ""
        return source_name.split(" (", 1)[1][:-1].split(", ", 1)[0]

    async def __async_save_store_last_input(self, last_input: str) -> None:
        """Save the last input source in storage if it changed."""
        storage_data = await self._store.async_load()
        if storage_data is None:
            storage_data = {}
        last_input_dict = storage_data.setdefault(STORAGE_LAST_INPUT_KEY, {})
        if last_input_dict.get(self._zone_output_key) != last_input:
            last_input_dict[self._zone_output_key] = last_input
            await self._store.async_save(storage_data)

    async def __async_load_store_last_input(self) -> str | None:
        """Load the store data asynchronously."""
        storage_data = await self._store.async_load()
        if storage_data is None:
            return None
        return storage_data.get(STORAGE_LAST_INPUT_KEY, {}).get(self._zone_output_key)

    async def __async_load_store_last_aes67_stream(self) -> str | None:
        """Load the store data asynchronously."""
        storage_data = await self._store.async_load()
        if storage_data is None:
            return None
        return storage_data.get(STORAGE_LAST_AES67_STREAM_KEY, {}).get(
            self._zone_output_key
        )
