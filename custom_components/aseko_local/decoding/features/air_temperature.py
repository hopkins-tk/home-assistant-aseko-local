"""Measured air (ambient) temperature (degrees C).

16-bit big-endian two's complement at bytes 23-24, / 10 -- the same encoding
as water_temperature, which sits directly after it.  Confirmed on an ASIN
AQUA Salt against two diagnostics dumps, both matching the unit
display:

    2026-08-11 10:33 -> 0x0168 = 36.0 C air | 0x0128 = 29.6 C water
    2026-08-17 18:50 -> 0x0134 = 30.8 C air | 0x0122 = 29.0 C water

Signedness: read unsigned, units without an air probe decode to 6513.6 C
(0xFE70) and 6502.8 C (0xFDC4); as two's complement the same bytes read
-40.0 C and -57.2 C, i.e. an open-circuit input.  A genuine sub-zero reading
has not been captured yet, so the plausibility window below keeps both
sentinels out either way.  0xFFFF is rejected before the window because as a
signed value it would read a plausible -0.1 C.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...const import UNSPECIFIED_VALUE
from ..feature import Feature
from ..presence import NOT_PRESENT

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


# Units without an air probe report an open-circuit value here (-40.0 C and
# -57.2 C were both observed), and unrelated data lands in these bytes on
# models that do not carry the field.  Anything outside this window is
# reported as "not measured".
AIR_TEMPERATURE_MIN = -30.0
AIR_TEMPERATURE_MAX = 60.0


class AirTemperature(Feature):
    """v7: bytes 23-24, signed, / 10, within a plausibility window."""

    field = "air_temperature"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> float | NotPresent:
        raw = frame[23:25]
        if all(byte == UNSPECIFIED_VALUE for byte in raw):
            return NOT_PRESENT

        value = int.from_bytes(raw, "big", signed=True) / 10
        if not AIR_TEMPERATURE_MIN <= value <= AIR_TEMPERATURE_MAX:
            return NOT_PRESENT
        return value
