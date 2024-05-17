import threading
from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import device_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .nax.nax_api import NaxApi
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities_to_add = []
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = await hass.async_add_executor_job(api.get_device_mac_address)

    sources = api.get_input_sources()
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
                api=api, unique_id=f"{mac_address}_{source}_clipping", input_id=source
            )
        )

    zones = await hass.async_add_executor_job(api.get_all_zone_outputs)
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
        if api.get_zone_amplification_supported(zone):
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
            entities_to_add.append(
                NaxZoneDCFaultSensor(
                    api=api,
                    unique_id=f"{mac_address}_{zone}_dc_fault",
                    zone_output=zone,
                )
            )
            entities_to_add.append(
                NaxZoneOverCurrentSensor(
                    api=api,
                    unique_id=f"{mac_address}_{zone}_over_current",
                    zone_output=zone,
                )
            )
            entities_to_add.append(
                NaxZoneOverTemperatureSensor(
                    api=api,
                    unique_id=f"{mac_address}_{zone}_over_temperature",
                    zone_output=zone,
                )
            )
            entities_to_add.append(
                NaxZoneVoltageFaultSensor(
                    api=api,
                    unique_id=f"{mac_address}_{zone}_voltage_fault",
                    zone_output=zone,
                )
            )

    async_add_entities(entities_to_add)


class NaxBaseSensor(SensorEntity):

    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.api = api
        self._attr_unique_id = unique_id
        self._entity_id = f"sensor.{self._attr_unique_id}"
        threading.Timer(1.1, self.base_subscribtions).start()

    def base_subscribtions(self) -> None:
        self.api.subscribe_connection_updates(self._update_connection)


    @callback
    def _generic_update(self, path: str, data: Any) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _update_connection(self, connected: bool) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @property
    def unique_id(self) -> str:
        """Set unique device_id"""
        return self._attr_unique_id

    @property
    def entity_id(self) -> str:
        """Provide an entity ID"""
        return self._entity_id

    @entity_id.setter
    def entity_id(self, new_entity_id) -> None:
        self._entity_id = new_entity_id

    @property
    def should_poll(self) -> bool:
        """Return if hass should poll this entity"""
        return False

    @property
    def available(self) -> bool:
        """Could the resource be accessed during the last update call."""
        return self.api.get_websocket_connected()

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
    def entity_registry_visible_default(self) -> bool:
        """If the entity should be visible in the entity registry."""
        return False


class NaxSourceSignalSensor(NaxBaseSensor):
    """Representation of an NAX source signal sensor."""

    def __init__(self, api: NaxApi, unique_id: str, input_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.input_id = input_id
        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.IsSignalPresent",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_input_source_name(self.input_id)} ({self.input_id}) Signal Present"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:waveform"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.IsClippingDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.InputSources.Inputs.{self.input_id}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_input_source_name(self.input_id)} ({self.input_id}) Clipping"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:square-wave"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.IsSignalDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Signal Present"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:waveform"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.IsSignalClipping",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Signal Clipping"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:square-wave"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsClippingDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Speaker Clipping"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:square-wave"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsCriticalFaultDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Critical Fault"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:exclamation"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsDcFaultDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} DC Fault"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:current-dc"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsOverCurrentConditionDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Over Current"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:debug-step-over"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsOverTemperatureConditionDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Over Temperature"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:fire"

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

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.Speaker.Faults.IsVoltageFaultDetected",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Voltage Fault"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:flash-triangle"

    @property
    def native_value(self) -> bool | None:
        """Return the state of the signal."""
        return self.api.get_zone_speaker_voltage_fault(self.zone_output)
