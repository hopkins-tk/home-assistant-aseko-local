"""Heating control tied to filtration ("heating is parent to filtration").

v7: byte[38] bit 0x10.  Confirmed on an ASIN AQUA Salt (2026-09-14): set with
the setting switched on, cleared with it off, heating control on throughout.
The unit offers the setting only while heating control is on and sends the
bit cleared while it is off; the value is reported as sent either way, so a
dashboard can hide it when heating control is off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


HEATING_LINKED_TO_FILTRATION = 0x10


class HeatingLinkedToFiltration(Feature):
    """v7: byte[38] bit 0x10."""

    field = "heating_linked_to_filtration"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        return flag_or_none(frame[38], HEATING_LINKED_TO_FILTRATION)
