"""Config flow for Aseko Local integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    DEFAULT_BINDING_ADDRESS,
    DEFAULT_BINDING_PORT,
    DEFAULT_FORWARDER_HOST,
    DEFAULT_FORWARDER_PORT,
    CONF_FORWARDER_ENABLED,
    CONF_FORWARDER_HOST,
    CONF_FORWARDER_PORT,
)
from .aseko_server import AsekoDeviceServer, ServerConnectionError

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
    except ServerConnectionError as err:
        await AsekoDeviceServer.remove(host=data[CONF_HOST], port=data[CONF_PORT])
        raise CannotConnectError from err
    return {"title": f"Aseko Local - {data[CONF_HOST]}:{data[CONF_PORT]}"}


class AsekoLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aseko Local."""

    VERSION = 1
    _input_data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self._async_handle_discovery_without_unique_id()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow reconfiguration of an existing entry."""
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
                # 🛑 Server hart stoppen, bevor neu geladen wird
                await AsekoDeviceServer.remove_all()
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Link options flow to config flow."""
        return AsekoLocalOptionsFlowHandler(config_entry)


class AsekoLocalOptionsFlowHandler(OptionsFlow):
    """Handle Aseko Local options."""

    def __init__(self, config_entry):
        self._entry_id = config_entry.entry_id

    async def async_step_init(self, user_input=None):
        return await self.async_step_options_init(user_input)

    async def async_step_options_init(self, user_input=None):
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(self._entry_id)

        if user_input is not None:
            # 🛑 Server hart stoppen, bevor neu geladen wird
            await AsekoDeviceServer.remove_all()

            # save the options
            entry = self.async_create_entry(title="", data=user_input)

            # Reload integration to apply new options
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(config_entry.entry_id)
            )
            return entry

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FORWARDER_ENABLED,
                    default=config_entry.options.get(CONF_FORWARDER_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_FORWARDER_HOST,
                    default=config_entry.options.get(
                        CONF_FORWARDER_HOST, DEFAULT_FORWARDER_HOST
                    ),
                ): str,
                vol.Optional(
                    CONF_FORWARDER_PORT,
                    default=config_entry.options.get(
                        CONF_FORWARDER_PORT, DEFAULT_FORWARDER_PORT
                    ),
                ): int,
                # vol.Optional(
                #     CONF_ENABLE_RAW_LOGGING,
                #     default=config_entry.options.get(CONF_ENABLE_RAW_LOGGING, False),
                # ): bool,
            }
        )

        return self.async_show_form(
            step_id="options_init", data_schema=options_schema, errors=errors
        )


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""
