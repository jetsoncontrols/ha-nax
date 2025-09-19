"""Nax Select Entities."""

from __future__ import annotations

import logging
import socket
from typing import Any
import json

import deepmerge

from cresnextws import DataEventManager
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_LAST_AES67_STREAM_KEY
from .nax_entity import NaxEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NAX select entities for a config entry."""

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

    nax_sdp_streams = (
        (await api.client.http_get("/Device/NaxAudio/NaxSdp/NaxSdpStreams") or {})
        .get("content", {})
        .get("Device", {})
        .get("NaxAudio", {})
        .get("NaxSdp", {})
        .get("NaxSdpStreams", {})
    )

    nax_rx = (
        (await api.client.http_get("/Device/NaxAudio/NaxRx") or {})
        .get("content", {})
        .get("Device", {})
        .get("NaxAudio", {})
        .get("NaxRx", {})
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
            nax_sdp_streams is not None,
            nax_rx,
        ]
    ):
        _LOGGER.error("Could not retrieve required NAX device information")
        return

    entities_to_add = []

    # Only create select entities for zones that have AES67 receivers
    for zone_output in zone_outputs:
        zone_output_data = zone_outputs[zone_output]
        zone_aes67_receiver_key = zone_output_data.get("NaxRxStream", "")

        if zone_aes67_receiver_key:
            entities_to_add.append(
                NaxAes67StreamSelect(
                    api=api,
                    mac_address=mac_address,
                    nax_device_name=nax_device_name,
                    nax_device_manufacturer=nax_device_manufacturer,
                    nax_device_model=nax_device_model,
                    nax_device_firmware_version=nax_device_firmware_version,
                    nax_device_serial_number=nax_device_serial_number,
                    zone_output_key=zone_output,
                    zone_output_data=zone_output_data,
                    zone_nax_rx_data=nax_rx.get("NaxRxStreams", {}).get(
                        zone_aes67_receiver_key, {}
                    ),
                    nax_sdp_streams=nax_sdp_streams,
                    store=store,
                )
            )

    async_add_entities(entities_to_add)


class NaxAes67StreamSelect(NaxEntity, SelectEntity):
    """Representation of a NAX AES67 Stream Select."""

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
        zone_nax_rx_data: dict,
        nax_sdp_streams: dict,
        store: Store,
    ) -> None:
        """Initialize the select entity."""
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
        self._zone_aes67_receiver_key = zone_output_data.get("NaxRxStream", "")
        self._nax_sdp_streams = nax_sdp_streams
        self._store = store
        self._load_store_task = None
        self._save_store_task = None

        # Initialize attributes
        self._attr_unique_id = (
            f"{format_mac(mac_address)}_{zone_output_key}_aes67_stream"
        )
        self.entity_id = f"select.{self._attr_unique_id}"
        self._attr_entity_registry_visible_default = True
        self._attr_icon = "mdi:multicast"
        self._zone_name_update(
            event_name="", message=zone_output_data.get("Name", "Unknown")
        )
        self._nax_sdp_update(
            event_name="", message=None
        )  # Initialize available options
        self._zone_aes67_stream_update(
            event_name="", message=zone_nax_rx_data.get("NetworkAddressStatus", "")
        )  # Initialize current selection

        # Subscribe to relevant events
        api.subscribe(
            f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name",
            self._zone_name_update,
        )
        api.subscribe(
            "/Device/NaxAudio/NaxSdp/NaxSdpStreams",
            self._nax_sdp_update,
            full_message=True,
        )
        api.subscribe(
            f"/Device/NaxAudio/NaxRx/NaxRxStreams/{self._zone_aes67_receiver_key}/NetworkAddressStatus",
            self._zone_aes67_stream_update,
        )

    @callback
    def _zone_name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the zone name."""
        self._attr_name = f"{message} AES67 Stream"
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _nax_sdp_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the NAX RX data (available streams)."""
        if message is not None:
            deepmerge.always_merger.merge(
                self._nax_sdp_streams,
                message.get("Device", {})
                .get("NaxAudio", {})
                .get("NaxSdp", {})
                .get("NaxSdpStreams", {}),
            )
        options = [{"name": "None", "address": "0.0.0.0"}]
        for stream in self._nax_sdp_streams.values():
            stream_address = stream.get("NetworkAddressStatus", "")
            stream_name = stream.get("SessionNameStatus", "Unknown")
            if stream_address:
                options.append({"name": stream_name, "address": stream_address})

        self._attr_options = [
            self.__mux_stream_name(stream)
            for stream in sorted(
                options, key=lambda item: socket.inet_aton(item["address"])
            )
            # if not self.api.get_aes67_address_is_local(stream["address"]) # Ignore local streams
        ]

        # Ensure current selection is still valid
        if self._attr_current_option not in self._attr_options:
            if self.hass is not None:
                self.hass.async_create_task(self.async_select_option("None"))

        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _zone_aes67_stream_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the current AES67 stream selection."""
        if not message:
            self._attr_current_option = self.__mux_stream_name(
                {"name": "None", "address": "0.0.0.0"}
            )
        else:
            # Find the matching option in our list
            current_address = str(message)
            found_option = self.__mux_stream_name(
                {"name": "None", "address": "0.0.0.0"}
            )
            for stream in self._nax_sdp_streams.values():
                stream_address = stream.get("NetworkAddressStatus", "")
                stream_name = stream.get("SessionNameStatus", "Unknown")
                if stream_address == current_address:
                    found_option = self.__mux_stream_name(
                        {"name": stream_name, "address": stream_address}
                    )
                    if self.hass is not None and stream_address != "0.0.0.0":
                        self.hass.async_create_task(
                            self.__async_save_store_last_aes67_stream(stream_address)
                        )
                    break
            self._attr_current_option = found_option
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected AES67 stream."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid option selected: %s", option)
            return

        stream_address = self.__demux_stream_name(option)

        await self.api.client.ws_post(
            payload={
                "Device": {
                    "NaxAudio": {
                        "NaxRx": {
                            "NaxRxStreams": {
                                self._zone_aes67_receiver_key: {
                                    "NetworkAddressRequested": stream_address
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
        await self.api.client.ws_get("/Device/NaxAudio/NaxSdp/NaxSdpStreams")
        await self.api.client.ws_get(
            f"/Device/NaxAudio/NaxRx/NaxRxStreams/{self._zone_aes67_receiver_key}/NetworkAddressStatus"
        )

    # Helper Functions
    async def __async_save_store_last_aes67_stream(
        self, last_aes67_stream: str
    ) -> None:
        """Save the last AES67 stream address in storage if it changed."""
        storage_data = await self._store.async_load()
        if storage_data is None:
            storage_data = {}
        stream_dict = storage_data.setdefault(STORAGE_LAST_AES67_STREAM_KEY, {})
        if stream_dict.get(self._zone_output_key) != last_aes67_stream:
            stream_dict[self._zone_output_key] = last_aes67_stream
            await self._store.async_save(storage_data)

    def __mux_stream_name(self, stream_arg: dict[str, str] | None) -> str:
        if not stream_arg:
            return ""
        return f"{stream_arg['name']} ({stream_arg['address']})"

    def __demux_stream_name(self, stream_arg: str) -> str:
        if not stream_arg:
            return ""
        return stream_arg.split(" (", 1)[1][:-1]
