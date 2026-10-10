"""Period 1 start of the filtration timer.  v7: bytes 56-57 (hour, minute).

Filtration periods share bytes 56-63 on every model with a filtration output.
The unit keeps sending the last configured period-2 times even after period
2 is disabled at the controller (Issue #133, verified on serial 110169464),
so the bytes are read as-is; whether period 2 is active is what
filtration_schedule says.

v8: reqs[5] is the start hour and reqs[7] the stop hour, whole hours only.
A unit set to a timer from 08:00 to 20:00 sends 8 and 20; a unit running
nonstop sends 0 and 24, which is midnight to midnight (Issue #131, two
units).  24 is read as 00:00, and filtration_schedule says which of the two
a 00:00 - 00:00 pair is.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import time_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


#: v8 sends whole hours; 24 is midnight at the end of the day.
HOURS_IN_A_DAY = 24


def hour_or_none(value: int | None) -> time | None:
    """Return a whole hour as a time; 24 (end of the day) as 00:00."""
    if value is None or not 0 <= value <= HOURS_IN_A_DAY:
        return None
    return time(hour=value % HOURS_IN_A_DAY)


class FiltrationPeriod1Start(Feature):
    """v7: bytes 56-57.  v8: reqs[5], a whole hour."""

    field = "filtration_period_1_start"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> time | NotPresent:
        return time_or_absent(frame[56:58])

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> time | None:
        return hour_or_none(frame.value("reqs", 5))
