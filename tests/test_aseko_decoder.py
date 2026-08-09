"""Test the Aseko Decoder."""

from datetime import time, datetime

import pytest

from custom_components.aseko_local.aseko_data import (
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoFiltrationMode,
    AsekoProbeType,
)
from custom_components.aseko_local.aseko_decoder import AsekoDecoder
from custom_components.aseko_local.const import (
    UNIT_TYPE_PROFI,
    WATER_FLOW_TO_PROBES,
    YEAR_OFFSET,
)


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
        0xFF  # UNSPECIFIED (0xFF) → byte[101] not routed; flowrate_algicide and flowrate_floc both None
    )
    data[54] = (
        5  # required dosing rate (byte 54); algicide or floc depending on byte[37]
    )
    data[55] = 28  # required_water_temperature
    data[56] = 8  # start1 hour
    data[57] = 0  # start1 min
    data[58] = 10  # stop1 hour
    data[59] = 0  # stop1 min
    data[60] = 14  # start2 hour
    data[61] = 0  # start2 min
    data[62] = 16  # stop2 hour
    data[63] = 0  # stop2 min
    data[68] = 3  # backwash_every_n_days
    data[69] = 2  # backwash_time hour
    data[70] = 30  # backwash_time min
    data[71] = 2  # backwash_duration (20)
    data[74:76] = (120).to_bytes(2, "big")  # delay_after_startup
    data[92:94] = (5000).to_bytes(2, "big")  # pool_volume
    data[95] = 10  # flowrate_chlor
    data[94:96] = (60).to_bytes(2, "big")  # max_filling_time
    data[97] = 20  # flowrate_ph_plus
    data[99] = 255  # flowrate_ph_minus (not measured)
    data[101] = 40  # flowrate_floc
    data[106:108] = (30).to_bytes(2, "big")  # delay_after_dose
    return data


def test_decode_redox() -> None:
    """Test decoding of Redox probe data."""

    data = _make_base_bytes()
    data[4] = 0x0A  # NET with Redox probe
    data[18:20] = (550).to_bytes(2, "big")  # Redox
    data[53] = 65  # required Redox

    device = AsekoDecoder.decode(bytes(data))
    assert device.required_redox == 650
    assert device.redox == 550


def test_decode_clf() -> None:
    """Test decoding of CL free probe data."""

    data = _make_base_bytes()
    data[4] = 0x09  # NET with CL probe
    data[16:18] = (50).to_bytes(2, "big")  # CL free
    data[53] = 9  # required CL free

    device = AsekoDecoder.decode(bytes(data))
    assert device.required_cl_free == 0.9
    assert device.cl_free == 0.5


def test_flowrates() -> None:
    """Test decoding of flowrate data."""

    data = _make_base_bytes()
    data[37] = 0x00  # flocculant mode → byte[101] routes to flowrate_floc

    device = AsekoDecoder.decode(bytes(data))
    assert device.flowrate_chlor is None
    assert device.flowrate_ph_plus is None
    assert device.flowrate_ph_minus == 60
    assert device.flowrate_floc == 40


def test_decode_home() -> None:
    """Test decoding of HOME device data."""

    data = _make_base_bytes()
    data[4] = 0x03  # HOME with Redox probe
    data[14:16] = (720).to_bytes(2, "big")  # ph
    data[37] = (
        0xB3  # pump presence/config byte (HOME has independent ports, not routed)
    )
    data[52] = 72  # required_ph

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.serial_number == 1234
    assert device.ph == 7.2
    assert device.required_ph == 7.2
    assert device.water_temperature == 24.5
    assert device.filtration_pump_running is True
    assert device.water_flow_to_probes is True
    assert device.pool_volume == 5000
    assert device.max_filling_time == 60  # raw = minutes directly (verified Issue #110)
    assert device.delay_after_startup == 120
    assert device.delay_after_dose == 30
    assert device.start1 == time(8, 0)
    assert device.stop1 == time(10, 0)
    assert device.start2 == time(14, 0)
    assert device.stop2 == time(16, 0)
    assert device.backwash_every_n_days == 3
    assert device.backwash_time == time(2, 30)
    assert device.backwash_duration == 20
    # HOME has 4 independent pump ports — byte[37] routing does not apply.
    # byte[54] = required_floc, byte[72] = required_algicide (same layout as OXY).
    # Base bytes: data[54]=5, data[72]=0 (default zero).
    assert device.required_floc == 5
    assert device.required_algicide == 0
    assert device.required_water_temperature == 28
    assert device.timestamp is not None
    assert device.timestamp.year == YEAR_OFFSET + 24
    assert device.timestamp.month == 6
    assert device.timestamp.day == 15
    assert device.timestamp.hour == 12
    assert device.timestamp.minute == 34
    assert device.timestamp.second == 56


def test_decode_filtration_period2_disabled() -> None:
    """Period 2 times are still populated when disabled, but the mode is P1 only.

    Issue #133: pre-fix, the decoder returned ``None`` for start2/stop2 when
    byte[37] bit 0x20 was clear, which made already-registered entities go
    ``unknown`` once the user switched the controller back to "P1 only"
    (Home Assistant protects the entity registry, so the entity stays).
    Post-fix, the bytes 60-63 are read for any device in FILTRATION_TYPES
    because the controller keeps sending the last-configured Period 2 times
    (verified on dtpugh's serial 110169464: bytes 60-63 stay populated in
    P1 only / P1&P2 / 24h / OFF_MANUAL modes).  The *mode* still flips
    between TIMER_PERIOD_1 and TIMER_PERIOD_1_AND_2 per byte[37] bit 0x20,
    so the user can tell which schedule is active.
    """
    data = _make_base_bytes()
    data[37] = 0x93  # bit 0x20 clear -> period 2 disabled in the controller

    device = AsekoDecoder.decode(bytes(data))

    # Period 1 is still parsed.
    assert device.start1 == time(8, 0)
    assert device.stop1 == time(10, 0)
    # Period 2 times ARE populated (bytes 60-63 are stable) — but the mode
    # entity correctly reports TIMER_PERIOD_1 so the user knows the schedule
    # is not active.
    assert device.start2 == time(14, 0)
    assert device.stop2 == time(16, 0)
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1


def test_decode_filtration_period2_enabled() -> None:
    """Second filtration period is exposed when enabled (byte 37 bit 0x20 set)."""
    data = _make_base_bytes()
    data[37] = 0xB3  # bit 0x20 set -> period 2 enabled

    device = AsekoDecoder.decode(bytes(data))

    assert device.start2 == time(14, 0)
    assert device.stop2 == time(16, 0)
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1_AND_2


def test_decode_filtration_period2_bytes_unspecified() -> None:
    """When bytes 60-63 themselves are 0xFF (no schedule ever configured),
    start2 / stop2 stay None — the lazy-creation guard in sensor.py then
    skips registering the entity.  This is the key branch that keeps
    devices without a filtration output (NET) from ever surfacing
    Period 2 entities (Issue #133 contract).
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT (in FILTRATION_TYPES)
    data[60:64] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 2 schedule at all
    data[37] = 0xB7  # SALT algicide routing — bit 0x20 set, but no schedule

    device = AsekoDecoder.decode(bytes(data))
    assert device.start2 is None
    assert device.stop2 is None


def test_decode_filtration_period2_none_for_net() -> None:
    """NET has no filtration output — start1/2 / stop1/2 are all None
    even if the frame happens to carry non-0xFF values in bytes 56-63.
    Issue #133 contract: lazy creation in sensor.py never registers the
    entities for NET.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    # Garbage values in the schedule bytes (mimic real-world case where a
    # measurement-only device reports random data in slots it doesn't implement).
    data[56:64] = bytes([8, 0, 10, 0, 14, 0, 16, 0])

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.start1 is None
    assert device.stop1 is None
    assert device.start2 is None
    assert device.stop2 is None


def test_decode_filtration_period2_real_dtpugh_frames() -> None:
    """Issue #133 end-to-end: decode all four real diagnostic frames from
    @dtpugh (serial 110169464, ASIN AQUA Home firmware B) and verify
    Period 2 times are stable across all four modes (P1 only / P1&P2 /
    24h / OFF_MANUAL).  This is the user-visible regression: pre-fix the
    entity would go "unknown" when the user toggled the controller back
    from P1&P2 to P1 only.
    """
    import json
    from pathlib import Path

    # Diagnostic files live in /tmp/issue133 (downloaded from the issue);
    # when the test runs in CI without that directory, skip instead of fail.
    diag_dir = Path("/tmp/issue133")
    if not diag_dir.exists():
        pytest.skip("diagnostic files from issue #133 are not available")

    def _first_frame(payload):
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

    scenarios = {
        "01_p1only.json": (0x11, AsekoFiltrationMode.TIMER_PERIOD_1),
        "02_p1andp2.json": (0x31, AsekoFiltrationMode.TIMER_PERIOD_1_AND_2),
        "03_24h.json": (0x01, AsekoFiltrationMode.NONSTOP_24H),
        "04_off.json": (0x35, AsekoFiltrationMode.OFF_MANUAL),
    }

    for filename, (expected_b37, expected_mode) in scenarios.items():
        with open(diag_dir / filename) as f:
            frame = bytes.fromhex(_first_frame(json.load(f)))
        assert frame[37] == expected_b37, f"{filename}: byte 37 mismatch"

        device = AsekoDecoder.decode(frame)
        # Period 1 is always there.
        assert device.start1 is not None, f"{filename}: start1 unexpectedly None"
        assert device.stop1 is not None, f"{filename}: stop1 unexpectedly None"
        # Period 2 is ALSO always there after the fix (entity stays populated).
        assert device.start2 is not None, (
            f"{filename}: start2 is None — entity would go 'unknown' (Issue #133)"
        )
        assert device.stop2 is not None, (
            f"{filename}: stop2 is None — entity would go 'unknown' (Issue #133)"
        )
        # Mode entity correctly reports which schedule is active.
        assert device.filtration_mode == expected_mode, (
            f"{filename}: expected {expected_mode}, got {device.filtration_mode}"
        )


def test_decode_electrolyzer_data() -> None:
    """Test decoding of electrolyzer data with right direction."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT with REDOX probe
    data[20] = 32  # salinity = 3.2
    data[21] = 80  # electrolyzer_power
    data[29] = 0x10  # ELECTROLYZER_RUNNING_RIGHT
    data[16:18] = (50).to_bytes(2, "big")  # cl_free < MAX_CLF_LIMIT
    data[14:16] = (700).to_bytes(2, "big")  # ph
    data[52] = 70

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.salinity == 3.2
    assert device.electrolyzer_power == 80
    assert device.electrolyzer_active is True
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.RIGHT


def test_decode_electrolyzer_data_left_direction() -> None:
    """Test decoding of electrolyzer data with left direction."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT with REDOX probe
    data[20] = 32
    data[21] = 80
    data[29] = 0x50  # ELECTROLYZER_RUNNING_LEFT

    device = AsekoDecoder.decode(bytes(data))
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.LEFT


def test_decode_electrolyzer_data_waiting_direction() -> None:
    """Test decoding of electrolyzer data with waiting direction."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT with REDOX probe
    data[20] = 32
    data[21] = 80
    data[29] = 0  # neither running nor left

    device = AsekoDecoder.decode(bytes(data))
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.WAITING


def test_decode_profi() -> None:
    """Test decoding of PROFI device data."""

    data = _make_base_bytes()
    data[4] = UNIT_TYPE_PROFI  # PROFI with Redox & CLF probe
    data[16:18] = (100).to_bytes(2, "big")
    data[18:20] = (650).to_bytes(2, "big")
    data[14:16] = (800).to_bytes(2, "big")
    data[52] = 80
    data[53] = 20

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.PROFI
    assert device.configuration == {
        AsekoProbeType.PH,
        AsekoProbeType.CLF,
        AsekoProbeType.REDOX,
    }
    assert device.ph == 8.0
    assert device.redox == 650
    assert device.cl_free == 1.0
    assert device.required_ph == 8.0
    assert (
        device.required_redox is None
    )  # PROFI has no required redox instead required_cl_free is existing
    assert device.required_cl_free == 2.0


def test_decode_net() -> None:
    """Test decoding of NET device data."""

    data = _make_base_bytes(111)
    data[4] = 0x09  # NET device
    data[6] = 0xFF  # year
    data[7] = 0xFF  # month
    data[8] = 0xFF  # day
    data[9] = 0xFF  # hour
    data[10] = 0xFF  # minute
    data[11] = 0xFF  # second

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    # NET (Aqua NET) has no filtration output → no schedule is reported (PR #122),
    # even though the frame carries values in the schedule bytes.
    assert device.start1 is None
    assert device.stop1 is None
    assert device.start2 is None
    assert device.stop2 is None
    # Issue #129: NET has no backwash valve, so the schedule must stay None
    # regardless of what the frame carries in bytes 68-71.
    assert device.backwash_every_n_days is None
    assert device.backwash_time is None
    assert device.backwash_duration is None
    assert device.last_backwash is None
    assert device.next_backwash is None
    assert device.backwash_active is None
    # NET has no filling valve, so the water_level group is empty too.
    assert device.water_level is None
    assert device.water_level_low_alarm is None
    assert device.water_level_filling_on is None
    assert device.water_level_filling_off is None
    assert device.water_level_high_alarm is None
    assert device.water_filling_active is None
    assert device.max_filling_time is None
    # Pool volume and dosing delays are still available on NET.
    assert device.pool_volume == 5000
    assert device.delay_after_dose == 30


def test_decode_corrupted_timestamp() -> None:
    """Test decoding data with corrupted timestamp should fallback to server timestamp."""

    data = bytearray.fromhex(
        "0691ffff0d01050e01010101000002d002bfffff02bfff01bc00ffffaa0000080000000000ff0173"
        "0691ffff0d0305ffffffffff484608ffffffffffffffffff02d100ffffffffffffffffffffffff97"
        "0691ffff0d0205ffffffffff0007003cffff003cffff010181ff012c0102581e28ffffffff0048cd"
    )

    device = AsekoDecoder.decode(bytes(data))
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

    device = AsekoDecoder.decode(bytes(data))
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
    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type is None


def test_decode_net_no_backwash_with_garbage_bytes() -> None:
    """Issue #129: A NET frame carrying non-0xFF data in the backwash/water-level
    byte slots must not surface phantom backwash or water-level entities.

    Pre-fix behaviour: the decoder blindly read bytes 68-71, 27, 102-105 and
    94-95 on every device type. When a NET device happened to send non-0xFF
    values in those slots, the integration created disabled backwash /
    water-level entities with semantically meaningless numbers (e.g.
    max_filling_time=65535 from bytes 0xFFFF being decoded as a 16-bit int).

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
    data[68] = 7  # would-be backwash_every_n_days
    data[69] = 9  # would-be backwash_time hour
    data[70] = 30  # would-be backwash_time min
    data[71] = 12  # would-be backwash_duration (×10 s)
    data[102] = 13  # would-be water_level_low_alarm
    data[103] = 21  # would-be water_level_filling_on
    data[104] = 60  # would-be water_level_filling_off
    data[105] = 100  # would-be water_level_high_alarm
    data[94:96] = bytes([0xFF, 0xFF])  # would-be max_filling_time → must be None

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    # None of these may leak through on a NET device, no matter what the frame carries.
    assert device.backwash_every_n_days is None
    assert device.backwash_time is None
    assert device.backwash_duration is None
    assert device.last_backwash is None
    assert device.next_backwash is None
    assert device.backwash_active is None
    assert device.water_level is None
    assert device.water_level_low_alarm is None
    assert device.water_level_filling_on is None
    assert device.water_level_filling_off is None
    assert device.water_level_high_alarm is None
    assert device.water_filling_active is None
    assert device.max_filling_time is None


def test_max_filling_time_unspecified_sentinel() -> None:
    """Issue #129: 0xFFFF in bytes 94-95 must decode to None, not 65535.

    Pre-fix behaviour: a bare ``int.from_bytes(data[94:96], "big")`` returned
    65535 for the 0xFFFF sentinel, surfacing a nonsensical "max filling time
    = 65535 min" sensor on devices that do not implement filling (NET, PROFI).
    """
    data = _make_base_bytes()  # default SALT — has max_filling_time
    data[4] = 0x09  # but flip to NET
    data[94:96] = bytes([0xFF, 0xFF])  # UNSPECIFIED sentinel
    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.max_filling_time is None


def test_max_filling_time_real_value_home() -> None:
    """Sanity check: on a HOME device, a real value still decodes correctly.

    This guards against an accidental regression where the new
    _max_filling_time_from_bytes() helper breaks the verified
    "60 min from 0x003c" mapping (Issue #110).
    """
    data = _make_base_bytes()
    data[4] = 0x02  # UNIT_TYPE_HOME_CLF — any HOME subtype works
    data[6:12] = bytes([24, 6, 15, 12, 34, 56])
    data[94:96] = (60).to_bytes(2, "big")  # 60 min
    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.max_filling_time == 60


def test_decode_issue_17() -> None:
    """Test decoding data from issue #17."""

    data = bytearray.fromhex(
        "0690ffff0d01190519160832000002c6006c0249200000fe7000e0fe00400000000000000033001f"
        "0690ffff0d031905191608324809001b07000b1e0c1e1500030c00e8000c1e0aff2800780e1081bd"
        "0690ffff0d02190519160832003c003c3a1066ff003c1e3c6e9603840a0bb80f0900b505fff401eb"
    )

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT


def test_decode_issue_20() -> None:
    """Test decoding data from issue #20."""

    data = bytearray.fromhex(
        "0691ffff0a01ffffffffffff000002d002bfffff02bfff01bc00ffffaa0000080000000000ff0173"
        "0691ffff0a03ffffffffffff484608ffffffffffffffffff02d100ffffffffffffffffffffffff97"
        "0691ffff0a02ffffffffffff0007003cffff003cffff010181ff012c0102581e28ffffffff0048cd"
    )

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.timestamp is not None
    assert device.cl_free is None
    assert device.cl_free_mv is None
    assert device.redox == 703


def test_decode_issue_22() -> None:
    """Test decoding data from issue #22."""

    data = bytearray.fromhex(
        "0690ffff0901ffffffffffff000002cb003bffff007bff00000121ffaa0000040000000000ff0000"
        "0690ffff0903ffffffffffff480608ffffffffffffffffff02b90129ffffffffffffffffffffff2f"
        "0690ffff0902ffffffffffff0026003cffff003cffff010183ff012c0102581e28ffffffff0047a6"
    )

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.timestamp is not None
    assert device.cl_free == 0.59
    assert device.cl_free_mv == 123
    assert device.redox is None


def test_decode_issue_28() -> None:
    """Test decoding data from issue #28."""

    data = bytearray.fromhex(
        "068fffff0e0119061d113428000002ee019001902300ff006f011c32aa48000000000000004720c5"
        "068fffff0e0319061d1134284c2803200a0014001605160a02d3010c07110006ff2800780e10021b"
        "068fffff0e0219061d1134280012003c330434ff003c2d2f323402580a0bb80f0f0134ffff990197"
    )

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.timestamp is not None
    assert device.cl_free is None
    assert device.redox == 400
    assert device.ph == 7.5
    assert device.salinity == 3.5
    assert device.electrolyzer_power == 0
    assert device.electrolyzer_active is False
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.WAITING
    assert device.water_temperature == 28.4


def test_decode_issue_61() -> None:
    """Test decoding data from issue #61."""

    data = bytearray.fromhex(
        "0690cafe0301190a12103232000402cb015201520152a3fe700099fe000800000000000000130267"
        "0690cafe0303190a121032324842011d080f122d15001737027600a9000c1e0a012801e00e10a202"
        "0690cafe03 02190a1210 3232002d00 3c003c003c 000a1e3c6e 9600f00802 580f0f0f1e 14ffbf0297"
    )

    device = AsekoDecoder.decode(bytes(data))
    print(device)
    assert device.device_type == AsekoDeviceType.HOME
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.REDOX}
    assert device.ph is not None
    assert device.redox is not None
    assert device.cl_free is None


# test combinations of different methodes like date, time, normalize, probe types etc.


def test_decode_net_pump_states() -> None:
    """Test pump state decoding for Aqua NET (confirmed byte 29 masks from Issue #66)."""

    data = _make_base_bytes()
    data[4] = 0x09  # NET with CLF probe

    # Bit 0x08 is not mapped for NET – filtration_pump_running stays None
    data[29] = 0x08
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_pump_running is None
    assert device.cl_pump_running is False
    assert device.ph_minus_pump_running is False

    # CL pump only (0x02; bit 0x08 has no meaning on NET)
    data[29] = 0x0A  # 0x08 | 0x02
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_pump_running is None
    assert device.cl_pump_running is True
    assert device.ph_minus_pump_running is False

    # PH-minus pump only (0x01; bit 0x08 has no meaning on NET)
    data[29] = 0x09  # 0x08 | 0x01
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_pump_running is None
    assert device.cl_pump_running is False
    assert device.ph_minus_pump_running is True

    # No pump running
    data[29] = 0x00
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_pump_running is None
    assert device.cl_pump_running is False
    assert device.ph_minus_pump_running is False

    # SALT-specific fields must be None for NET
    assert device.electrolyzer_active is None
    assert device.electrolyzer_direction is None


def test_decode_salt_pump_states() -> None:
    """Test pump state decoding for Aqua SALT (electrolyzer, no CL pump)."""

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[20] = 32  # salinity
    data[21] = 80  # electrolyzer_power

    # Electrolyzer running, right direction (no filtration bit)
    data[29] = 0x10  # ELECTROLYZER_RUNNING_RIGHT
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_pump_running is False
    assert device.electrolyzer_active is True
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.RIGHT
    assert device.cl_pump_running is None  # SALT has no CL pump

    # Electrolyzer running, left direction
    data[29] = 0x58  # 0x50 | 0x08 (LEFT + FILTRATION)
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_pump_running is True
    assert device.electrolyzer_active is True
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.LEFT

    # Electrolyzer off
    data[29] = 0x08  # filtration only
    device = AsekoDecoder.decode(bytes(data))
    assert device.electrolyzer_active is False
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.WAITING


def test_decode_salt_algicide_pump_running() -> None:
    """Test algicide pump running detection for SALT.

    Confirmed by @hopkins-tk 2026-04-04 (19 consecutive frames w/o electrolyzer, PR #87):
    algicide running → byte[29]=0x28 (bit 5 / 0x20), same mask as flocculant.
    not running → byte[29]=0x08. Routing via byte[37] bit 7 (0x80) = algicide configured.
    """

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[37] = 0xB3  # algicide configured (bit 7 set); 0xB3 = real Hopkins value
    data[54] = 10  # required_algicide = 10 ml/m³/day (non-FF → not None)
    data[101] = 60  # flowrate_algicide = 60 ml/min

    # Algicide pump running: byte[29] bit 5 (0x20) set
    data[29] = 0x28  # 0x08 | 0x20 — confirmed by 19 live frames 2026-04-04
    device = AsekoDecoder.decode(bytes(data))
    assert device.algicide_pump_running is True
    assert device.floc_pump_running is None  # algicide configured → floc slot vacant

    # Algicide pump not running
    data[29] = 0x08  # baseline; confirmed 2026-04-04
    device = AsekoDecoder.decode(bytes(data))
    assert device.algicide_pump_running is False
    assert device.floc_pump_running is None


def test_decode_salt_flocculant_pump_running() -> None:
    """Test flocculant pump running detection for SALT.

    Confirmed by @hopkins-tk 2026-04-03 (PR #87): flocculant running → byte[29]=0x28
    (bit 5 / 0x20), not running → byte[29]=0x08 (immediate stop, no linger).
    Byte[37] bit 7 (0x80) clear = flocculant configured.
    """

    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[37] = 0x33  # flocculant configured (bit 7 clear); 0x33 = real Hopkins value
    data[54] = 1  # required_floc placeholder (not used for type check)
    data[101] = 60  # flowrate_floc = 60 ml/min

    # Flocculant pump running: byte[29] bit 5 (0x20) set
    data[29] = 0x28  # 0x08 | 0x20 — confirmed by live frame 2026-04-03
    device = AsekoDecoder.decode(bytes(data))
    assert device.floc_pump_running is True
    assert (
        device.algicide_pump_running is None
    )  # flocculant configured → alg slot vacant

    # Flocculant pump not running
    data[29] = 0x08  # baseline; confirmed 2026-04-03 (immediate stop, no linger)
    device = AsekoDecoder.decode(bytes(data))
    assert device.floc_pump_running is False


# test combinations of different methodes like date, time, normalize, probe types etc.


def test_normalize_value_edge_cases() -> None:
    """Test normalization of edge cases."""

    assert AsekoDecoder._normalize_value(None, int) is None
    assert AsekoDecoder._normalize_value(255, int) is None
    assert AsekoDecoder._normalize_value("", str) is None
    assert AsekoDecoder._normalize_value("255", str) is None
    assert AsekoDecoder._normalize_value(42, int) == 42
    assert AsekoDecoder._normalize_value("42", str) == "42"

    with pytest.raises(ValueError):
        AsekoDecoder._normalize_value(0xFF, float)


def test_timestamp_unspecified() -> None:
    """Test timestamp decoding with unspecified values."""

    data = bytearray(120)
    data[6:12] = b"\xff\xff\xff\xff\xff\xff"
    ts = AsekoDecoder._timestamp(data)
    assert isinstance(ts, datetime)
    now = datetime.now(ts.tzinfo)
    assert abs((ts - now).total_seconds()) < 5


def test_timestamp_invalid() -> None:
    """Test timestamp decoding with invalid values."""
    data = bytearray(120)
    data[6:12] = b"\xf0\xf0\xf0\xf0\xf0\xf0"
    ts = AsekoDecoder._timestamp(data)
    assert isinstance(ts, datetime)
    now = datetime.now(ts.tzinfo)
    assert abs((ts - now).total_seconds()) < 5


def test_time_unspecified() -> None:
    """Test time decoding with unspecified values."""

    data = bytearray(120)
    data[0] = 255
    data[1] = 255
    t = AsekoDecoder._time(data)
    assert t is None


def test_time_invalid() -> None:
    """Test time decoding with invalid values."""

    data = bytearray(120)
    data[0] = 200
    data[1] = 200
    t = AsekoDecoder._time(data)
    assert t is None


def test_available_probes_combinations() -> None:
    from custom_components.aseko_local.const import (
        PROBE_CLF_MISSING,
        PROBE_DOSE_MISSING,
        PROBE_REDOX_MISSING,
        PROBE_OXY_MISSING,
    )

    # All probes present
    data = bytearray(120)
    data[4] = 0x00
    probes = AsekoDecoder._configuration(data)
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
    probes = AsekoDecoder._configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.CLF not in probes

    # Just REDOX is missing
    data[4] = PROBE_REDOX_MISSING
    probes = AsekoDecoder._configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.REDOX not in probes

    # Just OXY is missing
    data[4] = PROBE_OXY_MISSING
    probes = AsekoDecoder._configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.OXY not in probes

    # Just DOSE is missing
    data[4] = PROBE_DOSE_MISSING
    probes = AsekoDecoder._configuration(data, AsekoDeviceType.PROFI)
    assert AsekoProbeType.DOSE not in probes


# def test_decode_pump_types() -> None:
#    """Test decoding of different pump types."""
#
#    data = _make_base_bytes()
#
#    # Test: Chlor pump running
#    data[29] = 0x48
#    device = AsekoDecoder.decode(bytes(data))
#    assert device.active_pump == AsekoPumpType.CHLOR
#
#    # Test: PH+ pump running --> data Byte is unknwon
#    # data[29] = -1
#    # device = AsekoDecoder.decode(bytes(data))
#    # assert device.active_pump == AsekoPumpType.PH_PLUS
#
#    # Test: PH- pump running
#    data[29] = 0x88
#    device = AsekoDecoder.decode(bytes(data))
#    assert device.active_pump == AsekoPumpType.PH_MINUS
#
#    # Test: Floc pump running
#    data[29] = 0x28
#    device = AsekoDecoder.decode(bytes(data))
#    assert device.active_pump == AsekoPumpType.FLOC
#
#    # Test: No pump running
#    data[29] = 0x00
#    device = AsekoDecoder.decode(bytes(data))
#    assert device.active_pump == 0


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
    device = AsekoDecoder.decode(_oxy_bytes(_OXY_NORMAL_HEX))

    # Device type and probes
    assert device.device_type == AsekoDeviceType.OXY
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.OXY}

    # CLF/REDOX must be None – firmware placeholder 0x001E must not be decoded
    assert device.cl_free is None
    assert device.redox is None
    assert device.required_cl_free is None
    assert device.required_redox is None

    # byte[37]=0x03 on OXY must NOT trigger SALT-style algicide/floc routing.
    # OXY has two independent pump ports: byte[54]=required_floc, byte[72]=required_algicide.
    # 2026-04-11 frame: floc=10 ml/h, algicide=15 ml/m³/d.
    assert device.required_floc == 10  # byte[54] = 0x0a
    assert device.required_algicide == 15  # byte[72] = 0x0f

    # OXY-specific setpoint (byte[53] = 0x0c = 12)
    assert device.required_oxy_dose == 12

    # Pumps
    assert device.filtration_pump_running is True
    assert device.ph_minus_pump_running is False  # bit 0x80 clear
    assert device.floc_pump_running is False
    assert device.algicide_pump_running is False  # bit 0x10 clear
    assert device.oxy_pump_running is False  # bit 0x40 clear

    # Flow rates (sub-frame 3)
    assert device.flowrate_ph_minus == 60  # byte[95] = 0x3c
    assert device.flowrate_oxy == 60  # byte[99] = 0x3c (OXY Pure pump slot)
    assert device.flowrate_chlor is None  # not set on OXY devices
    assert device.flowrate_floc == 10  # byte[101] = 0x0a
    assert device.flowrate_algicide == 60  # byte[103] = 0x3c

    # Basic data
    assert device.serial_number == 110_157_485
    assert device.ph == pytest.approx(7.2, abs=0.01)
    assert device.water_temperature == pytest.approx(19.9, abs=0.1)
    assert device.water_flow_to_probes is True
    assert device.required_ph == pytest.approx(7.2, abs=0.01)
    assert device.required_water_temperature == 25
    assert device.pool_volume == 41


def test_decode_oxy_floc_pump_running() -> None:
    """Decode the OXY frame where the flocculant pump is running.

    Real frame captured 2026-04-11 23:51:25 UTC+2. Only change vs normal frame:
    byte[29] 0x08 → 0x28 (bit 0x20 set = flocculant pump confirmed).
    """
    device = AsekoDecoder.decode(_oxy_bytes(_OXY_FLOC_HEX))

    assert device.device_type == AsekoDeviceType.OXY
    assert device.filtration_pump_running is True
    assert device.floc_pump_running is True

    # All other OXY fields still intact
    assert device.cl_free is None
    assert device.redox is None
    assert device.required_oxy_dose == 12
    assert device.flowrate_floc == 10


def test_decode_oxy_ph_minus_pump_running() -> None:
    """Decode the OXY frame where the pH− pump is running.

    Real frame captured 2026-04-12 15:27:38 UTC+2. Only change vs normal frame:
    byte[29] 0x08 → 0x88 (bit 0x80 set = pH− pump confirmed).
    """
    device = AsekoDecoder.decode(_oxy_bytes(_OXY_PH_MINUS_HEX))

    assert device.device_type == AsekoDeviceType.OXY
    assert device.filtration_pump_running is True
    assert device.ph_minus_pump_running is True  # bit 0x80 set
    assert device.floc_pump_running is False
    assert device.algicide_pump_running is False
    assert device.oxy_pump_running is False

    # All other OXY fields intact
    assert device.cl_free is None
    assert device.redox is None
    assert device.required_oxy_dose == 12
    assert device.flowrate_ph_minus == 60
    assert device.flowrate_floc == 10


def test_decode_issue_99_home() -> None:
    """Test decoding data from issue #99 (HOME with CLF - 0x02)."""

    data = bytearray.fromhex(
        "06 90 ff ff 02 01 1a 04 19 0e 13 0a 00 00 02 b7 00 1e 00 1e 00 1f 90 fe 70 01 30 26 aa 08 00 00 00 00 00 00 00 43 0a b3"
        "06 90 ff ff 02 03 1a 04 19 0e 13 0a 46 03 0a 19 08 00 10 00 12 00 16 00 02 be 01 30 03 15 00 0c 00 28 01 e0 2a 30 a2 55"
        "06 90 ff ff 02 02 1a 04 19 0e 13 0a 00 3c 00 3c 00 3c 00 3c 00 0a 0d 21 37 64 00 f0 14 02 58 0f 0f 0f 1e 14 ff bc 02 77"
    )

    device = AsekoDecoder.decode(bytes(data))
    print(device)
    assert device.device_type == AsekoDeviceType.HOME
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.CLF}
    assert device.cl_free is not None
    assert device.cl_free_mv is not None
    assert device.redox is None
    # Bug fix: required_floc and required_algicide must be decoded for HOME devices.
    # byte[54] = 0x0a = 10 → required_floc = 10 ml/h
    # byte[72] = 0x00 = 0  → required_algicide = 0 ml/m³/day
    assert device.required_floc == 10
    assert device.required_algicide == 0


def test_decode_home_clf_real_frame() -> None:
    """Real-world frame from serial 110128063 (ASIN AQUA Home, CLF variant).

    Frame captured 2026-04-28 08:27:07.  Verified against Aseko Live app.
    Confirms fix: required_floc (byte[54]) and required_algicide (byte[72])
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

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.CLF}
    # Probe readings
    assert device.ph == pytest.approx(6.29)
    assert device.cl_free == pytest.approx(0.0)
    assert device.cl_free_mv == 2
    assert device.water_temperature == pytest.approx(37.9)
    assert device.water_flow_to_probes is False
    # Setpoints — all confirmed against Aseko Live Config page
    assert device.required_ph == pytest.approx(7.0)
    assert device.required_cl_free == pytest.approx(0.3)
    assert (
        device.required_floc == 10
    )  # byte[54] = 0x0a = 10 ml/h  (was None before fix)
    assert (
        device.required_algicide == 0
    )  # byte[72] = 0x00 = 0 ml/m³/d (was None before fix)
    assert device.required_water_temperature == 25
    # Schedule
    assert device.start1 == time(8, 0)
    assert device.stop1 == time(16, 0)
    # Issue #133: Period 2 times are now always populated for any device in
    # FILTRATION_TYPES (HOME here).  The mode entity tells the user which
    # schedule is active — on this frame byte[37] = 0x43 (firmware A) so the
    # mode is NONSTOP_24H, but bytes 60-63 still report the last-configured
    # Period 2 times.  Pre-fix, the assertions below were ``is None``.
    assert device.start2 == time(18, 0)
    assert device.stop2 == time(22, 0)
    assert device.filtration_mode == AsekoFiltrationMode.NONSTOP_24H
    # Backwash
    assert device.backwash_every_n_days == 3
    assert device.backwash_time == time(21, 0)
    assert device.backwash_duration == 120
    # Pool parameters
    assert device.pool_volume == 60
    assert device.max_filling_time == 60  # raw = minutes directly (verified Issue #110)
    assert device.delay_after_startup == 480
    assert device.delay_after_dose == 240
    # Flowrates
    assert device.flowrate_chlor == 60
    assert device.flowrate_ph_minus == 60
    assert device.flowrate_floc == 10


def test_decode_issue_99_salt() -> None:
    """Test decoding data from issue #99 (SALT with CLF - 0x0d)."""

    data = bytearray.fromhex(
        "06 8f ff ff 0d 01 1a 04 19 0e 2d 28 00 20 02 cd 00 00 00 01 1f 00 ff fd c4 00 dd 4e 00 00 00 00 00 00 00 00 00 57 00 3a"
        "06 8f ff ff 0d 03 1a 04 19 0e 2d 28 49 05 08 19 0a 1e 0e 1e 17 37 01 0a 02 b1 00 dd 07 0a 1e 0a ff 28 01 e0 0e 10 01 e7"
        "06 8f ff ff 0d 02 1a 04 19 0e 2d 28 00 41 00 3c 19 4c db ff 00 3c 1e 2d 4b 96 00 f0 0a 0b b8 0f 0f 01 7b ff ff 9a 01 bc"
    )

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.SALT
    assert device.configuration == {AsekoProbeType.PH, AsekoProbeType.CLF}
    assert device.cl_free is not None
    assert device.cl_free_mv is not None
    assert device.redox is None


# ── HOME independent flowrate tests (Issue #115) ─────────────────────────────


def test_decode_home_independent_flowrates() -> None:
    """HOME devices use byte[101]=floc, byte[103]=algicide independently.

    Before this fix, HOME fell through to the SALT routing logic, which routed
    byte[101] exclusively to either floc or algicide (per byte[37] bit 7).
    This caused Issue #115: `required_algicide` and `flowrate_algicide`
    entities were never created on HOME, and the algicide pump binary sensor
    was always missing.

    Confirmed by HOME frame from Issue #110 (serial 110071590, byte[4]=0x02):
        byte[101] = 0x0a (10) → flowrate_floc
        byte[103] = 0x0b (11) → flowrate_algicide  (was None before fix)
    """
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 60  # flowrate_chlor (Chlor Pure)
    data[101] = 10  # flowrate_floc
    data[103] = 11  # flowrate_algicide — was never read on HOME before
    data[37] = 0x53  # HOME filtration mode flag (irrelevant for flowrates)

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.flowrate_chlor == 60
    # byte[95] is overwritten to 60 by the max_filling_time setter in _make_base_bytes.
    assert device.flowrate_ph_minus == 60
    assert device.flowrate_floc == 10
    assert device.flowrate_algicide == 11  # NEW — previously None
    # Byte 37 bit 7 has no meaning on HOME (no shared pump port).
    # Confirms we do not depend on byte[37] for HOME flowrates.
    data[37] = 0xB3  # SALT-style "algicide routing" value — must be IGNORED on HOME
    device = AsekoDecoder.decode(bytes(data))
    assert device.flowrate_floc == 10
    assert device.flowrate_algicide == 11


def test_decode_home_flowrates_unspecified() -> None:
    """HOME flowrates: 0xFF → None (e.g. pump not installed)."""
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 0xFF  # chlorine pump not installed
    data[101] = 0xFF  # flocculant pump not installed
    data[103] = 0xFF  # algicide pump not installed

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.flowrate_chlor is None
    assert device.flowrate_floc is None
    assert device.flowrate_algicide is None


def test_decode_home_algicide_pump_running() -> None:
    """Issue #115: HOME devices must expose algicide_pump_running binary sensor.

    Before the HOME-specific flowrate branch was added, flowrate_algicide
    was always None on HOME, which made _fill_consumable_data short-circuit
    the algicide_pump_running assignment — so the binary sensor was never
    registered.  With flowrate_algicide now decoded, the binary sensor
    correctly reflects byte[29] bit 5 (0x20).
    """
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 60  # chlor
    data[101] = 10  # floc — pump installed
    data[103] = 20  # algicide — pump installed (key for this test)
    data[37] = 0x53

    # Algicide running: bit 5 (0x20) set, bit 3 (0x08) filtration on
    data[29] = 0x28
    device = AsekoDecoder.decode(bytes(data))
    assert device.algicide_pump_running is True
    # On HOME, floc and algicide share bit 0x20 in byte[29] (the existing
    # HOME masks in ACTUATOR_MASKS mark both algicide=0x20 and flocculant=0x20
    # with the "uncertain" comment).  The current implementation reports
    # BOTH as active when bit 0x20 is set — this is a known limitation and
    # the binary sensors exist for both chemicals.  See home_device_analysis.md
    # §"Actuator byte[29] — HOME masks (uncertain)" for confirmation that
    # the per-pump bit for HOME is unverified.  The important point of this
    # test is that algicide_pump_running is no longer None on HOME.

    # Algicide stopped
    data[29] = 0x08
    device = AsekoDecoder.decode(bytes(data))
    assert device.algicide_pump_running is False


def test_decode_home_floc_pump_running_independent() -> None:
    """On HOME the floc pump runs independently of algicide (different pump ports).

    byte[101] set (floc installed) and byte[103] = 0xFF (no algicide) →
    floc_pump_running tracks byte[29] bit 5, algicide_pump_running stays None.
    """
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    data[99] = 0xFF  # no chlor
    data[101] = 10  # floc installed
    data[103] = 0xFF  # NO algicide pump
    data[37] = 0x53

    data[29] = 0x28
    device = AsekoDecoder.decode(bytes(data))
    assert device.floc_pump_running is True
    assert device.algicide_pump_running is None


# ── HOME water level and alarm tests (Issue #100 / #110) ─────────────────────


def _make_home_bytes() -> bytearray:
    """Base HOME device frame (CLF variant, byte[4]=0x02) for water-level tests."""
    data = _make_base_bytes()
    data[4] = 0x02  # HOME CLF
    return data


def test_home_water_level_decoding() -> None:
    """byte[27] is decoded as water_level (cm) for HOME devices only."""
    data = _make_home_bytes()
    data[27] = 0x0E  # 14 cm — confirmed by issue #110 frame

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
    assert device.water_level == 14


def test_home_water_level_unspecified() -> None:
    """byte[27] = 0xFF → water_level is None."""
    data = _make_home_bytes()
    data[27] = 0xFF

    device = AsekoDecoder.decode(bytes(data))
    assert device.water_level is None


def test_home_water_filling_active() -> None:
    """byte[29] bit 0x02: water filling active for HOME devices."""
    data = _make_home_bytes()

    # bit 0x02 set: filling active
    data[29] = 0x4A  # confirmed transition in DomSchCoding #100 (0x48 → 0x4a)
    device = AsekoDecoder.decode(bytes(data))
    assert device.water_filling_active is True

    # bit 0x02 clear: filling inactive
    data[29] = 0x48
    device = AsekoDecoder.decode(bytes(data))
    assert device.water_filling_active is False


def test_home_water_level_thresholds() -> None:
    """bytes [102..105] decode to the four water level thresholds for HOME devices.

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

    device = AsekoDecoder.decode(bytes(data))
    assert device.water_level_low_alarm == 9
    assert device.water_level_filling_on == 11
    assert device.water_level_filling_off == 13
    assert device.water_level_high_alarm == 15


def test_home_water_level_threshold_unspecified() -> None:
    """0xFF threshold values → None (e.g. feature not configured)."""
    data = _make_home_bytes()
    data[102] = 0xFF
    data[103] = 0xFF
    data[104] = 0xFF
    data[105] = 0xFF

    device = AsekoDecoder.decode(bytes(data))
    assert device.water_level_low_alarm is None
    assert device.water_level_filling_on is None
    assert device.water_level_filling_off is None
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

    device = AsekoDecoder.decode(bytes(data))
    assert device.water_level is None
    assert device.water_level_low_alarm is None
    assert device.water_level_filling_on is None
    assert device.water_level_filling_off is None
    assert device.water_level_high_alarm is None
    assert device.water_filling_active is None


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

        device = AsekoDecoder.decode(bytes(data))
        assert device.water_level == 14, f"byte[4]={device_byte:#x}"
        assert device.water_filling_active is True, f"byte[4]={device_byte:#x}"
        assert device.water_level_low_alarm == 9, f"byte[4]={device_byte:#x}"
        assert device.water_level_filling_on == 11, f"byte[4]={device_byte:#x}"
        assert device.water_level_filling_off == 13, f"byte[4]={device_byte:#x}"
        assert device.water_level_high_alarm == 15, f"byte[4]={device_byte:#x}"


def test_filtration_nonstop24_none_for_net() -> None:
    """filtration_nonstop24 is None for NET only (no filtration output).

    Issue #133 follow-up: SALT / OXY / PROFI now also expose a filtration
    mode. NET is the only AsekoDeviceType that has no filtration output
    (Issue #66), so the legacy boolean stays None on NET.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    data[37] = 0xFF  # NET byte 37 is always unspecified

    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_nonstop24 is None


def test_filtration_nonstop24_decoded_for_all_device_types() -> None:
    """filtration_nonstop24 mirrors the new 4-state filtration_mode enum.

    For SALT / OXY / PROFI: the value is derived from the schedule bytes
    56-63 (no schedule → NONSTOP_24H, otherwise timer with or without P2
    depending on byte 37 bit 0x20 / start2 presence). With the base test
    fixture (P1 + P2 schedule, byte 37 bit 0x20 set on SALT 0xb7 via
    _make_base_bytes default), the legacy boolean reads False.

    For NET: stays None (NET is excluded from FILTRATION_TYPES).
    """
    # NET: no filtration output → legacy boolean stays None
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    data[37] = 0xFF
    assert AsekoDecoder.decode(bytes(data)).filtration_nonstop24 is None

    # SALT / OXY / PROFI: with default schedule (P1 + P2), legacy bool = False
    for device_byte in (0x0E, 0x05, 0x10):  # SALT, OXY, PROFI
        data = _make_base_bytes()
        data[4] = device_byte
        # keep default schedule + byte[37]
        assert AsekoDecoder.decode(bytes(data)).filtration_nonstop24 is False, (
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

        device = AsekoDecoder.decode(bytes(data))
        assert device.alarm_no_flow_to_probes is True, f"byte[4]={device_byte:#x}"
        assert device.alarm_ph_too_many_doses is False, f"byte[4]={device_byte:#x}"
        assert device.alarm_orp_too_many_doses is False, f"byte[4]={device_byte:#x}"
        assert device.alarm_rapid_ph_change is False, f"byte[4]={device_byte:#x}"


def test_home_filtration_nonstop24() -> None:
    """byte[37] filtration mode: 0x43 = nonstop, 0x53 = timer, others = None."""
    data = _make_home_bytes()

    data[37] = 0x43  # nonstop 24 h
    assert AsekoDecoder.decode(bytes(data)).filtration_nonstop24 is True

    data[37] = 0x53  # timer mode
    assert AsekoDecoder.decode(bytes(data)).filtration_nonstop24 is False

    data[37] = 0x47  # transitional edit state → None
    assert AsekoDecoder.decode(bytes(data)).filtration_nonstop24 is None

    data[37] = 0x57  # transitional edit state → None
    assert AsekoDecoder.decode(bytes(data)).filtration_nonstop24 is None


# ── Issue #133: HOME v7 firmware B (4-state enum + manual OFF override) ──────


def test_filtration_mode_new_encoding_24h() -> None:
    """Firmware B byte[37] = 0x01 → NONSTOP_24H (serial 110169464)."""
    data = _make_home_bytes()
    data[37] = 0x01  # new encoding: nonstop 24h
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.NONSTOP_24H
    assert device.filtration_nonstop24 is True  # legacy mirror


def test_filtration_mode_new_encoding_p1() -> None:
    """Firmware B byte[37] = 0x11 → TIMER_PERIOD_1 (P1 only, P2 disabled)."""
    data = _make_home_bytes()
    data[37] = 0x11  # new encoding: P1 only
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1
    assert device.filtration_nonstop24 is False


def test_filtration_mode_new_encoding_p1_and_p2() -> None:
    """Firmware B byte[37] = 0x31 → TIMER_PERIOD_1_AND_2 (both periods)."""
    data = _make_home_bytes()
    data[37] = 0x31  # new encoding: P1 & P2
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1_AND_2
    assert device.filtration_nonstop24 is False


def test_filtration_mode_new_encoding_off_manual_p1_and_p2() -> None:
    """Firmware B byte[37] = 0x35 → OFF_MANUAL (P1 & P2 + manual override).

    The original frame from @dtpugh (serial 110169464) had 0x35: both
    periods enabled and the user manually toggled filtration OFF.
    """
    data = _make_home_bytes()
    data[37] = 0x35  # new encoding: P1 & P2 + manual override (bit 2 set)
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.OFF_MANUAL
    assert device.filtration_nonstop24 is False


def test_filtration_mode_new_encoding_off_manual_p1_only() -> None:
    """Firmware B byte[37] = 0x15 → OFF_MANUAL (P1 only + manual override).

    Diagnostic 42 from @dtpugh (serial 110175608): user switched pump OFF
    while only Period 1 was active. byte[37] = 0x15 (bits 0,2,4 set).
    Bit 2 (0x04) = manual override → must decode as OFF_MANUAL.
    """
    data = _make_home_bytes()
    data[37] = 0x15  # P1 + manual override
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.OFF_MANUAL
    assert device.filtration_nonstop24 is False


def test_filtration_mode_old_encoding_24h() -> None:
    """Firmware A byte[37] = 0x43 → NONSTOP_24H (serial 110128063)."""
    data = _make_home_bytes()
    data[37] = 0x43
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.NONSTOP_24H
    assert device.filtration_nonstop24 is True


def test_filtration_mode_old_encoding_timer() -> None:
    """Firmware A byte[37] = 0x53 → TIMER_PERIOD_1_AND_2 (cannot distinguish P1 vs P1&P2)."""
    data = _make_home_bytes()
    data[37] = 0x53
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1_AND_2
    assert device.filtration_nonstop24 is False


def test_filtration_mode_old_encoding_transitional() -> None:
    """Firmware A byte[37] = 0x47 / 0x57 → leave as None (transitional edit state)."""
    for transitional in (0x47, 0x57):
        data = _make_home_bytes()
        data[37] = transitional
        device = AsekoDecoder.decode(bytes(data))
        assert device.filtration_mode is None
        assert device.filtration_nonstop24 is None


def test_filtration_mode_unspecified() -> None:
    """byte[37] = 0xFF → None (defensive, also covers NET-like values on HOME)."""
    data = _make_home_bytes()
    data[37] = 0xFF
    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode is None
    assert device.filtration_nonstop24 is None


def test_filtration_mode_none_for_net() -> None:
    """filtration_mode stays None for NET — no filtration output (Issue #66).

    NET is the only AsekoDeviceType excluded from FILTRATION_TYPES, so the
    decoder returns without setting filtration_mode. SALT, HOME, OXY and
    PROFI all populate the field.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET CLF
    data[37] = 0xFF  # NET byte 37 is always unspecified
    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.NET
    assert device.filtration_mode is None


def test_filtration_mode_derived_for_salt_oxy_profi() -> None:
    """For SALT / OXY / PROFI the mode is derived from the schedule bytes 56-63.

    The base test fixture has start1 = 08:00 / stop1 = 10:00 / start2 = 14:00 /
    stop2 = 16:00 (see _make_base_bytes). With both periods set, the derived
    mode is TIMER_PERIOD_1_AND_2 regardless of the byte[37] value (SALT
    0xb7, OXY 0x03, PROFI 0x53) — those bits are algicide routing / pump
    presence / unknown, NOT filtration-mode flags.
    """
    for device_byte in (0x0E, 0x05, 0x10):  # SALT, OXY, PROFI
        data = _make_base_bytes()
        data[4] = device_byte
        # keep default schedule (08:00, 10:00, 14:00, 16:00) and byte[37]
        device = AsekoDecoder.decode(bytes(data))
        assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1_AND_2, (
            f"byte[4]={device_byte:#x}"
        )


def test_filtration_mode_salt_p1_only_when_period2_disabled() -> None:
    """SALT with byte[37] bit 0x20 clear (period-2 disabled) → TIMER_PERIOD_1.

    Mirrors test_decode_filtration_period2_disabled but checks the new
    `filtration_mode` enum (not the legacy boolean).
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[60:64] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 2 schedule
    data[37] = 0x93  # bit 0x20 clear, period 2 disabled

    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1


def test_filtration_mode_salt_nonstop_when_no_schedule() -> None:
    """SALT with start1 = 0xFF (no schedule) → NONSTOP_24H.

    Bytes 56-63 are read directly here (this test runs the decoder end-to-end
    on a SALT fixture, and `_fill_filtration_mode` runs before the schedule
    is decoded into `unit.start1`).
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[56:60] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 1
    data[60:64] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # no period 2
    data[37] = 0xB7  # SALT algicide routing — irrelevant for mode derivation

    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.NONSTOP_24H


def test_filtration_pump_running_off_when_manual_override() -> None:
    """byte[29] bit 3 stays set in OFF_MANUAL mode, but pump must read as False.

    The @dtpugh issue: with the user manually switched the pump off, byte[29]
    bit 3 (filtration relay) is still 0x08 in the frame. The decoder trusts
    the explicit OFF_MANUAL flag in byte[37] and forces False.

    Tests both known OFF_MANUAL byte[37] values:
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

        device = AsekoDecoder.decode(bytes(data))
        assert device.filtration_mode == AsekoFiltrationMode.OFF_MANUAL, (
            f"byte[37]={override_value:#x}"
        )
        assert device.filtration_pump_running is False, f"byte[37]={override_value:#x}"


def test_filtration_pump_running_on_when_not_override() -> None:
    """Regression guard: outside OFF_MANUAL, byte[29] bit 3 still drives the entity."""
    data = _make_home_bytes()
    data[4] = 0x03
    data[29] = 0x08
    data[37] = 0x11  # P1 only — pump should be on per the schedule

    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1
    assert device.filtration_pump_running is True


def test_filtration_pump_running_not_overridden_on_salt() -> None:
    """The OFF_MANUAL short-circuit is gated on HOME — SALT behaviour unchanged.

    On SALT the override does not apply even if byte[37] is a value that
    means OFF_MANUAL on HOME (0x35), because SALT uses byte[37] for
    algicide routing and never reaches the OFF_MANUAL branch.
    """
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT
    data[29] = 0x08
    data[37] = 0x35  # would be OFF_MANUAL on HOME — irrelevant on SALT

    device = AsekoDecoder.decode(bytes(data))
    # SALT byte[37] does not encode OFF_MANUAL → mode is derived from
    # the schedule (default base fixture: P1 + P2 → TIMER_PERIOD_1_AND_2).
    assert device.filtration_mode == AsekoFiltrationMode.TIMER_PERIOD_1_AND_2
    assert device.filtration_pump_running is True  # unchanged: byte[29] bit 3 wins


def test_filtration_pump_running_off_when_pump_actually_off() -> None:
    """byte[29] = 0x00 (no pump running) + OFF_MANUAL → still False (no-op)."""
    data = _make_home_bytes()
    data[4] = 0x03
    data[29] = 0x00
    data[37] = 0x35

    device = AsekoDecoder.decode(bytes(data))
    assert device.filtration_pump_running is False


def test_home_alarm_bitmask_byte13() -> None:
    """byte[13] alarm bitmask is decoded for all device types; tested here on HOME.

    Bit mapping (Issue #151, serial 110175608): 0x01 = disinfection/Cl dose fault,
    0x02 = pH dose fault, 0x04 = no flow, 0x08 = rapid pH change.
    """
    data = _make_home_bytes()

    # All four bits set
    data[13] = 0x0F
    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_ph_too_many_doses is True  # bit 0x02
    assert device.alarm_orp_too_many_doses is True  # bit 0x01
    assert device.alarm_no_flow_to_probes is True  # bit 0x04
    assert device.alarm_rapid_ph_change is True  # bit 0x08

    # No alarm
    data[13] = 0x00
    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_ph_too_many_doses is False
    assert device.alarm_orp_too_many_doses is False
    assert device.alarm_no_flow_to_probes is False
    assert device.alarm_rapid_ph_change is False

    # Only no-flow bit (0x04) — as seen in NET frame (serial 06918724)
    data[13] = 0x04
    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_no_flow_to_probes is True
    assert device.alarm_ph_too_many_doses is False
    assert device.alarm_orp_too_many_doses is False
    assert device.alarm_rapid_ph_change is False


def test_home_alarm_byte13_bit01_is_disinfection() -> None:
    """byte[13] bit 0x01 = disinfection/Cl dose fault → alarm_orp_too_many_doses.

    Issue #151 regression: dtpugh's config48 frame (HOME serial 110175608) shows
    byte[13]=0x01 while the controller displayed "Maximum disinfection dose
    exceeded".  Pre-fix this bit was mapped to alarm_ph_too_many_doses, so the
    chlorine fault falsely lit the "Too many doses of pH" sensor.
    """
    data = _make_home_bytes()
    data[13] = 0x01

    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_orp_too_many_doses is True
    assert device.alarm_ph_too_many_doses is False
    assert device.alarm_no_flow_to_probes is False
    assert device.alarm_rapid_ph_change is False


def test_home_alarm_byte13_bit02_is_ph() -> None:
    """byte[13] bit 0x02 = pH dose fault → alarm_ph_too_many_doses.

    Inferred mapping (symmetric to bit 0x01, per dtpugh's expectation in
    Issue #151 that a pH fault would read 0x02).  Direct frame capture pending.
    """
    data = _make_home_bytes()
    data[13] = 0x02

    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_ph_too_many_doses is True
    assert device.alarm_orp_too_many_doses is False
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
    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_orp_too_many_doses is True
    assert device.alarm_ph_too_many_doses is False

    # pH only
    data[12] = 0x40
    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_ph_too_many_doses is True
    assert device.alarm_orp_too_many_doses is False

    # Both
    data[12] = 0x60
    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_ph_too_many_doses is True
    assert device.alarm_orp_too_many_doses is True

    # None
    data[12] = 0x00
    data[13] = 0x00
    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_ph_too_many_doses is False
    assert device.alarm_orp_too_many_doses is False


def test_decode_alarm_real_dtpugh_frames() -> None:
    """Issue #151 end-to-end: decode the three real diagnostic frames from
    @dtpugh (HOME serial 110175608) and verify the correct alarm sensors fire.

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
        device = AsekoDecoder.decode(bytes.fromhex(hex_dump))
        assert device.device_type == AsekoDeviceType.HOME, f"config{name}"
        assert device.alarm_ph_too_many_doses is exp_ph, (
            f"config{name}: alarm_ph_too_many_doses expected {exp_ph}"
        )
        assert device.alarm_orp_too_many_doses is exp_orp, (
            f"config{name}: alarm_orp_too_many_doses expected {exp_orp}"
        )


def test_home_byte12_not_an_alarm_byte() -> None:
    """byte[12] = 0x04 must NOT set any alarm field (it is NOT an error byte).

    Confirmed by user's NET frame (serial 0x06918724): byte[12]=0x00 while
    byte[13]=0x04 (active no-flow error) and byte[28]=0x00.
    """
    data = _make_home_bytes()
    data[12] = 0x04  # would have set alarm_rapid_ph_change in old design
    data[13] = 0x00  # all alarms off

    device = AsekoDecoder.decode(bytes(data))
    assert device.alarm_rapid_ph_change is False
    assert device.alarm_ph_too_many_doses is False
    assert device.alarm_orp_too_many_doses is False
    assert device.alarm_no_flow_to_probes is False


def test_home_max_filling_time() -> None:
    """max_filling_time is stored in minutes (raw value × 1).

    Confirmed against the Aseko Live app for serial 110071590:
        raw bytes 94:95 = 0x003c = 60
        app shows "Max filling time 60 min"
    Earlier interpretation as "raw × 30 seconds = 1800 s = 30 min"
    was rejected by the live app screenshot from mannekung (Issue #110).
    """
    data = _make_home_bytes()
    data[94:96] = (60).to_bytes(2, "big")  # raw = 60

    device = AsekoDecoder.decode(bytes(data))
    assert device.max_filling_time == 60  # raw value = minutes directly


# ── Backwash relay state (Issue #100) ────────────────────────────────────────


def test_backwash_active_decoded_for_home() -> None:
    """HOME devices: byte[29] bit 0x01 → backwash_active.

    Mapping from JS-DE-Tech relay_byte bit 0 ('backwash relay').
    """
    data = _make_home_bytes()

    # Backwash relay on (bit 0x01 set, plus filtration bit 0x08 for realism)
    data[29] = 0x09
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is True

    # Backwash relay off
    data[29] = 0x08  # filtration only
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is False


def test_backwash_active_decoded_for_salt() -> None:
    """SALT devices: byte[29] bit 0x01 → backwash_active (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT

    data[29] = 0x09  # bit 0 set
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is True

    data[29] = 0x08
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is False


def test_backwash_active_decoded_for_oxy() -> None:
    """OXY devices: byte[29] bit 0x01 → backwash_active (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x05  # OXY

    data[29] = 0x09
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is True

    data[29] = 0x08
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is False


def test_backwash_active_none_for_net() -> None:
    """NET devices: no backwash valve → backwash_active stays None.

    The binary sensor is therefore not registered for NET devices.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET

    data[29] = 0x09  # bit 0 set
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is None


def test_backwash_active_independent_of_water_filling() -> None:
    """byte[29] bit 0x01 (backwash) is independent of bit 0x02 (water filling)."""
    data = _make_home_bytes()

    # Both backwash and water filling on
    data[29] = 0x0B  # 0x08 | 0x02 | 0x01
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is True
    assert device.water_filling_active is True

    # Only backwash on (water filling off)
    data[29] = 0x09  # 0x08 | 0x01
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is True
    assert device.water_filling_active is False

    # Only water filling on (backwash off)
    data[29] = 0x0A  # 0x08 | 0x02
    device = AsekoDecoder.decode(bytes(data))
    assert device.backwash_active is False
    assert device.water_filling_active is True


# ── Heating demand relay (Issue #115, JS-DE-Tech relay_byte bit 2) ──────────


def test_heating_active_decoded_for_home() -> None:
    """HOME devices: byte[29] bit 0x04 → heating_active."""
    data = _make_home_bytes()

    # Heating demand on (bit 0x04 set, plus filtration bit 0x08 for realism)
    data[29] = 0x0C
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is True

    # Heating demand off
    data[29] = 0x08  # filtration only
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is False


def test_heating_active_decoded_for_salt() -> None:
    """SALT devices: byte[29] bit 0x04 → heating_active (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x0E  # SALT

    data[29] = 0x0C
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is True

    data[29] = 0x08
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is False


def test_heating_active_decoded_for_oxy() -> None:
    """OXY devices: byte[29] bit 0x04 → heating_active (parallel to HOME)."""
    data = _make_base_bytes()
    data[4] = 0x05  # OXY

    data[29] = 0x0C
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is True

    data[29] = 0x08
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is False


def test_heating_active_none_for_net() -> None:
    """NET devices: no heating output → heating_active stays None.

    The binary sensor is therefore not registered for NET devices.
    """
    data = _make_base_bytes()
    data[4] = 0x09  # NET

    data[29] = 0x0C  # bit 2 set
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is None


def test_heating_active_independent_of_backwash_and_filling() -> None:
    """byte[29] bit 0x04 is independent of bits 0x01 and 0x02."""
    data = _make_home_bytes()

    # All three relays on
    data[29] = 0x0F  # 0x08 | 0x04 | 0x02 | 0x01
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is True
    assert device.water_filling_active is True
    assert device.backwash_active is True

    # Only heating on
    data[29] = 0x0C  # 0x08 | 0x04
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is True
    assert device.water_filling_active is False
    assert device.backwash_active is False

    # Only backwash on
    data[29] = 0x09  # 0x08 | 0x01
    device = AsekoDecoder.decode(bytes(data))
    assert device.heating_active is False
    assert device.backwash_active is True


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

    device = AsekoDecoder.decode(data)

    assert device.device_type == AsekoDeviceType.HOME
    assert device.water_level == 14  # byte[27] = 0x0e confirmed
    assert device.water_flow_to_probes is True  # byte[28] = 0xAA
    assert device.water_filling_active is False  # byte[29] = 0x08, bit 0x02 not set
    assert device.filtration_nonstop24 is False  # byte[37] = 0x53 = timer mode
    assert device.water_level_low_alarm == 9  # byte[102]
    assert device.water_level_filling_on == 11  # byte[103]
    assert device.water_level_filling_off == 13  # byte[104]
    assert device.water_level_high_alarm == 15  # byte[105]
    assert device.pool_volume == 20  # bytes[92:94] = 0x0014
    assert (
        device.max_filling_time == 60
    )  # raw = minutes directly (verified Issue #110 app)
