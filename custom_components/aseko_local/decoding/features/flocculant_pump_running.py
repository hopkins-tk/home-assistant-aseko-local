"""Whether the flocculant dosing pump is running.

v7: byte[29] bit 0x20 (confirmed on OXY: toggles exactly at the 19:33:52 floc
event; confirmed on SALT: Apr 3 frames, same bit as algicide; uncertain on
HOME and PROFI).  Reported only once the flow-rate reading shows the port is
configured for flocculant (see flocculant_flow_rate).


v8: outs[11], the third pump port, which ``fncs[6]`` says the chemical of:
10 algicide, 18 flocculant.  The same unit read 10 with algicide configured
and 18 after its owner switched the port to flocculant (Issue #131,
2026-07-19), and outs[11] was 1 in the capture labelled "algicide pump
running".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import THIRD_PUMP_FLOCCULANT, flag_when_known
from ..presence import NOT_PRESENT
from .flocculant_flow_rate import FlocculantFlowRate

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


FLOC_PUMP = 0x20


class FlocculantPumpRunning(Feature):
    """v7: byte[29] bit 0x20, only while a flow rate is configured."""

    field = "flocculant_pump_running"
    depends_on = (FlocculantFlowRate,)
    # v8 has no flow rates; there the chemical comes from fncs[6]
    optional_depends_on = (FlocculantFlowRate,)

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | NotPresent:
        return flag_when_known(device.flocculant_flow_rate, frame[29], FLOC_PUMP)

    @override
    def decode_v8(
        self, frame: V8Frame, device: AsekoDevice
    ) -> bool | NotPresent | None:
        ours = frame.third_pump_is(THIRD_PUMP_FLOCCULANT)
        if ours is None:
            return None
        return frame.flag("outs", 11) if ours else NOT_PRESENT
