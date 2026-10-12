"""The variable-speed pump (VSP) type selected in the unit's configuration.

v7: byte[78] bits 0x0C.  The unit stores a pump protocol, not a brand, so
brands sharing one read the same (HOME PRO manuals call them type A, B, C):

    0x00 = Speck / Uwe EO PM   0x04 = Pentair / Dab E.SWIM   0x08 = Hayward

Confirmed on an ASIN AQUA Salt by selecting every brand in turn, with the
pump on and off (2026-09-13/14 marked test cases): the type stays stored
while the pump is switched off.  The same values on HOME (Issue #137:
0x22 / 0x26 / 0x2a).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...const import UNSPECIFIED_VALUE
from ...models import AsekoVariableSpeedPumpType
from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


TYPE_BITS = 0x0C
_BY_BITS = {
    0x00: AsekoVariableSpeedPumpType.SPECK_UWE,
    0x04: AsekoVariableSpeedPumpType.PENTAIR_DAB,
    0x08: AsekoVariableSpeedPumpType.HAYWARD,
}


class VariableSpeedPumpType(Feature):
    """v7: byte[78] bits 0x0C."""

    field = "variable_speed_pump_type"

    @override
    def decode_v7(
        self, frame: V7Frame, device: AsekoDevice
    ) -> AsekoVariableSpeedPumpType | None:
        if frame[78] == UNSPECIFIED_VALUE:
            return None  # this frame does not say
        return _BY_BITS.get(frame[78] & TYPE_BITS)
