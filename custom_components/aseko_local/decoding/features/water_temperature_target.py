"""Water temperature setpoint (degrees C).  v7: byte[55]."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class WaterTemperatureTarget(Feature):
    """v7: byte[55]."""

    field = "water_temperature_target"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[55])
