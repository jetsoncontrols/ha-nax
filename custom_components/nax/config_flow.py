"""Config Flow for NAX Home Assistant Integration."""

from typing import Any

import voluptuous as vol

from cresnextws import ClientConfig, CresNextWSClient
from homeassistant import config_entries, exceptions
import homeassistant.helpers.config_validation as cv

from .const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


class NaxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Nax integration."""

    VERSION = 1
    config_entry: config_entries.ConfigEntry | None

    async def async_step_user(self, user_input=None):
        """Handle the user step of the config flow."""
        errors = {}
        if user_input is not None:
            errors = self.check_for_user_input_errors(user_input)
            if errors:
                raise exceptions.ConfigEntryError
            connected, api = await self.login(user_input)
            if not connected:
                errors["base"] = "cannot_connect"
            else:
                device_name_response = await api.http_get("/Device/DeviceInfo/Name")
                device_name = device_name_response["content"]["Device"]["DeviceInfo"][
                    "Name"
                ]
                return self.async_create_entry(title=device_name, data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Handle the reconfigure of the config flow."""
        self.config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        errors = {}
        if user_input is not None:
            errors = self.check_for_user_input_errors(user_input)
            if errors:
                raise exceptions.ConfigEntryError
            connected, api = await self.login(user_input)
            if not connected:
                errors["base"] = "cannot_connect"
            else:
                device_name_response = await api.http_get("/Device/DeviceInfo/Name")
                device_name = device_name_response["content"]["Device"]["DeviceInfo"][
                    "Name"
                ]
                return self.async_update_reload_and_abort(
                    self.config_entry,
                    title=device_name,
                    data=user_input,
                    reason="reconfigure_successful",
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=DATA_SCHEMA, errors=errors
        )

    def check_for_user_input_errors(self, user_input):
        """Check for errors in the user input."""
        errors = {}
        if (
            user_input[CONF_HOST] is None
            or user_input[CONF_USERNAME] is None
            or user_input[CONF_PASSWORD] is None
        ):
            errors["base"] = "missing_data"
        return errors

    async def login(self, user_input) -> tuple[bool, CresNextWSClient]:
        """Login to the NAX API using the provided user input."""
        api = CresNextWSClient(
            ClientConfig(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )
        )
        connected = await api.connect()
        return connected, api
