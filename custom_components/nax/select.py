import socket
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NaxEntity
from .const import DOMAIN
from .nax.nax_api import NaxApi


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities_to_add = []
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = await hass.async_add_executor_job(api.get_device_mac_address)

    zones = await hass.async_add_executor_job(api.get_all_zone_outputs)
    for zone in zones:
        entities_to_add.append(
            NaxZoneNightModeSelect(
                api=api,
                unique_id=f"{mac_address}_{zone}_night_mode",
                zone_output=zone,
            )
        )
        entities_to_add.append(
            NaxZoneAes67StreamSelect(
                api=api,
                unique_id=f"{mac_address}_{zone}_aes67_stream",
                zone_output=zone,
            )
        )
    async_add_entities(entities_to_add)


class NaxBaseSelect(NaxEntity, SelectEntity):
    def __init__(self, api: NaxApi, unique_id: str) -> None:
        super().__init__(api=api, unique_id=unique_id)
        self.entity_id = f"select.{self._attr_unique_id}"


class NaxZoneNightModeSelect(NaxBaseSelect):
    def __init__(self, api: NaxApi, unique_id: str, zone_output: int) -> None:
        """Initialize the select."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:weather-night"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.NightMode",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Night Mode"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self.api.get_zone_night_mode(self.zone_output)

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return self.api.get_zone_night_modes()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.api.set_zone_night_mode(zone_output=self.zone_output, mode=option)


class NaxZoneAes67StreamSelect(NaxBaseSelect):
    def __init__(self, api: NaxApi, unique_id: str, zone_output: int) -> None:
        """Initialize the select."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_entity_registry_visible_default = True
        self._attr_icon = "mdi:multicast"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.NaxAudio.NaxRx.NaxRxStreams.{self.api.get_stream_zone_receiver_mapping(zone_output=self.zone_output)}.NetworkAddressStatus",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            "Device.NaxAudio.NaxSdp.NaxSdpStreams",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Aes67 Stream"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        zone_streamer = self.api.get_stream_zone_receiver_mapping(
            zone_output=self.zone_output
        )
        streamer_address = self.api.get_nax_rx_stream_address(streamer=zone_streamer)
        streams = self.api.get_aes67_streams()
        streams.append({"name": "None", "address": "0.0.0.0"})
        matching_stream = None
        for stream in streams:
            if stream["address"] == streamer_address:
                matching_stream = stream
                break
        if streamer_address:
            return self.__mux_stream_name(matching_stream)

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        streams = self.api.get_aes67_streams()
        streams.append({"name": "None", "address": "0.0.0.0"})
        return [
            self.__mux_stream_name(stream)
            for stream in sorted(
                streams, key=lambda item: socket.inet_aton(item["address"])
            )
            if not self.api.get_aes67_address_is_local(stream["address"])
        ]

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        zone_streamer = self.api.get_stream_zone_receiver_mapping(
            zone_output=self.zone_output
        )
        await self.api.set_nax_rx_stream(
            streamer=zone_streamer, address=self.__demux_stream_name(option)
        )

    def __mux_stream_name(self, stream_arg: dict) -> str:
        if not stream_arg:
            return ""
        return f"{stream_arg["name"]} ({stream_arg["address"]})"

    def __demux_stream_name(self, stream_arg: str) -> dict:
        if not stream_arg:
            return ""
        return stream_arg.split(" (", 1)[1][:-1]
