"""Configured pH-minus pump flow rate (ml/min).

v7: byte[95] on every model.  v8 does not transmit it; 60 ml/min is assumed
so the consumption counters have something to integrate.
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


class PhMinusFlowRate(Feature):
    """v7: byte[95].  v8: assumed 60."""

    field = "ph_minus_flow_rate"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[95])

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int:
        return ASSUMED_V8_FLOWRATE
