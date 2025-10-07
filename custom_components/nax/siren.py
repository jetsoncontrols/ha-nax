"""Nax Siren Entities."""

from __future__ import annotations

import logging
from typing import Any

import deepmerge

from cresnextws import DataEventManager
from homeassistant.components.siren import ATTR_TONE, SirenEntity, SirenEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nax_entity import NaxEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NAX siren entities for a config entry."""

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

    door_chimes = (
        (await api.client.http_get("/Device/DoorChimes") or {})
        .get("content", {})
        .get("Device", {})
        .get("DoorChimes", {})
    )

    # Create a basic siren entity
    entities = [
        NaxSiren(
            api=api,
            mac_address=mac_address,
            nax_device_name=nax_device_name,
            nax_device_manufacturer=nax_device_manufacturer,
            nax_device_model=nax_device_model,
            nax_device_firmware_version=nax_device_firmware_version,
            nax_device_serial_number=nax_device_serial_number,
            door_chimes=door_chimes,
        )
    ]

    async_add_entities(entities)


class NaxSiren(NaxEntity, SirenEntity):
    """Representation of a NAX Siren."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        nax_device_name: str,
        nax_device_manufacturer: str,
        nax_device_model: str,
        nax_device_firmware_version: str,
        nax_device_serial_number: str,
        door_chimes: dict[str, Any],
    ) -> None:
        """Initialize the siren."""
        super().__init__(
            api,
            mac_address,
            nax_device_name,
            nax_device_manufacturer,
            nax_device_model,
            nax_device_firmware_version,
            nax_device_serial_number,
        )

        self._attr_name = f"{nax_device_name} Chime"
        self._attr_unique_id = f"{format_mac(mac_address)}_siren"
        self.entity_id = f"siren.{self._attr_unique_id}"

        # Enable tone support
        self._attr_supported_features = (
            SirenEntityFeature.TURN_ON | SirenEntityFeature.TONES
        )

        # Initialize attributes
        self._door_chimes = door_chimes
        self._door_chimes_update(
            event_name="",
            message=None,  # None bypasses merge
        )

        # Subscribe to relevant events
        api.subscribe(
            "/Device/DoorChimes",
            self._door_chimes_update,
            match_children=False,
            full_message=True,
        )

    @callback
    def _door_chimes_update(self, event_name: str, message: Any) -> None:
        """Handle updates to the signal presence."""
        if message is not None:
            deepmerge.always_merger.merge(
                self._door_chimes,
                message.get("Device", {}).get("DoorChimes", {}),
            )

        self._attr_is_on = False
        self._attr_available_tones = []

        for parent_data in self._door_chimes.values():
            # Skip non-dict items like "FilterType", "Version", etc.
            if not isinstance(parent_data, dict):
                continue
            # Iterate through all chimes in this parent category
            for chime_data in parent_data.values():
                if isinstance(chime_data, dict):
                    if chime_data.get("PlaybackInProgress") is True:
                        self._attr_is_on = True
                    if (name := chime_data.get("Name")) is not None:
                        self._attr_available_tones.append(name)

        if self.hass is not None:
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the siren on."""
        tone = kwargs.get(ATTR_TONE) or (
            self.available_tones[0] if self.available_tones else None
        )

        _LOGGER.info("Siren turn_on called with tone=%s", tone)

        if tone:
            for parent_key, parent_data in self._door_chimes.items():
                if not isinstance(parent_data, dict):
                    continue
                for slot_name, chime_data in parent_data.items():
                    if isinstance(chime_data, dict) and chime_data.get("Name") == tone:
                        await self.api.client.ws_post(
                            payload={
                                "Device": {
                                    "DoorChimes": {
                                        parent_key: {
                                            slot_name: {
                                                "DurationInSeconds": 0,
                                                "RepeatCount": 1,
                                                "PlaybackMode": "Count",
                                                "Play": True,
                                            }
                                        }
                                    }
                                }
                            }
                        )
                        return
