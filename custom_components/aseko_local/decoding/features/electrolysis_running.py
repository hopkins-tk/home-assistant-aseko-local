"""Whether the electrolyser is running.

byte[29] bit 0x10 = electrolyser running (confirmed: 25 SALT frames read
0x18 = 0x08 | 0x10, PR #87).  Bit 0x40 on top of it marks the left polarity
(tentative: a single Apr 2 frame read 0x58 = 0x08 | 0x10 | 0x40).

v8: outs[14], which is 0 with the electrolyser off and 2 or 3 while it runs
-- the two polarities, see electrode_polarity (Issue #131, frames an owner
labelled with what the app showed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


ELECTROLYZER_RUNNING = 0x10


class ElectrolysisRunning(Feature):
    """v7: byte[29] bit 0x10.  v8: outs[14] is not 0."""

    field = "electrolysis_running"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool:
        return bool(frame[29] & ELECTROLYZER_RUNNING)

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> bool | None:
        return frame.flag("outs", 14)
