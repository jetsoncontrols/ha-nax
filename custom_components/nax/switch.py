import logging

from homeassistant.components.switch import SwitchEntity
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
    """Set up NAX switch entities for a config entry."""
    _LOGGER.debug("Setting up NAX switch entities for %s", config_entry.entry_id)
    api: NaxApi = hass.data[DOMAIN][config_entry.entry_id]

    mac_address = await hass.async_add_executor_job(api.get_device_mac_address)

    entities_to_add = []
    zones = await hass.async_add_executor_job(api.get_all_zone_outputs)
    if not zones:
        _LOGGER.debug(
            "No zone outputs returned for NAX device %s; skipping switch entities",
            mac_address,
        )
    else:
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


class NaxBaseSwitch(NaxEntity, SwitchEntity):
    """Base class for NAX switches."""

    def __init__(self, api: NaxApi, unique_id: str) -> None:
        """Initialize the base switch with API reference and unique ID."""
        super().__init__(api=api, unique_id=unique_id)
        self.entity_id = f"switch.{self._attr_unique_id}"


class NaxZoneTestToneSwitch(NaxBaseSwitch):
    """Representation of an NAX zone signal generator switch."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the test tone switch for a zone output."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:square-wave"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.IsTestToneActive",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Test Tone"

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
    """Representation of an NAX zone loudness switch."""

    def __init__(self, api: NaxApi, unique_id: str, zone_output: str) -> None:
        """Initialize the loudness switch for a zone output."""
        super().__init__(api, unique_id)
        self.zone_output = zone_output
        self._attr_icon = "mdi:bullhorn-variant-outline"
        self.__subscriptions()

    def __subscriptions(self) -> None:
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.ZoneAudio.IsLoudnessEnabled",
            self._generic_update,
        )
        self.api.subscribe_data_updates(
            f"Device.ZoneOutputs.Zones.{self.zone_output}.Name",
            self._generic_update,
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.api.get_device_name()} {self.api.get_zone_name(self.zone_output)} Zone Loudness"

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
