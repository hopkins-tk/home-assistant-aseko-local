"""Rapid pH change, regulation stopped.

Alarm bitmasks, bytes 12 and 13, on every model.

byte[13] (several bits may be set at once):
    0x01 = ORP / disinfection dose fault: maximum dose exceeded (Issue #151,
           HOME serial 110175608, while the controller showed "Maximum
           disinfection dose exceeded"; the same fault as v8 ins[12] 0x80)
    0x02 = pH dose fault: too many doses without a change (inferred,
           symmetric to 0x01 -- no direct capture yet)
    0x04 = no flow to probes (DomSchCoding, NET frame: confirmed)
    0x08 = rapid pH change, regulation stopped ~2 h (error_codes.md,
           unconfirmed by capture)

byte[12] dosing-warning bitmask (HOME, Issues #134 / #151, serial 110175608):
    0x20 = disinfection / chlorine dosing warning
           (Pool Live: MAXIMUM_DISINFECTION_DOSE_EXCEEDED)
    0x40 = pH dosing warning
           (Pool Live: TOO_MANY_PH_DOSING_ATTEMPTS_WITHOUT_CHANGE)

Both bytes encode the two dosing faults: Issue #134 (2026-07-05) showed the
disinfection one in byte[12] 0x20, Issue #151 (2026-08-06) in byte[13] 0x01,
most likely a firmware change on the Home.  The two features OR both paths.
On NET byte[12] is typically 0x00 while no-flow lives in byte[13].
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


class AlarmRapidPhChange(Feature):
    """v7: byte[13] bit 0x08."""

    field = "alarm_rapid_ph_change"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool:
        return bool(frame[13] & 0x08)
