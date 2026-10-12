"""Whether the filtration pump relay bit is set, as the unit sends it.

v7: byte[29] bit 0x08 on every model with a filtration output (confirmed on
OXY and SALT in every captured frame; assumed on HOME and PROFI).  v8: outs[2].

On HOME (Issue #133) the bit stays set while the pump has been switched off
by hand at the unit; that state is byte[37] bit 0x04.  ``filtration_running``
is the derived value that takes it into account (``derived.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


FILTRATION = 0x08


class FiltrationRelay(Feature):
    """v7: byte[29] bit 0x08.  v8: outs[2]."""

    field = "filtration_relay"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool:
        return bool(frame[29] & FILTRATION)

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> bool | None:
        return frame.flag("outs", 2)
