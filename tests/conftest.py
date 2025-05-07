"""Common fixtures for the Aseko Local tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from custom_components.aseko_local.aseko_server import ServerConnectionError


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""
    return


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.aseko_local.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications. These calls would fail without this fixture since the persistent_notification
# integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture() -> Generator:
    """Skip notification calls."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield


# This fixture, when used, will result in calls to async_get_data to return None. To have the call
# return a value, we would add the `return_value=<VALUE_TO_RETURN>` parameter to the patch call.
@pytest.fixture(name="bypass_get_data")
def bypass_get_data_fixture() -> Generator:
    """Skip calls to get data from API."""
    with patch("custom_components.aseko_local.AsekoDeviceServer.start"):
        yield


# In this fixture, we are forcing calls to async_get_data to raise an Exception. This is useful
# for exception handling.
@pytest.fixture(name="error_on_get_data")
def error_get_data_fixture() -> Generator:
    """Simulate error when retrieving data from API."""
    with patch(
        "custom_components.aseko_local.AsekoDeviceServer.start",
        side_effect=ServerConnectionError,
    ):
        yield


@pytest.fixture(name="api_server_running")
def api_server_running_fixture() -> Generator:
    """Skip calls to chech if the server is running."""

    with patch(
        "custom_components.aseko_local.AsekoDeviceServer.running",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


@pytest.fixture(name="api_server_not_running")
def api_server_not_running_fixture() -> Generator:
    """Skip calls to chech if the server is running."""

    with patch(
        "custom_components.aseko_local.AsekoDeviceServer.running",
        new_callable=PropertyMock,
        return_value=False,
    ):
        yield
