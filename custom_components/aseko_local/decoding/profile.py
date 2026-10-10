"""A profile: what one (protocol, model) combination reads, and how.

The profile is the only place that knows models.  It lists the features a
device has, names a different reading for the few that are encoded
differently on this model, records the evidence behind each entry, and
carries the semantic flags consumers need instead of a device type.

Validation happens at construction, i.e. at import time: a feature listed
without a reading for the profile's protocol, an override naming a reading
the feature does not have, or a dependency cycle all fail before a single
frame is decoded.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ..const import (
    UNIT_TYPE_HOME,
    UNIT_TYPE_NET,
    UNIT_TYPE_OXY,
    UNIT_TYPE_PROFI,
    UNIT_TYPE_SALT,
)
from ..models import AsekoDeviceType, AsekoProfileFlag
from .evidence import Evidence, EvidenceStatus
from .feature import NOT_LOCATED
from .frames import Protocol

if TYPE_CHECKING:
    from ..models import AsekoDevice
    from .feature import Feature

_LOGGER = logging.getLogger(__name__)

Reader = Callable[[Any, "AsekoDevice"], Any]


@dataclass(frozen=True)
class Profile:
    """One (protocol, model) combination and everything it reads."""

    name: str
    protocol: Protocol
    #: None for a v7 unit type nobody has mapped yet.
    model: AsekoDeviceType | None
    #: The features this device has.  Order is a hint only; dependencies win.
    features: tuple[type[Feature], ...] = ()
    #: Feature -> name of the reading to use instead of the protocol default.
    overrides: Mapping[type[Feature], str] = field(default_factory=dict)
    #: Feature -> why we believe this profile reads it the way it does.
    evidence: Mapping[type[Feature], Evidence] = field(default_factory=dict)
    flags: frozenset[AsekoProfileFlag] = frozenset()

    #: Decoding order with the bound reading for each feature.  Built once.
    plan: tuple[tuple[Feature, Reader], ...] = field(
        init=False, repr=False, compare=False
    )
    #: Names of the AsekoDevice fields this profile fills.
    feature_names: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Freeze the mappings, validate the profile and build its decode plan."""
        # read-only copies: the plan below is built from them once, so a
        # change in memory later could only make it disagree with them
        object.__setattr__(self, "overrides", MappingProxyType(dict(self.overrides)))
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        self._validate()
        plan = []
        for feature_cls in _ordered(self.features):
            feature = feature_cls()
            plan.append((feature, getattr(feature, self.reading_for(feature_cls))))
        object.__setattr__(self, "plan", tuple(plan))
        object.__setattr__(
            self, "feature_names", frozenset(f.field for f in self.features)
        )

    def reading_for(self, feature: type[Feature]) -> str:
        """Name of the reading this profile uses for ``feature``."""
        override = self.overrides.get(feature)
        if override is not None:
            return override
        default = feature.default_reading(self.protocol)
        if default is None:
            msg = (
                f"{self.name}: {feature.__name__} has no {self.protocol.value} reading"
            )
            raise ValueError(msg)
        return default

    def _validate(self) -> None:
        listed = set(self.features)
        if len(listed) != len(self.features):
            msg = f"{self.name}: a feature is listed twice"
            raise ValueError(msg)
        fields = [f.field for f in self.features]
        if len(set(fields)) != len(fields):
            msg = f"{self.name}: two features fill the same field"
            raise ValueError(msg)

        for feature, reading in self.overrides.items():
            if feature not in listed:
                msg = f"{self.name}: override for unlisted {feature.__name__}"
                raise ValueError(msg)
            if not reading.startswith(f"decode_{self.protocol.value}"):
                msg = (
                    f"{self.name}: {feature.__name__}.{reading} is not a "
                    f"{self.protocol.value} reading"
                )
                raise ValueError(msg)
            if not feature.has_reading(reading):
                msg = f"{self.name}: {feature.__name__} has no reading {reading!r}"
                raise ValueError(msg)
        for feature, evidence in self.evidence.items():
            self._validate_evidence(feature, evidence, listed)
        for feature in self.features:
            self.reading_for(feature)  # raises when there is nothing to call
            for dependency in feature.depends_on:
                if (
                    dependency not in listed
                    and dependency not in feature.optional_depends_on
                ):
                    msg = (
                        f"{self.name}: {feature.__name__} needs "
                        f"{dependency.__name__}, which is not listed"
                    )
                    raise ValueError(msg)

    def _validate_evidence(
        self, feature: type[Feature], evidence: Evidence, listed: set[type[Feature]]
    ) -> None:
        """Check one evidence entry against the profile it sits in."""
        name = f"{self.name}: {feature.__name__}"
        if feature not in listed:
            msg = f"{self.name}: evidence for unlisted {feature.__name__}"
            raise ValueError(msg)
        if not isinstance(evidence, Evidence):
            msg = f"{name}: evidence must be an Evidence, not {evidence!r}"
            raise TypeError(msg)
        if (
            evidence.status is EvidenceStatus.CONFIRMED_ON
            and self.model in evidence.models
        ):
            msg = f"{name}: confirmed on its own model is confirmed"
            raise ValueError(msg)
        not_located_reading = self.overrides.get(feature) in NOT_LOCATED
        if not_located_reading != (evidence.status is EvidenceStatus.NOT_LOCATED):
            msg = (
                f"{name}: not_located evidence goes with a *_not_located "
                "override, and only with one"
            )
            raise ValueError(msg)


def _ordered(features: tuple[type[Feature], ...]) -> list[type[Feature]]:
    """Return ``features`` with every dependency ahead of its dependant.

    Stable: features stay in listed order unless a dependency forces a move.
    Only an optional dependency (``Feature.optional_depends_on``) can be
    missing here -- ``Profile._validate`` rejects any other -- and the
    dependant then sees None for it.
    """
    listed = set(features)
    done: list[type[Feature]] = []
    seen: set[type[Feature]] = set()
    visiting: set[type[Feature]] = set()

    def visit(feature: type[Feature]) -> None:
        if feature in seen:
            return
        if feature in visiting:
            msg = f"dependency cycle through {feature.__name__}"
            raise ValueError(msg)
        visiting.add(feature)
        for dependency in feature.depends_on:
            if dependency in listed:
                visit(dependency)
        visiting.remove(feature)
        seen.add(feature)
        done.append(feature)

    for feature in features:
        visit(feature)
    return done


# ---------------------------------------------------------------------------
# Detection helpers: frame bytes -> model.  Pure functions; the
# lookup into the registry lives in ``profiles/__init__.py``.
# ---------------------------------------------------------------------------


_MODEL_BY_UNIT_TYPE: dict[int, AsekoDeviceType] = {
    UNIT_TYPE_HOME: AsekoDeviceType.HOME,  # 0x02 CLF
    UNIT_TYPE_HOME + 1: AsekoDeviceType.HOME,  # 0x03 REDOX
    UNIT_TYPE_HOME + 2: AsekoDeviceType.HOME,  # 0x04 DOSE (no capture yet)
    UNIT_TYPE_OXY: AsekoDeviceType.OXY,  # 0x05
    UNIT_TYPE_NET + 1: AsekoDeviceType.NET,  # 0x09 CLF
    UNIT_TYPE_NET + 2: AsekoDeviceType.NET,  # 0x0A REDOX
    UNIT_TYPE_NET + 3: AsekoDeviceType.NET,  # 0x0B DOSE
    UNIT_TYPE_SALT + 1: AsekoDeviceType.SALT,  # 0x0D CLF
    UNIT_TYPE_SALT + 2: AsekoDeviceType.SALT,  # 0x0E REDOX
    UNIT_TYPE_SALT + 3: AsekoDeviceType.SALT,  # 0x0F DOSE
    UNIT_TYPE_PROFI: AsekoDeviceType.PROFI,  # 0x10 (unconfirmed)
}


def unit_type_from_byte(value: int) -> AsekoDeviceType | None:
    """Map v7 byte[4] to a model, or None for a value nobody has mapped yet.

    byte[4] carries the probe configuration in its low bits, so a model
    covers a few exact values: HOME 0x02-0x04, NET 0x09-0x0B, SALT 0x0D-0x0F
    (CLF, REDOX, DOSE).  OXY (0x05) and PROFI (0x10, unconfirmed) are single
    values.  Anything else -- 0x06, 0x0C, 0x11, 0xFF ... -- is unmapped and
    goes to the unknown-unit profile, where it shows up in diagnostics
    instead of being decoded as a model it may not be.
    """
    model = _MODEL_BY_UNIT_TYPE.get(value)
    if model is not None:
        return model

    _LOGGER.warning("Unknown unit type: %s", value)
    return None
