"""Tests for the Aseko Local button platform (canister-reset buttons)."""

import pytest
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntry

from custom_components.aseko_local.button import (
    async_setup_entry,
    AsekoResetButtonEntity,
)
from custom_components.aseko_local.aseko_decoder import AsekoDecoder
from custom_components.aseko_local.aseko_data import AsekoDeviceType
from custom_components.aseko_local.const import WATER_FLOW_TO_PROBES


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_net_bytes() -> bytearray:
    data = bytearray([0xFF] * 120)
    data[0:4] = (1001).to_bytes(4, "big")
    data[4] = 0x09  # NET with CLF probe
    data[6:12] = [24, 6, 15, 12, 0, 0]
    data[14:16] = (700).to_bytes(2, "big")
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = (
        0x00  # no pump running, but masks are set → running_attr = False (not None)
    )
    data[94:96] = (60).to_bytes(
        2, "big"
    )  # max_filling_time (byte 95 = flowrate_ph_minus = 60)
    data[99] = 60  # flowrate_chlor present
    data[101] = 0xFF  # flowrate_floc: not present
    return data


def _make_salt_bytes() -> bytearray:
    data = bytearray([0xFF] * 120)
    data[0:4] = (2002).to_bytes(4, "big")
    data[4] = 0x0E  # SALT with REDOX
    data[6:12] = [24, 6, 15, 12, 0, 0]
    data[14:16] = (700).to_bytes(2, "big")
    data[21] = 80
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x10  # electrolyzer on
    data[94:96] = (60).to_bytes(
        2, "big"
    )  # max_filling_time (byte 95 = flowrate_ph_minus = 60)
    data[99] = 0xFF  # no chlor
    data[101] = 0xFF  # no floc
    return data


def _make_profi_bytes() -> bytearray:
    data = bytearray([0xFF] * 120)
    data[0:4] = (3003).to_bytes(4, "big")
    data[4] = 0x08  # PROFI with CLF+REDOX
    data[6:12] = [24, 6, 15, 12, 0, 0]
    data[14:16] = (700).to_bytes(2, "big")
    data[16:18] = (100).to_bytes(2, "big")
    data[18:20] = (650).to_bytes(2, "big")
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x08  # filtration on
    data[95] = 60  # flowrate_ph_minus (byte 95)
    data[99] = 60  # flowrate_chlor
    data[101] = 60  # flowrate_floc present → floc_pump_running will be set
    return data


def _dummy_entry(device):
    class DummyCoordinator:
        reset_consumption = MagicMock()

        def get_devices(self):
            return [device]

        def get_tracker(self, serial_number):
            return None

    entry = MagicMock(spec=ConfigEntry)
    entry.runtime_data = type("RuntimeData", (), {"coordinator": DummyCoordinator()})()
    return entry


def _mock_add_entities(added):
    def _cb(new_entities, update_before_add=False, *, config_subentry_id=None):
        added.extend(new_entities)

    return _cb


# ── button creation tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_reset_buttons(hass) -> None:
    """NET: cl + ph_minus buttons are created (no algicide/floc/ph_plus)."""
    device = AsekoDecoder.decode(_make_net_bytes())
    assert device.device_type == AsekoDeviceType.NET

    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    keys = {e.entity_description.key for e in added}
    assert keys == {"chlor_refill_reset", "ph_minus_refill_reset"}


@pytest.mark.asyncio
async def test_salt_reset_buttons(hass) -> None:
    """SALT: only ph_minus button (algicide skipped – flowrate_algicide byte unknown)."""
    device = AsekoDecoder.decode(_make_salt_bytes())
    assert device.device_type == AsekoDeviceType.SALT

    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    keys = {e.entity_description.key for e in added}
    assert keys == {"ph_minus_refill_reset"}


@pytest.mark.asyncio
async def test_profi_reset_buttons(hass) -> None:
    """PROFI: cl + ph_minus + floc buttons (floc present because flowrate_floc != 0xFF)."""
    device = AsekoDecoder.decode(_make_profi_bytes())
    assert device.device_type == AsekoDeviceType.PROFI

    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    keys = {e.entity_description.key for e in added}
    assert keys == {"chlor_refill_reset", "ph_minus_refill_reset", "floc_refill_reset"}


# ── async_press test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_press_resets_canister_counter(hass) -> None:
    """Pressing a reset button calls coordinator.reset_consumption with counter=canister."""
    device = AsekoDecoder.decode(_make_net_bytes())
    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    cl_button = next(
        e for e in added if e.entity_description.key == "chlor_refill_reset"
    )
    assert isinstance(cl_button, AsekoResetButtonEntity)

    await cl_button.async_press()

    entry.runtime_data.coordinator.reset_consumption.assert_called_once_with(
        pump_key="cl", counter="canister"
    )
