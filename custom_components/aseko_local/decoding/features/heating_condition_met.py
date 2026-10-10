"""Whether the heating condition -- time window or outside temperature -- is met right now.

v7: byte[78] bit 0x80.  A live state, not a setting.  Confirmed on an ASIN
AQUA Salt (2026-09-13/14 marked test cases): with a heating time window of
08:00-16:00 at 23:59 the bit cleared, with 00:00-14:50 at 00:01 it was set;
with "outside temperature above 17 C" it cleared and "below 17 C" set it,
the unit having no air probe (-40.0 C).

The unit evaluates the condition whether or not Heating control is on: with
Heating control off and no condition set the bit is set in every frame
(559 such frames in the same test cases), so on its own it does not say that
heating is allowed.  ``heating_allowed`` is the derived value that also
needs Heating control on (``derived.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


MASK = 0x80


class HeatingConditionMet(Feature):
    """v7: byte[78] bit 0x80."""

    field = "heating_condition_met"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        return flag_or_none(frame[78], MASK)
