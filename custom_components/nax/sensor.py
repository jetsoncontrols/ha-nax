"""NAX sensors for signal, clipping, casting, and fault status."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NaxEntity
from .const import DOMAIN
from .nax.nax_api import NaxApi


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NAX sensor entities for a config entry."""
    entities_to_add = []
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = await hass.async_add_executor_job(api.get_device_mac_address)

    sources = api.get_input_sources()
    if not sources:
        _LOGGER.debug(
            "No input sources returned for NAX device %s; skipping source sensors",
            mac_address,
        )
    else:
        for source in sources:
            entities_to_add.append(
                NaxSourceSignalSensor(
                    api=api,
                    unique_id=f"{mac_address}_{source}_signal_present",
                    input_id=source,
                )
            )
            entities_to_add.append(
                NaxSourceClippingSensor(
                    api=api,
                    unique_id=f"{mac_address}_{source}_clipping",
                    input_id=source,
                )
            )

    zones = await hass.async_add_executor_job(api.get_all_zone_outputs)
    if not zones:
        _LOGGER.debug(
            "No zone outputs returned for NAX device %s; skipping zone sensors",
            mac_address,
        )
    else:
        for zone in zones:
            entities_to_add.append(
                NaxZoneSignalSensor(
                    api=api,
                    unique_id=f"{mac_address}_{zone}_signal_present",
                    zone_output=zone,
                )
            )
            entities_to_add.append(
                NaxZoneSignalClippingSensor(
                    api=api,
                    unique_id=f"{mac_address}_{zone}_signal_clipping",
                    zone_output=zone,
                )
            )
            entities_to_add.append(
                NaxZoneCastingActiveSensor(
                    api=api,
                    unique_id=f"{mac_address}_{zone}_casting_active",
                    zone_output=zone,
                )
            )
            if api.get_zone_amplification_supported(zone):  # Fix
                entities_to_add.append(
                    NaxZoneSpeakerClippingSensor(
                        api=api,
                        unique_id=f"{mac_address}_{zone}_speaker_clipping",
                        zone_output=zone,
                    )
                )
                entities_to_add.append(
                    NaxZoneCriticalFaultSensor(
                        api=api,
                        unique_id=f"{mac_address}_{zone}_critical_fault",
                        zone_output=zone,
                    )
                )
                entities_to_add.append(  # Fix
                    NaxZoneDCFaultSensor(
                        api=api,
                        unique_id=f"{mac_address}_{zone}_dc_fault",
                        zone_output=zone,
                    )
                )
                entities_to_add.append(  # Fix
                    NaxZoneOverCurrentSensor(
                        api=api,
                        unique_id=f"{mac_address}_{zone}_over_current",
                        zone_output=zone,
                    )
                )
                entities_to_add.append(  # Fix
                    NaxZoneOverTemperatureSensor(
                        api=api,
                        unique_id=f"{mac_address}_{zone}_over_temperature",
                        zone_output=zone,
                    )
                )
                entities_to_add.append(  # Fix
                    NaxZoneVoltageFaultSensor(
                        api=api,
                        unique_id=f"{mac_address}_{zone}_voltage_fault",
                        zone_output=zone,
                    )
                )

    async_add_entities(entities_to_add)


class NaxBaseSensor(NaxEntity, SensorEntity):
    """Base class for NAX sensors providing shared initialization."""

    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(api=api, unique_id=unique_id)
        self.entity_id = f"sensor.{self._attr_unique_id}"


class NaxZoneCastingActiveSensor(NaxBaseSensor):
    """Representation of an NAX zone casting active sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:cast-audio"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneBasedProviders.IsCastingActive",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Casting Active"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_casting_active(self.zone_output)


class NaxSourceSignalSensor(NaxBaseSensor):
    """Representation of an NAX source signal sensor."""

    def __init__(self, api: NaxApi, unique_id: str, input_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.input_id = input_id
        self._attr_icon = "mdi:waveform"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.IsSignalPresent",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_input_source_name(self.input_id)} ({self.input_id}) Signal Present"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_input_source_signal_present(self.input_id)


class NaxSourceClippingSensor(NaxBaseSensor):
    """Representation of an NAX source clipping sensor."""

    def __init__(self, api: NaxApi, unique_id: str, input_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.input_id = input_id
        self._attr_icon = "mdi:square-wave"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.IsClippingDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_input_source_name(self.input_id)} ({self.input_id}) Clipping"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_input_source_clipping(self.input_id)


class NaxZoneSignalSensor(NaxBaseSensor):
    """Representation of an NAX zone signal sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:waveform"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.IsSignalDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Signal Present"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_signal_detected(self.zone_output)


class NaxZoneSignalClippingSensor(NaxBaseSensor):
    """Representation of an NAX zone signal clipping sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:square-wave"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.IsSignalClipping",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Signal Clipping"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_signal_clipping(self.zone_output)


class NaxZoneSpeakerClippingSensor(NaxBaseSensor):
    """Representation of an NAX zone speaker clipping sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:square-wave"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsClippingDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Speaker Clipping"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_speaker_clipping(self.zone_output)


class NaxZoneCriticalFaultSensor(NaxBaseSensor):
    """Representation of an NAX zone critical fault sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:exclamation"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsCriticalFaultDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Critical Fault"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_speaker_critical_fault(self.zone_output)


class NaxZoneDCFaultSensor(NaxBaseSensor):
    """Representation of an NAX zone DC fault sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:current-dc"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsDcFaultDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} DC Fault"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_speaker_dc_fault(self.zone_output)


class NaxZoneOverCurrentSensor(NaxBaseSensor):
    """Representation of an NAX zone over current sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:debug-step-over"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsOverCurrentConditionDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Over Current"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_speaker_over_current(self.zone_output)


class NaxZoneOverTemperatureSensor(NaxBaseSensor):
    """Representation of an NAX zone over temperature sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:fire"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsOverTemperatureConditionDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Over Temperature"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_speaker_over_temperature(self.zone_output)


class NaxZoneVoltageFaultSensor(NaxBaseSensor):
    """Representation of an NAX zone voltage fault sensor."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:flash-triangle"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsVoltageFaultDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Voltage Fault"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_speaker_voltage_fault(self.zone_output)
