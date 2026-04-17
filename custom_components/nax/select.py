"""Nax Select Entities."""

from __future__ import annotations

from enum import Enum
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
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    STORAGE_LAST_AES67_STREAM_KEY,
    STORAGE_LAST_BTS_STREAM_KEY,
    safe_get,
)
from .nax_entity import NaxEntity

_LOGGER = logging.getLogger(__name__)


class NaxStreamEncoding(Enum):
    """Network encoding format reported by NAX RX receivers and SDP announcements.

    Enum value is the exact string the device returns in ``EncodingFormat`` on
    ``NaxRxStreams`` and ``NaxSdpStreams``. (Transmitters label BTS as ``PCM``
    instead — this enum tracks the receiver/SDP side, which is what selection
    logic compares against.) Enum name doubles as the user-facing label.
    """

    AES67 = "Lpcm"
    BTS = "BTS"


_STORAGE_KEY_BY_ENCODING = {
    NaxStreamEncoding.AES67: STORAGE_LAST_AES67_STREAM_KEY,
    NaxStreamEncoding.BTS: STORAGE_LAST_BTS_STREAM_KEY,
}


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

    zone_outputs = safe_get(
        await api.client.http_get("/Device/ZoneOutputs/Zones") or {},
        "content", "Device", "ZoneOutputs", "Zones", default={}
    )

    nax_sdp_streams = safe_get(
        await api.client.http_get("/Device/NaxAudio/NaxSdp/NaxSdpStreams") or {},
        "content", "Device", "NaxAudio", "NaxSdp", "NaxSdpStreams", default={}
    )

    nax_rx = safe_get(
        await api.client.http_get("/Device/NaxAudio/NaxRx") or {},
        "content", "Device", "NaxAudio", "NaxRx", default={}
    )

    tone_generator = safe_get(
        await api.client.http_get("/Device/ToneGenerator") or {},
        "content", "Device", "ToneGenerator", default={}
    )

    if not all(
        [
            mac_address,
            nax_device_name,
            nax_device_manufacturer,
            nax_device_model,
            nax_device_firmware_version,
            nax_device_serial_number,
        ]
    ):
        _LOGGER.error("Could not retrieve required NAX device information")
        return

    av_matrix_routing_v2_config = safe_get(
        await api.client.http_get("/Device/AvMatrixRoutingV2/Config") or {},
        "content", "Device", "AvMatrixRoutingV2", "Config", default={}
    )

    avio_v2_inputs = safe_get(
        await api.client.http_get("/Device/AvioV2/Inputs") or {},
        "content", "Device", "AvioV2", "Inputs", default={}
    )

    device_params = {
        "api": api,
        "mac_address": mac_address,
        "nax_device_name": nax_device_name,
        "nax_device_manufacturer": nax_device_manufacturer,
        "nax_device_model": nax_device_model,
        "nax_device_firmware_version": nax_device_firmware_version,
        "nax_device_serial_number": nax_device_serial_number,
    }

    entities_to_add: list[SelectEntity] = []

    # Tone generator mode select (standard NAX devices)
    if tone_generator:
        entities_to_add.append(
            NaxToneGeneratorModeSelect(
                **device_params,
                tone_generator_data=tone_generator,
            )
        )

    # RX stream selects (standard NAX devices with zones — AES67 only; receivers on
    # these devices are all Lpcm).
    if zone_outputs and nax_rx:
        for zone_output in zone_outputs:
            zone_output_data = zone_outputs[zone_output]
            zone_aes67_receiver_key = zone_output_data.get("NaxRxStream", "")

            if zone_aes67_receiver_key:
                zone_rx_data = nax_rx.get("NaxRxStreams", {}).get(
                    zone_aes67_receiver_key, {}
                )
                entities_to_add.append(
                    NaxRxStreamSelect(
                        **device_params,
                        zone_output_key=zone_output,
                        receiver_key=zone_aes67_receiver_key,
                        encoding=NaxStreamEncoding.AES67,
                        initial_name=zone_output_data.get("Name", "Unknown"),
                        initial_address=zone_rx_data.get("NetworkAddressStatus", ""),
                        nax_sdp_streams=nax_sdp_streams,
                        store=store,
                    )
                )
    # RX stream selects (XSP-style devices — no zones; enumerate receivers directly
    # and emit one entity per supported EncodingFormat).
    elif nax_rx:
        for receiver_key, receiver_data in nax_rx.get("NaxRxStreams", {}).items():
            if not isinstance(receiver_data, dict):
                continue
            try:
                encoding = NaxStreamEncoding(receiver_data.get("EncodingFormat"))
            except ValueError:
                continue
            entities_to_add.append(
                NaxRxStreamSelect(
                    **device_params,
                    receiver_key=receiver_key,
                    encoding=encoding,
                    initial_name=receiver_key,
                    initial_address=receiver_data.get("NetworkAddressStatus", ""),
                    nax_sdp_streams=nax_sdp_streams,
                    store=store,
                )
            )

    # Input selection selects (XSP devices with AvMatrixRoutingV2 Config)
    if av_matrix_routing_v2_config and avio_v2_inputs:
        # Build input key-to-name mapping for audio-routable inputs
        input_name_map = {}
        for input_key, input_data in avio_v2_inputs.items():
            if isinstance(input_data, dict) and input_data.get(
                "Capabilities", {}
            ).get("IsAudioRoutingSupported", False):
                input_name_map[input_key] = input_data.get(
                    "UserSpecifiedName", input_key
                )

        for output_key, output_config in av_matrix_routing_v2_config.items():
            if not isinstance(output_config, dict):
                continue

            entities_to_add.append(
                NaxInputSelectionSelect(
                    **device_params,
                    output_key=output_key,
                    input_name_map=input_name_map,
                    current_source=output_config.get(
                        "AudioSourceConfigured", "No Source"
                    ),
                )
            )

    async_add_entities(entities_to_add)


class NaxRxStreamSelect(NaxEntity, SelectEntity):
    """NAX RX stream selector for a single receiver.

    Handles both AES67 and BTS receivers via :class:`NaxStreamEncoding`. The
    dropdown is filtered to SDP-discovered streams matching the receiver's
    encoding — selecting an incompatible stream is rejected by the device.

    Works for both zone-backed devices (amps/pre-amps, always AES67) and
    zone-less devices (XSP, one AES67 + one BTS receiver). When
    ``zone_output_key`` is omitted, the entity is keyed and named directly
    off the receiver key.
    """

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
        receiver_key: str,
        encoding: NaxStreamEncoding,
        initial_name: str,
        initial_address: str,
        nax_sdp_streams: dict,
        store: Store,
        zone_output_key: str | None = None,
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
        self._receiver_key = receiver_key
        self._encoding = encoding
        self._nax_sdp_streams = nax_sdp_streams
        self._store = store
        self._storage_dict_key = _STORAGE_KEY_BY_ENCODING[encoding]
        self._storage_entry_key = zone_output_key or receiver_key
        self._load_store_task = None
        self._save_store_task = None

        # Initialize attributes. Unique-id suffix is the lowercase enum name
        # ("aes67" / "bts"); for AES67 this matches the pre-refactor format
        # exactly, preserving entity identity for existing automations.
        id_part = zone_output_key or receiver_key
        self._attr_unique_id = (
            f"{mac_address.replace(':', '_').replace('.', '_')}"
            f"_{id_part}_{encoding.name.lower()}_stream"
        )
        self._attr_entity_registry_visible_default = True
        self._attr_icon = "mdi:multicast"
        self._name_update(event_name="", message=initial_name)
        self._nax_sdp_update(
            event_name="", message=None
        )  # Initialize available options
        self._rx_stream_update(
            event_name="", message=initial_address
        )  # Initialize current selection

        # Subscribe to relevant events
        if zone_output_key is not None:
            api.subscribe(
                f"/Device/ZoneOutputs/Zones/{zone_output_key}/Name",
                self._name_update,
            )
        api.subscribe(
            "/Device/NaxAudio/NaxSdp/NaxSdpStreams",
            self._nax_sdp_update,
            full_message=True,
        )
        api.subscribe(
            f"/Device/NaxAudio/NaxRx/NaxRxStreams/{self._receiver_key}/NetworkAddressStatus",
            self._rx_stream_update,
        )

    @callback
    def _name_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the display name prefix."""
        self._attr_name = f"{message} {self._encoding.name} Stream"
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _nax_sdp_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the NAX SDP data (available streams)."""
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
            if not isinstance(stream, dict):
                continue
            if stream.get("EncodingFormat") != self._encoding.value:
                continue
            stream_address = stream.get("NetworkAddressStatus", "")
            stream_name = stream.get("SessionNameStatus", "Unknown")
            if stream_address:
                options.append({"name": stream_name, "address": stream_address})

        self._attr_options = [
            self.__mux_stream_name(stream)
            for stream in sorted(
                options, key=lambda item: socket.inet_aton(item["address"])
            )
        ]

        # Ensure current selection is still valid
        if hasattr(self, '_attr_current_option') and self._attr_current_option not in self._attr_options:
            if self.hass is not None:
                self.hass.async_create_task(self.async_select_option("None"))

        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _rx_stream_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the current receiver stream selection."""
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
                            self.__async_save_store_last_stream(stream_address)
                        )
                    break
            self._attr_current_option = found_option
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected receiver stream."""
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
                                self._receiver_key: {
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
        if self._zone_output_key is not None:
            await self.api.client.ws_get(
                f"/Device/ZoneOutputs/Zones/{self._zone_output_key}/Name"
            )
        await self.api.client.ws_get("/Device/NaxAudio/NaxSdp/NaxSdpStreams")
        await self.api.client.ws_get(
            f"/Device/NaxAudio/NaxRx/NaxRxStreams/{self._receiver_key}/NetworkAddressStatus"
        )

    # Helper Functions
    async def __async_save_store_last_stream(self, last_stream: str) -> None:
        """Save the last selected stream address in storage if it changed."""
        storage_data = await self._store.async_load()
        if storage_data is None:
            storage_data = {}
        stream_dict = storage_data.setdefault(self._storage_dict_key, {})
        if stream_dict.get(self._storage_entry_key) != last_stream:
            stream_dict[self._storage_entry_key] = last_stream
            await self._store.async_save(storage_data)

    def __mux_stream_name(self, stream_arg: dict[str, str] | None) -> str:
        if not stream_arg:
            return ""
        return f"{stream_arg['name']} ({stream_arg['address']})"

    def __demux_stream_name(self, stream_arg: str) -> str:
        if not stream_arg:
            return ""
        return stream_arg.split(" (", 1)[1][:-1]


class NaxToneGeneratorModeSelect(NaxEntity, SelectEntity):
    """Representation of a NAX Tone Generator Mode Select."""

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

        # Initialize attributes
        self._attr_unique_id = f"{mac_address.replace(':', '_').replace('.', '_')}_tone_generator_mode"
        self._attr_name = f"{nax_device_name} Tone Generator Mode"
        self._attr_icon = "mdi:sine-wave"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_options = ["Tone", "WhiteNoise", "PinkNoise"]
        self._tone_generator_mode_update(
            event_name="", message=tone_generator_data.get("Mode", "Tone")
        )

        # Subscribe to relevant events
        api.subscribe(
            "/Device/ToneGenerator/Mode",
            self._tone_generator_mode_update,
        )

    @callback
    def _tone_generator_mode_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the tone generator mode."""
        self._attr_current_option = message
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the tone generator mode."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid option selected: %s", option)
            return

        await self.api.client.ws_post(
            payload={
                "Device": {
                    "ToneGenerator": {
                        "Mode": option
                    }
                }
            }
        )

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get("/Device/ToneGenerator/Mode")


class NaxInputSelectionSelect(NaxEntity, SelectEntity):
    """Select entity for audio input selection on XSP devices."""

    _no_source = "None"

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
        output_key: str,
        input_name_map: dict[str, str],
        current_source: str,
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
        self._output_key = output_key
        self._input_name_map = input_name_map
        # Reverse map: display name -> input key
        self._name_to_key = {v: k for k, v in input_name_map.items()}

        self._attr_unique_id = (
            f"{mac_address.replace(':', '_').replace('.', '_')}_{output_key}_input_selection"
        )
        self._attr_name = f"{nax_device_name} Input Selection"
        self._attr_icon = "mdi:audio-input-stereo-minijack"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_entity_registry_visible_default = True
        self._attr_options = [self._no_source] + sorted(input_name_map.values())
        self._source_update(event_name="", message=current_source)

        api.subscribe(
            f"/Device/AvMatrixRoutingV2/Config/{output_key}/AudioSourceConfigured",
            self._source_update,
        )

    @callback
    def _source_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the configured audio source."""
        if message == "No Source" or not message:
            self._attr_current_option = self._no_source
        else:
            self._attr_current_option = self._input_name_map.get(
                message, self._no_source
            )
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the audio input selection."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid option selected: %s", option)
            return

        if option == self._no_source:
            source_value = "No Source"
        else:
            source_value = self._name_to_key.get(option, "No Source")

        await self.api.client.ws_post(
            payload={
                "Device": {
                    "AvMatrixRoutingV2": {
                        "Routes": {
                            self._output_key: {
                                "AudioSource": source_value
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
            f"/Device/AvMatrixRoutingV2/Config/{self._output_key}/AudioSourceConfigured"
        )
