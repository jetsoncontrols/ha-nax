from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant import config_entries, exceptions
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from .nax.nax_api import NaxApi

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

DATA_SCHEME = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


class NaxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input[CONF_HOST] is None:
                raise exceptions.HomeAssistantError
            elif user_input[CONF_USERNAME] is None:
                raise exceptions.HomeAssistantError
            elif user_input[CONF_PASSWORD] is None:
                raise exceptions.HomeAssistantError
            else:
                api = NaxApi(
                    ip=user_input[CONF_HOST],
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                )
                connected, message = await self.hass.async_add_executor_job(api.http_login)
                if not connected:
                    errors["base"] = message
                else:
                    device_name = await self.hass.async_add_executor_job(
                        api.get_device_name
                    )
                    return self.async_create_entry(title=device_name, data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEME, errors=errors
        )
