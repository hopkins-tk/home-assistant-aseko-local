"""Algicide dose setpoint (ml/m3/day).

Independent ports (OXY, HOME): byte[72].  Confirmed on OXY (2026-04-11,
    value 15) and HOME (2026-04-28, serial 110128063, value 0).
Shared port (SALT, NET): byte[54], ours only while byte[37] bit 0x80 routes
    the port to algicide; see algaecide_flow_rate for the routing.
v8: areqs[4], ours only while fncs[6] says the third port is algicide (10).
    An ASIN Aqua Salt NET set to 5 ml/m3/day sent areqs[4] = 5, and 0 after
    its owner switched the port to flocculant (Issue #131).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import THIRD_PUMP_ALGICIDE, byte_or_absent, byte_when_flags
from ..presence import NOT_PRESENT

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


# byte[37] bit 0x80 routes the shared third-pump port: set for algicide,
# clear for flocculant
SHARED_PORT_ROUTING = 0x80
ROUTED_TO_ALGICIDE = 0x80


class AlgaecideDoseTarget(Feature):
    """v7: byte[72], or byte[54] when byte[37] routes the shared port to algicide."""

    field = "algaecide_dose_target"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        """Independent algicide port."""
        return byte_or_absent(frame[72])

    def decode_v7_routed_by_byte37(
        self, frame: V7Frame, device: AsekoDevice
    ) -> int | NotPresent:
        """Shared third-pump port, ours only while byte[37] bit 0x80 is set."""
        return byte_when_flags(
            frame[54], frame[37], SHARED_PORT_ROUTING, ROUTED_TO_ALGICIDE
        )

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int | NotPresent | None:
        ours = frame.third_pump_is(THIRD_PUMP_ALGICIDE)
        if ours is None:
            return None
        return frame.value("areqs", 4) if ours else NOT_PRESENT
