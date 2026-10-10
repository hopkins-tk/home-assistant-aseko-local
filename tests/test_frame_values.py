"""The value helpers features read a frame with: what 0xFF and -500 turn into."""

from __future__ import annotations

import pytest

from custom_components.aseko_local.decoding.frames import (
    V8Frame,
    byte_or_absent,
    byte_or_none,
    byte_when_flags,
    flag_or_none,
    flag_when_known,
)
from custom_components.aseko_local.decoding.presence import NOT_PRESENT


@pytest.mark.parametrize(("value", "expected"), [(0, 0), (54, 54), (0xFE, 0xFE)])
def test_a_filled_in_byte_reads_as_it_is(value, expected) -> None:
    assert byte_or_none(value) == expected
    assert byte_or_absent(value) == expected


def test_an_unfilled_byte_is_unknown_or_absent_depending_on_the_helper() -> None:
    assert byte_or_none(0xFF) is None  # a measurement or setpoint the unit has
    assert byte_or_absent(0xFF) is NOT_PRESENT  # a setting never made


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(0x00, False), (0x08, True), (0xF7, False), (0x0C, True), (0xFF, None)],
)
def test_flag_or_none(flags, expected) -> None:
    assert flag_or_none(flags, 0x08) is expected


def test_flag_when_known_needs_the_required_value() -> None:
    assert flag_when_known(None, 0x20, 0x20) is NOT_PRESENT
    assert flag_when_known(0, 0x20, 0x20) is True  # 0 ml/min is a known value
    assert flag_when_known(60, 0x00, 0x20) is False


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(0x80, 54), (0x00, NOT_PRESENT), (0xFF, NOT_PRESENT)],
)
def test_byte_when_flags_follows_the_routing_bit(flags, expected) -> None:
    assert byte_when_flags(54, flags, 0x80, 0x80) == expected


def _v8(**sections: list[int | None]) -> V8Frame:
    return V8Frame(raw=b"", serial_number=1, header_type=804, sections=sections)


def test_v8_flag() -> None:
    frame = _v8(outs=[0, 1, 2, None])
    assert frame.flag("outs", 0) is False
    assert frame.flag("outs", 1) is True
    assert frame.flag("outs", 2) is True  # any non-zero value is on
    assert frame.flag("outs", 3) is None  # unreadable token
    assert frame.flag("outs", 9) is None  # section too short
    assert frame.flag("ins", 0) is None  # section not sent


def test_v8_measurement() -> None:
    frame = _v8(ains=[708, -500, None])
    assert frame.measurement("ains", 0, divisor=100) == 7.08
    assert frame.measurement("ains", 1, divisor=100) is NOT_PRESENT  # probe not fitted
    assert frame.measurement("ains", 2, divisor=100) is None  # unreadable token
    assert frame.measurement("ains", 7, divisor=100) is None  # not sent
