"""Whether "Waterlevel" (the level meter) is enabled in the unit's configuration.

v7: byte[37] bit 0x40.  Confirmed on an ASIN AQUA Salt: switching Waterlevel
OFF cleared the bit and ON set it again (2026-09-13 marked test cases).  Winter
mode clears it too, because the unit stops level control in winter.

This is the bit the decoder once took for a HOME "firmware A / B" split:
"firmware A" units have the level meter enabled, "firmware B" ones do not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


MASK = 0x40


class WaterLevelSensorEnabled(Feature):
    """v7: byte[37] bit 0x40."""

    field = "water_level_sensor_enabled"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        return flag_or_none(frame[37], MASK)
