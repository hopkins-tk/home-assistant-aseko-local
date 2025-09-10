import pytest
from unittest.mock import AsyncMock

from custom_components.aseko_local.sensor import (
    async_setup_entry,
    AsekoLocalSensorEntity,
    SENSORS,
)
from custom_components.aseko_local.aseko_data import AsekoDevice


# Helper function to create a base bytearray for a device
def _make_base_bytes() -> bytearray:
    """Create a base bytearray for test data with default values."""

    data = bytearray(120)
    data[0:4] = (1234).to_bytes(4, "big")  # serial_number
    data[4] = 0x0E  # SALT with REDOX probe
    data[6] = 24  # year (2024)
    data[7] = 6  # month
    data[8] = 15  # day
    data[9] = 12  # hour
    data[10] = 34  # minute
    data[11] = 56  # second
    data[14:16] = (700).to_bytes(2, "big")  # pH = 7.00
    data[16:18] = (650).to_bytes(2, "big")  # redox = 650 mV
    data[18:20] = (200).to_bytes(2, "big")  # chlorine = 2.00 mg/L
    data[20] = 32  # salinity = 3.2
    data[21] = 80  # electrolyzer_power
    data[25:27] = (245).to_bytes(2, "big")  # water_temperature = 24.5
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x08  # pump_running
    data[52] = 70  # required_ph = 7.0
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
async def test_async_setup_entry_adds_entities(hass):
    """Test that async_setup_entry adds sensor entities for available sensors."""

    # Create a dummy device from base bytes
    class DummyDevice(AsekoDevice):
        def __init__(self):
            # You may need to adjust this depending on your AsekoDevice implementation
            super().__init__(raw=_make_base_bytes())
            # self.serial_number = "12345678"
            # self.air_temperature = 25
            # self.ph = 7.2

    # Mock coordinator with one device
    class DummyCoordinator:
        def get_devices(self):
            return [DummyDevice()]

    # Mock config entry with runtime_data
    class DummyConfigEntry:
        runtime_data = type("RuntimeData", (), {"coordinator": DummyCoordinator()})

    # Collect added entities
    added_entities = []

    async def mock_add_entities(entities):
        added_entities.extend(entities)

    # Call the setup function
    await async_setup_entry(hass, DummyConfigEntry(), mock_add_entities)

    # Check that at least one sensor entity was added
    assert any(isinstance(e, AsekoLocalSensorEntity) for e in added_entities)
    # Check that the entity has the expected serial number
    assert any(
        getattr(e.device, "serial_number", None) == "1234" for e in added_entities
    )
    # Optionally, check that a pH sensor entity is present
    assert any(e.entity_description.key == "ph" for e in added_entities)
