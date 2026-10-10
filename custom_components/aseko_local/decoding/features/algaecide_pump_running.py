"""Whether the algicide dosing pump is running.

v7: byte[29] bit 0x20 on SALT (confirmed: 27 algicide frames read 0x28 =
0x08 | 0x20, PR #87), bit 0x10 on OXY (confirmed: 2026-04-11 Winnetoux log,
0x08 -> 0x18 with the pump on).  HOME has the same four independent pump
ports as OXY and reads 0x10 too (``decode_v7_oxy``, assumed); its algicide
flow rate is not located, so no HOME algicide state is reported yet.

On SALT the same bit also means flocculant: one physical port, configured for
either chemical.  Whether the port is set up for algicide at all is settled
by the flow-rate reading (see algaecide_flow_rate), so the pump state is only
reported once that is known.


v8: outs[11], the third pump port, which ``fncs[6]`` says the chemical of:
10 algicide, 18 flocculant.  The same unit read 10 with algicide configured
and 18 after its owner switched the port to flocculant (Issue #131,
2026-07-19), and outs[11] was 1 in the capture labelled "algicide pump
running".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import THIRD_PUMP_ALGICIDE, flag_when_known
from ..presence import NOT_PRESENT
from .algaecide_flow_rate import AlgaecideFlowRate

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


ALGICIDE_PUMP = 0x20  # SALT confirmed (PR #87)
ALGICIDE_PUMP_OXY = 0x10  # OXY confirmed 2026-04-11; HOME assumed


class AlgaecidePumpRunning(Feature):
    """v7: byte[29] bit 0x20 (0x10 on OXY), only while a flow rate is configured."""

    field = "algaecide_pump_running"
    depends_on = (AlgaecideFlowRate,)
    # v8 has no flow rates; there the chemical comes from fncs[6]
    optional_depends_on = (AlgaecideFlowRate,)

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | NotPresent:
        return flag_when_known(device.algaecide_flow_rate, frame[29], ALGICIDE_PUMP)

    def decode_v7_oxy(self, frame: V7Frame, device: AsekoDevice) -> bool | NotPresent:
        """Read the OXY algicide pump bit; absent while no algicide flow rate is set."""
        return flag_when_known(device.algaecide_flow_rate, frame[29], ALGICIDE_PUMP_OXY)

    @override
    def decode_v8(
        self, frame: V8Frame, device: AsekoDevice
    ) -> bool | NotPresent | None:
        ours = frame.third_pump_is(THIRD_PUMP_ALGICIDE)
        if ours is None:
            return None
        return frame.flag("outs", 11) if ours else NOT_PRESENT
