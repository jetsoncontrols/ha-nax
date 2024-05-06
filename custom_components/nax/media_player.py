"""Support for Nax media player."""

import logging
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
    RepeatMode,
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
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]
    device_info = await hass.async_add_executor_job(
        api.get_request, "/Device/DeviceInfo"
    )

    entities_to_add = []
    zone_outputs_json = await hass.async_add_executor_job(
        api.get_request, "/Device/ZoneOutputs"
    )
    for zone_output in zone_outputs_json["Device"]["ZoneOutputs"]["Zones"]:
        entities_to_add.append(
            NaxMediaPlayer(
                zone_name=zone_outputs_json["Device"]["ZoneOutputs"]["Zones"][
                    zone_output
                ]["Name"],
                zone_output=zone_output,
                device_name=device_info["Device"]["DeviceInfo"]["Name"],
                mac_address=device_info["Device"]["DeviceInfo"]["MacAddress"],
                manufacturer=device_info["Device"]["DeviceInfo"]["Manufacturer"],
                device_model=device_info["Device"]["DeviceInfo"]["Model"],
                firmware_version=device_info["Device"]["DeviceInfo"]["DeviceVersion"],
                serial_number=device_info["Device"]["DeviceInfo"]["SerialNumber"],
                api=api,
            )
        )
    async_add_entities(entities_to_add)


# https://developers.home-assistant.io/docs/core/entity/media-player?_highlight=media
class NaxMediaPlayer(MediaPlayerEntity):
    """Representation of an NAX media player."""

    zone_name: str = None
    zone_output: str = None
    mac_address: str = None
    _unique_id: str = None
    _entity_id: str = None
    api: NaxApi = None

    def __init__(
        self,
        zone_name: str,
        zone_output: str,
        device_name: str,
        mac_address: str,
        manufacturer: str,
        device_model: str,
        firmware_version: str,
        serial_number: str,
        api: NaxApi,
    ) -> None:
        self.zone_name = zone_name
        self.zone_output = zone_output
        self.mac_address = mac_address
        self._unique_id = f"{mac_address}_{zone_output}"
        self.api = api
        self._attr_device_info = DeviceInfo(
            configuration_url=api.get_base_url(),
            connections={(device_registry.CONNECTION_NETWORK_MAC, mac_address)},
            identifiers={(DOMAIN, serial_number)},
            serial_number=serial_number,
            manufacturer=manufacturer,
            model=device_model,
            sw_version=firmware_version,
            name=device_name,
        )

    @property
    def name(self, name: str):
        """Set the name of the device."""
        self.zone_name = name

    @property
    def name(self) -> str | None:
        """Return the name of the device."""
        return self.zone_name

    @property
    def unique_id(self) -> str:
        """Set unique device_id"""
        return self._unique_id

    @property
    def entity_id(self) -> str:
        """Provide an entity ID"""
        if self._entity_id is None:
            self._entity_id = f"media_player.{self.mac_address}_{self.zone_output}"
        return self._entity_id

    @entity_id.setter
    def entity_id(self, new_entity_id) -> None:
        self._entity_id = new_entity_id

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device."""
        if self.api.get_logged_in() is False:
            return None
        return MediaPlayerState.IDLE

    @property
    def available(self) -> bool:
        """Could the resource be accessed during the last update call."""
        return self.api.get_logged_in()
