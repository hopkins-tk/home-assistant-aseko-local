"""Redox setpoint (mV).

byte[53] carries one disinfection setpoint whose meaning depends on the
installed probes, in this order of precedence: a CLF probe makes it the
free-chlorine setpoint, otherwise a REDOX probe makes it the redox setpoint,
otherwise a DOSE probe makes it the timed chlorine dose.  Each of the three
features reads the byte and answers only when it is the one that applies.

v8: areqs[1] * 10, unconditionally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...models import AsekoProbeType
from ..feature import Feature
from ..frames import byte_or_none
from ..presence import NOT_PRESENT
from .configuration import Configuration

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


class RedoxTarget(Feature):
    """v7: byte[53] * 10 with a REDOX probe and no CLF probe.  v8: areqs[1] * 10."""

    field = "redox_target"
    depends_on = (Configuration,)

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        probes = device.configuration
        if AsekoProbeType.CLF in probes or AsekoProbeType.REDOX not in probes:
            return NOT_PRESENT
        value = byte_or_none(frame[53])  # None: the setpoint is not filled in
        return None if value is None else value * 10

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int | None:
        raw = frame.value("areqs", 1)
        return raw * 10 if raw is not None else None
