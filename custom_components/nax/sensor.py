"""Nax Sensors."""

from __future__ import annotations

import json
import logging

from cresnextws import DataEventManager
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nax_entity import NaxEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NAX sensor entities for a config entry."""

    api: DataEventManager = hass.data[DOMAIN][config_entry.entry_id]
    # mac_address = await hass.async_add_executor_job(api.get_device_mac_address)

    mac_address = (
        (await api.client.http_get("/Device/DeviceInfo/MacAddress") or {})
        .get("content", {})
        .get("Device", {})
        .get("DeviceInfo", {})
        .get("MacAddress")
    )
    source_inputs = (
        (await api.client.http_get("/Device/InputSources/Inputs") or {})
        .get("content", {})
        .get("Device", {})
        .get("InputSources", {})
        .get("Inputs", [])
    )

    if not mac_address or not source_inputs:
        _LOGGER.error("Could not retrieve NAX device MAC address or inputs")
        raise ConfigEntryNotReady("NAX device not available")

    entities_to_add = [
        NaxInputSignalSensor(
            api=api,
            mac_address=mac_address,
            source_input_key=source_input,
            source_input_data=source_inputs[source_input],
        )
        for source_input in source_inputs
    ]

    async_add_entities(entities_to_add)


class NaxInputSignalSensor(NaxEntity, SensorEntity):
    """Representation of a NAX Input Signal Sensor."""

    def __init__(
        self,
        api: DataEventManager,
        mac_address: str,
        source_input_key: str,
        source_input_data: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(api=api, mac_address=mac_address)
        self._source_input_key = source_input_key
        self._source_input_data = source_input_data
        print(
            f"Source Input {self._source_input_key} Data: {json.dumps(self._source_input_data, indent=2)}"
        )
        # "/Device/InputSources/Inputs"
        api.subscribe(
            f"Device.InputSources.Inputs.{self._source_input_key}.IsSignalPresent",
            self._is_signal_present_update,
        )
        # subscriptions = [
        #     (f"Device.InputSources.Inputs.{input_id}.Signal", self._signal_update),
        #     (f"Device.InputSources.Inputs.{input_id}.Name", self._name_update),
        # ]
        # LogicalInputId

    def _is_signal_present_update(self, message: dict) -> None:
        """Handle updates to the signal presence."""
        is_signal_present = message.get("Value")
        print(f"Input {self._source_input_key} IsSignalPresent: {is_signal_present}")
        if is_signal_present:
            self._attr_state = "Present"
        else:
            self._attr_state = "Not Present"
        self.async_write_ha_state()

    # @property
    # def extra_state_attributes(self) -> dict:
    #     """Return the state attributes."""
    #     return {
    #         "input_id": self._input.get("Id"),
    #         "input_name": self._input.get("Name"),
    #         "input_type": self._input.get("Type"),
    #     }

    # async def async_update(self) -> None:
    #     """Fetch new state data for the sensor."""
    #     try:
    #         signal_data = (
    #             (
    #                 await self.api.client.http_get(
    #                     f"/Device/InputSources/Inputs/{self._input.get('Id')}/Signal"
    #                 )
    #                 or {}
    #             )
    #             .get("content", {})
    #             .get("Device", {})
    #             .get("InputSources", {})
    #             .get("Inputs", {})
    #             .get("Signal", {})
    #         )
    #         self._attr_state = signal_data.get("Strength")
    #     except Exception as e:
    #         _LOGGER.error(f"Error updating NAX input signal sensor: {e}")
    #         self._attr_state = None
