"""Tests for AsekoV8Decoder."""

import logging
from datetime import time

import pytest

from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.decoding.frames import parse_v8
from custom_components.aseko_local.models import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoElectrodePolarity,
    AsekoFiltrationSchedule,
    AsekoProbeType,
    AsekoProfileFlag,
)

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
def device_sep() -> AsekoDevice:
    return decode(REFERENCE_FRAME)


@pytest.fixture
def device_805() -> AsekoDevice:
    return decode(REFERENCE_FRAME_805)


@pytest.fixture
def device_812() -> AsekoDevice:
    return decode(REFERENCE_FRAME_812)


@pytest.fixture
def device_105() -> AsekoDevice:
    return decode(REFERENCE_FRAME_105)


@pytest.fixture
def device_apr() -> AsekoDevice:
    return decode(REFERENCE_FRAME_APR)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_serial_number(device_sep) -> None:
    assert device_sep.serial_number == 123456789


def test_device_type_is_net(device_sep) -> None:
    assert device_sep.device_type == AsekoDeviceType.NET


def test_device_805_type_is_net(device_805) -> None:
    assert device_805.device_type == AsekoDeviceType.NET


def test_device_812_type_is_net(device_812) -> None:
    assert device_812.device_type == AsekoDeviceType.NET


def test_device_105_type_is_salt(device_105) -> None:
    assert device_105.device_type == AsekoDeviceType.SALT


def test_configuration_contains_ph_and_redox(device_sep) -> None:
    assert AsekoProbeType.PH in device_sep.configuration
    assert AsekoProbeType.REDOX in device_sep.configuration


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def test_water_temperature_sep(device_sep) -> None:
    assert device_sep.water_temperature == pytest.approx(31.4)


def test_water_temperature_apr(device_apr) -> None:
    assert device_apr.water_temperature == pytest.approx(18.0)


def test_ph_sep(device_sep) -> None:
    assert device_sep.ph == pytest.approx(7.08)


def test_ph_apr(device_apr) -> None:
    assert device_apr.ph == pytest.approx(6.49)


def test_redox_sep(device_sep) -> None:
    assert device_sep.redox == 779


def test_redox_apr(device_apr) -> None:
    assert device_apr.redox == 809


def test_water_flow_to_probes(device_sep) -> None:
    assert device_sep.water_flow_to_probes is True


# ---------------------------------------------------------------------------
# Pump states
# ---------------------------------------------------------------------------


def test_filtration_pump_running(device_sep) -> None:
    assert device_sep.filtration_running is True


def test_ph_minus_pump_not_running_baseline(device_sep) -> None:
    """Baseline frame has outs[8] == 0 → ph_minus_pump_running is False."""
    assert device_sep.ph_minus_pump_running is False


def test_ph_minus_pump_running_when_dosing() -> None:
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
    device = decode(dosing_frame)
    assert device.ph_minus_pump_running is True
    # Other pump states must be unaffected
    assert device.filtration_running is True


# ---------------------------------------------------------------------------
# Setpoints / configuration
# ---------------------------------------------------------------------------


def test_required_ph_sep(device_sep) -> None:
    assert device_sep.ph_target == pytest.approx(7.4)


def test_required_ph_apr(device_apr) -> None:
    assert device_apr.ph_target == pytest.approx(7.4)


def test_required_redox_sep(device_sep) -> None:
    # areqs[1] = 73 → 73 × 10 = 730 mV
    assert device_sep.redox_target == 730


def test_required_redox_apr(device_apr) -> None:
    # areqs[1] = 74 → 74 × 10 = 740 mV  (matches app screenshot)
    assert device_apr.redox_target == 740


def test_pool_volume(device_sep) -> None:
    assert device_sep.pool_volume == 45


def test_delay_after_startup(device_sep) -> None:
    assert device_sep.startup_delay == 2


def test_delay_after_dose(device_sep) -> None:
    assert device_sep.dosing_delay == 2


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------


def test_timestamp_hour_minute(device_sep) -> None:
    assert device_sep.timestamp is not None
    assert device_sep.timestamp.hour == 22
    assert device_sep.timestamp.minute == 27


def test_timestamp_hour_minute_apr(device_apr) -> None:
    assert device_apr.timestamp is not None
    assert device_apr.timestamp.hour == 12
    assert device_apr.timestamp.minute == 27


# ---------------------------------------------------------------------------
# Absent-probe sentinel (-500 → None)
# ---------------------------------------------------------------------------


def test_absent_probe_returns_none() -> None:
    """A frame where all ains are -500 must yield None for ph and redox."""
    frame = (
        b"{v1 999 804 0 27 "
        b"ins: -500 -500 -500 -500 0 0 0 0 0 -500 -500 -500 0 0 0 0 0 0 0 "
        b"ains: -500 -500 -500 -500 0 0 -500 -500 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = decode(frame)
    assert device.ph is None
    assert device.redox is None
    assert device.water_temperature is None
    assert AsekoProbeType.PH not in device.configuration
    assert AsekoProbeType.REDOX not in device.configuration


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_braces_raises() -> None:
    with pytest.raises(ValueError, match="braces"):
        parse_v8(b"v1 999999999 804 0 27 ins: 0\n")


def test_bad_header_raises() -> None:
    with pytest.raises(ValueError, match="header"):
        parse_v8(b"{not a valid v8 header}\n")


def test_unknown_header_type_is_tolerated(caplog) -> None:
    """A header type no product line matches must not raise (PR #119).

    It decodes with the unknown v8 profile -- no model, so no entities --
    and a warning names it; a new firmware of a known line (813, 106) does
    not get here.
    """
    with caplog.at_level(
        logging.WARNING, logger="custom_components.aseko_local.decoding.profiles"
    ):
        device = decode(
            b"{v1 123456789 999 0 27 "
            b"ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 22 27 0 "
            b"ains: 708 708 774 7790 0 0 779 779 0 0 0 0 0 0 0 0 "
            b"outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
            b"areqs: 74 73 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
            b"crc16: C3C8}\n"
        )
    assert device.device_type is None
    assert device.serial_number == 123456789
    assert device.ph == pytest.approx(7.08)
    # Warning must have been emitted to help diagnose the unknown header in the wild.
    assert any("999" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Pump states — outs[] mapping
# ---------------------------------------------------------------------------


def test_cl_pump_running_false_in_reference_frame(device_sep) -> None:
    """Baseline frames have outs[9] = 0 → chlorine_pump_running is False."""
    assert device_sep.chlorine_pump_running is False


def test_cl_pump_running_true_when_outs9_set() -> None:
    """Frame with outs[9] = 1 → chlorine_pump_running is True (confirmed April 19 fekberg)."""
    frame = (
        b"{v1 999999999 804 0 27 "
        b"ins: 214 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 30 18 23 0 "
        b"ains: 740 688 734 7390 0 0 739 739 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = decode(frame)
    assert device.chlorine_pump_running is True
    assert device.ph_minus_pump_running is False


def test_ph_minus_pump_running_true_when_outs8_set() -> None:
    """Frame with outs[8] = 1 → ph_minus_pump_running is True (confirmed April 15 fekberg)."""
    frame = (
        b"{v1 999999999 804 0 27 "
        b"ins: 183 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 27 2 14 0 "
        b"ains: 741 689 789 7940 0 0 794 794 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = decode(frame)
    assert device.ph_minus_pump_running is True
    assert device.chlorine_pump_running is False


def test_both_pumps_independent() -> None:
    """outs[8] and outs[9] are independently decoded."""
    frame = (
        b"{v1 999999999 804 0 27 "
        b"ins: 200 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 27 12 0 0 "
        b"ains: 740 688 789 7940 0 0 794 794 0 0 0 0 0 0 0 0 "
        b"outs: 0 0 1 0 0 0 0 0 1 1 0 0 0 0 0 0 0 0 0 "
        b"areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
        b"crc16: 0000}\n"
    )
    device = decode(frame)
    assert device.ph_minus_pump_running is True
    assert device.chlorine_pump_running is True


def test_delays_are_minutes_and_the_profile_says_so() -> None:
    """R3: areqs[17] / areqs[18] = 2 is "2 min" in the app; kept as 2, flagged as minutes."""
    device = decode(REFERENCE_FRAME)
    assert device.startup_delay == 2
    assert device.dosing_delay == 2
    assert AsekoProfileFlag.DELAYS_IN_MINUTES in device.flags
    assert AsekoProfileFlag.DELAYS_IN_MINUTES in decode(REFERENCE_FRAME_105).flags


# ---------------------------------------------------------------------------
# Unreadable values and the profile on the device
# ---------------------------------------------------------------------------


def test_crc16_is_read_as_hex() -> None:
    """crc16 is the one hex section; it no longer comes out empty."""
    assert parse_v8(REFERENCE_FRAME).sections["crc16"] == [0xC3C8]
    assert parse_v8(REFERENCE_FRAME).problems == ()


def test_one_unreadable_value_does_not_blank_its_section() -> None:
    """A corrupt token reads None and is reported; its neighbours stay."""
    frame = parse_v8(REFERENCE_FRAME.replace(b"ains: 708 ", b"ains: 7x8 "))
    assert frame.sections["ains"][0] is None
    assert frame.sections["ains"][1] == 708
    assert frame.problems == ("ains[0] is not a number",)

    device = decode(REFERENCE_FRAME.replace(b"ains: 708 ", b"ains: 7x8 "))
    assert device.ph is None
    assert device.redox == 779
    assert device.frame_problems == ("ains[0] is not a number",)


def test_device_names_the_profile_that_read_it() -> None:
    assert decode(REFERENCE_FRAME).profile == "v8 NET"
    assert decode(REFERENCE_FRAME_105).profile == "v8 SALT"
    unknown = decode(REFERENCE_FRAME.replace(b" 804 ", b" 999 "))
    assert unknown.profile == "v8 unknown header type"


def test_a_header_without_sections_reads_unknown_and_says_so() -> None:
    """Nothing to read is not an error, but the missing sections are reported."""
    device = decode(b"{v1 123456789 804 0 27}")
    assert device.profile == "v8 NET"
    assert device.ph is None
    assert device.water_temperature is None
    assert device.chlorine_pump_running is None
    assert device.frame_problems == (
        "section 'ins' is missing",
        "section 'ains' is missing",
        "section 'outs' is missing",
        "section 'areqs' is missing",
    )


def test_a_complete_frame_reports_no_problem() -> None:
    assert decode(REFERENCE_FRAME).frame_problems == ()


def test_an_unreadable_probe_value_is_unknown_not_absent() -> None:
    """Audit N6: only -500 says the probe is missing; a bad token reads unknown."""
    bad = decode(REFERENCE_FRAME.replace(b"ains: 708 ", b"ains: 7x8 "))
    assert bad.ph is None
    assert "ph" in bad.present_features  # the entity stays available, reads unknown

    absent = decode(REFERENCE_FRAME.replace(b"ains: 708 ", b"ains: -500 "))
    assert absent.ph is None
    assert "ph" not in absent.present_features


def test_changing_bad_tokens_are_one_problem() -> None:
    """Audit N5: the problem names the place, so it is counted, not multiplied."""
    problems = {
        decode(
            REFERENCE_FRAME.replace(b"ains: 708 ", f"ains: bad{i} ".encode())
        ).frame_problems
        for i in range(50)
    }
    assert problems == {("ains[0] is not a number",)}


def test_bad_values_in_unknown_sections_are_one_problem() -> None:
    """Audit: section names a frame invents must not make new kinds of problem."""
    problems = {
        decode(
            REFERENCE_FRAME.replace(b"crc16:", f"other{i}: x crc16:".encode())
        ).frame_problems
        for i in range(50)
    }
    assert problems == {("unexpected section",)}


# ---------------------------------------------------------------------------
# ASIN Aqua Salt NET (Issue #131): frames an owner captured and labelled with
# what the app showed at that moment.  Serial numbers redacted.
# ---------------------------------------------------------------------------


def _salt_net_frame(  # noqa: PLR0913 - one argument per labelled position
    *,
    header: int = 100,
    salinity: int = 53,
    production: int = 19,
    electrolyser: int = 2,
    third_pump: int = 0,
    third_pump_code: int = 10,
    algicide_dose: int = 5,
    flocculant_dose: int = 0,
    alarms: int = 0,
    filtration: tuple[int, int] = (8, 20),
) -> bytes:
    """Return a Salt NET frame with the labelled positions filled in."""
    outs = [0] * 19
    outs[2] = 1  # filtration
    outs[11] = third_pump
    outs[14] = electrolyser
    ains = [740, 740, 715, 7200, 0, 0, 720, 720, salinity, production, 401] + [0] * 5
    areqs = [74, 72, 4, flocculant_dose, algicide_dose, 33, 33, 0, 0, 0]
    areqs += [33, 33, 33, 0, 55, 255, 255, 5, 5, 10, 0, 15, 0, 0, 0, 3]
    ins = [346, -500, -500, -500, 0, 0, 0, 0, 1, -500, -500, -500, alarms]
    ins += [24, 7, 9, 18, 25, 0]
    fncs = [0, 0, 1, 0, 0, 0, third_pump_code, 0]
    reqs = [0] * 10
    reqs[5], reqs[7] = filtration

    def part(name: str, values: list[int]) -> str:
        return name + ": " + " ".join(str(v) for v in values) + " "

    body = (
        f"{{v1 123456789 {header} 0 31 "
        + part("ins", ins)
        + part("ains", ains)
        + part("outs", outs)
        + part("areqs", areqs)
        + part("reqs", reqs)
        + part("fncs", fncs)
        + "crc16: FA37}\n"
    )
    return body.encode()


@pytest.mark.parametrize("header", [100, 105, 106])
def test_every_salt_net_firmware_reads_the_salt_values(header) -> None:
    """The product line picks the profile, not the firmware version in the header."""
    device = decode(_salt_net_frame(header=header))

    assert device.device_type == AsekoDeviceType.SALT
    assert device.salinity == 5.3
    assert device.chlorine_production == 19


# Issues #131 and #169: the firmware 106 unit's frame as its owner posted it
# (serial redacted).  fncs[2] = 3 where the header 100 unit sends 1, with the
# same hardware.
SALT_NET_106_FRAME = (
    b"{v1 123456789 106 0 31 "
    b"ins: 295 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 9 13 12 14 0 "
    b"ains: 709 709 537 5420 0 0 542 542 101 12 459 0 0 0 0 0 "
    b"outs: 0 0 2 0 0 0 0 0 0 0 0 0 0 0 2 0 0 0 0 "
    b"areqs: 71 72 4 0 2 33 33 0 0 0 33 33 33 0 49 255 255 5 5 10 0 15 0 0 0 0 "
    b"reqs: 0 0 0 0 0 0 0 24 0 2 "
    + b"0 " * 23
    + b"10 10 "
    + b"0 " * 25
    + b"fncs: 0 0 3 0 0 0 10 0 mods: 2 1 0 1 1 0 0 0 flags: 2 0 0 0 0 0 0 0 "
    b"crc16: 07AF}\n"
)


def test_the_firmware_106_frame_reads_as_its_display_showed() -> None:
    """Issue #169: the values its owner compared with the display and the app."""
    device = decode(SALT_NET_106_FRAME)

    assert device.device_type == AsekoDeviceType.SALT
    assert device.frame_problems == ()
    assert device.salinity == 10.1
    assert device.chlorine_production == 12
    assert device.electrolysis_running is True
    assert device.electrode_polarity is AsekoElectrodePolarity.RIGHT
    assert device.algaecide_dose_target == 2
    assert device.pool_volume == 49
    # reqs[7] = 24 while the display read "Timer 24dag" (Issue #131)
    assert device.filtration_schedule is AsekoFiltrationSchedule.NONSTOP_24H
    # pH- and the algicide port, whatever fncs[2] says; no chlorine pump
    assert {"ph_minus_pump_running", "algaecide_pump_running"} <= device.features
    assert "chlorine_pump_running" not in device.possible_features
    assert "flocculant_pump_running" not in device.features


def test_the_firmware_106_algicide_dose_is_outs_11() -> None:
    """Issue #169: outs[11] went on and off with the unit's algicide dose."""
    dosing = SALT_NET_106_FRAME.replace(
        b"outs: 0 0 2 0 0 0 0 0 0 0 0 0", b"outs: 0 0 2 0 0 0 0 0 0 0 0 1", 1
    )

    assert decode(SALT_NET_106_FRAME).algaecide_pump_running is False
    assert decode(dosing).algaecide_pump_running is True


def test_salinity_matches_the_display() -> None:
    """Issue #131: the second unit's display read 10.1 with ains[8] = 101."""
    assert decode(_salt_net_frame(salinity=101)).salinity == 10.1


@pytest.mark.parametrize(
    ("outs14", "running", "polarity"),
    [
        (0, False, AsekoElectrodePolarity.WAITING),
        (2, True, AsekoElectrodePolarity.RIGHT),
        (3, True, AsekoElectrodePolarity.LEFT),
    ],
)
def test_the_electrolyser_state_and_direction_come_from_outs_14(
    outs14, running, polarity
) -> None:
    device = decode(_salt_net_frame(electrolyser=outs14))

    assert device.electrolysis_running is running
    assert device.electrode_polarity is polarity


def test_the_electrolyser_output_is_reported_as_sent() -> None:
    off = decode(_salt_net_frame(electrolyser=0, production=0))

    assert off.chlorine_production == 0
    assert decode(_salt_net_frame(production=20)).chlorine_production == 20


def test_the_third_pump_is_algicide_while_fncs_6_says_so() -> None:
    """outs[11] is the port; fncs[6] = 10 algicide, 18 flocculant (Issue #131)."""
    idle = decode(_salt_net_frame(third_pump=0))
    dosing = decode(_salt_net_frame(third_pump=1))

    assert idle.algaecide_pump_running is False
    assert dosing.algaecide_pump_running is True
    assert dosing.algaecide_dose_target == 5
    # the port is not flocculant, so that unit has no flocculant entities
    assert "flocculant_pump_running" not in dosing.features
    assert "flocculant_dose_target" not in dosing.features


def test_the_same_port_switched_to_flocculant() -> None:
    device = decode(
        _salt_net_frame(
            third_pump=1, third_pump_code=18, algicide_dose=0, flocculant_dose=10
        )
    )

    assert device.flocculant_pump_running is True
    assert device.flocculant_dose_target == 10
    assert "algaecide_pump_running" not in device.features
    assert "algaecide_dose_target" not in device.features


@pytest.mark.parametrize(
    ("alarms", "no_flow", "max_dose"),
    [(0, False, False), (0x100, True, False), (0x80, False, True)],
)
def test_the_v8_alarms_are_bits_of_ins_12(alarms, no_flow, max_dose) -> None:
    """Issue #151: ins[12] flipped 0 -> 128 with 'maximum disinfection dose'."""
    device = decode(_salt_net_frame(alarms=alarms))

    assert device.alarm_no_flow_to_probes is no_flow
    assert device.alarm_max_disinfection_dose is max_dose


def test_a_salt_net_has_no_chlorine_pump() -> None:
    """A salt unit makes its chlorine; the NET's canister entities do not apply."""
    device = decode(_salt_net_frame())

    assert "chlorine_pump_running" not in device.possible_features
    assert "chlorine_flow_rate" not in device.possible_features


@pytest.mark.parametrize(
    ("start", "stop", "reads", "schedule"),
    [
        (8, 20, (time(8, 0), time(20, 0)), AsekoFiltrationSchedule.TIMER_PERIOD_1),
        (0, 24, (time(0, 0), time(0, 0)), AsekoFiltrationSchedule.NONSTOP_24H),
        (9, 17, (time(9, 0), time(17, 0)), AsekoFiltrationSchedule.TIMER_PERIOD_1),
    ],
)
def test_the_filtration_timer_is_whole_hours_in_reqs_5_and_7(
    start, stop, reads, schedule
) -> None:
    """Issue #131: 8 / 20 on a unit set to 08:00-20:00, 0 / 24 on one running nonstop."""
    device = decode(_salt_net_frame(filtration=(start, stop)))

    assert (device.filtration_period_1_start, device.filtration_period_1_end) == reads
    assert device.filtration_schedule is schedule


def test_an_hour_outside_the_day_is_not_a_time() -> None:
    assert decode(_salt_net_frame(filtration=(0, 25))).filtration_period_1_end is None
