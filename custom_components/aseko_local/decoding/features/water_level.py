"""Current water level (cm).  v7: byte[27].

Water level, on models with a level probe and a filling valve.  Confirmed
byte positions (domin211, DomSchCoding #100, Issue #110):

    byte[27]  = current level (cm)
    byte[29] bit 0x02 = filling valve open
    byte[102] = low alarm threshold (cm)
    byte[103] = filling ON threshold (cm)
    byte[104] = filling OFF threshold (cm)
    byte[105] = high alarm threshold (cm)

NET carries unrelated non-0xFF data in bytes 102-104, so no NET profile
lists these.  OXY has no level probe and sends its algicide flow rate in
byte[103] instead.  HOME uses bytes 102-105 for the level thresholds like
SALT (confirmed there against the unit, 2026-09-11); where HOME sends its
algicide flow rate is not known.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent
from ..presence import NOT_PRESENT

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


LEVEL_SENSOR_DISCONNECTED = 0xFE  # manufacturer's RS485 protocol document


class WaterLevel(Feature):
    """v7: byte[27]; 0xFE = level sensor disconnected."""

    field = "water_level"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        if frame[27] == LEVEL_SENSOR_DISCONNECTED:
            # No sensor is wired (every captured OXY frame reads 0xFE) or it
            # dropped out.  Absent rather than 254 cm: a unit that never had
            # one gets no entity, and presence is sticky, so an existing
            # entity just shows no value while the sensor is off.
            return NOT_PRESENT
        return byte_or_absent(frame[27])
