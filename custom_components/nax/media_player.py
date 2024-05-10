"""Support for Nax media player."""

import threading
from typing import Any
import logging
import numpy
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.helpers import device_registry
from .nax.nax_api import NaxApi

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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


# https://developers.home-assistant.io/docs/core/entity/media-player?_highlight=media
class NaxMediaPlayer(MediaPlayerEntity):
    """Representation of an NAX media player."""

    api: NaxApi = None
    zone_output: str = None
    _entity_id: str = None

    _attr_device_class = "speaker"
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
        # | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(
        self,
        api: NaxApi,
        unique_id: str,
        zone_output: str,
    ) -> None:
        self.api = api
        self._attr_unique_id = unique_id
        self.zone_output = zone_output

        threading.Timer(1.0, self.subscribe_api_data_updates).start()

    def subscribe_api_data_updates(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Volume",
            self._update_volume,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.IsMuted",
            self._update_mute,
        )
        self.api.subscribe_data_updates(
            f"Device.AvMatrixRouting.Routes.{self.zone_output}.AudioSource",
            self._update_zone_audio_source,
        )

    @callback
    def _update_volume(self, path: str, data: Any) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _update_mute(self, path: str, data: Any) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _update_zone_audio_source(self, path: str, data: Any) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @property
    def should_poll(self) -> bool:
        """Return if hass should poll this entity"""
        return False

    @property
    def unique_id(self) -> str:
        """Set unique device_id"""
        return self._attr_unique_id

    @property
    def entity_id(self) -> str:
        """Provide an entity ID"""
        if self._entity_id is None:
            self._entity_id = f"media_player.{self._attr_unique_id}"
        return self._entity_id

    @entity_id.setter
    def entity_id(self, new_entity_id) -> None:
        self._entity_id = new_entity_id

    @property
    def name(self) -> str:
        return self.api.get_zone_name(self.zone_output)

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device."""
        logged_in = self.api.get_logged_in()
        if logged_in is False:
            return None
        return MediaPlayerState.IDLE

    @property
    def available(self) -> bool:
        """Could the resource be accessed during the last update call."""
        return self.api.get_logged_in()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            configuration_url=self.api.get_base_url(),
            connections={
                (
                    device_registry.CONNECTION_NETWORK_MAC,
                    self.api.get_device_mac_address(),
                )
            },
            identifiers={(DOMAIN, self.api.get_device_serial_number())},
            serial_number=self.api.get_device_serial_number(),
            manufacturer=self.api.get_device_manufacturer(),
            model=self.api.get_device_model(),
            sw_version=self.api.get_device_firmware_version(),
            name=self.api.get_device_name(),
        )

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
        if zone_audio_source is not None:
            return self.__mux_source_name(zone_audio_source)
        return None

    @property
    def source_list(self) -> list[str] | None:
        """List of available input sources."""
        result = []
        input_sources = self.api.get_input_sources()
        for input_source in input_sources:
            result.append(self.__mux_source_name(input_source))
        return result

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        await self.api.set_zone_audio_source(
            self.zone_output, self.__demux_source_name(source)
        )

    def __mux_source_name(self, input_source: str) -> str:
        return f"{input_source} ({self.api.get_input_source_name(input_source)})"

    def __demux_source_name(self, source_name: str) -> str:
        if not source_name:
            return ""
        source_split = source_name.split(" (", 1)
        # source_name = source_split[1][:-1]
        source = source_split[0]
        print(f"source_split: {source_split}")
        return source
