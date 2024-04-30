"""Support for Nax media player."""

# https://developers.home-assistant.io/docs/core/entity/media-player?_highlight=media

import logging
from homeassistant.components.media_player import (
    MediaPlayerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .nax.nax_api import NaxApi

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load NAX media players"""
    name: str = config_entry.data[CONF_NAME]
    assert config_entry.unique_id is not None
    api: NaxApi = hass.data[DOMAIN][config_entry.unique_id]
    # async_add_entities([NaxMediaPlayer(name, config_entry.unique_id, api)])


class NaxMediaPlayer(MediaPlayerEntity):
    """Representation of an NAX media player."""

    name: str = None
    unique_id: str = None
    api: NaxApi = None

    def __init__(self, name: str, unique_id: str, api: NaxApi) -> None:
        self.name = name
        self.unique_id = unique_id
        self.api = api
