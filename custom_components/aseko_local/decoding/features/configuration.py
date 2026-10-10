"""Which probes the unit has installed.

v7 keeps this in byte[4], the same byte that carries the device type, but the
encoding differs by model -- which is why this feature has one reading per
encoding and the profile picks.  v8 has no probe bits: a probe is installed
when its analog input reports a value other than the -500 sentinel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...const import (
    PROBE_CLF_MISSING,
    PROBE_DOSE_MISSING,
    PROBE_REDOX_MISSING,
    UNIT_TYPE_HOME_CLF,
    UNIT_TYPE_HOME_REDOX,
)
from ...models import AsekoProbeType
from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


class Configuration(Feature):
    """The set of installed probes."""

    field = "configuration"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> set[AsekoProbeType]:
        """Missing-probe bits in byte[4]: 0x01 REDOX, 0x02 CLF, 0x04 DOSE (NET, SALT)."""
        probes = self._from_missing_bits(frame.unit_type)
        if not frame.unit_type & PROBE_DOSE_MISSING:
            probes.add(AsekoProbeType.DOSE)
        return probes

    def decode_v7_without_dose(
        self, frame: V7Frame, device: AsekoDevice
    ) -> set[AsekoProbeType]:
        """Return the missing-probe bits without a DOSE bit (PROFI)."""
        return self._from_missing_bits(frame.unit_type)

    def decode_v7_by_unit_type_byte(
        self, frame: V7Frame, device: AsekoDevice
    ) -> set[AsekoProbeType]:
        """byte[4] as an exact sub-type rather than a bitmask (HOME).

        The bits are not consistent with NET / SALT: the value names a fixed
        probe configuration.  0x02 = CLF, 0x03 = REDOX, anything else = DOSE.
        """
        if frame.unit_type == UNIT_TYPE_HOME_CLF:
            return {AsekoProbeType.PH, AsekoProbeType.CLF}
        if frame.unit_type == UNIT_TYPE_HOME_REDOX:
            return {AsekoProbeType.PH, AsekoProbeType.REDOX}
        return {AsekoProbeType.PH, AsekoProbeType.DOSE}

    def decode_v7_ph_and_oxy(
        self, frame: V7Frame, device: AsekoDevice
    ) -> set[AsekoProbeType]:
        """Return a fixed pH + OXY Pure pair (ASIN AQUA Oxygen).

        The SANOSIL probe occupies the CLF slot physically, so the CLF
        "missing" bit is 0 and the bitmask reading would wrongly add CLF.
        """
        return {AsekoProbeType.PH, AsekoProbeType.OXY}

    def decode_v7_all_probes(
        self, frame: V7Frame, device: AsekoDevice
    ) -> set[AsekoProbeType]:
        """Every probe -- for a unit type nobody has mapped yet, read it all."""
        return set(AsekoProbeType)

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> set[AsekoProbeType]:
        probes: set[AsekoProbeType] = set()
        if frame.value("ains", 0) is not None:
            probes.add(AsekoProbeType.PH)
        if frame.value("ains", 6) is not None:
            probes.add(AsekoProbeType.REDOX)
        return probes

    @staticmethod
    def _from_missing_bits(probe_info: int) -> set[AsekoProbeType]:
        probes = {AsekoProbeType.PH}
        if not probe_info & PROBE_REDOX_MISSING:
            probes.add(AsekoProbeType.REDOX)
        if not probe_info & PROBE_CLF_MISSING:
            probes.add(AsekoProbeType.CLF)
        return probes
