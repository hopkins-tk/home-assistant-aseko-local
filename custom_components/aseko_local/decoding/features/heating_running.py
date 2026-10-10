"""Whether the unit is requesting heat from the configured heater.

v7: byte[29] bit 0x04, the heating demand relay (JS-DE-Tech "relay_byte"
bit 2).  Available on every model with a heating output; NET has none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


HEATING = 0x04


class HeatingRunning(Feature):
    """v7: byte[29] bit 0x04."""

    field = "heating_running"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool:
        return bool(frame[29] & HEATING)
