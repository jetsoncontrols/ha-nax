"""Config Flow for NAX Home Assistant Integration."""

from typing import Any

import voluptuous as vol

from cresnextws import ClientConfig, CresNextWSClient
from homeassistant import config_entries
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import homeassistant.helpers.config_validation as cv

from .const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


DISCOVERY_CONFIRM_SCHEMA = vol.Schema(
    {
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
        self._discovered_host: str | None = None
        self._discovered_hostname: str | None = None
        self._discovered_mac: str | None = None

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle DHCP discovery of a NAX device."""
        mac = discovery_info.macaddress.upper()
        # Format MAC as XX:XX:XX:XX:XX:XX
        if ":" not in mac and len(mac) == 12:
            mac = ":".join(mac[i : i + 2] for i in range(0, 12, 2))

        self._discovered_host = discovery_info.ip
        self._discovered_hostname = discovery_info.hostname.upper()
        self._discovered_mac = mac

        # Abort if any existing entry already uses this host (covers legacy
        # entries that were created before unique_id backfill)
        for entry in self._async_current_entries():
            if entry.data.get(CONF_HOST) == self._discovered_host:
                return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: self._discovered_host}
        )

        self.context["title_placeholders"] = {"name": self._discovered_hostname}
        return await self.async_step_discovery_confirm()

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle discovery of a NAX device via CIP broadcast."""
        mac = discovery_info["mac"]
        self._discovered_host = discovery_info[CONF_HOST]
        self._discovered_hostname = discovery_info["hostname"]
        self._discovered_mac = mac

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: self._discovered_host}
        )

        self.context["title_placeholders"] = {"name": self._discovered_hostname}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm discovery and gather credentials."""
        errors = {}
        if user_input is not None:
            full_input = {
                CONF_HOST: self._discovered_host,
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            api = None
            try:
                connected, api = await self.login(full_input)
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    device_name_response = await api.http_get("/Device/DeviceInfo/Name")
                    if device_name_response and "content" in device_name_response:
                        device_name = device_name_response["content"]["Device"][
                            "DeviceInfo"
                        ]["Name"]
                    else:
                        device_name = self._discovered_hostname
                    return self.async_create_entry(title=device_name, data=full_input)
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            finally:
                if api is not None:
                    await api.disconnect()

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=DISCOVERY_CONFIRM_SCHEMA,
            description_placeholders={
                "host": self._discovered_host,
                "hostname": self._discovered_hostname,
            },
            errors=errors,
        )

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
