"""Configured pH-plus pump flow rate (ml/min).

Not mapped: byte[97] was the pH+ output on first-generation HOME units, but
second-generation HOME units put the algicide pump there; HOME and OXY read it
as the algicide rate (Issues #173, #183).  No frame has shown a pH+ rate, so the field
stays None everywhere and no profile lists this feature.
"""

from __future__ import annotations

from ..feature import Feature


class PhPlusFlowRate(Feature):
    """No known reading yet."""

    field = "ph_plus_flow_rate"
