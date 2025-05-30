"""Config flow for Example Integration integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .aseko_server import AsekoDeviceServer, ServerConnectionError
from .const import DEFAULT_BINDING_ADDRESS, DEFAULT_BINDING_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_BINDING_ADDRESS): str,
        vol.Required(CONF_PORT, default=DEFAULT_BINDING_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    try:
        await AsekoDeviceServer.create(host=data[CONF_HOST], port=data[CONF_PORT])
        await AsekoDeviceServer.remove(host=data[CONF_HOST], port=data[CONF_PORT])
        # If you cannot connect, raise CannotConnect
    except ServerConnectionError as err:
        await AsekoDeviceServer.remove(host=data[CONF_HOST], port=data[CONF_PORT])
        raise CannotConnectError from err
    return {"title": f"Aseko Local - {data[CONF_HOST]}:{data[CONF_PORT]}"}


class AsekoLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Example Integration."""

    VERSION = 1
    _input_data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        # Called when you initiate adding an integration via the UI
        errors: dict[str, str] = {}

        if user_input is not None:
            # The form has been filled in and submitted, so process the data provided.
            try:
                # Validate that the setup data is valid and if not handle errors.
                # The errors["base"] values match the values in your strings.json and translation files.
                info = await validate_input(self.hass, user_input)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            if "base" not in errors:
                # Validation was successful, so create a unique id for this instance of your integration
                # and create the config entry.
                await self._async_handle_discovery_without_unique_id()
                return self.async_create_entry(title=info["title"], data=user_input)

        # Show initial form.
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add reconfigure step to allow to reconfigure a config entry."""
        # This methid displays a reconfigure option in the integration and is
        # different to options.
        # It can be used to reconfigure any of the data submitted when first installed.
        # This is optional and can be removed if you do not want to allow reconfiguration.
        errors: dict[str, str] = {}
        entry_id = self.context.get("entry_id")

        if entry_id is None:
            return self.async_abort(reason="missing_entry_id")

        config_entry = self.hass.config_entries.async_get_entry(entry_id)

        if config_entry is None:
            return self.async_abort(reason="missing_entry")

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    config_entry,
                    title=info["title"],
                    unique_id=config_entry.unique_id,
                    data={**config_entry.data, **user_input},
                    reason="reconfigure_successful",
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=user_input[CONF_HOST]
                        if user_input is not None
                        else config_entry.data[CONF_HOST],
                    ): str,
                    vol.Required(
                        CONF_PORT,
                        default=user_input[CONF_PORT]
                        if user_input is not None
                        else config_entry.data[CONF_PORT],
                    ): int,
                }
            ),
            errors=errors,
        )


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""
