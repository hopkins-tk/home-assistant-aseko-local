"""Test the Aseko Decoder."""

from datetime import time

from custom_components.aseko_local.aseko_data import (
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
)
from custom_components.aseko_local.aseko_decoder import AsekoDecoder
from custom_components.aseko_local.const import (
    ELECTROLYZER_RUNNING,
    ELECTROLYZER_RUNNING_LEFT,
    WATER_FLOW_TO_PROBES,
    YEAR_OFFSET,
)


def _make_base_bytes(size: int = 120) -> bytearray:
    """Create a base bytearray for test data with default values."""

    data = bytearray(size)
    data[0:4] = (1234).to_bytes(4, "big")  # serial_number
    data[4] = 0x02  # REDOX probe
    data[6] = 24  # year (2024)
    data[7] = 6  # month
    data[8] = 15  # day
    data[9] = 12  # hour
    data[10] = 34  # minute
    data[11] = 56  # second
    data[25:27] = (245).to_bytes(2, "big")  # water_temperature = 24.5
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x08  # pump_running
    data[54] = 5  # required_algicide
    data[55] = 28  # required_temperature
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
    data[92:94] = (5000).to_bytes(2, "big")  # pool_volume
    data[94:96] = (60).to_bytes(2, "big")  # max_filling_time
    data[74:76] = (120).to_bytes(2, "big")  # delay_after_startup
    data[106:108] = (30).to_bytes(2, "big")  # delay_after_dose
    return data


def test_decode_redox() -> None:
    """Test decoding of Redox probe data."""

    data = _make_base_bytes()
    data[4] = 0x02  # Redox probe
    data[18:20] = (550).to_bytes(2, "big")  # Redox
    data[53] = 65  # required Redox

    device = AsekoDecoder.decode(bytes(data))
    assert device.required_redox == 650
    assert device.redox == 550


def test_decode_clf() -> None:
    """Test decoding of CL free probe data."""

    data = _make_base_bytes()
    data[4] = 0x01  # CL probe
    data[16:18] = (50).to_bytes(2, "big")  # CL free
    data[53] = 9  # required CL free

    device = AsekoDecoder.decode(bytes(data))
    assert device.required_cl_free == 0.9
    assert device.cl_free == 0.5


def test_decode_home() -> None:
    """Test decoding of HOME device data."""

    data = _make_base_bytes()
    data[14:16] = (720).to_bytes(2, "big")  # ph
    data[52] = 72  # required_ph

    device = AsekoDecoder.decode(bytes(data))
    assert device.type == AsekoDeviceType.HOME
    assert device.serial_number == 1234
    assert device.ph == 7.2
    assert device.required_ph == 7.2
    assert device.water_temperature == 24.5
    assert device.pump_running is True
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
    assert device.required_temperature == 28
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
    data[20] = 32  # salinity = 3.2
    data[21] = 80  # electrolyzer_power
    data[29] = ELECTROLYZER_RUNNING  # electrolyzer_active
    data[16:18] = (50).to_bytes(2, "big")  # cl_free < MAX_CLF_LIMIT
    data[14:16] = (700).to_bytes(2, "big")  # ph
    data[52] = 70

    device = AsekoDecoder.decode(bytes(data))
    assert device.type == AsekoDeviceType.SALT
    assert device.salinity == 3.2
    assert device.electrolyzer_power == 80
    assert device.electrolyzer_active is True
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.RIGHT


def test_decode_electrolyzer_data_left_direction() -> None:
    """Test decoding of electrolyzer data with left direction."""

    data = _make_base_bytes()
    data[20] = 32
    data[21] = 80
    data[29] = ELECTROLYZER_RUNNING_LEFT

    device = AsekoDecoder.decode(bytes(data))
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.LEFT


def test_decode_electrolyzer_data_waiting_direction() -> None:
    """Test decoding of electrolyzer data with waiting direction."""

    data = _make_base_bytes()
    data[20] = 32
    data[21] = 80
    data[29] = 0  # neither running nor left

    device = AsekoDecoder.decode(bytes(data))
    assert device.electrolyzer_direction == AsekoElectrolyzerDirection.WAITING


def test_decode_profi() -> None:
    """Test decoding of PROFI device data."""

    data = _make_base_bytes()
    data[4] = 0x03  # Redox & CLF probe
    data[16:18] = (100).to_bytes(2, "big")
    data[18:20] = (200).to_bytes(2, "big")
    data[14:16] = (800).to_bytes(2, "big")
    data[52] = 80
    data[53] = 20

    device = AsekoDecoder.decode(bytes(data))
    assert device.type == AsekoDeviceType.PROFI
    assert device.ph == 8.0
    assert device.redox == 200
    assert device.cl_free == 1.0
    assert device.required_ph == 8.0
    assert device.required_redox == 200
    assert device.required_cl_free == 2.0


def test_decode_net() -> None:
    """Test decoding of NET device data."""

    data = _make_base_bytes(111)

    device = AsekoDecoder.decode(bytes(data))
    assert device.type == AsekoDeviceType.NET
