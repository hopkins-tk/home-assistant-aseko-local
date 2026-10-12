"""Whether the variable-speed pump (VSP) is enabled in the unit's configuration.

v7: byte[22] bit 0x08.  A setting, not the pump's run state: on an ASIN AQUA
Salt the bit followed "VS Pump" ON / OFF in the Configuration menu exactly,
for Speck, Pentair, Hayward, Dab and Uwe alike (2026-09-13 marked test
cases), and filtration started right after it was switched on.  Earlier read
as "running" from a HOME unit (0x83 off, 0x8b on).  0xFF = not reported.
The pump type is in variable_speed_pump_type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


VSP_ENABLED = 0x08


class VariableSpeedPumpEnabled(Feature):
    """v7: byte[22] bit 0x08."""

    field = "variable_speed_pump_enabled"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        return flag_or_none(frame[22], VSP_ENABLED)
