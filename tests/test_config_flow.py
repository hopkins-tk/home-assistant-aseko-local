"""Test the Aseko Local config flow."""

from unittest.mock import AsyncMock, call, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aseko_local.config_flow import (
    AsekoLocalConfigFlow,
    CannotConnectError,
    _remove_entry_server,
    parse_port,
    validate_input,
)
from custom_components.aseko_local.const import (
    CONF_CLOCK_ALERT_MINUTES,
    CONF_FORWARDER_ENABLED,
    CONF_FORWARDER_HOST,
    DEFAULT_FORWARDER_HOST,
    DOMAIN,
)
from custom_components.aseko_local.server import (
    AsekoDeviceServer,
    ServerConnectionError,
)


async def test_form(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test we get the form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result.get("type") is FlowResultType.FORM
    assert result.get("errors") == {}

    with patch(
        "custom_components.aseko_local.server.AsekoDeviceServer.start",
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_PORT: "12345",  # the port picker sends text
            },
        )
        await hass.async_block_till_done()

    assert result.get("type") is FlowResultType.CREATE_ENTRY
    assert result.get("title") == "Aseko Local - 1.1.1.1:12345"
    assert result.get("data") == {
        CONF_HOST: "1.1.1.1",
        CONF_PORT: 12345,
    }


async def test_form_cannot_connect(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.aseko_local.server.AsekoDeviceServer.start",
        side_effect=ServerConnectionError,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_PORT: "12345",  # the port picker sends text
            },
        )
    assert result.get("type") is FlowResultType.FORM
    assert result.get("errors") == {"base": "cannot_connect"}

    # Make sure the config flow tests finish with either an
    # FlowResultType.CREATE_ENTRY or FlowResultType.ABORT so
    # we can show the config flow is able to recover from an error.

    with patch(
        "custom_components.aseko_local.server.AsekoDeviceServer.start",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_PORT: "12345",  # the port picker sends text
            },
        )
        await hass.async_block_till_done()

    assert result.get("type") is FlowResultType.CREATE_ENTRY
    assert result.get("title") == "Aseko Local - 1.1.1.1:12345"
    assert result.get("data") == {
        CONF_HOST: "1.1.1.1",
        CONF_PORT: 12345,
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_options_flow(
    hass, mock_config_entry, mock_setup_entry: AsyncMock
) -> None:
    """Test the options flow for Aseko Local."""

    # If the fixture is async:
    if callable(getattr(mock_config_entry, "__await__", None)):
        mock_config_entry = await mock_config_entry

    # Start options flow
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "options_init"

    options = {
        CONF_FORWARDER_ENABLED: True,
        CONF_FORWARDER_HOST: DEFAULT_FORWARDER_HOST,
        CONF_CLOCK_ALERT_MINUTES: 10,
    }

    with patch("custom_components.aseko_local.server.AsekoDeviceServer.remove_all"):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            options,
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"] == options


async def test_form_refuses_a_port_that_is_not_a_number(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A typed port that is no number shows an error on the port field."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "1.1.1.1", CONF_PORT: "not a port"}
    )
    assert result.get("type") is FlowResultType.FORM
    assert result.get("errors") == {CONF_PORT: "invalid_port"}


@pytest.mark.parametrize("port", ["0", "65536", " 51050 "])
def test_parse_port_accepts_only_real_ports(port: str) -> None:
    if port.strip() == "51050":
        assert parse_port(port) == 51050
    else:
        with pytest.raises(ValueError, match="out of range"):
            parse_port(port)


async def test_form_reports_an_unexpected_error(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.aseko_local.config_flow.validate_input",
        side_effect=RuntimeError("bug"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.1.1.1", CONF_PORT: "12345"}
        )
    assert result.get("errors") == {"base": "unknown"}


async def test_an_address_already_listening_is_not_bound_again(
    hass: HomeAssistant, listeners
) -> None:
    """A test bind would stop the live server of the entry that owns the port."""
    await AsekoDeviceServer.remove_all()
    live = await AsekoDeviceServer.create(host="1.1.1.1", port=12346)

    info = await validate_input({CONF_HOST: "1.1.1.1", CONF_PORT: 12346})

    assert info == {"title": "Aseko Local - 1.1.1.1:12346"}
    assert len(listeners) == 1
    assert live.running
    await AsekoDeviceServer.remove_all()


async def test_a_failed_test_bind_leaves_no_server_behind(hass: HomeAssistant) -> None:
    await AsekoDeviceServer.remove_all()
    with (
        patch.object(AsekoDeviceServer, "start", side_effect=ServerConnectionError),
        pytest.raises(CannotConnectError),
    ):
        await validate_input({CONF_HOST: "1.1.1.1", CONF_PORT: 12347})
    assert AsekoDeviceServer.get("1.1.1.1", 12347) is None


async def test_removing_the_server_of_an_entry_without_an_address() -> None:
    with patch.object(AsekoDeviceServer, "remove", AsyncMock()) as remove:
        await _remove_entry_server(None)
        await _remove_entry_server(MockConfigEntry(domain=DOMAIN, data={}))
        await _remove_entry_server(
            MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "1.1.1.1", CONF_PORT: 1})
        )
    remove.assert_awaited_once_with("1.1.1.1", 1)


# -- reconfigure ---------------------------------------------------------------


def _existing_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Aseko Local - 0.0.0.0:47524",
        data={CONF_HOST: "0.0.0.0", CONF_PORT: 47524},
        unique_id="aseko",
    )
    entry.add_to_hass(hass)
    return entry


async def test_reconfigure_shows_the_current_address(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    defaults = {key.schema: key.default() for key in result["data_schema"].schema}
    assert defaults == {CONF_HOST: "0.0.0.0", CONF_PORT: "47524"}


async def test_reconfigure_keeps_the_typed_values_on_an_error(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "2.2.2.2", CONF_PORT: "no port"}
    )
    assert result["errors"] == {CONF_PORT: "invalid_port"}

    with patch.object(AsekoDeviceServer, "start", side_effect=ServerConnectionError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "2.2.2.2", CONF_PORT: "51050"}
        )
    assert result["errors"] == {"base": "cannot_connect"}
    defaults = {key.schema: key.default() for key in result["data_schema"].schema}
    assert defaults == {CONF_HOST: "2.2.2.2", CONF_PORT: "51050"}

    with patch(
        "custom_components.aseko_local.config_flow.validate_input",
        side_effect=RuntimeError("bug"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "2.2.2.2", CONF_PORT: "51050"}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_reconfigure_moves_the_entry_to_the_new_address(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)

    with (
        patch.object(AsekoDeviceServer, "start"),
        patch.object(AsekoDeviceServer, "remove", AsyncMock()) as remove,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "2.2.2.2", CONF_PORT: "51050"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_HOST: "2.2.2.2", CONF_PORT: 51050}
    assert entry.title == "Aseko Local - 2.2.2.2:51050"
    # the old address's server is stopped; the test bind removed its own
    assert call("0.0.0.0", 47524) in remove.await_args_list


async def test_reconfigure_without_an_entry_aborts(hass: HomeAssistant) -> None:
    flow = AsekoLocalConfigFlow()
    flow.hass = hass

    flow.context = {"source": config_entries.SOURCE_RECONFIGURE}
    result = await flow.async_step_reconfigure()
    assert result["reason"] == "missing_entry_id"

    flow.context = {"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "gone"}
    result = await flow.async_step_reconfigure()
    assert result["reason"] == "missing_entry"


# -- options -------------------------------------------------------------------


async def test_options_form_shows_the_saved_options(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "0.0.0.0", CONF_PORT: 47524},
        options={
            CONF_FORWARDER_ENABLED: True,
            CONF_FORWARDER_HOST: "cloud.test",
            CONF_CLOCK_ALERT_MINUTES: 30,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    defaults = {key.schema: key.default() for key in result["data_schema"].schema}
    assert defaults == {
        CONF_FORWARDER_ENABLED: True,
        CONF_FORWARDER_HOST: "cloud.test",
        CONF_CLOCK_ALERT_MINUTES: 30,
    }


async def test_saving_options_stops_only_this_entrys_server_and_reloads(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    entry = _existing_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with (
        patch.object(AsekoDeviceServer, "remove", AsyncMock()) as remove,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_FORWARDER_ENABLED: False,
                CONF_FORWARDER_HOST: DEFAULT_FORWARDER_HOST,
                CONF_CLOCK_ALERT_MINUTES: 15,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    remove.assert_awaited_once_with("0.0.0.0", 47524)
    reload.assert_awaited_once_with(entry.entry_id)
