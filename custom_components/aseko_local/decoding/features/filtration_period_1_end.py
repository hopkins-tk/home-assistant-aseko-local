"""Period 1 stop of the filtration timer.  v7: bytes 58-59 (hour, minute).

Filtration periods share bytes 56-63 on every model with a filtration output.
The unit keeps sending the last configured period-2 times even after period
2 is disabled at the controller (Issue #133, verified on serial 110169464),
so the bytes are read as-is; whether period 2 is active is what
filtration_schedule says.

v8: reqs[7], the stop hour, whole hours only; 24 (nonstop, midnight at the
end of the day) is read as 00:00.  See filtration_period_1_start.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import time_or_absent
from .filtration_period_1_start import hour_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


class FiltrationPeriod1End(Feature):
    """v7: bytes 58-59.  v8: reqs[7], a whole hour."""

    field = "filtration_period_1_end"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> time | NotPresent:
        return time_or_absent(frame[58:60])

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> time | None:
        return hour_or_none(frame.value("reqs", 7))
