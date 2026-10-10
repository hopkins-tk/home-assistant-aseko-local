"""Tests for the setpoint/schedule sensor descriptions."""

from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.sensor import SENSORS, _delay_unit

from .test_decode_v7 import _make_base_bytes
from .test_decode_v8 import REFERENCE_FRAME


def _value(key: str) -> object:
    """Decode the base test frame and return the value_fn output for a sensor key."""
    device = decode(bytes(_make_base_bytes()))
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


def test_delay_unit_follows_the_protocol() -> None:
    """R3: v7 delays are seconds, v8 delays minutes — the entity says which."""

    v7 = decode(bytes(_make_base_bytes()))
    v8 = decode(REFERENCE_FRAME)
    for key in ("delay_after_startup", "delay_after_dose"):
        description = next(d for d in SENSORS if d.key == key)
        assert description.unit_fn is _delay_unit
        assert description.unit_fn(v7) == "s"
        assert description.unit_fn(v8) == "min"
