"""Tests for AsekoV8Decoder."""

import pytest
from datetime import datetime
from unittest.mock import patch

from custom_components.aseko_local.aseko_data import (
    AsekoDeviceType,
    AsekoProbeType,
)
from custom_components.aseko_local.aseko_decoder_v8 import AsekoV8Decoder


# ---------------------------------------------------------------------------
# Real reference frame from fekberg (Sep 16, 2025, 22:27 CEST).
# Used as the primary test fixture — all expected values are cross-validated
# against a second frame (Apr 13, 2026, 12:27 CEST) and Aseko app screenshots.
# ---------------------------------------------------------------------------
REFERENCE_FRAME = (
    b"{v1 123456789 804 0 27 "
    b"ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 22 27 0 "
    b"ains: 708 708 774 7790 0 0 779 779 0 0 0 0 0 0 0 0 "
    b"outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"areqs: 74 73 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
    b"reqs: 0 0 0 0 0 0 0 24 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 3 0 0 0 2 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 0 0 0 0 0 "
    b"crc16: C3C8}\n"
)

# Second reference frame (Apr 13, 2026, 12:27 CEST) — used as cross-check fixture.
REFERENCE_FRAME_APR = (
    b"{v1 123456789 804 0 27 "
    b"ins: 180 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 24 12 27 0 "
    b"ains: 649 649 804 8090 0 0 809 809 0 0 0 0 0 0 0 0 "
    b"outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
    b"reqs: 0 0 0 0 0 0 0 24 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 3 0 0 0 2 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 0 0 0 0 0 "
    b"crc16: C3C8}\n"
)


@pytest.fixture
def device_sep():
    return AsekoV8Decoder.decode(REFERENCE_FRAME)


@pytest.fixture
def device_apr():
    return AsekoV8Decoder.decode(REFERENCE_FRAME_APR)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_serial_number(device_sep):
    assert device_sep.serial_number == 123456789


def test_device_type_is_net(device_sep):
    assert device_sep.device_type == AsekoDeviceType.NET


def test_configuration_contains_ph_and_redox(device_sep):
    assert AsekoProbeType.PH in device_sep.configuration
    assert AsekoProbeType.REDOX in device_sep.configuration


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

def test_water_temperature_sep(device_sep):
    assert device_sep.water_temperature == pytest.approx(31.4)


def test_water_temperature_apr(device_apr):
    assert device_apr.water_temperature == pytest.approx(18.0)


def test_ph_sep(device_sep):
    assert device_sep.ph == pytest.approx(7.08)


def test_ph_apr(device_apr):
    assert device_apr.ph == pytest.approx(6.49)


def test_redox_sep(device_sep):
    assert device_sep.redox == 779


def test_redox_apr(device_apr):
    assert device_apr.redox == 809


def test_water_flow_to_probes(device_sep):
    assert device_sep.water_flow_to_probes is True


# ---------------------------------------------------------------------------
# Pump states
# ---------------------------------------------------------------------------

def test_filtration_pump_running(device_sep):
    assert device_sep.filtration_pump_running is True


def test_ph_minus_pump_not_running_baseline(device_sep):
    """Baseline frame has outs[8] == 0 → ph_minus_pump_running is False."""
    assert device_sep.ph_minus_pump_running is False


def test_ph_minus_pump_running_when_dosing():
    """Frame with outs[8] == 1 (pH− dosing event) → ph_minus_pump_running is True."""
    dosing_frame = (
        b"{v1 123456789 804 0 27 "
        b"ins: 180 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 24 12 27 0 "
        b"ains: 649 649 804 8090 0 0 809 809 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"reqs: 0 0 0 0 0 0 0 24 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"fncs: 0 0 3 0 0 0 2 0 "
        b"mods: 2 0 0 1 0 0 0 0 "
        b"flags: 2 0 0 0 0 0 0 0 "
        b"crc16: C3C8}\n"
    )
    device = AsekoV8Decoder.decode(dosing_frame)
    assert device.ph_minus_pump_running is True
    # Other pump states must be unaffected
    assert device.filtration_pump_running is True


# ---------------------------------------------------------------------------
# Setpoints / configuration
# ---------------------------------------------------------------------------

def test_required_ph_sep(device_sep):
    assert device_sep.required_ph == pytest.approx(7.4)


def test_required_ph_apr(device_apr):
    assert device_apr.required_ph == pytest.approx(7.4)


def test_required_redox_sep(device_sep):
    # areqs[1] = 73 → 73 × 10 = 730 mV
    assert device_sep.required_redox == 730


def test_required_redox_apr(device_apr):
    # areqs[1] = 74 → 74 × 10 = 740 mV  (matches app screenshot)
    assert device_apr.required_redox == 740


def test_pool_volume(device_sep):
    assert device_sep.pool_volume == 45


def test_delay_after_startup(device_sep):
    assert device_sep.delay_after_startup == 2


def test_delay_after_dose(device_sep):
    assert device_sep.delay_after_dose == 2


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------

def test_timestamp_hour_minute(device_sep):
    assert device_sep.timestamp is not None
    assert device_sep.timestamp.hour == 22
    assert device_sep.timestamp.minute == 27


def test_timestamp_hour_minute_apr(device_apr):
    assert device_apr.timestamp is not None
    assert device_apr.timestamp.hour == 12
    assert device_apr.timestamp.minute == 27


# ---------------------------------------------------------------------------
# Absent-probe sentinel (-500 → None)
# ---------------------------------------------------------------------------

def test_absent_probe_returns_none():
    """A frame where all ains are -500 must yield None for ph and redox."""
    frame = (
        b"{v1 999 804 0 27 "
        b"ins: -500 -500 -500 -500 0 0 0 0 0 -500 -500 -500 0 0 0 0 0 0 0 "
        b"ains: -500 -500 -500 -500 0 0 -500 -500 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = AsekoV8Decoder.decode(frame)
    assert device.ph is None
    assert device.redox is None
    assert device.water_temperature is None
    assert AsekoProbeType.PH not in device.configuration
    assert AsekoProbeType.REDOX not in device.configuration


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_missing_braces_raises():
    with pytest.raises(ValueError, match="braces"):
        AsekoV8Decoder.decode(b"v1 110203680 804 0 27 ins: 0\n")


def test_bad_header_raises():
    with pytest.raises(ValueError, match="header"):
        AsekoV8Decoder.decode(b"{not a valid v8 header}\n")
