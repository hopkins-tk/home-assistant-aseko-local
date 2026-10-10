"""A unit type nobody has mapped gets no entities but does reach diagnostics."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from custom_components.aseko_local.coordinator import AsekoLocalDataUpdateCoordinator
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.decoding.profiles import v7
from custom_components.aseko_local.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .test_decode_v7 import _make_base_bytes


@pytest.fixture(autouse=True)
def _quiet_logging() -> Iterator[None]:
    """Silence logging for this module's tests only, and turn it back on."""
    before = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(before)


SERIAL = 1234


def _diagnostics_hass() -> MagicMock:
    """Return a hass whose executor runs the job inline, as diagnostics hands work to it."""

    async def run_inline(job, *args: object) -> object:
        return job(*args)

    hass = MagicMock()
    hass.async_add_executor_job = run_inline
    return hass


def _unknown_frame() -> bytes:
    data = _make_base_bytes()
    data[4] = 0x00  # maps to no model
    return bytes(data)


def _coordinator() -> AsekoLocalDataUpdateCoordinator:
    hass = MagicMock()
    hass.config.path.side_effect = lambda *parts: "/tmp/aseko_test/" + "/".join(parts)
    hass.async_create_task.side_effect = lambda coro, *args, **kwargs: coro.close()
    entry = MagicMock()
    entry.data = {"host": "0.0.0.0", "port": 47524}
    entry.unique_id = "test"
    return AsekoLocalDataUpdateCoordinator(hass, entry)


def test_unknown_type_reads_everything_generic() -> None:
    device = decode(_unknown_frame())
    assert device.device_type is None
    # the generic readings did their job on the base frame
    assert device.ph == 0.0  # bytes 14-15 are zero in the base frame
    assert device.water_temperature == 24.5
    assert device.filtration_period_1_start is not None
    assert device.backwash_interval == 3
    assert "filtration_running" in device.features
    # and nothing model-specific was guessed
    for field in (
        "salinity",
        "oxygen_dose_target",
        "heating_control_enabled",
        "air_temperature",
    ):
        assert field not in v7.UNKNOWN.feature_names, field


def test_unrecognised_unit_is_kept_aside_not_stored() -> None:
    coordinator = _coordinator()
    discovered: list = []
    grown: list = []
    coordinator.async_add_new_device_listener(discovered.append)
    coordinator.async_add_new_features_listener(lambda d, f: grown.append(f))

    coordinator.devices_update_callback(decode(_unknown_frame()))
    coordinator.devices_update_callback(decode(_unknown_frame()))

    assert coordinator.get_devices() == []
    assert discovered == []
    assert grown == []
    unrecognised = coordinator.get_unrecognised_devices()
    assert [d.serial_number for d in unrecognised] == [SERIAL]


def test_diagnostics_report_the_unrecognised_unit_with_its_frame() -> None:
    coordinator = _coordinator()
    raw = _unknown_frame()
    coordinator.store_raw_frame(raw)
    coordinator.devices_update_callback(decode(raw))

    entry = MagicMock()
    entry.data = {"host": "0.0.0.0", "port": 47524}
    entry.options = {}
    entry.runtime_data.coordinator = coordinator

    dump = asyncio.run(async_get_config_entry_diagnostics(_diagnostics_hass(), entry))

    assert dump["devices"] == []
    assert len(dump["unrecognised_devices"]) == 1
    entry_dump = dump["unrecognised_devices"][0]
    assert entry_dump["device"]["serial_number"] == SERIAL
    assert entry_dump["device"]["device_type"] is None
    assert entry_dump["device"]["profile"] == v7.UNKNOWN.name
    assert entry_dump["device"]["water_temperature"] == 24.5
    assert entry_dump["raw_frame_v7"]["available"] is True
    assert entry_dump["raw_frame_v7"]["hex_dump"] == raw.hex()
    assert "GitHub issue" in entry_dump["note"]


def test_diagnostics_still_report_a_known_unit_the_same_way() -> None:
    coordinator = _coordinator()
    raw = bytes(_make_base_bytes())  # SALT
    coordinator.store_raw_frame(raw)
    coordinator.devices_update_callback(decode(raw))

    entry = MagicMock()
    entry.data = {"host": "0.0.0.0", "port": 47524}
    entry.options = {}
    entry.runtime_data.coordinator = coordinator

    dump = asyncio.run(async_get_config_entry_diagnostics(_diagnostics_hass(), entry))

    assert dump["unrecognised_devices"] == []
    (info,) = dump["devices"]
    assert info["device"]["device_type"] == "ASIN AQUA Salt"
    assert info["device"]["features"]
    # which profile read it, and where it reads differently from the default
    assert info["device"]["profile"] == "v7 SALT"
    overrides = info["device"]["reading_overrides"]
    assert overrides["freeze_protection_enabled"] == "decode_v7_winter_mode"
    assert info["device"]["frame_problems"] == []
    assert info["raw_frame_v7"]["available"] is True
    assert info["raw_frame_v8"]["available"] is False
    assert info["partial_frame"]["available"] is False
