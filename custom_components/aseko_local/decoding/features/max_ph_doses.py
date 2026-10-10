"""Safety function: the maximum number of pH doses.

After this many doses without the pH moving, the unit stops dosing and
raises "Too many doses of pH".

v7: byte[115].  Confirmed on the maintainer's ASIN AQUA Salt on 2026-09-12:
the setting was changed from 20 to 17 on the unit's Safety Functions screen
and byte[115] followed (0x14 -> 0x11) while every other unmapped byte stayed
put.  Reads 40 on the maintainer's other SALT, 20 on the HOME frame in
home_device_analysis.md, 30 on the OXY frames and 0xFF on every NET frame
captured so far.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class MaxPhDoses(Feature):
    """v7: byte[115], 0xFF = not set."""

    field = "max_ph_doses"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[115])
