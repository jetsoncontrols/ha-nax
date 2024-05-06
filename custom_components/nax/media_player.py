"""Support for Nax media player."""

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
    zone_outputs_names = await hass.async_add_executor_job(
        api.get_all_zone_outputs_names
    )
    serial_number = await hass.async_add_executor_job(api.get_device_serial_number)
    manufacturer = await hass.async_add_executor_job(api.get_device_manufacturer)
    device_model = await hass.async_add_executor_job(api.get_device_model)
    firmware_version = await hass.async_add_executor_job(
        api.get_device_firmware_version
    )
    device_name = await hass.async_add_executor_job(api.get_device_name)

    for zone_output in zone_outputs:
        entities_to_add.append(
            NaxMediaPlayer(
                api=api,
                unique_id=f"{mac_address}_{zone_output}",
                zone_output=zone_output,
                zone_name=zone_outputs_names[zone_output],
                mac_address=mac_address,
                serial_number=serial_number,
                manufacturer=manufacturer,
                device_model=device_model,
                firmware_version=firmware_version,
                device_name=device_name,
            )
        )
    async_add_entities(entities_to_add)


# https://developers.home-assistant.io/docs/core/entity/media-player?_highlight=media
class NaxMediaPlayer(MediaPlayerEntity):
    """Representation of an NAX media player."""

    api: NaxApi = None
    zone_output: str = None
    _entity_id: str = None
    _mac_address: str = None
    _serial_number: str = None
    _manufacturer: str = None
    _device_model: str = None
    _firmware_version: str = None
    _device_name: str = None
    _device_volume: float = None

    _attr_device_class = "speaker"
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
        # | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        api: NaxApi,
        unique_id: str,
        zone_output: str,
        zone_name: str,
        mac_address: str,
        serial_number: str,
        manufacturer: str,
        device_model: str,
        firmware_version: str,
        device_name: str,
    ) -> None:
        self.api = api
        self._attr_unique_id = unique_id
        self.zone_output = zone_output
        self._attr_name = zone_name
        self._mac_address = mac_address
        self._serial_number = serial_number
        self._manufacturer = manufacturer
        self._device_model = device_model
        self._firmware_version = firmware_version
        self._device_name = device_name

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
            connections={(device_registry.CONNECTION_NETWORK_MAC, self._mac_address)},
            identifiers={(DOMAIN, self._serial_number)},
            serial_number=self._serial_number,
            manufacturer=self._manufacturer,
            model=self._device_model,
            sw_version=self._firmware_version,
            name=self._device_name,
        )

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        if self._device_volume is not None:
            return self._device_volume / 1000.0

    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        self._device_volume = await self.hass.async_add_executor_job(
            self.api.get_zone_volume, self.zone_output
        )
        await self.hass.async_add_executor_job(
            self.api.set_zone_volume,
            self.zone_output,
            numpy.clip(self._device_volume + 10.0, 0, 1000),
        )
        self._device_volume = await self.hass.async_add_executor_job(
            self.api.get_zone_volume, self.zone_output
        )

    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        self._device_volume = await self.hass.async_add_executor_job(
            self.api.get_zone_volume, self.zone_output
        )
        await self.hass.async_add_executor_job(
            self.api.set_zone_volume,
            self.zone_output,
            numpy.clip(self._device_volume - 10.0, 0, 1000),
        )
        self._device_volume = await self.hass.async_add_executor_job(
            self.api.get_zone_volume, self.zone_output
        )

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self.hass.async_add_executor_job(
            self.api.set_zone_volume, self.zone_output, volume * 1000.0
        )
        self._device_volume = await self.hass.async_add_executor_job(
            self.api.get_zone_volume, self.zone_output
        )
