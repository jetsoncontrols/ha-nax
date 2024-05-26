from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry  # noqa: ICN001
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nax.nax_api import NaxApi


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]

    mac_address = await hass.async_add_executor_job(api.get_device_mac_address)

    entities_to_add = []
    zones = await hass.async_add_executor_job(api.get_all_zone_outputs)
    for zone in zones:
        entities_to_add.append(
            NaxZoneTestToneSwitch(
                api=api,
                unique_id=f"{mac_address}_{zone}_test_tone",
                zone_output=zone,
            )
        )
        entities_to_add.append(
            NaxZoneLoudnessSwitch(
                api=api,
                unique_id=f"{mac_address}_{zone}_loudness",
                zone_output=zone,
            )
        )
    async_add_entities(entities_to_add)


class NaxBaseSwitch(SwitchEntity):
    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the switch."""
        super().__init__()
        self.api = api
        self._attr_unique_id = unique_id
        self._entity_id = f"switch.{self._attr_unique_id}"
        self.__base_subscriptions()

    def __base_subscriptions(self) -> None:
        self.api.subscribe_connection_updates(self._update_connection)

    @callback
    def _generic_update(self, path: str, data: Any) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @callback
    def _update_connection(self, connected: bool) -> None:
        self.schedule_update_ha_state(force_refresh=False)

    @property
    def unique_id(self) -> str:
        """Set unique device_id."""
        return self._attr_unique_id

    @property
    def entity_id(self) -> str:
        """Provide an entity ID."""
        return self._entity_id

    @entity_id.setter
    def entity_id(self, new_entity_id) -> None:
        self._entity_id = new_entity_id

    @property
    def should_poll(self) -> bool:
        """Return if hass should poll this entity."""
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


class NaxZoneTestToneSwitch(NaxBaseSwitch):
    """Representation of an NAX zone signal generator switch."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_unique_id = unique_id
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.IsTestToneActive",
            self._generic_update,
        )
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
        """Is the entity on."""
        return self.api.get_zone_test_tone(self.zone_output)


class NaxZoneLoudnessSwitch(NaxBaseSwitch):
    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_unique_id = unique_id
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.IsLoudnessEnabled",
            self._generic_update,
        )
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
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Loudness"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:bullhorn-variant-outline"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        await self.api.set_zone_loudness(self.zone_output, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        await self.api.set_zone_loudness(self.zone_output, False)

    @property
    def is_on(self):
        """Is the entity on."""
        return self.api.get_zone_loudness(self.zone_output)
