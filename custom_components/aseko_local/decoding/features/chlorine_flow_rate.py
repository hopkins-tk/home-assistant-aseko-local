"""Configured chlorine pump flow rate (ml/min).

v7: byte[99] on every model but OXY, where the same byte is the OXY Pure
pump (see oxygen_flow_rate).  v8 does not transmit it; 60 ml/min is assumed so
the consumption counters have something to integrate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


ASSUMED_V8_FLOWRATE = 60


class ChlorineFlowRate(Feature):
    """v7: byte[99].  v8: assumed 60."""

    field = "chlorine_flow_rate"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[99])

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int:
        return ASSUMED_V8_FLOWRATE
