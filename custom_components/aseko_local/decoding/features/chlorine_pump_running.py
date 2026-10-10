"""Whether the chlorine dosing pump is running.

v7: byte[29] bit 0x40 on HOME and PROFI (uncertain -- the HOME port can be
configured as chlorine or OXY Pure and the routing byte is unknown), bit 0x02
on NET (confirmed: Issue #66).  v8: outs[9].
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


CL_PUMP = 0x40  # HOME, PROFI: uncertain
CL_PUMP_NET = 0x02  # NET: confirmed, Issue #66


class ChlorinePumpRunning(Feature):
    """v7: byte[29] bit 0x40, or bit 0x02 on NET.  v8: outs[9]."""

    field = "chlorine_pump_running"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool:
        return bool(frame[29] & CL_PUMP)

    def decode_v7_net(self, frame: V7Frame, device: AsekoDevice) -> bool:
        """Read the chlorine pump bit where the NET puts it."""
        return bool(frame[29] & CL_PUMP_NET)

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> bool | None:
        return frame.flag("outs", 9)
