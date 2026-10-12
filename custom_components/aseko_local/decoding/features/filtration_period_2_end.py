"""Period 2 stop of the filtration timer.  v7: bytes 62-63 (hour, minute).

Filtration periods share bytes 56-63 on every model with a filtration output.
The unit keeps sending the last configured period-2 times even after period
2 is disabled at the controller (Issue #133, verified on serial 110169464),
so the bytes are read as-is; whether period 2 is active is what
filtration_schedule says.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import time_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class FiltrationPeriod2End(Feature):
    """v7: bytes 62-63."""

    field = "filtration_period_2_end"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> time | NotPresent:
        return time_or_absent(frame[62:64])
