"""Timed chlorine dose (ml/m3/h), for units dosing by volume.

byte[53] carries one disinfection setpoint whose meaning depends on the
installed probes, in this order of precedence: a CLF probe makes it the
free-chlorine setpoint, otherwise a REDOX probe makes it the redox setpoint,
otherwise a DOSE probe makes it the timed chlorine dose.  Each of the three
features reads the byte and answers only when it is the one that applies.
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
    from ..frames import V7Frame
    from ..presence import NotPresent


class ChlorineDoseTarget(Feature):
    """v7: byte[53] with a DOSE probe and neither CLF nor REDOX."""

    field = "chlorine_dose_target"
    depends_on = (Configuration,)

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        probes = device.configuration
        if (
            AsekoProbeType.CLF in probes
            or AsekoProbeType.REDOX in probes
            or AsekoProbeType.DOSE not in probes
        ):
            return NOT_PRESENT
        return byte_or_none(frame[53])  # None: the dose is not filled in
