"""Test the Aseko Local config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.aseko_local.aseko_server import ServerConnectionError
from custom_components.aseko_local.const import DOMAIN


async def test_form(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test we get the form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result.get("type") is FlowResultType.FORM
    assert result.get("errors") == {}

    with patch(
        "custom_components.aseko_local.aseko_server.AsekoDeviceServer.start",
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_PORT: 12345,
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
        "custom_components.aseko_local.aseko_server.AsekoDeviceServer.start",
        side_effect=ServerConnectionError,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_PORT: 12345,
            },
        )
    assert result.get("type") is FlowResultType.FORM
    assert result.get("errors") == {"base": "cannot_connect"}

    # Make sure the config flow tests finish with either an
    # FlowResultType.CREATE_ENTRY or FlowResultType.ABORT so
    # we can show the config flow is able to recover from an error.

    with patch(
        "custom_components.aseko_local.aseko_server.AsekoDeviceServer.start",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_PORT: 12345,
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
