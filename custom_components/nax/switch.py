import threading
from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.switch import SwitchEntity
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

    zones = await hass.async_add_executor_job(api.get_all_zone_outputs)
    for zone in zones:
        entities_to_add.append(
            NaxZoneTestToneSwitch(
                api=api,
                unique_id=f"{mac_address}_{zone}_test_tone",
                zone_output=zone,
            )
        )
    async_add_entities(entities_to_add)


class NaxBaseSwitch(SwitchEntity):

    api: NaxApi = None
    _entity_id: str = None

    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.api = api
        self._attr_unique_id = unique_id
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
        if self._entity_id is None:
            self._entity_id = f"switch.{self._attr_unique_id}"
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
        return self.api.get_logged_in()

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


class NaxZoneTestToneSwitch(NaxBaseSwitch):
    """Representation of an NAX zone signal generator switch."""

    zone_output: str = None

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the sensor."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_unique_id = unique_id

        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.IsTestToneActive",
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
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Test Tone"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:square-wave"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        await self.api.set_zone_test_tone(self.zone_output, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        await self.api.set_zone_test_tone(self.zone_output, False)

    @property
    def is_on(self):
        """Is the entity on"""
        return self.api.get_zone_test_tone(self.zone_output)
