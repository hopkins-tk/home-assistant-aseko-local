"""Config flow for Aseko Local integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CLOCK_ALERT_MINUTES,
    CONF_FORWARDER_ENABLED,
    CONF_FORWARDER_HOST,
    DEFAULT_BINDING_ADDRESS,
    DEFAULT_BINDING_PORT,
    DEFAULT_FORWARDER_HOST,
    DEFAULT_FORWARDER_PORT_V8,
    DOMAIN,
)
from .server import AsekoDeviceServer, ServerConnectionError
from .trackers.clock import DEFAULT_ALERT_MINUTES

_LOGGER = logging.getLogger(__name__)


# The two ports Aseko units send to out of the box; any other can be typed.
PORT_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            SelectOptionDict(
                value=str(DEFAULT_BINDING_PORT), label=str(DEFAULT_BINDING_PORT)
            ),
            SelectOptionDict(
                value=str(DEFAULT_FORWARDER_PORT_V8),
                label=str(DEFAULT_FORWARDER_PORT_V8),
            ),
        ],
        custom_value=True,
        mode=SelectSelectorMode.DROPDOWN,
        translation_key="port",
    )
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_BINDING_ADDRESS): str,
        vol.Required(CONF_PORT, default=str(DEFAULT_BINDING_PORT)): PORT_SELECTOR,
    }
)


MAX_PORT = 65535


def parse_port(value: object) -> int:
    """Return the port a user picked or typed, as a number; ValueError when it is none."""
    port = int(str(value).strip())
    if not 1 <= port <= MAX_PORT:
        msg = f"port {port} out of range"
        raise ValueError(msg)
    return port


async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    existing = AsekoDeviceServer.get(data[CONF_HOST], data[CONF_PORT])
    if existing is not None and existing.running:
        # Already listening there (this entry's own server on a reconfigure):
        # the address works, and a test bind would stop the live server.
        return {"title": f"Aseko Local - {data[CONF_HOST]}:{data[CONF_PORT]}"}
    try:
        await AsekoDeviceServer.create(host=data[CONF_HOST], port=data[CONF_PORT])
        await AsekoDeviceServer.remove(host=data[CONF_HOST], port=data[CONF_PORT])
    except ServerConnectionError as err:
        await AsekoDeviceServer.remove(host=data[CONF_HOST], port=data[CONF_PORT])
        raise CannotConnectError from err
    return {"title": f"Aseko Local - {data[CONF_HOST]}:{data[CONF_PORT]}"}


async def _remove_entry_server(config_entry: ConfigEntry | None) -> None:
    """Stop the server of this entry only; an entry without an address has none."""
    if config_entry is None:
        return
    host = config_entry.data.get(CONF_HOST)
    port = config_entry.data.get(CONF_PORT)
    if host is not None and port is not None:
        await AsekoDeviceServer.remove(host, port)


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
                user_input = {
                    **user_input,
                    CONF_PORT: parse_port(user_input[CONF_PORT]),
                }
            except ValueError:
                errors[CONF_PORT] = "invalid_port"
        if user_input is not None and not errors:
            try:
                info = await validate_input(user_input)
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
                user_input = {
                    **user_input,
                    CONF_PORT: parse_port(user_input[CONF_PORT]),
                }
            except ValueError:
                errors[CONF_PORT] = "invalid_port"
        if user_input is not None and not errors:
            try:
                info = await validate_input(user_input)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Stop only this entry's server; the reload's unload removes it
                # too, and the other entries keep receiving.
                await _remove_entry_server(config_entry)
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
                        default=str(
                            user_input[CONF_PORT]
                            if user_input is not None
                            else config_entry.data[CONF_PORT]
                        ),
                    ): PORT_SELECTOR,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> AsekoLocalOptionsFlowHandler:
        """Link options flow to config flow."""
        return AsekoLocalOptionsFlowHandler(config_entry)


class AsekoLocalOptionsFlowHandler(OptionsFlow):
    """Handle Aseko Local options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Remember which config entry the options belong to."""
        self._entry_id = config_entry.entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the options flow."""
        return await self.async_step_options_init(user_input)

    async def async_step_options_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the forwarder and clock options, and save and reload on submit."""
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(self._entry_id)

        if user_input is not None:
            # Stop only this entry's server before its reload; other entries
            # keep receiving.
            await _remove_entry_server(config_entry)

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
                    CONF_CLOCK_ALERT_MINUTES,
                    default=config_entry.options.get(
                        CONF_CLOCK_ALERT_MINUTES, DEFAULT_ALERT_MINUTES
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=180,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="options_init", data_schema=options_schema, errors=errors
        )


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""
