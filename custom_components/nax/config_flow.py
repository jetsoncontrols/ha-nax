"""Config Flow for NAX Home Assistant Integration."""

from typing import Any

import voluptuous as vol

from cresnextws import ClientConfig, CresNextWSClient
from homeassistant import config_entries
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
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self.config_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the user step of the config flow."""
        errors = {}
        if user_input is not None:
            api = None
            try:
                connected, api = await self.login(user_input)
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    device_name_response = await api.http_get("/Device/DeviceInfo/Name")
                    if device_name_response and "content" in device_name_response:
                        device_name = device_name_response["content"]["Device"][
                            "DeviceInfo"
                        ]["Name"]
                    else:
                        device_name = f"NAX Device ({user_input[CONF_HOST]})"
                    return self.async_create_entry(title=device_name, data=user_input)
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            finally:
                if api is not None:
                    await api.disconnect()
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the reconfigure of the config flow."""
        entry_id = self.context.get("entry_id")
        if entry_id is None:
            return self.async_abort(reason="missing_entry_id")

        self.config_entry = self.hass.config_entries.async_get_entry(entry_id)
        if self.config_entry is None:
            return self.async_abort(reason="entry_not_found")
        errors = {}
        if user_input is not None:
            api = None
            try:
                connected, api = await self.login(user_input)
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    device_name_response = await api.http_get("/Device/DeviceInfo/Name")
                    if device_name_response and "content" in device_name_response:
                        device_name = device_name_response["content"]["Device"][
                            "DeviceInfo"
                        ]["Name"]
                    else:
                        device_name = f"NAX Device ({user_input[CONF_HOST]})"
                    return self.async_update_reload_and_abort(
                        self.config_entry,
                        title=device_name,
                        data=user_input,
                        reason="reconfigure_successful",
                    )
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            finally:
                if api is not None:
                    await api.disconnect()

        return self.async_show_form(
            step_id="reconfigure", data_schema=DATA_SCHEMA, errors=errors
        )

    async def login(self, user_input: dict[str, Any]) -> tuple[bool, CresNextWSClient]:
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
