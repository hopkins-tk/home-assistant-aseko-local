"""Tests for the setpoint/schedule sensor descriptions."""

from custom_components.aseko_local.aseko_decoder import AsekoDecoder
from custom_components.aseko_local.sensor import SENSORS

from .test_aseko_decoder import _make_base_bytes


def _value(key: str):
    """Decode the base test frame and return the value_fn output for a sensor key."""
    device = AsekoDecoder.decode(bytes(_make_base_bytes()))
    description = next(d for d in SENSORS if d.key == key)
    return description.value_fn(device)


def test_filtration_schedule_sensors() -> None:
    assert _value("filtration_1_start") == "08:00"
    assert _value("filtration_1_stop") == "10:00"
    assert _value("filtration_2_start") == "14:00"
    assert _value("filtration_2_stop") == "16:00"


def test_pool_volume_sensor() -> None:
    assert _value("pool_volume") == 5000


def test_delay_sensors() -> None:
    assert _value("delay_after_startup") == 120
    assert _value("delay_after_dose") == 30
