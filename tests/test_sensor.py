import pytest
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity

from custom_components.aseko_local.sensor import (
    async_setup_entry,
    AsekoLocalSensorEntity,
)
from custom_components.aseko_local.aseko_decoder import AsekoDecoder

from custom_components.aseko_local.const import WATER_FLOW_TO_PROBES
from custom_components.aseko_local.aseko_data import AsekoDeviceType


# Helper function to create a base bytearray for a device
def _make_salt_redox_bytes() -> bytearray:
    """Create a base bytearray with almost all possible entities."""

    data = bytearray([0xFF] * 120)
    data[0:4] = (1234).to_bytes(4, "big")  # serial_number
    data[4] = 0x0E  # SALT with REDOX probe
    data[6] = 24  # year (2024)
    data[7] = 6  # month
    data[8] = 15  # day
    data[9] = 12  # hour
    data[10] = 34  # minute
    data[11] = 56  # second
    data[14:16] = (700).to_bytes(2, "big")  # pH = 7.00
    data[16:18] = (680).to_bytes(2, "big")  # Redox = 650 mv
    data[20] = 32  # salinity = 3.2
    data[21] = 80  # electrolyzer_power
    data[25:27] = (245).to_bytes(2, "big")  # water_temperature = 24.5
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x10  # Electrolyzer on
    data[52] = 70  # required_ph = 7.0
    data[53] = 65  # required_redox = 650
    data[54] = 5  # required_algicide
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
    data[95] = 255  # flowrate_chlor
    data[94:96] = (60).to_bytes(2, "big")  # max_filling_time
    data[97] = 255  # flowrate_ph_plus
    data[99] = 60  # flowrate_ph_minus (not measured)
    data[101] = 70  # flowrate_floc
    data[106:108] = (30).to_bytes(2, "big")  # delay_after_dose
    return data


def _make_salt_clf_bytes() -> bytearray:
    """Create a base bytearray with almost all possible entities."""

    data = bytearray([0xFF] * 120)
    data[0:4] = (1234).to_bytes(4, "big")  # serial_number
    data[4] = 0x0D  # SALT with CLF probe
    data[6] = 24  # year (2024)
    data[7] = 6  # month
    data[8] = 15  # day
    data[9] = 12  # hour
    data[10] = 34  # minute
    data[11] = 56  # second
    data[14:16] = (700).to_bytes(2, "big")  # pH = 7.00
    data[16:18] = (100).to_bytes(2, "big")  # CL free = 1.00 mg/L
    data[20] = 32  # salinity = 3.2
    data[21] = 80  # electrolyzer_power
    data[25:27] = (245).to_bytes(2, "big")  # water_temperature = 24.5
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x50  # pump_running + Electrolyzer LEFT
    data[52] = 70  # required_ph = 7.0
    data[53] = 30  # required_cl = 3.0
    data[54] = 5  # required_algicide
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
    data[95] = 255  # flowrate_chlor
    data[94:96] = (60).to_bytes(2, "big")  # max_filling_time
    data[97] = 20  # flowrate_ph_plus
    data[99] = 255  # flowrate_ph_minus (not measured)
    data[101] = 255  # flowrate_floc
    data[106:108] = (30).to_bytes(2, "big")  # delay_after_dose
    return data


def _make_net_clf_bytes() -> bytearray:
    """Create a base bytearray for test data with default values for Aseko NET with CLF and PH."""
    """with CL free and cl free mV and PH no redox"""

    # data = bytearray.fromhex(
    #     "069187240901ffffffffffff000402d10024ffff0026ff00050147ff000001e90000000000ff0017"
    #     "069187240903ffffffffffff470a08ffffffffffffffffff028a0147ffffffffffffffffffffff1f"
    #     "069187240902ffffffffffff0001003cffff003cffff010383ff00781e02581e28ffffffff0049a9"
    # )

    data = bytearray([0xFF] * 120)
    data[0:4] = (110200612).to_bytes(4, "big")  # serial_number / HEX: 0x06918724
    data[4] = 9  # probe info / HEX: 0x09
    data[6] = 255  # year / HEX: 0xff
    data[7] = 255  # month / HEX: 0xff
    data[8] = 255  # day / HEX: 0xff
    data[9] = 255  # hour / HEX: 0xff
    data[10] = 255  # minute / HEX: 0xff
    data[11] = 255  # second / HEX: 0xff
    data[14:16] = (721).to_bytes(2, "big")  # ph_value / HEX: 0x02d1
    data[16:18] = (36).to_bytes(2, "big")  # cl_free or redox / HEX: 0x0024
    data[18:20] = (65535).to_bytes(2, "big")  # redox / HEX: 0xffff
    data[20] = 0  # salinity / HEX: 0x00
    data[21] = 38  # electrolyzer_power / HEX: 0x26
    data[20:22] = (38).to_bytes(2, "big")  # cl_free_mv / HEX: 0x0026
    data[25:27] = (327).to_bytes(2, "big")  # water_temperature / HEX: 0x0147
    data[28] = 0  # water_flow_probe / HEX: 0x00
    data[29] = 0  # pump_or_electrolizer / HEX: 0x00
    data[52] = 71  # required_ph / HEX: 0x47
    data[53] = 10  # required_cl_free_or_redox / HEX: 0x0a
    data[54] = 8  # required_algicide / HEX: 0x08
    data[55] = 255  # required_water_temperature / HEX: 0xff
    data[56:58] = (65535).to_bytes(2, "big")  # start_1_time / HEX: 0xffff
    data[58:60] = (65535).to_bytes(2, "big")  # stop_1_time / HEX: 0xffff
    data[60:62] = (65535).to_bytes(2, "big")  # start_2_time / HEX: 0xffff
    data[62:64] = (65535).to_bytes(2, "big")  # stop_2_time / HEX: 0xffff
    data[68] = 255  # backwash_every_n_days / HEX: 0xff
    data[69:71] = (65535).to_bytes(2, "big")  # backwash_time / HEX: 0xffff
    data[71] = 255  # backwash_duration / HEX: 0xff
    data[74:76] = (65535).to_bytes(2, "big")  # delay_after_startup / HEX: 0xffff
    data[92:94] = (1).to_bytes(2, "big")  # pool_volume / HEX: 0x0001
    data[94:96] = (60).to_bytes(2, "big")  # max_filling_time / HEX: 0x003c
    data[95] = 60  # flowrate_chlor / HEX: 0x3c
    data[97] = 255  # flowrate_ph_plus / HEX: 0xff
    data[99] = 60  # flowrate_ph_minus / HEX: 0x3c
    data[101] = 255  # flowrate_floc / HEX: 0xff
    data[106:108] = (120).to_bytes(2, "big")  # delay_after_dose / HEX: 0x0078
    return data


def _make_profi_clf_redox_bytes() -> bytearray:
    """Create a base bytearray for Aseko Profi with CL and REDOX probe."""

    data = bytearray([0xFF] * 120)
    data[0:4] = (1234).to_bytes(4, "big")  # serial_number
    data[4] = 0x08  # PROFI with CL and REDOX probe
    data[6] = 24  # year (2024)
    data[7] = 6  # month
    data[8] = 15  # day
    data[9] = 12  # hour
    data[10] = 34  # minute
    data[11] = 56  # second
    data[14:16] = (800).to_bytes(2, "big")  # pH = 7.00
    data[16:18] = (100).to_bytes(2, "big")  # Redox
    data[18:20] = (650).to_bytes(2, "big")  # Redox = 650 mv if Byte 18 and 19
    # are not UNSPECIFIED
    data[25:27] = (245).to_bytes(2, "big")  # water_temperature = 24.5
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x08  # pump_running
    data[52] = 70  # required_ph = 7.0
    data[53] = 30  # required_cl = 3.0
    data[54] = 5  # required_algicide
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
    data[101] = 255  # flowrate_floc
    data[106:108] = (30).to_bytes(2, "big")  # delay_after_dose
    return data


@pytest.mark.asyncio
async def test_async_setup_salt_redox(hass) -> None:
    """Test that async_setup_entry adds sensor entities for available sensors."""

    # Use the decoder to create a valid device
    raw_bytes = _make_salt_redox_bytes()
    device = AsekoDecoder.decode(raw_bytes)

    class DummyCoordinator:
        def get_devices(self):
            return [device]

    # Create a MagicMock for ConfigEntry with runtime_data attribute
    dummy_entry = MagicMock(spec=ConfigEntry)
    dummy_entry.runtime_data = type(
        "RuntimeData", (), {"coordinator": DummyCoordinator()}
    )

    added_entities = []

    # Correct callback signature for async_add_entities
    def mock_add_entities(
        new_entities, update_before_add=False, *, config_subentry_id=None
    ):
        added_entities.extend(new_entities)

    await async_setup_entry(hass, dummy_entry, mock_add_entities)

    print(device.device_type)
    print(device.electrolyzer_power)

    for entity in added_entities:
        name = getattr(entity.entity_description, "key", "unknown")
        value = entity.native_value
        status = "enabled" if getattr(entity, "enabled", True) else "disabled"
        print(f"Sensor: {name}, Status: {status}, Value: {value}")

    assert device.device_type == AsekoDeviceType.SALT
    assert any(isinstance(e, AsekoLocalSensorEntity) for e in added_entities)
    assert any(
        getattr(e.device, "serial_number", None) == device.serial_number
        for e in added_entities
    )
    assert len(added_entities) == 13  # 1 sensors should be added for
    assert any(
        getattr(e.entity_description, "key", None) != "free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) != "free_chlorine_mv"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) != "required_free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "rx" for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "required_rx"
        for e in added_entities
    )


@pytest.mark.asyncio
async def test_async_setup_salt_clf(hass) -> None:
    """Test that async_setup_entry adds sensor entities for available sensors."""

    # Use the decoder to create a valid device
    raw_bytes = _make_salt_clf_bytes()
    device = AsekoDecoder.decode(raw_bytes)

    class DummyCoordinator:
        def get_devices(self):
            return [device]

    # Create a MagicMock for ConfigEntry with runtime_data attribute
    dummy_entry = MagicMock(spec=ConfigEntry)
    dummy_entry.runtime_data = type(
        "RuntimeData", (), {"coordinator": DummyCoordinator()}
    )

    added_entities = []

    # Correct callback signature for async_add_entities
    def mock_add_entities(
        new_entities, update_before_add=False, *, config_subentry_id=None
    ):
        added_entities.extend(new_entities)

    await async_setup_entry(hass, dummy_entry, mock_add_entities)

    print(device.device_type)
    print(device.electrolyzer_power)

    for entity in added_entities:
        name = getattr(entity.entity_description, "key", "unknown")
        value = entity.native_value
        status = "enabled" if getattr(entity, "enabled", True) else "disabled"
        print(f"Sensor: {name}, Status: {status}, Value: {value}")

    assert device.device_type == AsekoDeviceType.SALT
    assert any(isinstance(e, AsekoLocalSensorEntity) for e in added_entities)
    assert any(
        getattr(e.device, "serial_number", None) == device.serial_number
        for e in added_entities
    )
    assert len(added_entities) == 13  # 1 sensors should be added for
    assert any(
        getattr(e.entity_description, "key", None) == "free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "free_chlorine_mv"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "required_free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) != "rx" for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) != "required_rx"
        for e in added_entities
    )


@pytest.mark.asyncio
async def test_async_setup_net_clf(hass) -> None:
    """Test that async_setup_entry adds sensor entities for available sensors."""

    # Use the decoder to create a valid device
    raw_bytes = _make_net_clf_bytes()
    device = AsekoDecoder.decode(raw_bytes)

    class DummyCoordinator:
        def get_devices(self):
            return [device]

    # Create a MagicMock for ConfigEntry with runtime_data attribute
    dummy_entry = MagicMock(spec=ConfigEntry)
    dummy_entry.runtime_data = type(
        "RuntimeData", (), {"coordinator": DummyCoordinator()}
    )

    added_entities = []

    # Correct callback signature for async_add_entities
    def mock_add_entities(
        new_entities, update_before_add=False, *, config_subentry_id=None
    ):
        added_entities.extend(new_entities)

    await async_setup_entry(hass, dummy_entry, mock_add_entities)

    print(device.device_type)

    for entity in added_entities:
        name = getattr(entity.entity_description, "key", "unknown")
        value = entity.native_value
        status = "enabled" if getattr(entity, "enabled", True) else "disabled"
        print(f"Sensor: {name}, Status: {status}, Value: {value}")

    assert device.device_type == AsekoDeviceType.NET
    assert any(isinstance(e, AsekoLocalSensorEntity) for e in added_entities)
    assert any(
        getattr(e.device, "serial_number", None) == device.serial_number
        for e in added_entities
    )
    assert len(added_entities) == 9  # 9 sensors should be added for
    assert any(
        getattr(e.entity_description, "key", None) == "free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "free_chlorine_mv"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "required_free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) != "rx" for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) != "required_rx"
        for e in added_entities
    )


@pytest.mark.asyncio
async def test_async_setup_profi_clf_redox(hass) -> None:
    """Test that async_setup_entry adds sensor entities for available sensors."""

    # Use the decoder to create a valid device
    raw_bytes = _make_profi_clf_redox_bytes()
    device = AsekoDecoder.decode(raw_bytes)

    class DummyCoordinator:
        def get_devices(self):
            return [device]

    # Create a MagicMock for ConfigEntry with runtime_data attribute
    dummy_entry = MagicMock(spec=ConfigEntry)
    dummy_entry.runtime_data = type(
        "RuntimeData", (), {"coordinator": DummyCoordinator()}
    )

    added_entities = []

    # Correct callback signature for async_add_entities
    def mock_add_entities(
        new_entities, update_before_add=False, *, config_subentry_id=None
    ):
        added_entities.extend(new_entities)

    await async_setup_entry(hass, dummy_entry, mock_add_entities)

    print(device.device_type)

    for entity in added_entities:
        name = getattr(entity.entity_description, "key", "unknown")
        value = entity.native_value
        status = "enabled" if getattr(entity, "enabled", True) else "disabled"
        print(f"Sensor: {name}, Status: {status}, Value: {value}")

    assert device.device_type == AsekoDeviceType.PROFI
    assert any(isinstance(e, AsekoLocalSensorEntity) for e in added_entities)
    assert any(
        getattr(e.device, "serial_number", None) == device.serial_number
        for e in added_entities
    )
    assert len(added_entities) == 11  # 11 sensors should be added for
    assert any(
        getattr(e.entity_description, "key", None) == "free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "free_chlorine_mv"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "required_free_chlorine"
        for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) == "rx" for e in added_entities
    )
    assert any(
        getattr(e.entity_description, "key", None) != "required_rx"
        for e in added_entities
    )
