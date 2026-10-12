"""Backwash interval (days); 0 = automatic backwash disabled.  v7: byte[68].

Backwash schedule, bytes 68-71, on every model with a backwash valve.  NET
(Aqua NET) is a measurement and dosing unit with neither a filter nor a
backwash valve; before profiles, reading these bytes on every model surfaced
phantom backwash entities from a NET frame carrying non-0xFF data there
(Issue #129), so no NET profile lists them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class BackwashInterval(Feature):
    """v7: byte[68]."""

    field = "backwash_interval"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[68])
