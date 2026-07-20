"""Tests for AsekoV8Decoder."""

import pytest

from custom_components.aseko_local.aseko_data import (
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoFiltrationMode,
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

REFERENCE_FRAME_805 = (
    b"{v1 123456789 805 0 27 "
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

REFERENCE_FRAME_812 = (
    b"{v1 123456789 812 0 27 "
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

# Header type 105 = ASIN Aqua Salt NET. Same body as the 805 reference; only the
# type field differs, to verify 105 decodes to AsekoDeviceType.SALT.
REFERENCE_FRAME_105 = (
    b"{v1 123456789 105 0 27 "
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

# Reference frame for FW 8.05 devices (header type 805).
# Same body layout as REFERENCE_FRAME — only the f2 header value changes.
REFERENCE_FRAME_805 = (
    b"{v1 123456789 805 0 27 "
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

# Reference frame for FW 8.12 devices (header type 812).
# Same body layout as REFERENCE_FRAME — only the f2 header value changes.
REFERENCE_FRAME_812 = (
    b"{v1 123456789 812 0 27 "
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


@pytest.fixture
def device_sep():
    return AsekoV8Decoder.decode(REFERENCE_FRAME)


@pytest.fixture
def device_805():
    return AsekoV8Decoder.decode(REFERENCE_FRAME_805)


@pytest.fixture
def device_812():
    return AsekoV8Decoder.decode(REFERENCE_FRAME_812)


@pytest.fixture
def device_105():
    return AsekoV8Decoder.decode(REFERENCE_FRAME_105)


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


def test_device_805_type_is_net(device_805):
    assert device_805.device_type == AsekoDeviceType.NET


def test_device_812_type_is_net(device_812):
    assert device_812.device_type == AsekoDeviceType.NET


def test_device_105_type_is_salt(device_105):
    assert device_105.device_type == AsekoDeviceType.SALT


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
    """NET v8 areqs[17] = 2 min → 2 * 60 = 120 s (matches v7 byte 74:75 unit)."""
    assert device_sep.delay_after_startup == 120


def test_delay_after_dose(device_sep):
    """NET v8 areqs[18] = 2 min → 2 * 60 = 120 s (matches v7 byte 106:107 unit)."""
    assert device_sep.delay_after_dose == 120


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
        AsekoV8Decoder.decode(b"v1 999999999 804 0 27 ins: 0\n")


def test_bad_header_raises():
    with pytest.raises(ValueError, match="header"):
        AsekoV8Decoder.decode(b"{not a valid v8 header}\n")


def test_unknown_header_type_is_tolerated(caplog):
    """Unknown f2 values must not raise — they fall back to NET with a warning.

    Backport of v1.6.3 hotfix (PR #119) so unknown future FW revisions do not
    crash the integration when an unreleased header type appears in the field.
    """
    import logging

    with caplog.at_level(
        logging.WARNING, logger="custom_components.aseko_local.aseko_decoder_v8"
    ):
        device = AsekoV8Decoder.decode(
            b"{v1 123456789 999 0 27 "
            b"ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 22 27 0 "
            b"ains: 708 708 774 7790 0 0 779 779 0 0 0 0 0 0 0 0 "
            b"outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
            b"areqs: 74 73 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
            b"crc16: C3C8}\n"
        )
    assert device.device_type == AsekoDeviceType.NET
    assert device.serial_number == 123456789
    assert device.ph == pytest.approx(7.08)
    # Warning must have been emitted to help diagnose the unknown header in the wild.
    assert any("999" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Pump states — outs[] mapping
# ---------------------------------------------------------------------------


def test_cl_pump_running_false_in_reference_frame(device_sep):
    """Baseline frames have outs[9] = 0 → cl_pump_running is False."""
    assert device_sep.cl_pump_running is False


def test_cl_pump_running_true_when_outs9_set():
    """Frame with outs[9] = 1 → cl_pump_running is True (confirmed April 19 fekberg)."""
    frame = (
        b"{v1 999999999 804 0 27 "
        b"ins: 214 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 30 18 23 0 "
        b"ains: 740 688 734 7390 0 0 739 739 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 "
        b"fncs: 0 0 3 0 0 0 2 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = AsekoV8Decoder.decode(frame)
    assert device.cl_pump_running is True
    assert device.ph_minus_pump_running is False


def test_ph_minus_pump_running_true_when_outs8_set():
    """Frame with outs[8] = 1 → ph_minus_pump_running is True (confirmed April 15 fekberg)."""
    frame = (
        b"{v1 999999999 804 0 27 "
        b"ins: 183 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 27 2 14 0 "
        b"ains: 741 689 789 7940 0 0 794 794 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 "
        b"fncs: 0 0 3 0 0 0 2 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = AsekoV8Decoder.decode(frame)
    assert device.ph_minus_pump_running is True
    assert device.cl_pump_running is False


def test_both_pumps_independent():
    """outs[8] and outs[9] are independently decoded."""
    frame = (
        b"{v1 999999999 804 0 27 "
        b"ins: 200 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 27 12 0 0 "
        b"ains: 740 688 789 7940 0 0 794 794 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 1 1 0 0 0 0 0 0 0 0 0 "
        b"fncs: 0 0 3 0 0 0 2 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = AsekoV8Decoder.decode(frame)
    assert device.ph_minus_pump_running is True
    assert device.cl_pump_running is True


# ---------------------------------------------------------------------------
# fncs[2] capability gating — see salt_net_v8_device_analysis.md §11.5
# ---------------------------------------------------------------------------


def test_salt_net_cl_pump_absent(device_salt_net_f1):
    """SALT NET (fncs[2] = 1) must have cl_pump_running = None, not False.

    With the new fncs[2] gate, a SALT NET device no longer exposes a
    permanently-False "CL pump running" binary sensor. The pump is
    treated as physically absent (None) so the entity layer can
    suppress the entity entirely.
    """
    assert device_salt_net_f1.cl_pump_running is None


def test_salt_net_ph_plus_pump_absent(device_salt_net_f1):
    """pH+ pump is not present on any v8 device captured so far."""
    assert device_salt_net_f1.ph_plus_pump_running is None


def test_salt_net_floc_pump_absent(device_salt_net_f1):
    """Flocculant pump is not present on any v8 device captured so far.

    SALT NET has algicide on a dedicated physical port, not flocculant.
    """
    assert device_salt_net_f1.floc_pump_running is None


def test_salt_net_oxy_pump_absent(device_salt_net_f1):
    """OXY pump is not present on any v8 device captured so far."""
    assert device_salt_net_f1.oxy_pump_running is None


def test_salt_net_ignores_outs9_when_fncs2_is_1():
    """SALT NET (fncs[2] = 1) must ignore outs[9] entirely.

    Even if a malformed SALT NET frame happened to carry a non-zero
    outs[9], the fncs[2] gate means the decoder will still return None
    for cl_pump_running. The CL pump is structurally absent.
    """
    frame = (
        b"{v1 110215844 100 0 31 "
        b"ins: 323 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 10 28 0 "
        b"ains: 752 752 716 7210 0 0 721 721 49 0 401 0 0 0 0 0 "
        b"outs: 0 0 2 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 72 4 0 5 33 33 0 0 0 33 33 33 0 55 255 255 5 5 10 0 15 0 0 0 3 "
        b"reqs: 0 0 0 0 0 8 0 20 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"fncs: 0 0 1 0 0 0 10 0 "
        b"mods: 2 0 0 1 0 0 0 0 "
        b"flags: 2 0 0 0 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = AsekoV8Decoder.decode(frame)
    assert device.device_type == AsekoDeviceType.SALT_NET
    # outs[9] = 1, but fncs[2] = 1 → CL pump is structurally absent
    assert device.cl_pump_running is None


def test_v8_frame_without_fncs_section_does_not_crash():
    """Frames without a `fncs:` section must not crash.

    With no `fncs:` section, `fncs2` is None. Per the Aseko SALT NET
    documentation (Issue #131), pH− is the *universal* first pump on
    every Aseko device — it is NOT gated on `fncs[2]`. The capability
    gate in `installed_pumps_from_fncs` therefore returns
    `frozenset({"ph_minus"})` as a safe lower bound: we know pH− is
    there, but we cannot determine any other pump from the missing
    `fncs:` section. The other per-pump `*_pump_running` fields stay
    None (the conservative "unknown" answer; the entity layer treats
    None as "pump not present"). `filtration_pump_running` is the one
    exception because its presence is determined by the schedule
    bytes (start1, etc.), not by `fncs[2]`.
    """
    frame = (
        b"{v1 999999999 804 0 27 "
        b"ins: 200 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 27 12 0 0 "
        b"ains: 740 688 789 7940 0 0 794 794 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = AsekoV8Decoder.decode(frame)
    # No `fncs:` → installed_pumps is exactly {"ph_minus"} (universal pH−).
    # All other per-pump *_pump_running fields are None ("unknown", not "off").
    assert device.installed_pumps == frozenset({"ph_minus"})
    # pH− pump is universally present, so its outs[8] read goes through.
    # In this fixture outs[8] = 0 → pH− pump is off (False, not None).
    assert device.ph_minus_pump_running is False
    assert device.cl_pump_running is None
    assert device.ph_plus_pump_running is None
    assert device.floc_pump_running is None
    assert device.oxy_pump_running is None
    assert device.algicide_pump_running is None
    # Filtration is gated only by the schedule bytes (start1), not by
    # `fncs[2]` — outs[2] = 1 → filtration pump is on.
    assert device.filtration_pump_running is True


# ---------------------------------------------------------------------------
# Issue #131 — ASIN AQUA Salt NET (v8 text frame, header type 100)
# Reference frames captured by @mirovra (serial 110215844, July 2026).
# Working notes: docs/temp/Issue-131-analyze.md
# ---------------------------------------------------------------------------

# F1: filtration ON, water flow YES, electrolysis 40.1, no dosing
# Original diagnostic JSON: docs/temp/Issue-131.json
SALT_NET_FRAME_F1 = (
    b"{v1 110215844 100 0 31 "
    b"ins: 323 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 10 28 0 "
    b"ains: 752 752 716 7210 0 0 721 721 49 0 401 0 0 0 0 0 "
    b"outs: 0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"areqs: 74 72 4 0 5 33 33 0 0 0 33 33 33 0 55 255 255 5 5 10 0 15 0 0 0 3 "
    b"reqs: 0 0 0 0 0 8 0 20 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 1 0 0 0 10 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 0 0 0 0 0 "
    b"crc16: 6142}\n"
)

# F2: filtration OFF, no flow to probes (no-flow alarm active)
# docs/temp/Issue-131-scenario1-off.json
SALT_NET_FRAME_F2 = (
    b"{v1 110215844 100 0 31 "
    b"ins: 290 -500 -500 -500 0 0 0 0 0 -500 -500 -500 256 24 6 30 21 49 0 "
    b"ains: 733 733 673 6780 0 0 678 678 48 0 336 0 0 0 0 0 "
    b"outs: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"areqs: 74 72 4 0 5 33 33 0 0 0 33 33 33 0 55 255 255 5 5 10 0 15 0 0 0 3 "
    b"reqs: 0 0 0 0 0 8 0 20 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 1 0 0 0 10 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 1 0 0 0 0 "
    b"crc16: 02F6}\n"
)

# F3: algicide pump ON, electrolyzer RIGHT at 19 g/h
# Source: mirovra Jul 16 07:58:59 — algicide dosing confirmed via app
SALT_NET_FRAME_F3 = (
    b"{v1 110215844 100 0 31 "
    b"ins: 310 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 7 10 8 1 0 "
    b"ains: 734 734 575 5800 0 0 580 580 53 19 346 0 0 0 0 0 "
    b"outs: 0 0 2 0 0 0 0 0 0 0 0 1 0 0 2 0 0 0 0 "
    b"areqs: 74 72 4 0 5 33 33 0 0 0 33 33 33 0 55 255 255 5 5 10 0 15 0 0 0 3 "
    b"reqs: 0 0 0 0 0 8 0 20 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 1 0 0 0 10 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 0 0 0 0 0 "
    b"crc16: 86AC}\n"
)

# F4: electrolyzer LEFT at 20 g/h, no dosing
# Source: mirovra Jul 16 08:13:09 — LEFT direction confirmed via app
SALT_NET_FRAME_F4 = (
    b"{v1 110215844 100 0 31 "
    b"ins: 326 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 7 10 8 15 0 "
    b"ains: 738 738 579 5840 0 0 584 584 51 20 407 0 0 0 0 0 "
    b"outs: 0 0 2 0 0 0 0 0 0 0 0 0 0 0 3 0 0 0 0 "
    b"areqs: 74 72 4 0 5 33 33 0 0 0 33 33 33 0 55 255 255 5 5 10 0 15 0 0 0 3 "
    b"reqs: 0 0 0 0 0 8 0 20 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 1 0 0 0 10 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 0 0 0 0 0 "
    b"crc16: 3663}\n"
)

# F5: electrolyzer OFF (outs[14]=0), filtration ON, no dosing
# Source: mirovra Jul 16 09:27:09 — OFF status confirmed via app
SALT_NET_FRAME_F5 = (
    b"{v1 110215844 100 0 31 "
    b"ins: 326 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 7 10 9 29 0 "
    b"ains: 741 741 716 7210 0 0 721 721 49 0 488 0 0 0 0 0 "
    b"outs: 0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"areqs: 74 72 4 0 5 33 33 0 0 0 33 33 33 0 55 255 255 5 5 10 0 15 0 0 0 3 "
    b"reqs: 0 0 0 0 0 8 0 20 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 1 0 0 0 10 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 0 0 0 0 0 "
    b"crc16: 56A4}\n"
)


@pytest.fixture
def device_salt_net_f1():
    return AsekoV8Decoder.decode(SALT_NET_FRAME_F1)


@pytest.fixture
def device_salt_net_f2():
    return AsekoV8Decoder.decode(SALT_NET_FRAME_F2)


@pytest.fixture
def device_salt_net_f3():
    return AsekoV8Decoder.decode(SALT_NET_FRAME_F3)


@pytest.fixture
def device_salt_net_f4():
    return AsekoV8Decoder.decode(SALT_NET_FRAME_F4)


@pytest.fixture
def device_salt_net_f5():
    return AsekoV8Decoder.decode(SALT_NET_FRAME_F5)


# F6: Flocculant configured (fncs[6]=18), electrolyzer OFF, no dosing
# Source: mirovra Jul 19 17:20:28, Issue #131 comment 5016380761
SALT_NET_FRAME_F6 = (
    b"{v1 110215844 100 0 31 "
    b"ins: 336 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 1 17 20 0 "
    b"ains: 720 720 714 7190 0 0 719 719 46 0 446 0 0 0 0 0 "
    b"outs: 0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"areqs: 74 72 4 10 0 33 33 0 0 0 33 33 33 0 55 255 255 5 5 10 0 15 0 0 0 3 "
    b"reqs: 0 0 0 0 0 8 0 20 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 1 0 0 0 18 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 1 0 0 0 0 "
    b"crc16: 3334}\n"
)


@pytest.fixture
def device_salt_net_f6():
    return AsekoV8Decoder.decode(SALT_NET_FRAME_F6)


# --- Identity & header ---


def test_salt_net_device_type(device_salt_net_f1):
    """Header type 100 must decode to AsekoDeviceType.SALT_NET."""
    assert device_salt_net_f1.device_type == AsekoDeviceType.SALT_NET


def test_salt_net_serial(device_salt_net_f1):
    assert device_salt_net_f1.serial_number == 110215844


# --- Common measurements (NET-compatible) ---


def test_salt_net_water_temperature_f1(device_salt_net_f1):
    assert device_salt_net_f1.water_temperature == pytest.approx(32.3)


def test_salt_net_ph_f1(device_salt_net_f1):
    assert device_salt_net_f1.ph == pytest.approx(7.52)


def test_salt_net_redox_f1(device_salt_net_f1):
    assert device_salt_net_f1.redox == 721


def test_salt_net_water_flow_yes_f1(device_salt_net_f1):
    assert device_salt_net_f1.water_flow_to_probes is True


def test_salt_net_water_flow_no_f2(device_salt_net_f2):
    """F2 has ins[8] = 0 (no flow) — water_flow_to_probes must be False."""
    assert device_salt_net_f2.water_flow_to_probes is False


def test_salt_net_pool_volume(device_salt_net_f1):
    assert device_salt_net_f1.pool_volume == 55


def test_salt_net_delay_after_startup_5min(device_salt_net_f1):
    """SALT NET uses 5 min delay (NET v8 uses 2 min).

    v8 firmware reports areqs[17]/areqs[18] in MINUTES; the decoder
    multiplies by 60 to keep `AsekoDevice.delay_*` in seconds (matching
    the v7 byte 74:75 / 106:107 unit and the `UnitOfTime.SECONDS` sensor).
    5 min × 60 = 300 s.
    """
    assert device_salt_net_f1.delay_after_startup == 300


def test_salt_net_delay_after_dose_5min(device_salt_net_f1):
    """SALT NET delay_after_dose: 5 min × 60 = 300 s."""
    assert device_salt_net_f1.delay_after_dose == 300


def test_salt_net_required_ph(device_salt_net_f1):
    assert device_salt_net_f1.required_ph == pytest.approx(7.4)


def test_salt_net_required_redox(device_salt_net_f1):
    """areqs[1] = 72 → 72 × 10 = 720 mV."""
    assert device_salt_net_f1.required_redox == 720


# --- SALT-NET-specific measurements ---


def test_salt_net_salinity_f1(device_salt_net_f1):
    """ains[8] = 49 → 4.9 g/L."""
    assert device_salt_net_f1.salinity == pytest.approx(4.9)


def test_salt_net_salinity_f2(device_salt_net_f2):
    """ains[8] = 48 → 4.8 g/L."""
    assert device_salt_net_f2.salinity == pytest.approx(4.8)


def test_salt_net_salinity_f3(device_salt_net_f3):
    """F3: ains[8] = 53 → 5.3 g/L."""
    assert device_salt_net_f3.salinity == pytest.approx(5.3)


def test_salt_net_electrolyzer_power_off_f1(device_salt_net_f1):
    """F1: ains[9] = 0 → electrolyzer off → power = 0.0 g/h."""
    assert device_salt_net_f1.electrolyzer_power == pytest.approx(0.0)


def test_salt_net_electrolyzer_power_f3(device_salt_net_f3):
    """F3 (algicide ON, RIGHT): ains[9] = 19 → 19 g/h (matches app)."""
    assert device_salt_net_f3.electrolyzer_power == pytest.approx(19.0)


def test_salt_net_electrolyzer_power_f4(device_salt_net_f4):
    """F4 (LEFT): ains[9] = 20 → 20 g/h (matches app)."""
    assert device_salt_net_f4.electrolyzer_power == pytest.approx(20.0)


def test_salt_net_electrolyzer_power_off_f5(device_salt_net_f5):
    """F5: ains[9] = 0 → electrolyzer off → power = 0.0 g/h."""
    assert device_salt_net_f5.electrolyzer_power == pytest.approx(0.0)


def test_salt_net_electrolyzer_active_right_f3(device_salt_net_f3):
    """F3: outs[14] = 2 (RIGHT) → electrolyzer_active is True."""
    assert device_salt_net_f3.electrolyzer_active is True


def test_salt_net_electrolyzer_active_left_f4(device_salt_net_f4):
    """F4: outs[14] = 3 (LEFT) → electrolyzer_active is True."""
    assert device_salt_net_f4.electrolyzer_active is True


def test_salt_net_electrolyzer_active_off_f5(device_salt_net_f5):
    """F5: outs[14] = 0 → electrolyzer_active is False, direction None."""
    assert device_salt_net_f5.electrolyzer_active is False
    assert device_salt_net_f5.electrolyzer_direction is None


def test_salt_net_electrolyzer_direction_right_f3(device_salt_net_f3):
    """F3: outs[14] = 2 → RIGHT."""
    assert device_salt_net_f3.electrolyzer_direction == AsekoElectrolyzerDirection.RIGHT


def test_salt_net_electrolyzer_direction_left_f4(device_salt_net_f4):
    """F4: outs[14] = 3 → LEFT."""
    assert device_salt_net_f4.electrolyzer_direction == AsekoElectrolyzerDirection.LEFT


def test_salt_net_required_algicide(device_salt_net_f1):
    """F1 (fncs[6]=10): areqs[4] = 5 → 5 ml/m³/day."""
    assert device_salt_net_f1.required_algicide == 5


def test_salt_net_required_floc_is_none_when_algicide(device_salt_net_f1):
    """F1 (fncs[6]=10, algicide) → required_floc must be None."""
    assert device_salt_net_f1.required_floc is None


def test_salt_net_filtration_hours_per_day(device_salt_net_f1):
    """reqs[7] = 20 → 20 h/day (probable, unconfirmed by user)."""
    assert device_salt_net_f1.filtration_hours_per_day == 20


# --- Flocculant configuration (fncs[6]=18) ---


def test_salt_net_flocculant_device_type(device_salt_net_f6):
    """F6 must still decode as SALT_NET."""
    assert device_salt_net_f6.device_type == AsekoDeviceType.SALT_NET


def test_salt_net_flocculant_installed_pumps(device_salt_net_f6):
    """F6 (fncs[6]=18) → installed_pumps must contain floc, not algicide."""
    assert "floc" in device_salt_net_f6.installed_pumps
    assert "algicide" not in device_salt_net_f6.installed_pumps
    assert "ph_minus" in device_salt_net_f6.installed_pumps


def test_salt_net_flocculant_required_floc(device_salt_net_f6):
    """F6: areqs[3] = 10 → 10 ml/h (flocculant dose)."""
    assert device_salt_net_f6.required_floc == 10


def test_salt_net_flocculant_required_algicide_is_none(device_salt_net_f6):
    """F6 (flocculant) → required_algicide must be None."""
    assert device_salt_net_f6.required_algicide is None


def test_salt_net_flocculant_pump_off(device_salt_net_f6):
    """F6: outs[11] = 0 → floc_pump_running is False (same physical port)."""
    assert device_salt_net_f6.floc_pump_running is False


def test_salt_net_flocculant_algicide_pump_is_none(device_salt_net_f6):
    """F6 (flocculant) → algicide_pump_running must be None (not installed)."""
    assert device_salt_net_f6.algicide_pump_running is None


# --- Pump states (SALT-NET-specific semantics) ---


def test_salt_net_filtration_on_f1(device_salt_net_f1):
    """outs[2] = 2 means 'filtration ON' on SALT NET (NET v8 uses 1)."""
    assert device_salt_net_f1.filtration_pump_running is True


def test_salt_net_filtration_off_f2(device_salt_net_f2):
    """F2 has outs[2] = 0 → filtration off."""
    assert device_salt_net_f2.filtration_pump_running is False


def test_salt_net_algicide_off_f1(device_salt_net_f1):
    """F1 has outs[11] = 0 → algicide pump off (gate: installed_pumps has algicide)."""
    assert device_salt_net_f1.algicide_pump_running is False


def test_salt_net_algicide_on_f3(device_salt_net_f3):
    """F3 has outs[11] = 1 → algicide pump on (confirmed mirovra Jul 16)."""
    assert device_salt_net_f3.algicide_pump_running is True


def test_salt_net_algicide_on_f3_ph_minus_off(device_salt_net_f3):
    """F3: algicide ON, pH− OFF → ph_minus_pump_running must be False."""
    assert device_salt_net_f3.ph_minus_pump_running is False


def test_salt_net_flowrate_algicide_is_none(device_salt_net_f1):
    """v8 has no per-pump flow-rate bytes — flowrate_algicide stays None."""
    assert device_salt_net_f1.flowrate_algicide is None


# --- No-flow alarm dual encoding (Issue #131 §10) ---


def test_salt_net_no_flow_alarm_clear_f1(device_salt_net_f1):
    """F1: ins[12] = 0 → alarm not active.

    Writes to the same AsekoDevice field as the v7 decoder — the binary
    sensor in binary_sensor.py is protocol-agnostic. See
    salt_net_v8_device_analysis.md §10 and the AsekoDevice
    `alarm_no_flow_to_probes` docstring.
    """
    assert device_salt_net_f1.alarm_no_flow_to_probes is False


def test_salt_net_no_flow_alarm_active_f2(device_salt_net_f2):
    """F2: ins[12] = 256 (0x100) → alarm active."""
    assert device_salt_net_f2.alarm_no_flow_to_probes is True


def test_salt_net_no_flow_alarm_clear_f3(device_salt_net_f3):
    """F3: ins[12] = 0 → alarm not active."""
    assert device_salt_net_f3.alarm_no_flow_to_probes is False


# --- Filtration mode derivation for SALT NET v8 (Issue #131 + #133) ---


def test_salt_net_filtration_mode_off_f2(device_salt_net_f2):
    """F2: outs[2] = 0 (filtration off) + reqs[7] = 20 → OFF_MANUAL.

    The v8 frame does not carry a byte[37]-style mode flag, so the
    decoder derives the mode from outs[2] and filtration_hours_per_day.
    See salt_net_v8_device_analysis.md §6.2 and Issue #133.
    """
    assert device_salt_net_f2.filtration_mode == AsekoFiltrationMode.OFF_MANUAL


def test_salt_net_filtration_mode_timer_f3(device_salt_net_f3):
    """F3: outs[2] = 2 (filtration on) + reqs[7] = 20 (< 24) → TIMER_PERIOD_1.

    The SALT NET v8 firmware does not expose a second filtration period
    in the decoded sections, so the decoder cannot distinguish
    TIMER_PERIOD_1 from TIMER_PERIOD_1_AND_2 — this matches the old
    HOME v7 firmware A behaviour (see issue-133 §6.2 "Old encoding").
    """
    assert device_salt_net_f3.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1


def test_salt_net_filtration_mode_timer_f1(device_salt_net_f1):
    """F1: outs[2] = 2 (filtration on) + reqs[7] = 20 (< 24) → TIMER_PERIOD_1.

    F1 was captured during mirovra's "filtration on, no dosing" scenario.
    The schedule is 20 h/day so this is TIMER_PERIOD_1, not NONSTOP_24H.
    """
    assert device_salt_net_f1.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1


def test_net_v8_filtration_mode_is_none(device_sep):
    """NET v8 is not in FILTRATION_TYPES — filtration_mode stays None.

    NET has no filtration output (Issue #66). The decoder must not
    synthesize a mode for it.
    """
    assert device_sep.filtration_mode is None


# --- Regression guards for NET v8 ---


def test_net_v8_does_not_get_salt_net_specific_fields():
    """A NET v8 frame should not get phantom SALT-NET-specific fields.

    The SALT NET frame is a strict superset of NET v8, so the NET v8
    frame's ains[8..15] are zero-padded (real value 0, not absent). The
    decoder is gated on device_type == SALT_NET to avoid surfacing
    phantom 0-value entities for `salinity`, `electrolyzer_power`,
    `algicide_pump_running`, `flowrate_algicide`, `required_algicide`,
    and `filtration_hours_per_day` on NET devices.
    """
    device = AsekoV8Decoder.decode(REFERENCE_FRAME)
    assert device.device_type == AsekoDeviceType.NET
    # ains[8..15] are all 0 on the NET v8 reference frame but the decoder
    # is gated on device_type == SALT_NET, so all SALT-NET-specific
    # fields stay None on NET.
    assert device.salinity is None
    assert device.electrolyzer_power is None
    # electrolyzer_active is only set on SALT_NET (gated) → None on NET
    assert device.electrolyzer_active is None
    assert device.electrolyzer_direction is None
    assert device.flowrate_algicide is None
    assert device.algicide_pump_running is None
    assert device.required_algicide is None
    assert device.filtration_hours_per_day is None


def test_net_v8_no_flow_alarm_default_false(device_sep):
    """NET v8 with ins[12] = 0 → alarm_no_flow_to_probes = False (not None).

    NET v8 frames have ins[12] = 0 in all known captures, so the alarm
    field should be present and False, not None. Same field as v7
    writes to (AsekoDevice.alarm_no_flow_to_probes).
    """
    assert device_sep.alarm_no_flow_to_probes is False
