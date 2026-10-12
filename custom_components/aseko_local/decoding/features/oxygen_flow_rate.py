"""Configured OXY Pure pump flow rate (ml/min).

v7: byte[99] on ASIN AQUA Oxygen (confirmed), the slot that is the chlorine
pump on every other model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class OxygenFlowRate(Feature):
    """v7: byte[99]."""

    field = "oxygen_flow_rate"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[99])
