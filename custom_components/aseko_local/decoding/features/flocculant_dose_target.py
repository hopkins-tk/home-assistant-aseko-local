"""Flocculant dose setpoint (ml/h).

Independent ports (OXY, HOME): byte[54].  Confirmed on OXY (2026-04-11,
    value 10) and HOME (2026-04-28, serial 110128063, value 10).
Shared port (SALT, NET): byte[54] as well, but ours only while byte[37] bit
    0x80 is clear; see flocculant_flow_rate for the routing.
v8: areqs[3], ours only while fncs[6] says the third port is flocculant (18).
    An ASIN Aqua Salt NET switched to flocculant 10 ml/h sent areqs[3] = 10,
    and 0 while the port was algicide (Issue #131).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import THIRD_PUMP_FLOCCULANT, byte_or_absent, byte_when_flags
from ..presence import NOT_PRESENT

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


# byte[37] bit 0x80 routes the shared third-pump port: set for algicide,
# clear for flocculant
SHARED_PORT_ROUTING = 0x80
ROUTED_TO_FLOCCULANT = 0x00


class FlocculantDoseTarget(Feature):
    """v7: byte[54], on a shared port only while byte[37] routes it to flocculant."""

    field = "flocculant_dose_target"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        """Independent flocculant port."""
        return byte_or_absent(frame[54])

    def decode_v7_routed_by_byte37(
        self, frame: V7Frame, device: AsekoDevice
    ) -> int | NotPresent:
        """Shared third-pump port, ours only while byte[37] bit 0x80 is clear."""
        return byte_when_flags(
            frame[54], frame[37], SHARED_PORT_ROUTING, ROUTED_TO_FLOCCULANT
        )

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int | NotPresent | None:
        ours = frame.third_pump_is(THIRD_PUMP_FLOCCULANT)
        if ours is None:
            return None
        return frame.value("areqs", 3) if ours else NOT_PRESENT
