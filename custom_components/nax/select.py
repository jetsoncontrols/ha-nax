import threading
from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.select import SelectEntity
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


class NaxBaseSelect(SelectEntity):
    def __init__(self, api: NaxApi, unique_id: str) -> None:
        super().__init__()
        self.api = api
        self._attr_unique_id = unique_id
        self._entity_id = f"select.{self._attr_unique_id}"
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
        """Return the unique ID of the switch."""
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


class NaxZoneNightModeSelect(NaxBaseSelect):
    def __init__(self, api: NaxApi, unique_id: str, zone_output: int) -> None:
        """Initialize the select."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.NightMode",
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
        """Return the name of the select."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Night Mode"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:weather-night"

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
        threading.Timer(1.0, self.subscribtions).start()

    def subscribtions(self) -> None:
        self.api.subscribe_data_updates(
            "Device.DeviceInfo.Name",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the select."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Aes67 Stream"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:multicast"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self.api.get_zone_aes67_stream(self.zone_output)

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return self.api.get_aes67_streams()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.api.set_zone_aes67_stream(
            zone_output=self.zone_output, stream=option
        )
