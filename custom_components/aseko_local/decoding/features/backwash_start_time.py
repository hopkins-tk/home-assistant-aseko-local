"""Time of day the scheduled backwash starts.  v7: bytes 69-70 (hour, minute).

Backwash schedule, bytes 68-71, on every model with a backwash valve.  NET
(Aqua NET) is a measurement and dosing unit with neither a filter nor a
backwash valve; before profiles, reading these bytes on every model surfaced
phantom backwash entities from a NET frame carrying non-0xFF data there
(Issue #129), so no NET profile lists them.
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


class BackwashStartTime(Feature):
    """v7: bytes 69-70."""

    field = "backwash_start_time"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> time | NotPresent:
        return time_or_absent(frame[69:71])
