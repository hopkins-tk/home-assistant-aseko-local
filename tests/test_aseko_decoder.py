"""Test the Aseko Decoder."""

from datetime import time, datetime

import pytest

from custom_components.aseko_local.aseko_data import (
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoProbeType,
)
from custom_components.aseko_local.aseko_decoder import AsekoDecoder
from custom_components.aseko_local.const import (
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
    data[4] = 0x03  # HOME with CL probe
    data[14:16] = (720).to_bytes(2, "big")  # ph
    data[37] = 0xB3  # required_ph
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
    assert device.max_filling_time == 60
    assert device.delay_after_startup == 120
    assert device.delay_after_dose == 30
    assert device.start1 == time(8, 0)
    assert device.stop1 == time(10, 0)
    assert device.start2 == time(14, 0)
    assert device.stop2 == time(16, 0)
    assert device.backwash_every_n_days == 3
    assert device.backwash_time == time(2, 30)
    assert device.backwash_duration == 20
    assert device.required_algicide == 5
    assert device.required_water_temperature == 28
    assert device.timestamp is not None
    assert device.timestamp.year == YEAR_OFFSET + 24
    assert device.timestamp.month == 6
    assert device.timestamp.day == 15
    assert device.timestamp.hour == 12
    assert device.timestamp.minute == 34
    assert device.timestamp.second == 56


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
    data[4] = 0x08  # PROFI with Redox & CLF probe
    data[16:18] = (100).to_bytes(2, "big")
    data[18:20] = (650).to_bytes(2, "big")
    data[14:16] = (800).to_bytes(2, "big")
    data[52] = 80
    data[53] = 20

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.PROFI
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
        "0690cf4a0301190a12103232000402cb015201520152a3fe700099fe000800000000000000130267"
        "0690cf4a0303190a121032324842011d080f122d15001737027600a9000c1e0a012801e00e10a202"
        "0690cf4a03 02190a1210 3232002d00 3c003c003c 000a1e3c6e 9600f00802 580f0f0f1e 14ffbf0297"
    )

    device = AsekoDecoder.decode(bytes(data))
    assert device.device_type == AsekoDeviceType.HOME
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
    from custom_components.aseko_local.aseko_decoder import (
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
        AsekoProbeType.REDOX,
        AsekoProbeType.DOSE,
        AsekoProbeType.OXY,
    }

    # Just CLF is missing
    data[4] = PROBE_CLF_MISSING
    probes = AsekoDecoder._configuration(data)
    assert AsekoProbeType.CLF not in probes

    # Just REDOX is missing
    data[4] = PROBE_REDOX_MISSING
    probes = AsekoDecoder._configuration(data)
    assert AsekoProbeType.REDOX not in probes

    # Just OXY is missing
    data[4] = PROBE_OXY_MISSING
    probes = AsekoDecoder._configuration(data)
    assert AsekoProbeType.OXY not in probes

    # Just DOSE is missing
    data[4] = PROBE_DOSE_MISSING
    probes = AsekoDecoder._configuration(data)
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

# Real frames captured 2026-04-02, serial 0x0690DD6D (= 110_157_165)
# Normal frame: no pump running except filtration (19:33:38)
_OXY_NORMAL_HEX = (
    "0690dd6d05011a04021715"
    "0a00000 2cd001e001efd9d80fe70005ffe"
    "aa0800000000000000030835"
    "0690dd6d05031a04021715"
    "0a4808011908001000120016000 2c0005f000c"
    "1e0a0128 00f00e10aa3f"
    "0690dd6d05021a04021715"
    "0a00290 03c003c003c000a1e3c6e960078"
    "0802580f2b0f1e1eaacb003a"
)

# Flocculant pump running frame (19:33:52): byte[29] 0x08 → 0x28
_OXY_FLOC_HEX = (
    "0690dd6d05011a04021715"
    "1700000 2cd001e001efd9d80fe70005ffe"
    "aa2800000000000000030808"
    "0690dd6d05031a04021715"
    "1748080119080010001200160002c0005f000c"
    "1e0a012800f00e10aa2f"
    "0690dd6d05021a04021715"
    "170029003c003c003c000a1e3c6e960078"
    "0802580f2b0f1e1eaacb0027"
)


def _oxy_bytes(hex_str: str) -> bytes:
    """Strip whitespace and convert hex string to bytes."""
    return bytes.fromhex(hex_str.replace(" ", ""))


def test_decode_oxy_normal_frame() -> None:
    """Decode the OXY normal frame: filtration only, no floc pump.

    Real frame captured 2026-04-02 19:33:38 from ASIN AQUA Oxygen (serial 110_157_165).
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

    # OXY-specific setpoint (byte[53] = 0x08 = 8)
    assert device.required_oxy_dose == 8

    # Pumps
    assert device.filtration_pump_running is True
    assert device.floc_pump_running is False

    # Flow rates (sub-frame 3)
    assert device.flowrate_ph_minus == 60  # byte[95] = 0x3c
    assert device.flowrate_chlor == 60  # byte[99] = 0x3c (OXY Pure pump slot)
    assert device.flowrate_floc == 10  # byte[101] = 0x0a

    # Basic data
    assert device.serial_number == 110_157_165
    assert device.ph == pytest.approx(7.17, abs=0.01)
    assert device.water_temperature == pytest.approx(9.5, abs=0.1)
    assert device.water_flow_to_probes is True
    assert device.required_ph == pytest.approx(7.2, abs=0.01)
    assert device.required_water_temperature == 25
    assert device.pool_volume == 41


def test_decode_oxy_floc_pump_running() -> None:
    """Decode the OXY frame where the flocculant pump is running.

    Real frame captured 2026-04-02 19:33:52. Only change vs normal frame:
    byte[29] 0x08 → 0x28 (bit 0x20 set = flocculant pump confirmed).
    """
    device = AsekoDecoder.decode(_oxy_bytes(_OXY_FLOC_HEX))

    assert device.device_type == AsekoDeviceType.OXY
    assert device.filtration_pump_running is True
    assert device.floc_pump_running is True

    # All other OXY fields still intact
    assert device.cl_free is None
    assert device.redox is None
    assert device.required_oxy_dose == 8
    assert device.flowrate_floc == 10
