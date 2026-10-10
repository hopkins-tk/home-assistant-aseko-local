"""What heating control waits for: nothing, a time window, or the outside temperature.

v7: byte[22] bits 0x01 (heating time window), 0x02 (heat by outside
temperature) and 0x20 (outside temperature below the threshold; clear =
above).  The window and the outside temperature exclude each other: choosing
one cleared the other's bit.  Confirmed on an ASIN AQUA Salt (2026-09-13/14
marked test cases).  The window's times and the temperature threshold are
not in the frame.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...const import UNSPECIFIED_VALUE
from ...models import AsekoHeatingCondition
from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


TIME_WINDOW = 0x01
OUTSIDE_TEMPERATURE = 0x02
BELOW = 0x20


class HeatingCondition(Feature):
    """v7: byte[22] bits 0x01 / 0x02 / 0x20."""

    field = "heating_condition"

    @override
    def decode_v7(
        self, frame: V7Frame, device: AsekoDevice
    ) -> AsekoHeatingCondition | None:
        b = frame[22]
        if b == UNSPECIFIED_VALUE:
            return None  # this frame does not say
        if b & TIME_WINDOW and b & OUTSIDE_TEMPERATURE:
            return None  # never seen together
        if b & TIME_WINDOW:
            return AsekoHeatingCondition.TIME_WINDOW
        if b & OUTSIDE_TEMPERATURE:
            if b & BELOW:
                return AsekoHeatingCondition.OUTSIDE_TEMPERATURE_BELOW
            return AsekoHeatingCondition.OUTSIDE_TEMPERATURE_ABOVE
        return AsekoHeatingCondition.ALWAYS
