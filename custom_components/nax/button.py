from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NaxEntity
from .const import DOMAIN
from .nax.nax_api import NaxApi


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities_to_add = []
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = api.get_device_mac_address()

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


class NaxBaseButton(NaxEntity, ButtonEntity):
    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the button."""
        super().__init__(api=api, unique_id=unique_id)
        self.entity_id = f"button.{self._attr_unique_id}"


class NaxChimePlayButton(NaxBaseButton):
    """Representation of a Nax chime play button."""

    def __init__(self, api: NaxApi, unique_id: str, chime_id: str, chime_name) -> None:
        """Initialize the chime play button."""
        super().__init__(api, unique_id)
        self._chime_id = chime_id
        self._chime_name = chime_name
        self._attr_icon = "mdi:bell-outline"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self._chime_name} Play Chime"

    async def async_press(self) -> None:
        """Play the chime."""
        await self.api.play_chime(self._chime_id)
