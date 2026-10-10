"""Measured salinity (kg/m3).

v7: byte[20] / 10.  v8: ains[8] / 10, confirmed on an ASIN Aqua Salt NET
whose display read 10.1 with ains[8] = 101 in the same minute (Issue #131).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


class Salinity(Feature):
    """v7: byte[20] / 10; 0xFF (not filled in) reads unknown, not 25.5.  v8: ains[8] / 10."""

    field = "salinity"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> float | None:
        value = byte_or_none(frame[20])
        return None if value is None else value / 10

    @override
    def decode_v8(
        self, frame: V8Frame, device: AsekoDevice
    ) -> float | NotPresent | None:
        return frame.measurement("ains", 8, 10)
