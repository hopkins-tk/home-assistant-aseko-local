"""OXY Pure dose setpoint (ml/m3/day), ASIN AQUA Oxygen only.

v7: byte[53].  The OXY firmware fills the CLF / REDOX slots with the
placeholder 0x001E, which is why no OXY profile lists those setpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


class OxygenDoseTarget(Feature):
    """v7: byte[53]."""

    field = "oxygen_dose_target"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | None:
        return byte_or_none(frame[53])  # None: the OXY dose is not filled in
