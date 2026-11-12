"""Configured flocculant pump flow rate (ml/min).

Two layouts exist for the algicide / flocculant pair, and which one a model
uses is a property of the model -- so this feature offers both readings and
the profile picks:

Independent ports (OXY, HOME): flocculant at byte[101], algicide at
    byte[97] -- confirmed on OXY (Issue #183: 60 ml/min measured against the
    canister), observed on HOME (Issue #173).  byte[103] is the refill start
    level on both; OXY read the algicide there first because the 2026-04-11
    frame, from a unit without a level sensor, has 60 in byte[97] and in
    byte[103] (its default thresholds 30 / 60 / 110 / 150 cm).

Shared port (SALT; PROFI assumed): one physical pump at byte[101], configured
    for either chemical.  NET has neither pump.  byte[37] bit 0x80 set = algicide, clear =
    flocculant (confirmed by @hopkins-tk on SALT v7.x and consistent with
    @jmnemonicj, SALT v5.0, Issue #84).  byte[37] = 0xFF = configuration
    unknown, both stay None.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent, byte_when_flags

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


# byte[37] bit 0x80 routes the shared third-pump port: set for algicide,
# clear for flocculant
SHARED_PORT_ROUTING = 0x80
ROUTED_TO_FLOCCULANT = 0x00


class FlocculantFlowRate(Feature):
    """v7: byte[101], on a shared port only while byte[37] routes it to flocculant."""

    field = "flocculant_flow_rate"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        """Independent flocculant port."""
        return byte_or_absent(frame[101])

    def decode_v7_routed_by_byte37(
        self, frame: V7Frame, device: AsekoDevice
    ) -> int | NotPresent:
        """Shared third-pump port, ours only while byte[37] bit 0x80 is clear."""
        return byte_when_flags(
            frame[101], frame[37], SHARED_PORT_ROUTING, ROUTED_TO_FLOCCULANT
        )
