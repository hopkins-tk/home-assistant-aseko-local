"""Tests for the Aseko Local button platform (canister-reset buttons)."""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry

from custom_components.aseko_local import entity as entity_module
from custom_components.aseko_local.button import (
    AsekoResetButtonEntity,
    async_setup_entry,
)
from custom_components.aseko_local.const import UNIT_TYPE_PROFI, WATER_FLOW_TO_PROBES
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.models import AsekoDevice, AsekoDeviceType

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
    data[76:78] = (3600).to_bytes(2, "big")  # max_refill_time, raw 3600
    data[94:96] = (60).to_bytes(2, "big")  # byte 95 = ph_minus_flow_rate = 60
    data[99] = 60  # chlorine_flow_rate present
    data[101] = 0xFF  # flocculant_flow_rate: not present
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
    data[76:78] = (3600).to_bytes(2, "big")  # max_refill_time, raw 3600
    data[94:96] = (60).to_bytes(2, "big")  # byte 95 = ph_minus_flow_rate = 60
    data[99] = 0xFF  # no chlor
    data[101] = 0xFF  # no floc
    return data


def _make_profi_bytes() -> bytearray:
    data = bytearray([0xFF] * 120)
    data[0:4] = (3003).to_bytes(4, "big")
    data[4] = UNIT_TYPE_PROFI  # PROFI with CLF+REDOX
    data[6:12] = [24, 6, 15, 12, 0, 0]
    data[14:16] = (700).to_bytes(2, "big")
    data[16:18] = (100).to_bytes(2, "big")
    data[18:20] = (650).to_bytes(2, "big")
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x08  # filtration on
    data[95] = 60  # ph_minus_flow_rate (byte 95)
    data[99] = 60  # chlorine_flow_rate
    data[37] = 0x00  # flocculant mode → byte[101] routes to flocculant_flow_rate
    data[101] = 60  # flocculant_flow_rate present → flocculant_pump_running will be set
    return data


def _dummy_entry(device) -> MagicMock:
    class DummyCoordinator:
        reset_consumption = MagicMock()

        def get_devices(self) -> list[AsekoDevice]:
            return [device]

        def get_tracker(self, serial_number) -> None:
            return None

        def async_add_new_device_listener(self, listener) -> Callable[[], None]:
            return lambda: None

        def async_add_new_features_listener(self, listener) -> Callable[[], None]:
            return lambda: None

    entry = MagicMock(spec=ConfigEntry)
    entry.runtime_data = type("RuntimeData", (), {"coordinator": DummyCoordinator()})()
    return entry


def _mock_add_entities(added) -> Callable[..., None]:
    def _cb(new_entities, update_before_add=False, *, config_subentry_id=None) -> None:
        # only the buttons for pumps the unit has shown; the rest are disabled
        added.extend(e for e in new_entities if e.entity_registry_enabled_default)

    return _cb


# ── button creation tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_reset_buttons(hass) -> None:
    """NET: cl + ph_minus buttons are created (no algicide/floc/ph_plus)."""
    device = decode(_make_net_bytes())
    assert device.device_type == AsekoDeviceType.NET

    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    keys = {e.entity_description.key for e in added}
    assert keys == {"chlor_refill_reset", "ph_minus_refill_reset"}


@pytest.mark.asyncio
async def test_salt_reset_buttons(hass) -> None:
    """SALT: only ph_minus button (algicide skipped – algaecide_flow_rate byte unknown)."""
    device = decode(_make_salt_bytes())
    assert device.device_type == AsekoDeviceType.SALT

    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    keys = {e.entity_description.key for e in added}
    assert keys == {"ph_minus_refill_reset"}


@pytest.mark.asyncio
async def test_profi_reset_buttons(hass) -> None:
    """PROFI: cl + ph_minus + floc buttons (floc present because flocculant_flow_rate != 0xFF)."""
    device = decode(_make_profi_bytes())
    assert device.device_type == AsekoDeviceType.PROFI

    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    keys = {e.entity_description.key for e in added}
    assert keys == {"chlor_refill_reset", "ph_minus_refill_reset", "floc_refill_reset"}


# ── async_press test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_press_resets_canister_counter(hass) -> None:
    """Pressing a reset button resets the canister counter of its own unit only."""
    device = decode(_make_net_bytes())
    entry = _dummy_entry(device)
    added = []
    await async_setup_entry(hass, entry, _mock_add_entities(added))

    cl_button = next(
        e for e in added if e.entity_description.key == "chlor_refill_reset"
    )
    assert isinstance(cl_button, AsekoResetButtonEntity)

    await cl_button.async_press()

    entry.runtime_data.coordinator.reset_consumption.assert_called_once_with(
        pump_key="cl", counter="canister", serial_number=device.serial_number
    )


# ── units seen later ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_buttons_follow_units_and_pumps_seen_later(monkeypatch) -> None:
    """A new unit gets its buttons; a pump a known unit starts showing is enabled."""
    enabled: list[list[str]] = []
    monkeypatch.setattr(
        entity_module,
        "async_enable_entities",
        lambda hass, platform, unique_ids: enabled.append(list(unique_ids)),
    )
    net = decode(_make_net_bytes())
    entry = _dummy_entry(net)
    listeners: dict[str, Callable] = {}

    def keep(kind: str) -> Callable[[Callable], Callable[[], None]]:
        def add(listener: Callable) -> Callable[[], None]:
            listeners[kind] = listener
            return lambda: None

        return add

    coordinator = entry.runtime_data.coordinator
    coordinator.async_add_new_device_listener = keep("device")
    coordinator.async_add_new_features_listener = keep("features")
    added: list = []

    await async_setup_entry(MagicMock(), entry, added.extend)
    assert {e.unique_id for e in added} >= {"1001chlor_refill_reset"}
    first = len(added)

    listeners["device"](AsekoDevice(serial_number=42))  # no pumps at all
    assert len(added) == first

    listeners["device"](decode(_make_profi_bytes()))
    assert {e.unique_id for e in added[first:]} >= {"3003floc_refill_reset"}

    enabled.clear()
    listeners["features"](net, frozenset({"ph"}))
    listeners["features"](net, frozenset({"chlorine_pump_running"}))
    assert enabled == [[], ["1001chlor_refill_reset"]]
