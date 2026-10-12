"""Whether the OXY Pure (hydrogen peroxide) dosing pump is running.

v7: byte[29] bit 0x40 on ASIN AQUA Oxygen (confirmed: 2026-04-11 Winnetoux
log, 0x08 -> 0x48 with the pump on).  Reported only once the flow-rate
reading shows the port is configured (see oxygen_flow_rate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_when_known
from .oxygen_flow_rate import OxygenFlowRate

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


OXY_PUMP = 0x40  # confirmed, 2026-04-11


class OxygenPumpRunning(Feature):
    """v7: byte[29] bit 0x40, only while a flow rate is configured."""

    field = "oxygen_pump_running"
    depends_on = (OxygenFlowRate,)

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | NotPresent:
        return flag_when_known(device.oxygen_flow_rate, frame[29], OXY_PUMP)
