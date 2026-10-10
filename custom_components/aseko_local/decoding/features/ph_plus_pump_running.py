"""Whether the pH-plus dosing pump is running.

Not mapped on either protocol: no captured frame shows a pH+ pump running,
so the byte[29] bit is unknown.  The field stays None everywhere until a
frame with the pump active is shared, and no profile lists this feature.
"""

from __future__ import annotations

from ..feature import Feature


class PhPlusPumpRunning(Feature):
    """No known reading yet."""

    field = "ph_plus_pump_running"
