"""Test the Aseko Decoder."""

import json
from dataclasses import fields
from datetime import datetime, time
from pathlib import Path

import pytest

from custom_components.aseko_local.const import (
    PROBE_CLF_MISSING,
    PROBE_DOSE_MISSING,
    PROBE_OXY_MISSING,
    PROBE_REDOX_MISSING,
    UNIT_TYPE_PROFI,
    WATER_FLOW_TO_PROBES,
    YEAR_OFFSET,
)
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.decoding.features import Configuration
from custom_components.aseko_local.decoding.frames import (
    Protocol,
    decode_time,
    decode_timestamp,
    parse_v7,
)
from custom_components.aseko_local.decoding.profiles import profile_for
from custom_components.aseko_local.models import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoElectrodePolarity,
    AsekoFiltrationSchedule,
    AsekoProbeType,
)


def _configuration(
    data: bytes, device_type: AsekoDeviceType | None = None
) -> set[AsekoProbeType]:
    """Read the installed probes the way ``device_type``'s profile does."""
    profile = profile_for(Protocol.V7, device_type)
    read = getattr(Configuration(), profile.reading_for(Configuration))
    return read(parse_v7(data), AsekoDevice(device_type=device_type))


def _make_base_bytes(size: int = 120) -> bytearray:
    """Create a base bytearray for test data with default values."""

    data = bytearray(size)
    data[0:4] = (1234).to_bytes(4, "big")  # serial_number
    data[4] = 0x0E  # SALT with REDOX probe
    data[6] = 24  # year (2024)
    data[7] = 6  # month
    data[8] = 15  # day
    data[9] = 12  # hour
    data[10] = 34  # minute
    data[11] = 56  # second
    data[25:27] = (245).to_bytes(2, "big")  # water_temperature = 24.5
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x08  # pump_running
    data[37] = (
        0xFF  # UNSPECIFIED (0xFF) → byte[101] not routed; algaecide_flow_rate and flocculant_flow_rate both None
    )
    data[54] = (
        5  # required dosing rate (byte 54); algicide or floc depending on byte[37]
    )
    data[55] = 28  # water_temperature_target
    data[56] = 8  # filtration_period_1_start hour
    data[57] = 0  # filtration_period_1_start min
    data[58] = 10  # filtration_period_1_end hour
    data[59] = 0  # filtration_period_1_end min
    data[60] = 14  # filtration_period_2_start hour
    data[61] = 0  # filtration_period_2_start min
    data[62] = 16  # filtration_period_2_end hour
    data[63] = 0  # filtration_period_2_end min
    data[68] = 3  # backwash_interval
    data[69] = 2  # backwash_start_time hour
    data[70] = 30  # backwash_start_time min
    data[71] = 2  # backwash_duration (20)
    data[74:76] = (120).to_bytes(2, "big")  # startup_delay
    data[92:94] = (5000).to_bytes(2, "big")  # pool_volume
    data[95] = 10  # chlorine_flow_rate
    data[76:78] = (3600).to_bytes(2, "big")  # max_refill_time, raw 3600
    data[94:96] = (60).to_bytes(2, "big")  # byte 95 = ph_minus_flow_rate
    data[97] = 20  # ph_plus_flow_rate
    data[99] = 255  # ph_minus_flow_rate (not measured)
    data[101] = 40  # flocculant_flow_rate
    data[106:108] = (30).to_bytes(2, "big")  # dosing_delay
    return data


def test_decode_redox() -> None:
    """Test decoding of Redox probe data."""

    data = _make_base_bytes()
    data[4] = 0x0A  # NET with Redox probe
    data[18:20] = (550).to_bytes(2, "big")  # Redox
    data[53] = 65  # required Redox

    device = decode(bytes(data))
    assert device.redox_target == 650
    assert device.redox == 550


def test_decode_clf() -> None:
    """Test decoding of CL free probe data."""

    data = _make_base_bytes()
    data[4] = 0x09  # NET with CL probe
    data[16:18] = (50).to_bytes(2, "big")  # CL free
    data[53] = 9  # required CL free

    device = decode(bytes(data))
    assert device.free_chlorine_target == 0.9
    assert device.free_chlorine == 0.5


def test_flowrates() -> None:
    """Test decoding of flowrate data."""

    data = _make_base_bytes()
    data[37] = 0x00  # flocculant mode → byte[101] routes to flocculant_flow_rate

    device = decode(bytes(data))
    assert device.chlorine_flow_rate is None
    assert device.ph_plus_flow_rate is None
    assert device.ph_minus_flow_rate == 60
    assert device.flocculant_flow_rate == 40


def test_decode_home() -> None:
    """Test decoding of HOME device data."""

    data = _make_base_bytes()
    data[4] = 0x03  # HOME with Redox probe
    data[14:16] = (720).to_bytes(2, "big")  # ph
    data[37] = (
        0xB3  # pump presence/config byte (HOME has independent ports, not routed)
    )
    data[52] = 72  # ph_target

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.serial_number == 1234
    assert device.ph == 7.2
    assert device.ph_target == 7.2
    assert device.water_temperature == 24.5
    assert device.filtration_running is True
    assert device.water_flow_to_probes is True
    assert device.pool_volume == 5000
    assert device.max_refill_time == 3600  # bytes 76-77, raw
    assert device.startup_delay == 120
    assert device.dosing_delay == 30
    assert device.filtration_period_1_start == time(8, 0)
    assert device.filtration_period_1_end == time(10, 0)
    assert device.filtration_period_2_start == time(14, 0)
    assert device.filtration_period_2_end == time(16, 0)
    assert device.backwash_interval == 3
    assert device.backwash_start_time == time(2, 30)
    assert device.backwash_duration == 20
    # The frame carries the backwash *configuration* only; it never says when a
    # cycle last ran.  The decoder must therefore leave the history unknown
    # instead of deriving it from the schedule — the coordinator fills these in
    # from BackwashTracker once a real relay window has been observed.
    assert device.last_backwash is None
    assert device.last_scheduled_backwash is None
    assert device.last_manual_backwash is None
    assert device.last_backwash_trigger is None
    assert device.next_scheduled_backwash is None
    # HOME has 4 independent pump ports — byte[37] routing does not apply.
    # byte[54] = flocculant_dose_target, byte[72] = algaecide_dose_target (same layout as OXY).
    # Base bytes: data[54]=5, data[72]=0 (default zero).
    assert device.flocculant_dose_target == 5
    assert device.algaecide_dose_target == 0
    assert device.water_temperature_target == 28
    assert device.timestamp is not None
    assert device.timestamp.year == YEAR_OFFSET + 24
    assert device.timestamp.month == 6
    assert device.timestamp.day == 15
    assert device.timestamp.hour == 12
    assert device.timestamp.minute == 34
    assert device.timestamp.second == 56


def test_decode_filtration_period2_disabled() -> None:
    """Period 2 times are still populated when disabled, but the mode is P1 only.

    Issue #133: pre-fix, the decoder returned ``None`` for filtration_period_2_start/filtration_period_2_end when
    byte[37] bit 0x20 was clear, which made already-registered entities go
    ``unknown`` once the user switched the controller back to "P1 only"
    (Home Assistant protects the entity registry, so the entity stays).
    Post-fix, the bytes 60-63 are read for any device in FILTRATION_TYPES
    because the controller keeps sending the last-configured Period 2 times
    (verified on dtpugh's serial 110169464: bytes 60-63 stay populated in
    P1 only / P1&P2 / 24h / MANUAL modes).  The *mode* still flips
    between TIMER_PERIOD_1 and TIMER_PERIOD_1_AND_2 per byte[37] bit 0x20,
    so the user can tell which schedule is active.
    """
    data = _make_base_bytes()
    data[37] = 0x93  # bit 0x20 clear -> period 2 disabled in the controller

    device = decode(bytes(data))

    # Period 1 is still parsed.
    assert device.filtration_period_1_start == time(8, 0)
    assert device.filtration_period_1_end == time(10, 0)
    # Period 2 times ARE populated (bytes 60-63 are stable) — but the mode
    # entity correctly reports TIMER_PERIOD_1 so the user knows the schedule
    # is not active.
    assert device.filtration_period_2_start == time(14, 0)
    assert device.filtration_period_2_end == time(16, 0)
    assert device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1


def test_decode_filtration_period2_enabled() -> None:
    """Second filtration period is exposed when enabled (byte 37 bit 0x20 set)."""
    data = _make_base_bytes()
    data[37] = 0xB3  # bit 0x20 set -> period 2 enabled

    device = decode(bytes(data))

    assert device.filtration_period_2_start == time(14, 0)
    assert device.filtration_period_2_end == time(16, 0)
    assert device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2


def test_decode_filtration_period2_bytes_unspecified() -> None:
    """Leave period 2 None when bytes 60-63 are 0xFF (no schedule ever configured).

    filtration_period_2_start / filtration_period_2_end stay None — the lazy-creation guard in sensor.py then
    skips registering the entity.  This is the key branch that keeps
    devices without a filtration output (NET) from ever surfacing
    Period 2 entities (Issue #133 contract).
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT (in FILTRATION_TYPES)
    data[60:64] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 2 schedule at all
    data[37] = 0xB7  # SALT algicide routing — bit 0x20 set, but no schedule

    device = decode(bytes(data))
    assert device.filtration_period_2_start is None
    assert device.filtration_period_2_end is None


def test_decode_filtration_period2_none_for_net() -> None:
    """Read no filtration periods on NET, which has no filtration output.

    filtration_period_1_start/2 / filtration_period_1_end/2 are all None
    even if the frame happens to carry non-0xFF values in bytes 56-63.
    Issue #133 contract: lazy creation in sensor.py never registers the
    entities for NET.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    # Garbage values in the schedule bytes (mimic real-world case where a
    # measurement-only device reports random data in slots it doesn't implement).
    data[56:64] = bytes([8, 0, 10, 0, 14, 0, 16, 0])

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.filtration_period_1_start is None
    assert device.filtration_period_1_end is None
    assert device.filtration_period_2_start is None
    assert device.filtration_period_2_end is None


def test_decode_filtration_period2_real_dtpugh_frames() -> None:
    """Decode the four real diagnostic frames of Issue #133 end to end.

    Frames from @dtpugh (serial 110169464, ASIN AQUA Home firmware B); Period 2
    times must stay stable across all four modes (P1 only / P1&P2 /
    24h / MANUAL).  This is the user-visible regression: pre-fix the
    entity would go "unknown" when the user toggled the controller back
    from P1&P2 to P1 only.
    """
    # Diagnostic files live in /tmp/issue133 (downloaded from the issue);
    # when the test runs in CI without that directory, skip instead of fail.
    diag_dir = Path("/tmp/issue133")
    if not diag_dir.exists():
        pytest.skip("diagnostic files from issue #133 are not available")

    def _first_frame(payload) -> str:
        if isinstance(payload, dict):
            for v in payload.values():
                r = _first_frame(v)
                if r is not None:
                    return r
        elif isinstance(payload, list):
            for v in payload:
                r = _first_frame(v)
                if r is not None:
                    return r
        elif (
            isinstance(payload, str)
            and len(payload) >= 100
            and all(c in "0123456789abcdefABCDEF" for c in payload.strip())
        ):
            return payload
        return None

    # 04_off is the user switching to manual while both periods stay
    # configured, which is why it carries a schedule as well as a mode.
    scenarios = {
        "01_p1only.json": (
            0x11,
            AsekoFiltrationSchedule.TIMER_PERIOD_1,
            False,
        ),
        "02_p1andp2.json": (
            0x31,
            AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2,
            False,
        ),
        "03_24h.json": (
            0x01,
            AsekoFiltrationSchedule.NONSTOP_24H,
            False,
        ),
        "04_off.json": (
            0x35,
            AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2,
            True,
        ),
    }

    for filename, (
        expected_b37,
        expected_schedule,
        expected_menu,
    ) in scenarios.items():
        with (diag_dir / filename).open() as f:
            frame = bytes.fromhex(_first_frame(json.load(f)))
        assert frame[37] == expected_b37, f"{filename}: byte 37 mismatch"

        device = decode(frame)
        # Period 1 is always there.
        assert device.filtration_period_1_start is not None, (
            f"{filename}: filtration_period_1_start unexpectedly None"
        )
        assert device.filtration_period_1_end is not None, (
            f"{filename}: filtration_period_1_end unexpectedly None"
        )
        # Period 2 is ALSO always there after the fix (entity stays populated).
        assert device.filtration_period_2_start is not None, (
            f"{filename}: filtration_period_2_start is None — entity would go 'unknown' (Issue #133)"
        )
        assert device.filtration_period_2_end is not None, (
            f"{filename}: filtration_period_2_end is None — entity would go 'unknown' (Issue #133)"
        )
        # The schedule entity reports which schedule is configured...
        assert device.filtration_schedule == expected_schedule, (
            f"{filename}: expected {expected_schedule}, "
            f"got {device.filtration_schedule}"
        )
        # ...and the service-menu flag whether anybody was at the unit.
        assert device.service_menu_open is expected_menu, (
            f"{filename}: expected {expected_menu}, got {device.service_menu_open}"
        )


def test_decode_electrolyzer_data() -> None:
    """Test decoding of electrolyzer data with right direction."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT with REDOX probe
    data[20] = 32  # salinity = 3.2
    data[21] = 80  # chlorine_production
    data[29] = 0x50  # electrolysis running, polarity bit 0x40 = right
    data[16:18] = (50).to_bytes(2, "big")  # a free chlorine reading in range
    data[14:16] = (700).to_bytes(2, "big")  # ph
    data[52] = 70

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.salinity == 3.2
    assert device.chlorine_production == 80
    assert device.electrolysis_running is True
    assert device.electrode_polarity == AsekoElectrodePolarity.RIGHT


def test_decode_electrolyzer_data_left_direction() -> None:
    """Test decoding of electrolyzer data with left direction."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT with REDOX probe
    data[20] = 32
    data[21] = 80
    data[29] = 0x10  # electrolysis running, polarity bit clear = left

    device = decode(bytes(data))
    assert device.electrode_polarity == AsekoElectrodePolarity.LEFT


def test_decode_electrolyzer_data_waiting_direction() -> None:
    """Test decoding of electrolyzer data with waiting direction."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT with REDOX probe
    data[20] = 32
    data[21] = 80
    data[29] = 0  # neither running nor left

    device = decode(bytes(data))
    assert device.electrode_polarity == AsekoElectrodePolarity.WAITING


@pytest.mark.parametrize(
    ("byte21", "byte29", "measured", "derived"),
    [
        (22, 0x10, 22, 22),  # running
        (0, 0x08, 0, 0),  # stopped: the unit sends 0 almost always
        (18, 0x08, 18, 0),  # stopped, still running down: as sent / 0
        (0, 0x10, 0, 0),  # running, 0 around a start
        (0xFF, 0x10, None, None),  # not filled in
        (0xFF, 0x08, None, 0),  # not filled in, but stopped
    ],
)
def test_chlorine_production_is_byte21_while_electrolysing(
    byte21, byte29, measured, derived
) -> None:
    """byte[21] is kept as sent; the derived value reads 0 while byte[29] says stopped."""
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT with REDOX probe
    data[21] = byte21
    data[29] = byte29
    device = decode(bytes(data))
    assert device.chlorine_production_measured == measured
    assert device.chlorine_production == derived


def test_decode_profi() -> None:
    """Test decoding of PROFI device data."""

    data = _make_base_bytes()
    data[4] = UNIT_TYPE_PROFI  # PROFI with Redox & CLF probe
    data[16:18] = (100).to_bytes(2, "big")
    data[18:20] = (650).to_bytes(2, "big")
    data[14:16] = (800).to_bytes(2, "big")
    data[52] = 80
    data[53] = 20

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.PROFI
    assert device.configuration == {
        AsekoProbeType.PH,
        AsekoProbeType.CLF,
        AsekoProbeType.REDOX,
    }
    assert device.ph == 8.0
    assert device.redox == 650
    assert device.free_chlorine == 1.0
    assert device.ph_target == 8.0
    assert (
        device.redox_target is None
    )  # PROFI has no required redox instead free_chlorine_target is existing
    assert device.free_chlorine_target == 2.0


def test_decode_net() -> None:
    """Test decoding of NET device data."""

    data = _make_base_bytes()
    data[4] = 0x09  # NET device
    data[6] = 0xFF  # year
    data[7] = 0xFF  # month
    data[8] = 0xFF  # day
    data[9] = 0xFF  # hour
    data[10] = 0xFF  # minute
    data[11] = 0xFF  # second

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    # NET (Aqua NET) has no filtration output → no schedule is reported (PR #122),
    # even though the frame carries values in the schedule bytes.
    assert device.filtration_period_1_start is None
    assert device.filtration_period_1_end is None
    assert device.filtration_period_2_start is None
    assert device.filtration_period_2_end is None
    # Issue #129: NET has no backwash valve, so the schedule must stay None
    # regardless of what the frame carries in bytes 68-71.
    assert device.backwash_interval is None
    assert device.backwash_start_time is None
    assert device.backwash_duration is None
    assert device.last_backwash is None
    assert device.next_scheduled_backwash is None
    assert device.backwash_running is None
    # NET has no filling valve, so the water_level group is empty too.
    assert device.water_level is None
    assert device.water_level_low_alarm is None
    assert device.water_level_refill_start is None
    assert device.water_level_refill_stop is None
    assert device.water_level_high_alarm is None
    assert device.refilling is None
    assert device.max_refill_time is None
    # Pool volume and dosing delays are still available on NET.
    assert device.pool_volume == 5000
    assert device.dosing_delay == 30


def test_decode_corrupted_timestamp() -> None:
    """Test decoding data with corrupted timestamp should fallback to server timestamp."""

    data = bytearray.fromhex(
        "0691ffff0d01050e01010101000002d002bfffff02bfff01bc00ffffaa0000080000000000ff0173"
        "0691ffff0d0305ffffffffff484608ffffffffffffffffff02d100ffffffffffffffffffffffff97"
        "0691ffff0d0205ffffffffff0007003cffff003cffff010181ff012c0102581e28ffffffff0048cd"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.timestamp is not None
    assert device.timestamp.year != 2005


def test_decode_net_120_bytes() -> None:
    """Test decoding of NET device data with 120 bytes."""

    data = bytearray.fromhex(
        "0690ffff0901ffffffffffff0000027300caffff0140ff0c3c0120ffaa000d340000000000ff007f"
        "0690ffff0903ffffffffffff480608ffffffffffffffffff02720128ffffffffffffffffffffffe5"
        "0690ffff0902ffffffffffff0026003cffff003cffff010183ff012c0502581e28ffffffff0047a2"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.timestamp is not None


def test_decode_unknown_unit_type() -> None:
    """Unknown unit type must not raise – connection must stay open for cloud forwarding."""

    data = bytearray.fromhex(
        "0690ffff0001ffffffffffff0000027300caffff0140ff0c3c0120ffaa000d340000000000ff007f"
        "0690ffff0003ffffffffffff480608ffffffffffffffffff02720128ffffffffffffffffffffffe5"
        "0690ffff0002ffffffffffff0026003cffff003cffff010183ff012c0502581e28ffffffff0047a2"
    )

    # Must not raise – decoder returns a device with device_type=None
    device = decode(bytes(data))
    assert device.device_type is None


def test_decode_net_no_backwash_with_garbage_bytes() -> None:
    """Show no phantom backwash or water-level entities on NET (Issue #129).

    A NET frame carrying non-0xFF data in the backwash/water-level byte slots must not surface phantom backwash or water-level entities.

    Pre-fix behaviour: the decoder blindly read bytes 68-71, 27, 102-105 and
    94-95 on every device type. When a NET device happened to send non-0xFF
    values in those slots, the integration created disabled backwash /
    water-level entities with semantically meaningless numbers (e.g.
    max_refill_time=65535 from bytes 0xFFFF being decoded as a 16-bit int).

    Post-fix behaviour: device-type gating on BACKWASH_TYPES / WATER_LEVEL_TYPES
    forces the corresponding device fields to None on NET, which causes
    _build_sensor_entities() in sensor.py to skip the entity altogether.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET (CLF probe, default for _make_base_bytes is SALT)
    # Garbage values in the slots that belong to backwash / water-level.
    # These mimic the real-world case where a measurement-only device
    # reports random non-0xFF data in slots it does not implement.
    data[27] = 53  # would-be water_level (cm)
    data[68] = 7  # would-be backwash_interval
    data[69] = 9  # would-be backwash_start_time hour
    data[70] = 30  # would-be backwash_start_time min
    data[71] = 12  # would-be backwash_duration (×10 s)
    data[102] = 13  # would-be water_level_low_alarm
    data[103] = 21  # would-be water_level_refill_start
    data[104] = 60  # would-be water_level_refill_stop
    data[105] = 100  # would-be water_level_high_alarm
    data[94:96] = bytes([0xFF, 0xFF])  # would-be max_refill_time → must be None

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    # None of these may leak through on a NET device, no matter what the frame carries.
    assert device.backwash_interval is None
    assert device.backwash_start_time is None
    assert device.backwash_duration is None
    assert device.last_backwash is None
    assert device.next_scheduled_backwash is None
    assert device.backwash_running is None
    assert device.water_level is None
    assert device.water_level_low_alarm is None
    assert device.water_level_refill_start is None
    assert device.water_level_refill_stop is None
    assert device.water_level_high_alarm is None
    assert device.refilling is None
    assert device.max_refill_time is None


def test_decode_max_ph_doses() -> None:
    """byte[115] is the "Max. number of doses of pH" safety setting.

    Confirmed on an ASIN AQUA Salt: the setting was changed
    from 20 to 17 on the unit and the next frame (2026-09-12 19:47) carried
    byte[115] = 0x11, with no other byte in the frame equal to 17.
    """
    data = _make_base_bytes()  # SALT
    data[115] = 17
    device = decode(bytes(data))
    assert device.max_ph_doses == 17
    assert "max_ph_doses" in device.features

    data[115] = 0xFF  # never set
    device = decode(bytes(data))
    assert device.max_ph_doses is None
    assert "max_ph_doses" not in device.features

    data[4] = 0x09  # NET has no such setting, so no NET profile reads it
    data[115] = 20
    device = decode(bytes(data))
    assert device.max_ph_doses is None
    assert "max_ph_doses" not in device.features


def test_max_filling_time_unspecified_sentinel() -> None:
    """Issue #129: 0xFFFF in bytes 76-77 must decode to None, not 65535.

    Pre-fix behaviour: a bare ``int.from_bytes(data[76:78], "big")`` returned
    65535 for the 0xFFFF sentinel, surfacing a nonsensical "max filling time
    = 65535 min" sensor on devices that do not implement filling (NET, PROFI).
    """
    data = _make_base_bytes()  # default SALT — has max_refill_time
    data[4] = 0x09  # but flip to NET
    data[76:78] = bytes([0xFF, 0xFF])  # UNSPECIFIED sentinel
    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.max_refill_time is None


def test_max_filling_time_real_value_home() -> None:
    """Sanity check: on a HOME device, a real value still decodes correctly.

    This guards against an accidental regression where the new
    _max_filling_time_from_bytes() helper breaks the verified
    "60 min from 0x003c" mapping (Issue #110).
    """
    data = _make_base_bytes()
    data[4] = 0x02  # UNIT_TYPE_HOME_CLF — any HOME subtype works
    data[6:12] = bytes([24, 6, 15, 12, 34, 56])
    data[76:78] = (3600).to_bytes(2, "big")
    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.max_refill_time == 3600


def test_decode_issue_17() -> None:
    """Test decoding data from issue #17."""

    data = bytearray.fromhex(
        "0690ffff0d01190519160832000002c6006c0249200000fe7000e0fe00400000000000000033001f"
        "0690ffff0d031905191608324809001b07000b1e0c1e1500030c00e8000c1e0aff2800780e1081bd"
        "0690ffff0d02190519160832003c003c3a1066ff003c1e3c6e9603840a0bb80f0900b505fff401eb"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT


def test_decode_issue_20() -> None:
    """Test decoding data from issue #20."""

    data = bytearray.fromhex(
        "0691ffff0a01ffffffffffff000002d002bfffff02bfff01bc00ffffaa0000080000000000ff0173"
        "0691ffff0a03ffffffffffff484608ffffffffffffffffff02d100ffffffffffffffffffffffff97"
        "0691ffff0a02ffffffffffff0007003cffff003cffff010181ff012c0102581e28ffffffff0048cd"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.timestamp is not None
    assert device.free_chlorine is None
    assert device.free_chlorine_mv is None
    assert device.redox == 703


def test_decode_issue_22() -> None:
    """Test decoding data from issue #22."""

    data = bytearray.fromhex(
        "0690ffff0901ffffffffffff000002cb003bffff007bff00000121ffaa0000040000000000ff0000"
        "0690ffff0903ffffffffffff480608ffffffffffffffffff02b90129ffffffffffffffffffffff2f"
        "0690ffff0902ffffffffffff0026003cffff003cffff010183ff012c0102581e28ffffffff0047a6"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.timestamp is not None
    assert device.free_chlorine == 0.59
    assert device.free_chlorine_mv == 123
    assert device.redox is None


def test_decode_issue_28() -> None:
    """Test decoding data from issue #28."""

    data = bytearray.fromhex(
        "068fffff0e0119061d113428000002ee019001902300ff006f011c32aa48000000000000004720c5"
        "068fffff0e0319061d1134284c2803200a0014001605160a02d3010c07110006ff2800780e10021b"
        "068fffff0e0219061d1134280012003c330434ff003c2d2f323402580a0bb80f0f0134ffff990197"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.timestamp is not None
    assert device.free_chlorine is None
    assert device.redox == 400
    assert device.ph == 7.5
    assert device.salinity == 3.5
    assert device.chlorine_production == 0
    assert device.electrolysis_running is False
    assert device.electrode_polarity == AsekoElectrodePolarity.WAITING
    assert device.water_temperature == 28.4


def test_decode_issue_61() -> None:
    """Test decoding data from issue #61."""

    data = bytearray.fromhex(
        "0690cafe0301190a12103232000402cb015201520152a3fe700099fe000800000000000000130267"
        "0690cafe0303190a121032324842011d080f122d15001737027600a9000c1e0a012801e00e10a202"
        "0690cafe03 02190a1210 3232002d00 3c003c003c 000a1e3c6e 9600f00802 580f0f0f1e 14ffbf0297"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.REDOX}
    assert device.ph is not None
    assert device.redox is not None
    assert device.free_chlorine is None


# test combinations of different methodes like date, time, normalize, probe types etc.


def test_decode_net_pump_states() -> None:
    """Test pump state decoding for Aqua NET (confirmed byte 29 masks from Issue #66)."""

    data = _make_base_bytes()
    data[4] = 0x09  # NET with CLF probe

    # Bit 0x08 is not mapped for NET – filtration_running stays None
    data[29] = 0x08
    device = decode(bytes(data))
    assert device.filtration_running is None
    assert device.chlorine_pump_running is False
    assert device.ph_minus_pump_running is False

    # CL pump only (0x02; bit 0x08 has no meaning on NET)
    data[29] = 0x0A  # 0x08 | 0x02
    device = decode(bytes(data))
    assert device.filtration_running is None
    assert device.chlorine_pump_running is True
    assert device.ph_minus_pump_running is False

    # PH-minus pump only (0x01; bit 0x08 has no meaning on NET)
    data[29] = 0x09  # 0x08 | 0x01
    device = decode(bytes(data))
    assert device.filtration_running is None
    assert device.chlorine_pump_running is False
    assert device.ph_minus_pump_running is True

    # No pump running
    data[29] = 0x00
    device = decode(bytes(data))
    assert device.filtration_running is None
    assert device.chlorine_pump_running is False
    assert device.ph_minus_pump_running is False

    # SALT-specific fields must be None for NET
    assert device.electrolysis_running is None
    assert device.electrode_polarity is None


def test_decode_salt_pump_states() -> None:
    """Test pump state decoding for Aqua SALT (electrolyzer, no CL pump)."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[20] = 32  # salinity
    data[21] = 80  # chlorine_production

    # Electrolyzer running, right polarity (no filtration bit)
    data[29] = 0x50
    device = decode(bytes(data))
    assert device.filtration_running is False
    assert device.electrolysis_running is True
    assert device.electrode_polarity == AsekoElectrodePolarity.RIGHT
    assert device.chlorine_pump_running is None  # SALT has no CL pump

    # Electrolyzer running, left polarity
    data[29] = 0x18  # 0x10 | 0x08 (running + filtration, polarity bit clear)
    device = decode(bytes(data))
    assert device.filtration_running is True
    assert device.electrolysis_running is True
    assert device.electrode_polarity == AsekoElectrodePolarity.LEFT

    # Electrolyzer off
    data[29] = 0x08  # filtration only
    device = decode(bytes(data))
    assert device.electrolysis_running is False
    assert device.electrode_polarity == AsekoElectrodePolarity.WAITING


def test_decode_salt_algicide_pump_running() -> None:
    """Test algicide pump running detection for SALT.

    Confirmed by @hopkins-tk 2026-04-04 (19 consecutive frames w/o electrolyzer, PR #87):
    algicide running → byte[29]=0x28 (bit 5 / 0x20), same mask as flocculant.
    not running → byte[29]=0x08. Routing via byte[37] bit 7 (0x80) = algicide configured.
    """

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[37] = 0xB3  # algicide configured (bit 7 set); 0xB3 = real Hopkins value
    data[54] = 10  # algaecide_dose_target = 10 ml/m³/day (non-FF → not None)
    data[101] = 60  # algaecide_flow_rate = 60 ml/min

    # Algicide pump running: byte[29] bit 5 (0x20) set
    data[29] = 0x28  # 0x08 | 0x20 — confirmed by 19 live frames 2026-04-04
    device = decode(bytes(data))
    assert device.algaecide_pump_running is True
    assert (
        device.flocculant_pump_running is None
    )  # algicide configured → floc slot vacant

    # Algicide pump not running
    data[29] = 0x08  # baseline; confirmed 2026-04-04
    device = decode(bytes(data))
    assert device.algaecide_pump_running is False
    assert device.flocculant_pump_running is None


def test_decode_salt_flocculant_pump_running() -> None:
    """Test flocculant pump running detection for SALT.

    Confirmed by @hopkins-tk 2026-04-03 (PR #87): flocculant running → byte[29]=0x28
    (bit 5 / 0x20), not running → byte[29]=0x08 (immediate stop, no linger).
    Byte[37] bit 7 (0x80) clear = flocculant configured.
    """

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[37] = 0x33  # flocculant configured (bit 7 clear); 0x33 = real Hopkins value
    data[54] = 1  # flocculant_dose_target placeholder (not used for type check)
    data[101] = 60  # flocculant_flow_rate = 60 ml/min

    # Flocculant pump running: byte[29] bit 5 (0x20) set
    data[29] = 0x28  # 0x08 | 0x20 — confirmed by live frame 2026-04-03
    device = decode(bytes(data))
    assert device.flocculant_pump_running is True
    assert (
        device.algaecide_pump_running is None
    )  # flocculant configured → alg slot vacant

    # Flocculant pump not running
    data[29] = 0x08  # baseline; confirmed 2026-04-03 (immediate stop, no linger)
    device = decode(bytes(data))
    assert device.flocculant_pump_running is False


# test combinations of different methodes like date, time, normalize, probe types etc.


def test_timestamp_unspecified() -> None:
    """Test timestamp decoding with unspecified values."""

    data = bytearray(120)
    data[6:12] = b"\xff\xff\xff\xff\xff\xff"
    ts = decode_timestamp(data)
    assert isinstance(ts, datetime)
    now = datetime.now(ts.tzinfo)
    assert abs((ts - now).total_seconds()) < 5


def test_timestamp_invalid() -> None:
    """Test timestamp decoding with invalid values."""
    data = bytearray(120)
    data[6:12] = b"\xf0\xf0\xf0\xf0\xf0\xf0"
    ts = decode_timestamp(data)
    assert isinstance(ts, datetime)
    now = datetime.now(ts.tzinfo)
    assert abs((ts - now).total_seconds()) < 5


def test_time_unspecified() -> None:
    """Test time decoding with unspecified values."""

    data = bytearray(120)
    data[0] = 255
    data[1] = 255
    t = decode_time(data)
    assert t is None


def test_time_invalid() -> None:
    """Test time decoding with invalid values."""

    data = bytearray(120)
    data[0] = 200
    data[1] = 200
    t = decode_time(data)
    assert t is None


def test_available_probes_combinations() -> None:
    # All probes present
    data = bytearray(120)
    data[4] = 0x00
    probes = _configuration(data)
    assert probes == {
        AsekoProbeType.PH,
        AsekoProbeType.CLF,
        AsekoProbeType.CLT,
        AsekoProbeType.REDOX,
        AsekoProbeType.DOSE,
        AsekoProbeType.OXY,
    }

    # Just CLF is missing
    data[4] = PROBE_CLF_MISSING
    probes = _configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.CLF not in probes

    # Just REDOX is missing
    data[4] = PROBE_REDOX_MISSING
    probes = _configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.REDOX not in probes

    # Just OXY is missing
    data[4] = PROBE_OXY_MISSING
    probes = _configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.OXY not in probes

    # Just DOSE is missing
    data[4] = PROBE_DOSE_MISSING
    probes = _configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.DOSE not in probes


# ── ASIN AQUA Oxygen ────────────────────────────────────────────────────────

# Test frames for OXY device (anonymized serial: 0x0690DEAD)
# Normal frame: no pump running except filtration (23:51:00 UTC+2)
_OXY_NORMAL_HEX = (
    "0690dead05011a040b173300000002d0001e001efd9d80fe7000c7feaa0800000000000000030895"
    "0690dead05031a040b173300480c0a19080010001200160002c300c7000c1e0a0f2800f00e10aa8d"
    "0690dead05021a040b1733000029003c003c003c000a1e3c6e9600780c02580f2b0f1e1eaacb001b"
)

# pH− pump running frame (2026-04-12 15:27:38 UTC+2): byte[29] 0x08 → 0x88
_OXY_PH_MINUS_HEX = (
    "06 90 de ad 05 01 1a 04 0c 0f 1b 26 00 00 02 cf 00 1e 00 1e fd 9d 80 fe 70 00 bc fe aa 88 00 00 00 00 00 00 00 03 08 60"
    " 06 90 de ad 05 03 1a 04 0c 0f 1b 26 46 0c 0a 19 08 00 10 00 12 00 16 00 02 c2 00 bc 00 0c 1e 0a 0f 28 00 f0 0e 10 aa e8"
    " 06 90 de ad 05 02 1a 04 0c 0f 1b 26 00 29 00 3c 00 3c 00 3c 00 0a 1e 3c 6e 96 00 78 0c 02 58 0f 2b 0f 1e 1e aa cb 00 0a"
)

# Flocculant pump running frame (23:51:25 UTC+2): byte[29] 0x08 → 0x28
_OXY_FLOC_HEX = (
    "0690dead05011a040b173319000002d0001e001efd9d80fe7000c7feaa280000000000000003 08ac"
    "0690dead05031a040b173319480c0a19080010001200160002c300c7000c1e0a0f2800f00e10aa94"
    "0690dead05021a040b1733190029003c003c003c000a1e3c6e9600780c02580f2b0f1e1eaacb0002"
)


def _oxy_bytes(hex_str: str) -> bytes:
    """Strip whitespace and convert hex string to bytes."""
    return bytes.fromhex(hex_str.replace(" ", ""))


def test_decode_oxy_normal_frame() -> None:
    """Decode the OXY normal frame: filtration only, no floc pump.

    Test frame for ASIN AQUA Oxygen (anonymized serial).
    """
    device = decode(_oxy_bytes(_OXY_NORMAL_HEX))

    # Device type and probes
    assert device.device_type == AsekoDeviceType.OXY
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.OXY}

    # CLF/REDOX must be None – firmware placeholder 0x001E must not be decoded
    assert device.free_chlorine is None
    assert device.redox is None
    assert device.free_chlorine_target is None
    assert device.redox_target is None

    # byte[37]=0x03 on OXY must NOT trigger SALT-style algicide/floc routing.
    # OXY has two independent pump ports: byte[54]=flocculant_dose_target, byte[72]=algaecide_dose_target.
    # 2026-04-11 frame: floc=10 ml/h, algicide=15 ml/m³/d.
    assert device.flocculant_dose_target == 10  # byte[54] = 0x0a
    assert device.algaecide_dose_target == 15  # byte[72] = 0x0f

    # OXY-specific setpoint (byte[53] = 0x0c = 12)
    assert device.oxygen_dose_target == 12

    # Pumps
    assert device.filtration_running is True
    assert device.ph_minus_pump_running is False  # bit 0x80 clear
    assert device.flocculant_pump_running is False
    assert device.algaecide_pump_running is False  # bit 0x10 clear
    assert device.oxygen_pump_running is False  # bit 0x40 clear

    # Flow rates (sub-frame 3)
    assert device.ph_minus_flow_rate == 60  # byte[95] = 0x3c
    assert device.oxygen_flow_rate == 60  # byte[99] = 0x3c (OXY Pure pump slot)
    assert device.chlorine_flow_rate is None  # not set on OXY devices
    assert device.flocculant_flow_rate == 10  # byte[101] = 0x0a
    assert device.algaecide_flow_rate == 60  # byte[103] = 0x3c

    # Basic data
    assert device.serial_number == 110_157_485
    assert device.ph == pytest.approx(7.2, abs=0.01)
    assert device.water_temperature == pytest.approx(19.9, abs=0.1)
    assert device.water_flow_to_probes is True
    assert device.ph_target == pytest.approx(7.2, abs=0.01)
    assert device.water_temperature_target == 25
    assert device.pool_volume == 41


def test_decode_oxy_floc_pump_running() -> None:
    """Decode the OXY frame where the flocculant pump is running.

    Real frame captured 2026-04-11 23:51:25 UTC+2. Only change vs normal frame:
    byte[29] 0x08 → 0x28 (bit 0x20 set = flocculant pump confirmed).
    """
    device = decode(_oxy_bytes(_OXY_FLOC_HEX))

    assert device.device_type == AsekoDeviceType.OXY
    assert device.filtration_running is True
    assert device.flocculant_pump_running is True

    # All other OXY fields still intact
    assert device.free_chlorine is None
    assert device.redox is None
    assert device.oxygen_dose_target == 12
    assert device.flocculant_flow_rate == 10


def test_decode_oxy_ph_minus_pump_running() -> None:
    """Decode the OXY frame where the pH− pump is running.

    Real frame captured 2026-04-12 15:27:38 UTC+2. Only change vs normal frame:
    byte[29] 0x08 → 0x88 (bit 0x80 set = pH− pump confirmed).
    """
    device = decode(_oxy_bytes(_OXY_PH_MINUS_HEX))

    assert device.device_type == AsekoDeviceType.OXY
    assert device.filtration_running is True
    assert device.ph_minus_pump_running is True  # bit 0x80 set
    assert device.flocculant_pump_running is False
    assert device.algaecide_pump_running is False
    assert device.oxygen_pump_running is False

    # All other OXY fields intact
    assert device.free_chlorine is None
    assert device.redox is None
    assert device.oxygen_dose_target == 12
    assert device.ph_minus_flow_rate == 60
    assert device.flocculant_flow_rate == 10


def test_decode_issue_99_home() -> None:
    """Test decoding data from issue #99 (HOME with CLF - 0x02)."""

    data = bytearray.fromhex(
        "06 90 ff ff 02 01 1a 04 19 0e 13 0a 00 00 02 b7 00 1e 00 1e 00 1f 90 fe 70 01 30 26 aa 08 00 00 00 00 00 00 00 43 0a b3"
        "06 90 ff ff 02 03 1a 04 19 0e 13 0a 46 03 0a 19 08 00 10 00 12 00 16 00 02 be 01 30 03 15 00 0c 00 28 01 e0 2a 30 a2 55"
        "06 90 ff ff 02 02 1a 04 19 0e 13 0a 00 3c 00 3c 00 3c 00 3c 00 0a 0d 21 37 64 00 f0 14 02 58 0f 0f 0f 1e 14 ff bc 02 77"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.CLF}
    assert device.free_chlorine is not None
    assert device.free_chlorine_mv is not None
    assert device.redox is None
    # Bug fix: flocculant_dose_target and algaecide_dose_target must be decoded for HOME devices.
    # byte[54] = 0x0a = 10 → flocculant_dose_target = 10 ml/h
    # byte[72] = 0x00 = 0  → algaecide_dose_target = 0 ml/m³/day
    assert device.flocculant_dose_target == 10
    assert device.algaecide_dose_target == 0


def test_decode_home_clf_real_frame() -> None:
    """Real-world frame from serial 110128063 (ASIN AQUA Home, CLF variant).

    Frame captured 2026-04-28 08:27:07.  Verified against Aseko Live app.
    Confirms fix: flocculant_dose_target (byte[54]) and algaecide_dose_target (byte[72])
    are now correctly decoded for HOME devices.
    """

    data = bytearray.fromhex(
        # Segment 1: real-time sensor data
        "06906bbf02011a041c081b070028027500000000000290fe70017b080000ffff0000000000430a85"
        # Segment 2: setpoints and schedule
        "06906bbf02031a041c081b0746030a190800100012001600027c017b0315000c002801e02a30a0d8"
        # Segment 3: pool parameters and flowrates
        "06906bbf02021a041c081b07003c003c003c003c000a0d21376400f01402580f0f0f1e14ffbc0271"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.CLF}
    # Probe readings
    assert device.ph == pytest.approx(6.29)
    assert device.free_chlorine == pytest.approx(0.0)
    assert device.free_chlorine_mv == 2
    assert device.water_temperature == pytest.approx(37.9)
    assert device.water_flow_to_probes is False
    # Setpoints — all confirmed against Aseko Live Config page
    assert device.ph_target == pytest.approx(7.0)
    assert device.free_chlorine_target == pytest.approx(0.3)
    assert (
        device.flocculant_dose_target == 10
    )  # byte[54] = 0x0a = 10 ml/h  (was None before fix)
    assert (
        device.algaecide_dose_target == 0
    )  # byte[72] = 0x00 = 0 ml/m³/d (was None before fix)
    assert device.water_temperature_target == 25
    # Schedule
    assert device.filtration_period_1_start == time(8, 0)
    assert device.filtration_period_1_end == time(16, 0)
    # Issue #133: Period 2 times are now always populated for any device in
    # FILTRATION_TYPES (HOME here).  The mode entity tells the user which
    # schedule is active — on this frame byte[37] = 0x43 (firmware A) so the
    # mode is NONSTOP_24H, but bytes 60-63 still report the last-configured
    # Period 2 times.  Pre-fix, the assertions below were ``is None``.
    assert device.filtration_period_2_start == time(18, 0)
    assert device.filtration_period_2_end == time(22, 0)
    assert device.filtration_schedule == AsekoFiltrationSchedule.NONSTOP_24H
    # Backwash
    assert device.backwash_interval == 3
    assert device.backwash_start_time == time(21, 0)
    assert device.backwash_duration == 120
    # Pool parameters
    assert device.pool_volume == 60
    # bytes 76-77 = 0x2a30 = 10800 s = 180 min, a round 3 h, in the same
    # seconds encoding as its neighbour startup_delay (74-75 = 480 s).
    #
    # This used to assert 60, read from bytes 94-95.  That is ph_minus_flow_rate
    # — and this unit runs 60 ml/min on both the pH- and chlorine pumps, so the
    # wrong offset produced a plausible-looking "60 min", exactly as it did for
    # serial 110071590 in Issue #110.  Not separately confirmed against the app
    # for this serial; the offset itself was verified on a SALT v7 by changing
    # the setting and watching which bytes moved.
    assert device.max_refill_time == 10800
    assert device.startup_delay == 480
    assert device.dosing_delay == 240
    # Flowrates
    assert device.chlorine_flow_rate == 60
    assert device.ph_minus_flow_rate == 60
    assert device.flocculant_flow_rate == 10


def test_decode_issue_99_salt() -> None:
    """Test decoding data from issue #99 (SALT with CLF - 0x0d)."""

    data = bytearray.fromhex(
        "06 8f ff ff 0d 01 1a 04 19 0e 2d 28 00 20 02 cd 00 00 00 01 1f 00 ff fd c4 00 dd 4e 00 00 00 00 00 00 00 00 00 57 00 3a"
        "06 8f ff ff 0d 03 1a 04 19 0e 2d 28 49 05 08 19 0a 1e 0e 1e 17 37 01 0a 02 b1 00 dd 07 0a 1e 0a ff 28 01 e0 0e 10 01 e7"
        "06 8f ff ff 0d 02 1a 04 19 0e 2d 28 00 41 00 3c 19 4c db ff 00 3c 1e 2d 4b 96 00 f0 0a 0b b8 0f 0f 01 7b ff ff 9a 01 bc"
    )

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.CLF}
    assert device.free_chlorine is not None
    # bytes 20-21 are salinity (0x1f = 3.1) and chlorine production (0) on SALT
    assert device.salinity == 3.1
    assert device.free_chlorine_mv is None
    assert "free_chlorine_mv" not in device.possible_features
    assert device.redox is None


# ── HOME independent flowrate tests (Issue #115) ─────────────────────────────


def test_decode_home_independent_flowrates() -> None:
    """HOME reads the flocculant on byte[101] whatever byte[37] says (Issue #115).

    byte[103] was read as the algicide flow rate too, but bytes 102-105 are the
    water level thresholds (confirmed on SALT); on HOME byte[103] is the refill
    start, and where HOME sends the algicide flow rate is not known yet.
    """
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 60  # chlorine_flow_rate (Chlor Pure)
    data[101] = 10  # flocculant_flow_rate
    data[103] = 33  # the refill start threshold
    data[37] = 0x53

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.chlorine_flow_rate == 60
    assert device.ph_minus_flow_rate == 60
    assert device.flocculant_flow_rate == 10
    assert device.water_level_refill_start == 33
    assert device.algaecide_flow_rate is None  # not located
    assert "algaecide_flow_rate" in device.features
    # byte[37] bit 7 has no meaning on HOME (no shared pump port)
    data[37] = 0xB3
    device = decode(bytes(data))
    assert device.flocculant_flow_rate == 10


def test_decode_home_flowrates_unspecified() -> None:
    """HOME flowrates: 0xFF → None (e.g. pump not installed)."""
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 0xFF  # chlorine pump not installed
    data[101] = 0xFF  # flocculant pump not installed
    data[103] = 0xFF  # algicide pump not installed

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.chlorine_flow_rate is None
    assert device.flocculant_flow_rate is None
    assert device.algaecide_flow_rate is None


def test_decode_home_pump_bits_follow_oxy() -> None:
    """HOME has OXY's four independent ports: bit 0x20 is the flocculant only.

    The algicide pump (bit 0x10 on OXY) is not read until the algicide flow
    rate is located, so one running pump no longer counts two chemicals.
    """
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 60
    data[101] = 10  # floc pump installed
    data[103] = 20
    data[37] = 0x53

    data[29] = 0x28  # bit 0x20 + filtration
    device = decode(bytes(data))
    assert device.flocculant_pump_running is True
    assert device.algaecide_pump_running is None
    assert "algaecide_pump_running" not in device.features

    data[29] = 0x18  # bit 0x10 + filtration
    device = decode(bytes(data))
    assert device.flocculant_pump_running is False


def test_decode_home_floc_pump_running_independent() -> None:
    """On HOME the floc pump runs independently of algicide (different pump ports).

    byte[101] set (floc installed) and byte[103] = 0xFF (no algicide) →
    flocculant_pump_running tracks byte[29] bit 5, algaecide_pump_running stays None.
    """
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 0xFF  # no chlor
    data[101] = 10  # floc installed
    data[103] = 0xFF  # NO algicide pump
    data[37] = 0x53

    data[29] = 0x28
    device = decode(bytes(data))
    assert device.flocculant_pump_running is True
    assert device.algaecide_pump_running is None


# ── HOME water level and alarm tests (Issue #100 / #110) ─────────────────────


def _make_home_bytes() -> bytearray:
    """Return the base HOME device frame (CLF variant, byte[4]=0x02) for water-level tests."""
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    return data


def test_home_water_level_decoding() -> None:
    """byte[27] is decoded as water_level (cm) for HOME devices only."""
    data = _make_home_bytes()
    data[27] = 0x0E  # 14 cm — confirmed by issue #110 frame

    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.water_level == 14


def test_home_water_level_unspecified() -> None:
    """byte[27] = 0xFF → water_level is None."""
    data = _make_home_bytes()
    data[27] = 0xFF

    device = decode(bytes(data))
    assert device.water_level is None


def test_water_level_sensor_disconnected() -> None:
    """byte[27] = 0xFE means no level sensor reading, not 254 cm.

    Every captured OXY frame reads 0xFE there; the manufacturer's RS485
    protocol document calls it "sensor disconnected".
    """
    data = _make_home_bytes()
    data[27] = 0xFE

    device = decode(bytes(data))
    assert device.water_level is None
    assert "water_level" not in device.features


def test_unspecified_16_bit_values_are_not_decoded_as_numbers() -> None:
    """0xFFFF is the "not filled in" marker, not 655.35 pH or 65535 s.

    A measurement the unit has (pH, redox, water temperature) becomes None --
    known to exist, unreadable in this frame.  A setting becomes absent.
    """
    data = _make_base_bytes()  # SALT REDOX
    data[14:16] = bytes([0xFF] * 2)  # pH
    data[16:20] = bytes([0xFF] * 4)  # redox (both slots)
    data[25:27] = bytes([0xFF] * 2)  # water temperature
    data[74:76] = bytes([0xFF] * 2)  # delay after startup
    data[92:94] = bytes([0xFF] * 2)  # pool volume
    data[106:108] = bytes([0xFF] * 2)  # delay after dose

    device = decode(bytes(data))
    for field in ("ph", "redox", "water_temperature"):
        assert getattr(device, field) is None, field
        assert field in device.features, field
    for field in ("startup_delay", "pool_volume", "dosing_delay"):
        assert getattr(device, field) is None, field
        assert field not in device.features, field

    clf = _make_home_bytes()
    clf[4] = 0x02  # HOME CLF; SALT sends salinity in bytes 20-21 instead
    clf[16:18] = bytes([0xFF] * 2)
    clf[20:22] = bytes([0xFF] * 2)
    device = decode(bytes(clf))
    assert device.free_chlorine is None
    assert device.free_chlorine_mv is None
    assert {"free_chlorine", "free_chlorine_mv"} <= device.features


def test_home_water_filling_active() -> None:
    """byte[29] bit 0x02: water filling active for HOME devices."""
    data = _make_home_bytes()

    # bit 0x02 set: filling active
    data[29] = 0x4A  # confirmed transition in DomSchCoding #100 (0x48 → 0x4a)
    device = decode(bytes(data))
    assert device.refilling is True

    # bit 0x02 clear: filling inactive
    data[29] = 0x48
    device = decode(bytes(data))
    assert device.refilling is False


def test_home_water_level_thresholds() -> None:
    """Bytes [102..105] decode to the four water level thresholds for HOME devices.

    Values taken from the issue #110 frame:
      byte[102] = 0x09 = 9 cm  (low alarm)
      byte[103] = 0x0b = 11 cm (filling ON)
      byte[104] = 0x0d = 13 cm (filling OFF)
      byte[105] = 0x0f = 15 cm (high alarm)
    """
    data = _make_home_bytes()
    data[102] = 0x09
    data[103] = 0x0B
    data[104] = 0x0D
    data[105] = 0x0F

    device = decode(bytes(data))
    assert device.water_level_low_alarm == 9
    assert device.water_level_refill_start == 11
    assert device.water_level_refill_stop == 13
    assert device.water_level_high_alarm == 15


def test_home_water_level_threshold_unspecified() -> None:
    """0xFF threshold values → None (e.g. feature not configured)."""
    data = _make_home_bytes()
    data[102] = 0xFF
    data[103] = 0xFF
    data[104] = 0xFF
    data[105] = 0xFF

    device = decode(bytes(data))
    assert device.water_level_low_alarm is None
    assert device.water_level_refill_start is None
    assert device.water_level_refill_stop is None
    assert device.water_level_high_alarm is None


def test_water_level_not_decoded_for_net() -> None:
    """NET devices must have all water level fields as None (bytes [102..104] are unrelated data on NET)."""
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    # Set bytes that would produce values if wrongly decoded
    data[27] = 0x0E
    data[102] = 0x09
    data[103] = 0x0B
    data[104] = 0x0D
    data[105] = 0x0F

    device = decode(bytes(data))
    assert device.water_level is None
    assert device.water_level_low_alarm is None
    assert device.water_level_refill_start is None
    assert device.water_level_refill_stop is None
    assert device.water_level_high_alarm is None
    assert device.refilling is None


def test_water_level_decoded_for_oxy_and_salt() -> None:
    """OXY and SALT devices decode water level fields just like HOME."""
    for device_byte in (0x05, 0x0E):  # OXY, SALT
        data = _make_base_bytes()
        data[4] = device_byte
        data[27] = 0x0E  # 14 cm
        data[29] = data[29] | 0x02  # water filling active
        data[102] = 0x09  # low alarm 9 cm
        data[103] = 0x0B  # filling ON 11 cm
        data[104] = 0x0D  # filling OFF 13 cm
        data[105] = 0x0F  # high alarm 15 cm

        device = decode(bytes(data))
        assert device.water_level == 14, f"byte[4]={device_byte:#x}"
        assert device.refilling is True, f"byte[4]={device_byte:#x}"
        assert device.water_level_low_alarm == 9, f"byte[4]={device_byte:#x}"
        # OXY sends its algicide flow rate in byte[103]: refill start not located
        expected_start = None if device_byte == 0x05 else 11
        assert device.water_level_refill_start == expected_start, (
            f"byte[4]={device_byte:#x}"
        )
        assert device.water_level_refill_stop == 13, f"byte[4]={device_byte:#x}"
        assert device.water_level_high_alarm == 15, f"byte[4]={device_byte:#x}"


def test_filtration_schedule_nonstop_decoded_for_all_device_types() -> None:
    """Nonstop decodes the same on every device type that has filtration.

    byte[37] = 0x01 (firmware B "nonstop 24h") → NONSTOP_24H on SALT, OXY,
    PROFI and HOME alike.  NET has no filtration output (Issue #66) and is
    the only type left as None.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    data[37] = 0xFF
    assert decode(bytes(data)).filtration_schedule is None

    for device_byte in (0x0E, 0x05, 0x10, 0x03):  # SALT, OXY, PROFI, HOME
        data = _make_base_bytes()
        data[4] = device_byte
        data[37] = 0x01  # firmware B: nonstop 24h
        device = decode(bytes(data))
        assert device.filtration_schedule == AsekoFiltrationSchedule.NONSTOP_24H, (
            f"byte[4]={device_byte:#x}"
        )
        assert device.filtration_schedule == AsekoFiltrationSchedule.NONSTOP_24H, (
            f"byte[4]={device_byte:#x}"
        )


def test_alarms_decoded_for_all_device_types() -> None:
    """Alarm byte [13] bitmask is decoded for NET, OXY and SALT, not only HOME.

    Confirmed by NET frame serial 0x06918724: byte[13]=0x04 = active no-flow alarm.
    """
    for device_byte in (0x09, 0x05, 0x0E):  # NET, OXY, SALT
        data = _make_base_bytes()
        data[4] = device_byte
        data[13] = 0x04  # no-flow alarm only

        device = decode(bytes(data))
        assert device.alarm_no_flow_to_probes is True, f"byte[4]={device_byte:#x}"
        assert device.alarm_ph_dosing_ineffective is False, f"byte[4]={device_byte:#x}"
        assert device.alarm_max_disinfection_dose is False, f"byte[4]={device_byte:#x}"
        assert device.alarm_rapid_ph_change is False, f"byte[4]={device_byte:#x}"


# ── Issue #133: HOME v7 firmware B (4-state enum + manual OFF override) ──────


def test_filtration_schedule_new_encoding_24h() -> None:
    """Firmware B byte[37] = 0x01 → NONSTOP_24H (serial 110169464)."""
    data = _make_home_bytes()
    data[37] = 0x01  # new encoding: nonstop 24h
    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.NONSTOP_24H


def test_filtration_schedule_new_encoding_p1() -> None:
    """Firmware B byte[37] = 0x11 → TIMER_PERIOD_1 (P1 only, P2 disabled)."""
    data = _make_home_bytes()
    data[37] = 0x11  # new encoding: P1 only
    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1


def test_filtration_schedule_new_encoding_p1_and_p2() -> None:
    """Firmware B byte[37] = 0x31 → TIMER_PERIOD_1_AND_2 (both periods)."""
    data = _make_home_bytes()
    data[37] = 0x31  # new encoding: P1 & P2
    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2


def test_service_menu_new_encoding_p1_and_p2() -> None:
    """Firmware B byte[37] = 0x35 → MANUAL (P1 & P2 + manual override).

    The original frame from @dtpugh (serial 110169464) had 0x35: both
    periods enabled and the user switched to manual operation mode.
    """
    data = _make_home_bytes()
    data[37] = 0x35  # new encoding: P1 & P2 + manual override (bit 2 set)
    device = decode(bytes(data))
    assert device.service_menu_open is True


def test_service_menu_new_encoding_p1_only() -> None:
    """Firmware B byte[37] = 0x15 → MANUAL (P1 only + manual override).

    Diagnostic 42 from @dtpugh (serial 110175608): user switched to manual
    operation mode while only Period 1 was active. byte[37] = 0x15
    (bits 0,2,4 set). Bit 2 (0x04) = manual override → must decode as MANUAL.
    """
    data = _make_home_bytes()
    data[37] = 0x15  # P1 + manual override
    device = decode(bytes(data))
    assert device.service_menu_open is True


def test_filtration_schedule_old_encoding_24h() -> None:
    """Firmware A byte[37] = 0x43 → NONSTOP_24H (serial 110128063)."""
    data = _make_home_bytes()
    data[37] = 0x43
    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.NONSTOP_24H


def test_filtration_schedule_old_encoding_timer() -> None:
    """byte[37] = 0x53 is period 1 with the Waterlevel setting (0x40) on."""
    data = _make_home_bytes()
    data[37] = 0x53
    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1
    assert device.water_level_sensor_enabled is True


def test_filtration_schedule_with_the_menu_open_is_read_from_the_bits() -> None:
    """0x47 / 0x57: the old "transitional" values are the menu bit 0x04."""
    for byte37, schedule in (
        (0x47, AsekoFiltrationSchedule.NONSTOP_24H),
        (0x57, AsekoFiltrationSchedule.TIMER_PERIOD_1),
    ):
        data = _make_home_bytes()
        data[37] = byte37
        device = decode(bytes(data))
        assert device.filtration_schedule is schedule
        assert device.service_menu_open is True


def test_filtration_schedule_unspecified() -> None:
    """byte[37] = 0xFF → None (defensive, also covers NET-like values on HOME)."""
    data = _make_home_bytes()
    data[37] = 0xFF
    device = decode(bytes(data))
    assert device.filtration_schedule is None


def test_filtration_schedule_none_for_net() -> None:
    """filtration_schedule stays None for NET — no filtration output (Issue #66).

    NET is the only AsekoDeviceType excluded from FILTRATION_TYPES, so the
    decoder returns without setting filtration_schedule. SALT, HOME, OXY and
    PROFI all populate the field.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET CLF
    data[37] = 0xFF  # NET byte 37 is always unspecified
    device = decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.filtration_schedule is None


def test_filtration_schedule_byte37_flags_for_salt_oxy_profi() -> None:
    """SALT / OXY / PROFI decode the byte[37] mode flag exactly like HOME.

    byte[37] = 0x31 (firmware B: P1 & P2) → TIMER_PERIOD_1_AND_2 for every
    non-NET device type — the flag is not HOME-specific.
    """
    for device_byte in (0x0E, 0x05, 0x10):  # SALT, OXY, PROFI
        data = _make_base_bytes()
        data[4] = device_byte
        data[37] = 0x31  # firmware B: P1 & P2
        device = decode(bytes(data))
        assert (
            device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2
        ), f"byte[4]={device_byte:#x}"


def test_filtration_schedule_salt_p1_only_when_period2_disabled() -> None:
    """SALT with byte[37] bit 0x20 clear (period-2 disabled) → TIMER_PERIOD_1.

    Mirrors test_decode_filtration_period2_disabled but checks the new
    `filtration_schedule` enum (not the legacy boolean).
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[60:64] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 2 schedule
    data[37] = 0x93  # bit 0x20 clear, period 2 disabled

    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1


def test_filtration_schedule_salt_byte37_nonstop() -> None:
    """SALT decodes NONSTOP_24H from byte[37] = 0x01 even with no schedule.

    The mode now comes from the byte[37] flag, not from the schedule bytes
    56-63 (which are 0xFF here and no longer drive the mode).
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[56:60] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 1
    data[60:64] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 2
    data[37] = 0x01  # firmware B: nonstop 24h

    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.NONSTOP_24H


def test_filtration_pump_running_off_when_manual_override() -> None:
    """byte[29] bit 3 stays set in MANUAL mode, but pump must read as False.

    The @dtpugh issue: with the user manually switched the pump off, byte[29]
    bit 3 (filtration relay) is still 0x08 in the frame. The decoder trusts
    the explicit MANUAL flag in byte[37] and forces False.

    Tests both known MANUAL byte[37] values:
      - 0x35 = P1 & P2 + manual override (original firmware B frame)
      - 0x15 = P1 only + manual override (new diagnostic 42, serial 110175608)
    """
    for override_value in (0x35, 0x15):
        data = _make_home_bytes()
        data[4] = 0x03  # HOME REDOX (firmware B device)
        data[29] = (
            0x08  # schedule-driven output bit SET (would normally mean "running")
        )
        data[37] = override_value  # OFF (manual override)

        device = decode(bytes(data))
        assert device.service_menu_open is True, f"byte[37]={override_value:#x}"
        assert device.filtration_running is False, f"byte[37]={override_value:#x}"


def test_filtration_pump_running_on_when_not_override() -> None:
    """Regression guard: outside MANUAL, byte[29] bit 3 still drives the entity."""
    data = _make_home_bytes()
    data[4] = 0x03
    data[29] = 0x08
    data[37] = 0x11  # P1 only — pump should be on per the schedule

    device = decode(bytes(data))
    assert device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1
    assert device.filtration_running is True


def test_filtration_pump_running_not_overridden_on_salt() -> None:
    """Decode MANUAL on SALT from byte[37]=0x35 with the pump override HOME-gated.

    The filtration_running short-circuit in _fill_consumable_data only
    applies to HOME, so on SALT byte[29] bit 3 still drives the entity even
    though the mode reads MANUAL.
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[29] = 0x08
    data[37] = 0x35  # firmware B: P1 & P2 + manual override → MANUAL

    device = decode(bytes(data))
    assert device.service_menu_open is True
    assert device.filtration_running is True  # unchanged: byte[29] bit 3 wins


def test_filtration_pump_running_off_when_pump_actually_off() -> None:
    """byte[29] = 0x00 (no pump running) + MANUAL → still False (no-op)."""
    data = _make_home_bytes()
    data[4] = 0x03
    data[29] = 0x00
    data[37] = 0x35

    device = decode(bytes(data))
    assert device.filtration_running is False


def test_home_alarm_bitmask_byte13() -> None:
    """byte[13] alarm bitmask is decoded for all device types; tested here on HOME.

    Bit mapping (Issue #151, serial 110175608): 0x01 = disinfection/Cl dose fault,
    0x02 = pH dose fault, 0x04 = no flow, 0x08 = rapid pH change.
    """
    data = _make_home_bytes()

    # All four bits set
    data[13] = 0x0F
    device = decode(bytes(data))
    assert device.alarm_ph_dosing_ineffective is True  # bit 0x02
    assert device.alarm_max_disinfection_dose is True  # bit 0x01
    assert device.alarm_no_flow_to_probes is True  # bit 0x04
    assert device.alarm_rapid_ph_change is True  # bit 0x08

    # No alarm
    data[13] = 0x00
    device = decode(bytes(data))
    assert device.alarm_ph_dosing_ineffective is False
    assert device.alarm_max_disinfection_dose is False
    assert device.alarm_no_flow_to_probes is False
    assert device.alarm_rapid_ph_change is False

    # Only no-flow bit (0x04) — as seen in NET frame (serial 06918724)
    data[13] = 0x04
    device = decode(bytes(data))
    assert device.alarm_no_flow_to_probes is True
    assert device.alarm_ph_dosing_ineffective is False
    assert device.alarm_max_disinfection_dose is False
    assert device.alarm_rapid_ph_change is False


def test_home_alarm_byte13_bit01_is_disinfection() -> None:
    """byte[13] bit 0x01 = disinfection/Cl dose fault → alarm_max_disinfection_dose.

    Issue #151 regression: dtpugh's config48 frame (HOME serial 110175608) shows
    byte[13]=0x01 while the controller displayed "Maximum disinfection dose
    exceeded".  Pre-fix this bit was mapped to alarm_ph_dosing_ineffective, so the
    chlorine fault falsely lit the "Too many doses of pH" sensor.
    """
    data = _make_home_bytes()
    data[13] = 0x01

    device = decode(bytes(data))
    assert device.alarm_max_disinfection_dose is True
    assert device.alarm_ph_dosing_ineffective is False
    assert device.alarm_no_flow_to_probes is False
    assert device.alarm_rapid_ph_change is False


def test_home_alarm_byte13_bit02_is_ph() -> None:
    """byte[13] bit 0x02 = pH dose fault → alarm_ph_dosing_ineffective.

    Inferred mapping (symmetric to bit 0x01, per dtpugh's expectation in
    Issue #151 that a pH fault would read 0x02).  Direct frame capture pending.
    """
    data = _make_home_bytes()
    data[13] = 0x02

    device = decode(bytes(data))
    assert device.alarm_ph_dosing_ineffective is True
    assert device.alarm_max_disinfection_dose is False
    assert device.alarm_no_flow_to_probes is False
    assert device.alarm_rapid_ph_change is False


def test_home_alarm_byte12_dosing_warnings() -> None:
    """byte[12] dosing-warning bitmask: 0x20 = disinfection, 0x40 = pH (HOME).

    Confirmed by Issue #134 before/after captures (serial 110175608):
    both → 0x60, pH only → 0x40, cleared → 0x00.
    """
    data = _make_home_bytes()

    # Disinfection only
    data[12] = 0x20
    device = decode(bytes(data))
    assert device.alarm_max_disinfection_dose is True
    assert device.alarm_ph_dosing_ineffective is False

    # pH only
    data[12] = 0x40
    device = decode(bytes(data))
    assert device.alarm_ph_dosing_ineffective is True
    assert device.alarm_max_disinfection_dose is False

    # Both
    data[12] = 0x60
    device = decode(bytes(data))
    assert device.alarm_ph_dosing_ineffective is True
    assert device.alarm_max_disinfection_dose is True

    # None
    data[12] = 0x00
    data[13] = 0x00
    device = decode(bytes(data))
    assert device.alarm_ph_dosing_ineffective is False
    assert device.alarm_max_disinfection_dose is False


def test_decode_alarm_real_dtpugh_frames() -> None:
    """Decode the three real diagnostic frames of Issue #151 end to end.

    Frames from @dtpugh (HOME serial 110175608); the right alarm sensors must fire.

      config48 (chlorine/disinfection overdose): byte[13]=0x01 → disinfection ON,
        pH OFF.  config49 (pH fault only): byte[12]=0x40 → pH ON, disinfection OFF.
      config50 (cleared): both OFF.
    """
    frames = {
        # chlorine / disinfection dose exceeded (2026-08-06 17:29:15)
        "48": (
            "0691257803011a0806111d0f000102d202d802d802d8a3fe70012ffeaa48001d000000000005027b"
            "0691257803031a0806111d0f4a5000200800100a100f16000298012f00080515025a01e00e10a2ff"
            "0691257803021a0806111d0f008c003c003c003c000a1e3c6e9600f00502580f050f1e1effc20283",
            (False, True),
        ),
        # pH fault only (2026-08-08 09:08:40)
        "49": (
            "0691257803011a0808090828400002e3031003100310a3fe70012dfeaa08000000000000000102bd"
            "0691257803031a08080908284a4a00200800100a100f16000297012d00080515025a01e00e10a2cc"
            "0691257803021a0808090828008c003c003c003c000a1e3c6e9600f00a02580f050f1e1effc202a8",
            (True, False),
        ),
        # cleared (2026-08-08 09:22:20)
        "50": (
            "0691257803011a0808091614000002e1031003100310a3fe70012dfeaa08000000000000000102dd"
            "0691257803031a08080916144a4a00200800100a100f16000295012d00080515025a01e00e10a2ec"
            "0691257803021a0808091614008c003c003c003c000a1e3c6e9600f00a02580f050f1e1effc2028a",
            (False, False),
        ),
    }

    for name, (hex_dump, (exp_ph, exp_orp)) in frames.items():
        device = decode(bytes.fromhex(hex_dump))
        assert device.device_type == AsekoDeviceType.HOME, f"config{name}"
        assert device.alarm_ph_dosing_ineffective is exp_ph, (
            f"config{name}: alarm_ph_dosing_ineffective expected {exp_ph}"
        )
        assert device.alarm_max_disinfection_dose is exp_orp, (
            f"config{name}: alarm_max_disinfection_dose expected {exp_orp}"
        )


def test_home_byte12_not_an_alarm_byte() -> None:
    """byte[12] = 0x04 must NOT set any alarm field (it is NOT an error byte).

    Confirmed by user's NET frame (serial 0x06918724): byte[12]=0x00 while
    byte[13]=0x04 (active no-flow error) and byte[28]=0x00.
    """
    data = _make_home_bytes()
    data[12] = 0x04  # would have set alarm_rapid_ph_change in old design
    data[13] = 0x00  # all alarms off

    device = decode(bytes(data))
    assert device.alarm_rapid_ph_change is False
    assert device.alarm_ph_dosing_ineffective is False
    assert device.alarm_max_disinfection_dose is False
    assert device.alarm_no_flow_to_probes is False


def test_home_max_filling_time() -> None:
    """max_refill_time is transmitted at bytes 76-77.

    Verified on an ASIN AQUA Salt (v7) by changing the setting in the Aseko
    Live app: 0x0708 = 1800 s showed as 30 min, 0x0B04 = 2820 s as 47 min.

    Bytes 94-95 were the earlier guess. Byte 95 is ph_minus_flow_rate, and the
    mistake survived because one unit ran a 60 ml/min pH- pump next to a 60 min
    filling limit (Issue #110).
    """
    data = _make_home_bytes()
    data[76:78] = (3600).to_bytes(2, "big")

    device = decode(bytes(data))
    assert device.max_refill_time == 3600  # returned as transmitted


# ── Backwash relay state (Issue #100) ────────────────────────────────────────


def test_backwash_active_decoded_for_home() -> None:
    """HOME devices: byte[29] bit 0x01 → backwash_running.

    Mapping from JS-DE-Tech relay_byte bit 0 ('backwash relay').
    """
    data = _make_home_bytes()

    # Backwash relay on (bit 0x01 set, plus filtration bit 0x08 for realism)
    data[29] = 0x09
    device = decode(bytes(data))
    assert device.backwash_running is True

    # Backwash relay off
    data[29] = 0x08  # filtration only
    device = decode(bytes(data))
    assert device.backwash_running is False


def test_backwash_active_decoded_for_salt() -> None:
    """SALT devices: byte[29] bit 0x01 → backwash_running (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT

    data[29] = 0x09  # bit 0 set
    device = decode(bytes(data))
    assert device.backwash_running is True

    data[29] = 0x08
    device = decode(bytes(data))
    assert device.backwash_running is False


def test_backwash_active_decoded_for_oxy() -> None:
    """OXY devices: byte[29] bit 0x01 → backwash_running (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x05  # OXY

    data[29] = 0x09
    device = decode(bytes(data))
    assert device.backwash_running is True

    data[29] = 0x08
    device = decode(bytes(data))
    assert device.backwash_running is False


def test_backwash_active_none_for_net() -> None:
    """NET devices: no backwash valve → backwash_running stays None.

    The binary sensor is therefore not registered for NET devices.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET

    data[29] = 0x09  # bit 0 set
    device = decode(bytes(data))
    assert device.backwash_running is None


def test_backwash_active_independent_of_water_filling() -> None:
    """byte[29] bit 0x01 (backwash) is independent of bit 0x02 (water filling)."""
    data = _make_home_bytes()

    # Both backwash and water filling on
    data[29] = 0x0B  # 0x08 | 0x02 | 0x01
    device = decode(bytes(data))
    assert device.backwash_running is True
    assert device.refilling is True

    # Only backwash on (water filling off)
    data[29] = 0x09  # 0x08 | 0x01
    device = decode(bytes(data))
    assert device.backwash_running is True
    assert device.refilling is False

    # Only water filling on (backwash off)
    data[29] = 0x0A  # 0x08 | 0x02
    device = decode(bytes(data))
    assert device.backwash_running is False
    assert device.refilling is True


# ── Heating demand relay (Issue #115, JS-DE-Tech relay_byte bit 2) ──────────


def test_heating_active_decoded_for_home() -> None:
    """HOME devices: byte[29] bit 0x04 → heating_running."""
    data = _make_home_bytes()

    # Heating demand on (bit 0x04 set, plus filtration bit 0x08 for realism)
    data[29] = 0x0C
    device = decode(bytes(data))
    assert device.heating_running is True

    # Heating demand off
    data[29] = 0x08  # filtration only
    device = decode(bytes(data))
    assert device.heating_running is False


def test_heating_active_decoded_for_salt() -> None:
    """SALT devices: byte[29] bit 0x04 → heating_running (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT

    data[29] = 0x0C
    device = decode(bytes(data))
    assert device.heating_running is True

    data[29] = 0x08
    device = decode(bytes(data))
    assert device.heating_running is False


def test_heating_active_decoded_for_oxy() -> None:
    """OXY devices: byte[29] bit 0x04 → heating_running (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x05  # OXY

    data[29] = 0x0C
    device = decode(bytes(data))
    assert device.heating_running is True

    data[29] = 0x08
    device = decode(bytes(data))
    assert device.heating_running is False


def test_heating_active_none_for_net() -> None:
    """NET devices: no heating output → heating_running stays None.

    The binary sensor is therefore not registered for NET devices.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET

    data[29] = 0x0C  # bit 2 set
    device = decode(bytes(data))
    assert device.heating_running is None


def test_heating_active_independent_of_backwash_and_filling() -> None:
    """byte[29] bit 0x04 is independent of bits 0x01 and 0x02."""
    data = _make_home_bytes()

    # All three relays on
    data[29] = 0x0F  # 0x08 | 0x04 | 0x02 | 0x01
    device = decode(bytes(data))
    assert device.heating_running is True
    assert device.refilling is True
    assert device.backwash_running is True

    # Only heating on
    data[29] = 0x0C  # 0x08 | 0x04
    device = decode(bytes(data))
    assert device.heating_running is True
    assert device.refilling is False
    assert device.backwash_running is False

    # Only backwash on
    data[29] = 0x09  # 0x08 | 0x01
    device = decode(bytes(data))
    assert device.heating_running is False
    assert device.backwash_running is True


def test_home_issue_110_frame() -> None:
    """Full integration test using the real issue #110 frame.

    Frame from serial 0x068f8f26 (= 110071590), ASIN AQUA Home CLF.
    Water level 14 cm confirmed by the issue reporter (mannekung).
    Segments 1 and 3 taken directly from plan section 2.
    Segment 2 is a placeholder (schedule fields not relevant here).
    """
    data = bytes.fromhex(
        # Segment 1 (real-time, byte[5]=0x01) — confirmed from issue #110
        "068f8f2602011a0517170900000002f5006600660058"
        "88fdc400a10eaa08000000000000005302dd"
        # Segment 2 (config1, byte[5]=0x03) — placeholder
        "068f8f2602031a051717090000"
        "000000000000000000000000000000000000000000000000000000"
        # Segment 3 (config2, byte[5]=0x02) — confirmed from issue #110
        "068f8f2602021a051717090000"
        "14003c003c003c000a090b0d0f00f03c02580f0a0f1e1eff81015d"
    )
    assert len(data) == 120, f"Frame length = {len(data)}, expected 120"

    device = decode(data)

    assert device.device_type == AsekoDeviceType.HOME
    assert device.water_level == 14  # byte[27] = 0x0e confirmed
    assert device.water_flow_to_probes is True  # byte[28] = 0xAA
    assert device.refilling is False  # byte[29] = 0x08, bit 0x02 not set
    assert (
        device.filtration_schedule == AsekoFiltrationSchedule.TIMER_PERIOD_1
    )  # byte[37] = 0x53
    assert device.water_level_sensor_enabled is True  # byte[37] 0x40
    assert device.water_level_low_alarm == 9  # byte[102]
    assert device.water_level_refill_start == 11  # byte[103]
    assert device.water_level_refill_stop == 13  # byte[104]
    assert device.water_level_high_alarm == 15  # byte[105]
    assert device.pool_volume == 20  # bytes[92:94] = 0x0014
    # max_refill_time is not asserted against 60 here: segment 2 of this frame
    # is a zero placeholder (issue #110 only ever included segments 1 and 3),
    # so bytes 76-77 carry no real value.  The old "60 min" came from bytes
    # 94-95 — that is ph_minus_flow_rate, and the unit happened to run a
    # 60 ml/min pH- pump alongside a 60 min filling limit.
    assert device.max_refill_time == 0  # 0x0000 from the placeholder segment
    assert device.ph_minus_flow_rate == 60  # bytes 94-95 = 0x003c


# --- Air temperature (bytes 23-24) --------------------------------------
#
# Two diagnostics dumps from the same unit — an ASIN AQUA Salt
# (type byte 0x0d).  Both were checked against the values shown on the device:
#
#   2026-08-11 10:33 → 0x0168 = 36.0 °C air | 0x0128 = 29.6 °C water
#   2026-08-17 18:50 → 0x0134 = 30.8 °C air | 0x0122 = 29.0 °C water
#
# Air and water move independently between the two captures, and each raw air
# value occurs exactly once in its frame, so the offset is unambiguous.

_SALT_AIR_TEMP_2026_08_11_HEX = (
    "06916f9e0d011a080b0a2100000002b1004d003b1b16180168012822aa1804380000000000d3203d"
    "06916f9e0d031a080b0a210046090319090013001200160002d201280e0b2a09ff1401e00e10f282"
    "06916f9e0d021a080b0a21000032003c3401ddff003c1f21232800f00a0bb80f0e011328fffc0191"
)

_SALT_AIR_TEMP_2026_08_17_HEX = (
    "06916f9e0d011a0811123200000002bc005d00461a00180134012222aa4800000000000000d32061"
    "06916f9e0d031a081112320046090319090013001200160002dd01220e0b2a09ff1401e00e10e286"
    "06916f9e0d021a08111232000032003c2001f0ff003c1f21232800f00a0bb80f0e015728fffc01fd"
)


def test_decode_air_temperature_salt_real_frames() -> None:
    """Air temperature (bytes 23-24) on the two confirmed SALT frames."""

    device = decode(bytes.fromhex(_SALT_AIR_TEMP_2026_08_11_HEX))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.serial_number == 110_194_590
    assert device.timestamp is not None
    assert device.timestamp.replace(tzinfo=None) == datetime(2026, 8, 11, 10, 33, 0)
    assert device.air_temperature == pytest.approx(36.0)
    assert device.water_temperature == pytest.approx(29.6)

    device = decode(bytes.fromhex(_SALT_AIR_TEMP_2026_08_17_HEX))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.timestamp is not None
    assert device.timestamp.replace(tzinfo=None) == datetime(2026, 8, 17, 18, 50, 0)
    assert device.air_temperature == pytest.approx(30.8)
    assert device.water_temperature == pytest.approx(29.0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0x0168, 36.0),  # confirmed capture
        (0x0134, 30.8),  # confirmed capture
        (0x0000, 0.0),  # exactly 0 °C is a valid reading, not "missing"
        (0xFFE2, -3.0),  # two's complement, sub-zero (encoding still unverified)
        (0xFED4, -30.0),  # lower bound, inclusive
        (0x0258, 60.0),  # upper bound, inclusive
        (0xFED3, None),  # just below the lower bound
        (0x0259, None),  # just above the upper bound
        (0xFE70, None),  # -40.0 °C — open-circuit sentinel seen on real units
        (0xFDC4, None),  # -57.2 °C — same, second sentinel value
        (0x0C3C, None),  # 313.2 °C — unrelated data, seen on NET frames
        (0xFFFF, None),  # protocol-wide "unspecified" marker, not -0.1 °C
    ],
)
def test_air_temperature_plausibility_window(raw: int, expected: float | None) -> None:
    """Only plausible ambient values are reported; sentinels decode to None."""

    data = _make_base_bytes()
    data[4] = 0x0D  # SALT with CLF probe
    data[23:25] = raw.to_bytes(2, "big")

    device = decode(bytes(data))

    if expected is None:
        assert device.air_temperature is None
    else:
        assert device.air_temperature == pytest.approx(expected)


@pytest.mark.parametrize(
    "unit_type",
    [
        0x02,  # HOME CLF
        0x03,  # HOME REDOX
        0x05,  # OXY
    ],
)
def test_air_temperature_on_models_with_an_air_input(unit_type: int) -> None:
    """Bytes 23-24 are the air temperature wherever the unit has an air input.

    The manuals list an optional outdoor air thermometer for HOME and Oxygen
    units as for SALT.  Without a probe the unit sends the open-circuit marker
    0xFE70 (every captured HOME and OXY frame), which reads as absent, so
    no entity is created until a probe is fitted.
    """

    data = _make_base_bytes()
    data[4] = unit_type
    data[23:25] = (0x0168).to_bytes(2, "big")  # 36.0 °C
    device = decode(bytes(data))
    assert device.air_temperature == 36.0

    data[23:25] = (0xFE70).to_bytes(2, "big")  # no air probe
    device = decode(bytes(data))
    assert device.air_temperature is None
    assert "air_temperature" not in device.features


@pytest.mark.parametrize("unit_type", [0x09, UNIT_TYPE_PROFI])  # NET CLF, PROFI
def test_air_temperature_not_read_without_an_air_input(unit_type: int) -> None:
    """NET and PROFI have no air thermometer input (their manuals' terminal lists)."""

    data = _make_base_bytes()
    data[4] = unit_type
    data[23:25] = (0x0168).to_bytes(2, "big")  # 36.0 °C if it were decoded
    device = decode(bytes(data))
    assert device.air_temperature is None


# ── byte[37] firmware-A fallback is HOME-only ────────────────────────────────


@pytest.mark.parametrize(
    ("byte37", "expected_menu", "expected_schedule"),
    [
        (0xC3, False, AsekoFiltrationSchedule.NONSTOP_24H),
        (0xD3, False, AsekoFiltrationSchedule.TIMER_PERIOD_1),
        (
            0xF3,
            False,
            AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2,
        ),
        (0xC7, True, AsekoFiltrationSchedule.NONSTOP_24H),
        (
            0xD7,
            True,
            AsekoFiltrationSchedule.TIMER_PERIOD_1,
        ),
        (
            0xF7,
            True,
            AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2,
        ),
    ],
)
def test_filtration_schedule_salt_uses_the_firmware_b_bits(
    byte37: int,
    expected_menu: bool,
    expected_schedule: AsekoFiltrationSchedule,
) -> None:
    """SALT carries the mode in the same bits as HOME firmware B.

    Every value here was captured on an ASIN AQUA Salt while the mode shown
    on the unit itself was known, in both directions of each transition.
    The high nibble is SALT's own configuration (0x80 = algicide routing)
    and bit 0x40 is set in every frame — which is why routing on that bit
    sent SALT into the HOME firmware-A branch, where it matched none of the
    exact values and came out with no mode at all.

    Note 0xF7 is MANUAL, not two filtration periods: bit 0x04 is set, and
    whatever was configured stays underneath it.  The same goes for 0xC7,
    which is manual mode entered from nonstop — hence the second column:
    the schedule is reported alongside the mode, not replaced by it.
    """
    data = _make_base_bytes()  # SALT
    data[37] = byte37
    assert data[56] != 0xFF  # period 1 configured
    assert data[60] != 0xFF  # period 2 configured

    device = decode(bytes(data))

    assert device.device_type == AsekoDeviceType.SALT
    assert device.service_menu_open is expected_menu
    assert device.filtration_schedule == expected_schedule


def test_filtration_schedule_salt_unknown_bits_stay_unknown() -> None:
    """An unrecognised SALT value yields no mode rather than a guess.

    The schedule-derived fallback is HOME-only: SALT reports the filtration
    times unchanged in every mode, so deriving the mode from them there
    could only ever return one constant answer regardless of the truth.
    0xE3 has period 2 set without period 1, which the unit never sends.
    """
    data = _make_base_bytes()  # SALT
    data[37] = 0xE3
    assert data[56] != 0xFF  # a schedule is present to fall back on

    device = decode(bytes(data))

    assert device.device_type == AsekoDeviceType.SALT
    assert device.filtration_schedule is None
    assert device.filtration_schedule is None


def test_filtration_schedule_survives_the_service_menu() -> None:
    """Opening the settings menu does not disturb the schedule.

    Opening it and leaving again is the same schedule throughout —
    0xC3 -> 0xC7 -> 0xC3 on a captured SALT — so filtration_schedule reads
    the same in all three while service_menu_open flips.

    This is what makes the schedule usable on a dashboard while the override
    is on: it can be shown greyed out rather than disappearing.
    """
    data = _make_base_bytes()  # SALT

    schedules = []
    menus = []
    for byte37 in (0xC3, 0xC7, 0xC3):
        data[37] = byte37
        device = decode(bytes(data))
        schedules.append(device.filtration_schedule)
        menus.append(device.service_menu_open)

    assert schedules == [AsekoFiltrationSchedule.NONSTOP_24H] * 3
    assert menus == [False, True, False]


def test_unfilled_setpoints_read_unknown_not_scaled_0xff() -> None:
    """R2: 0xFF in a setpoint byte is 'not filled in', never 25.5 pH or 2550 mV."""
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT, REDOX probe
    data[52] = 0xFF
    data[53] = 0xFF
    device = decode(bytes(data))
    assert device.ph_target is None
    assert device.redox_target is None
    assert "ph_target" in device.features  # the probe is there, the entity stays
    assert "redox_target" in device.features

    data[4] = 0x0D  # SALT, CLF probe
    device = decode(bytes(data))
    assert device.free_chlorine_target is None
    assert "free_chlorine_target" in device.features

    data[4] = 0x05  # OXY
    device = decode(bytes(data))
    assert device.oxygen_dose_target is None


# ── frame edges ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("size", [0, 4, 50, 119, 121, 240])
def test_anything_but_a_whole_v7_frame_is_refused(size: int) -> None:
    """A fragment is the server's partial frame, never a frame to decode."""
    with pytest.raises(ValueError, match="not 120"):
        decode((bytes(_make_base_bytes()) * 2)[:size], Protocol.V7)


_UNIT_TYPES = [0x02, 0x03, 0x05, 0x09, 0x0B, 0x0D, 0x0E, 0x10, 0x00]


@pytest.mark.parametrize("unit_type", _UNIT_TYPES)
def test_a_frame_of_unfilled_bytes_decodes_no_number(unit_type: int) -> None:
    """0xFF everywhere: every numeric value reads unknown, none reads 255 or 25.5."""
    raw = bytearray(b"\xff" * 120)
    for start, segment in ((0, 1), (40, 3), (80, 2)):
        raw[start : start + 4] = (1234).to_bytes(4, "big")
        raw[start + 4] = unit_type
        raw[start + 5] = segment

    device = decode(bytes(raw))

    numbers = {
        f.name: getattr(device, f.name)
        for f in fields(AsekoDevice)
        if f.name != "serial_number"
        and isinstance(getattr(device, f.name), int | float)
        and not isinstance(getattr(device, f.name), bool)
    }
    assert numbers == {}, device.profile


@pytest.mark.parametrize(
    ("byte37", "byte38", "expected", "present"),
    [
        (0xD3 | 0x08, 0x10, True, True),  # heating on, linked to filtration
        (0xD3 | 0x08, 0x01, False, True),  # heating on, not linked (0x01 is unrelated)
        (0xD3, 0x00, False, True),  # heating off: the unit sends the bit cleared
        (0xD3, 0x10, True, True),  # read as sent, whatever heating control says
        (0xD3, 0xFF, None, True),  # an odd frame: unknown, still present
    ],
)
def test_heating_linked_to_filtration(byte37, byte38, expected, present) -> None:
    """byte[38] 0x10, confirmed on a SALT 2026-09-14; reported as the unit sends it."""
    data = _make_base_bytes()  # SALT REDOX
    data[37] = byte37
    data[38] = byte38
    device = decode(bytes(data))
    assert device.heating_control_enabled is (byte37 & 0x08 == 0x08)
    assert device.heating_linked_to_filtration is expected
    assert ("heating_linked_to_filtration" in device.present_features) is present
