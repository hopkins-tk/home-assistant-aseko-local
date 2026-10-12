"""Backwash duration (seconds).  v7: byte[71] * 10.

Backwash schedule, bytes 68-71, on every model with a backwash valve.  NET
(Aqua NET) is a measurement and dosing unit with neither a filter nor a
backwash valve; before profiles, reading these bytes on every model surfaced
phantom backwash entities from a NET frame carrying non-0xFF data there
(Issue #129), so no NET profile lists them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...const import UNSPECIFIED_VALUE
from ..feature import Feature
from ..presence import NOT_PRESENT

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class BackwashDuration(Feature):
    """v7: byte[71] * 10."""

    field = "backwash_duration"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        if frame[71] == UNSPECIFIED_VALUE:
            return NOT_PRESENT
        return frame[71] * 10
