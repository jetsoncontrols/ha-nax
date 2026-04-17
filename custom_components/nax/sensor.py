"""Nax Sensor Entities."""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any

from cresnextws import DataEventManager
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, safe_get
from .nax_entity import NaxEntity

_LOGGER = logging.getLogger(__name__)


class NaxAudioField(Enum):
    """Per-port digital audio field exposed by ``AvioV2`` ports.

    Enum value is the literal JSON key under
    ``{InputInfo|OutputInfo}/Ports/Port1/Audio/Digital/``.
    Enum name is used to form the user-facing label ("Audio Format" /
    "Audio Channels") and the unique-id suffix.
    """

    FORMAT = "Format"
    CHANNELS = "Channels"

    @property
    def label(self) -> str:
        return f"Audio {self.name.title()}"

    @property
    def id_suffix(self) -> str:
        return f"audio_{self.name.lower()}"

    @property
    def icon(self) -> str:
        return {
            NaxAudioField.FORMAT: "mdi:waveform",
            NaxAudioField.CHANNELS: "mdi:surround-sound",
        }[self]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NAX sensor entities for a config entry."""

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

    av_matrix_routing_v2_routes = safe_get(
        await api.client.http_get("/Device/AvMatrixRoutingV2/Routes") or {},
        "content", "Device", "AvMatrixRoutingV2", "Routes", default={}
    )

    avio_v2_inputs = safe_get(
        await api.client.http_get("/Device/AvioV2/Inputs") or {},
        "content", "Device", "AvioV2", "Inputs", default={}
    )

    avio_v2_outputs = safe_get(
        await api.client.http_get("/Device/AvioV2/Outputs") or {},
        "content", "Device", "AvioV2", "Outputs", default={}
    )

    if not av_matrix_routing_v2_config or not avio_v2_inputs:
        return

    # Build input key-to-name mapping
    input_name_map = {}
    for input_key, input_data in avio_v2_inputs.items():
        if isinstance(input_data, dict):
            input_name_map[input_key] = input_data.get(
                "UserSpecifiedName", input_key
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

    entities_to_add: list[SensorEntity] = []

    # Active audio selection sensor — one per Config output key
    for output_key in av_matrix_routing_v2_config:
        if not isinstance(av_matrix_routing_v2_config[output_key], dict):
            continue
        current_route = (
            av_matrix_routing_v2_routes.get(output_key, {}).get(
                "AudioSource", "No Source"
            )
        )
        entities_to_add.append(
            NaxActiveAudioSelectionSensor(
                **device_params,
                output_key=output_key,
                input_name_map=input_name_map,
                current_source=current_route,
            )
        )

    # Per-port audio format/channels diagnostic sensors — inputs + outputs
    for direction, info_key, ports_dict in (
        ("Input", "InputInfo", avio_v2_inputs),
        ("Output", "OutputInfo", avio_v2_outputs),
    ):
        for port_key, port_data in ports_dict.items():
            if not isinstance(port_data, dict):
                continue
            if not port_data.get("Capabilities", {}).get(
                "IsAudioRoutingSupported", False
            ):
                continue
            port_name = port_data.get("UserSpecifiedName", port_key)
            digital = (
                port_data.get(info_key, {})
                .get("Ports", {})
                .get("Port1", {})
                .get("Audio", {})
                .get("Digital", {})
            )
            for field in (NaxAudioField.FORMAT, NaxAudioField.CHANNELS):
                entities_to_add.append(
                    NaxPortAudioSensor(
                        **device_params,
                        direction=direction,
                        port_key=port_key,
                        port_name=port_name,
                        field=field,
                        initial_value=digital.get(field.value),
                    )
                )

    # HDMI resolution sensors (AvioV2 HDMI inputs + outputs — XSP-style devices)
    for direction, info_key, ports_dict in (
        ("Input", "InputInfo", avio_v2_inputs),
        ("Output", "OutputInfo", avio_v2_outputs),
    ):
        for port_key, port_data in ports_dict.items():
            if not isinstance(port_data, dict):
                continue
            port = port_data.get(info_key, {}).get("Ports", {}).get("Port1", {})
            if port.get("PortType") != "Hdmi":
                continue
            entities_to_add.append(
                NaxHdmiResolutionSensor(
                    **device_params,
                    direction=direction,
                    port_key=port_key,
                    port_name=port_data.get("UserSpecifiedName", port_key),
                    initial_value=port.get("CurrentResolution"),
                )
            )

    async_add_entities(entities_to_add)


class NaxActiveAudioSelectionSensor(NaxEntity, SensorEntity):
    """Read-only sensor showing the active audio source for an output."""

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
        """Initialize the sensor entity."""
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

        self._attr_unique_id = (
            f"{mac_address.replace(':', '_').replace('.', '_')}_{output_key}_active_audio"
        )
        self._attr_name = f"{nax_device_name} Active Audio Selection"
        self._attr_icon = "mdi:audio-input-stereo-minijack"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_visible_default = True
        self._source_update(event_name="", message=current_source)

        api.subscribe(
            f"/Device/AvMatrixRoutingV2/Routes/{output_key}/AudioSource",
            self._source_update,
        )

    @callback
    def _source_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the active audio source."""
        if message == "No Source" or not message:
            self._attr_native_value = "None"
        else:
            self._attr_native_value = self._input_name_map.get(message, message)
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(
            f"/Device/AvMatrixRoutingV2/Routes/{self._output_key}/AudioSource"
        )


class NaxPortAudioSensor(NaxEntity, SensorEntity):
    """Diagnostic sensor reporting a single Audio/Digital field on an AvioV2 port.

    Covers both inputs and outputs and both fields (Format, Channels) via
    :class:`NaxAudioField`. One sensor entity per (port, field) pair.
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
        direction: str,
        port_key: str,
        port_name: str,
        field: NaxAudioField,
        initial_value: Any,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._direction = direction
        self._port_key = port_key
        self._field = field

        self._attr_unique_id = (
            f"{mac_address.replace(':', '_').replace('.', '_')}"
            f"_{port_key}_{field.id_suffix}"
        )
        self._attr_name = (
            f"{nax_device_name} {direction} {port_name} {field.label}"
        )
        self._attr_icon = field.icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_visible_default = True
        self._field_update(event_name="", message=initial_value)

        api.subscribe(self.__path, self._field_update)

    @property
    def __path(self) -> str:
        """API path for this port/field's value."""
        return (
            f"/Device/AvioV2/{self._direction}s/{self._port_key}"
            f"/{self._direction}Info/Ports/Port1/Audio/Digital/{self._field.value}"
        )

    @callback
    def _field_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the audio field value."""
        self._attr_native_value = message
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(self.__path)


class NaxHdmiResolutionSensor(NaxEntity, SensorEntity):
    """Diagnostic sensor for an AvioV2 HDMI port's CurrentResolution.

    Works for both inputs and outputs via the ``direction`` parameter.
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
        direction: str,
        port_key: str,
        port_name: str,
        initial_value: Any,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
        )
        self._direction = direction
        self._port_key = port_key

        self._attr_unique_id = (
            f"{mac_address.replace(':', '_').replace('.', '_')}"
            f"_{port_key}_hdmi_resolution"
        )
        self._attr_name = f"{nax_device_name} {direction} {port_name} Resolution"
        self._attr_icon = "mdi:television"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_visible_default = True
        self._resolution_update(event_name="", message=initial_value)

        api.subscribe(self.__path, self._resolution_update)

    @property
    def __path(self) -> str:
        return (
            f"/Device/AvioV2/{self._direction}s/{self._port_key}"
            f"/{self._direction}Info/Ports/Port1/CurrentResolution"
        )

    @callback
    def _resolution_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the HDMI resolution value."""
        self._attr_native_value = message
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch new state data for this entity."""
        await super().async_update()
        await self.api.client.ws_get(self.__path)
