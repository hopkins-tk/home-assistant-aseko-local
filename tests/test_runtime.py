"""Which entries the services and the recording views act on (audit D3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.aseko_local import _check_backwash_history_ready
from custom_components.aseko_local.coordinator import BackwashHistoryLoadingError
from custom_components.aseko_local.runtime import loaded_entries


def _entry(state: ConfigEntryState, *, runtime_data: object = True) -> MagicMock:
    entry = MagicMock()
    entry.state = state
    entry.runtime_data = runtime_data
    return entry


@pytest.mark.parametrize(
    "state",
    [
        ConfigEntryState.SETUP_IN_PROGRESS,
        ConfigEntryState.SETUP_RETRY,
        ConfigEntryState.SETUP_ERROR,
        ConfigEntryState.NOT_LOADED,
    ],
)
def test_an_entry_not_loaded_is_skipped_even_with_runtime_data(state) -> None:
    """runtime_data is set early in the set-up and stays for a retry."""
    hass = MagicMock()
    loaded = _entry(ConfigEntryState.LOADED)
    hass.config_entries.async_entries.return_value = [_entry(state), loaded]

    assert loaded_entries(hass) == [loaded]


def test_a_loaded_entry_without_runtime_data_is_skipped() -> None:
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [
        _entry(ConfigEntryState.LOADED, runtime_data=None)
    ]

    assert loaded_entries(hass) == []


def _aseko_entry(coordinator: object) -> MagicMock:
    entry = MagicMock()
    entry.state = ConfigEntryState.LOADED
    entry.runtime_data.coordinator = coordinator
    return entry


def test_one_entry_still_reading_its_history_stops_the_service_before_any_write() -> (
    None
):
    """Audit R1: the check is asked of every entry before the first one writes."""
    ready = MagicMock()
    ready.loading_backwash_serials.return_value = []
    reading = MagicMock()
    reading.loading_backwash_serials.return_value = [4321]
    hass = MagicMock()

    for order in ([ready, reading], [reading, ready]):
        hass.config_entries.async_entries.return_value = [
            _aseko_entry(coordinator) for coordinator in order
        ]
        with pytest.raises(BackwashHistoryLoadingError, match="4321"):
            _check_backwash_history_ready(hass, None)
        assert ready.set_last_scheduled_backwash.call_count == 0
        assert ready.clear_last_scheduled_backwash.call_count == 0

    reading.loading_backwash_serials.return_value = []
    _check_backwash_history_ready(hass, None)  # both in: nothing raised


def test_the_serial_of_the_call_is_passed_on_to_every_entry() -> None:
    coordinator = MagicMock()
    coordinator.loading_backwash_serials.return_value = []
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [_aseko_entry(coordinator)]

    _check_backwash_history_ready(hass, 110071590)

    coordinator.loading_backwash_serials.assert_called_once_with(110071590)
