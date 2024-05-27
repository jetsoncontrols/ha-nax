"""Support for Nax media player."""

from typing import Any

import numpy

from config.custom_components.nax import NaxEntity
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nax.nax_api import NaxApi


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load NAX media players"""
    entities_to_add = []
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = await hass.async_add_executor_job(api.get_device_mac_address)
    zone_outputs = await hass.async_add_executor_job(api.get_all_zone_outputs)

    for zone_output in zone_outputs:
        entities_to_add.append(
            NaxMediaPlayer(
                api=api,
                unique_id=f"{mac_address}_{zone_output}",
                zone_output=zone_output,
            )
        )
    async_add_entities(entities_to_add)


# https://developers.home-assistant.io/docs/core/entity/media-player
class NaxMediaPlayer(NaxEntity, MediaPlayerEntity):
    """Representation of an NAX media player."""

    _attr_device_class = "speaker"
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SELECT_SOUND_MODE
    )

    def __init__(
        self,
        api: NaxApi,
        unique_id: str,
        zone_output: str,
    ) -> None:
        super().__init__(api=api, unique_id=unique_id)
        self.entity_id = f"media_player.{self._attr_unique_id}"
        self.zone_output = zone_output
        self._attr_entity_registry_visible_default = True
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name", self._generic_update
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Volume",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.IsMuted",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.AvMatrixRouting.Routes.{self.zone_output}",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.ToneProfile",
            self._generic_update,
        )
        input_sources = self.api.get_input_sources()
        for input_source in input_sources:
            self.api.subscribe_data_updates(
                f"Device.InputSources.Inputs.{input_source}.Name", self._generic_update
            )
        self.api.subscribe_connection_updates(self._update_connection)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)}"

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device."""
        if self.api.get_zone_audio_source(self.zone_output) is not None:
            return MediaPlayerState.PLAYING
        return MediaPlayerState.IDLE

    @property
    def media_content_type(self) -> MediaType | None:
        """Content type of current playing media."""
        if self.api.get_zone_audio_source(self.zone_output) is not None:
            return MediaType.MUSIC
        return None

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        return self.api.get_zone_volume(self.zone_output) / 1000.0

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        return self.api.get_zone_muted(self.zone_output)

    @property
    def volume_step(self) -> float:
        """Volume step value."""
        return 0.1

    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        await self.api.set_zone_volume(
            self.zone_output,
            numpy.clip(
                self.api.get_zone_volume(self.zone_output) + self.volume_step * 100,
                0,
                1000,
            ),
        )

    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        await self.api.set_zone_volume(
            self.zone_output,
            numpy.clip(
                self.api.get_zone_volume(self.zone_output) - self.volume_step * 100,
                0,
                1000,
            ),
        )

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self.api.set_zone_volume(self.zone_output, volume * 1000.0)

    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command."""
        await self.api.set_zone_mute(self.zone_output, mute)

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self.api.set_zone_audio_source(self.zone_output, "")

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        zone_audio_source = self.api.get_zone_audio_source(self.zone_output)
        if zone_audio_source:
            return self.__mux_source_name(zone_audio_source)
        return None

    @property
    def source_list(self) -> list[str] | None:
        """List of available input sources."""
        result = []
        input_sources = self.api.get_input_sources()
        if input_sources:
            for input_source in input_sources:
                result.append(self.__mux_source_name(input_source))
        return result

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        await self.api.set_zone_audio_source(
            self.zone_output, self.__demux_source_name(source)
        )

    @property
    def sound_mode(self) -> str | None:
        """Return the current sound mode."""
        return self.api.get_zone_tone_profile(self.zone_output)

    async def async_select_sound_mode(self, sound_mode):
        """Select sound mode."""
        await self.api.set_zone_tone_profile(self.zone_output, sound_mode)

    @property
    def sound_mode_list(self) -> list[str] | None:
        """List of available sound modes."""
        return ["Off", "Classical", "Jazz", "Pop", "Rock", "SpokenWord"]

    def __mux_source_name(self, input_source: str) -> str:
        if not input_source:
            return ""
        return f"{self.api.get_input_source_name(input_source)} ({input_source})"

    def __demux_source_name(self, source_name: str) -> str:
        if not source_name:
            return ""
        return source_name.split(" (", 1)[1][:-1]
