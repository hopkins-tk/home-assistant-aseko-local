"""The unit's own clock as it sent it, with nothing filled in from Home Assistant.

``timestamp`` falls back to Home Assistant's clock when the unit sends none,
which is right for a "when" but useless for asking how far the unit's clock
is off.  This field keeps only what the unit sent, for ``trackers.clock``:

* v7: bytes 6-11 as a ``datetime`` (year offset 2000) in Home Assistant's
  time zone -- the unit sends wall-clock time with no zone of its own;
* v8: ``ins[16]`` / ``ins[17]`` as a ``time`` -- hour and minute.  The frame
  does carry a date in ``ins[13:16]``, but it runs 444 to 736 days behind on
  every unit captured so far, so it is not read (see the v8 device
  analyses).

None when the bytes are unset or not a valid date.  A model that never
sends its clock (v7 NET: 0xFF on every frame) does not list the feature.
Both readings share their byte rules with ``timestamp`` (``frames.values``).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames.values import unit_clock_v7, unit_clock_v8

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


class UnitClock(Feature):
    """v7: bytes 6-11.  v8: ins[16] hour, ins[17] minute."""

    field = "unit_clock"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> datetime | None:
        return unit_clock_v7(frame.raw)

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> time | None:
        return unit_clock_v8(frame.get("ins", 16), frame.get("ins", 17))
