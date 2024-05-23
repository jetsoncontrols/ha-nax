from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceInfo
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

    chimes = await hass.async_add_executor_job(api.get_chimes)
    if chimes:
        for chime in chimes:
            entities_to_add.append(
                NaxChimePlayButton(
                    api=api,
                    unique_id=f"{mac_address}_{chime['id']}_play_chime_button",
                    chime_id=chime["id"],
                    chime_name=chime["name"],
                )
            )
    async_add_entities(entities_to_add)


class NaxBaseButton(ButtonEntity):

    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the button."""
        super().__init__()
        self.api = api
        self._attr_unique_id = unique_id
        self._entity_id = f"button.{self._attr_unique_id}"
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


class NaxChimePlayButton(NaxBaseButton):
    """Representation of a Nax chime play button."""

    def __init__(self, api: NaxApi, unique_id: str, chime_id: str, chime_name) -> None:
        """Initialize the chime play button."""
        super().__init__(api, unique_id)
        self._attr_unique_id = f"{unique_id}"
        self._chime_id = chime_id
        self._chime_name = chime_name

    @property
    def name(self) -> str:
        return f"{self.api.get_device_name()} {self._chime_name} Play Chime"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:bell-outline"

    async def async_press(self) -> None:
        """Play the chime."""
        await self.api.play_chime(self._chime_id)
