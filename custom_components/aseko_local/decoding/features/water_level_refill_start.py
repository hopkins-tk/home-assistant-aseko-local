"""Level at which filling starts (cm).  v7: byte[103].

Water level, on models with a level probe and a filling valve.  Confirmed
byte positions (domin211, DomSchCoding #100, Issue #110):

    byte[27]  = current level (cm)
    byte[29] bit 0x02 = filling valve open
    byte[102] = low alarm threshold (cm)
    byte[103] = filling ON threshold (cm)
    byte[104] = filling OFF threshold (cm)
    byte[105] = high alarm threshold (cm)

NET carries unrelated non-0xFF data in bytes 102-104, so no NET profile
lists these.  byte[103] doubles as algaecide_flow_rate on OXY and HOME, whose
independent-port layout reads it for both; SALT ignores it there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class WaterLevelRefillStart(Feature):
    """v7: byte[103]."""

    field = "water_level_refill_start"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[103])
