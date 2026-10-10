"""The profile registry and the lookup from a parsed frame into it."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...models import AsekoDeviceType
from ..frames import Protocol, V8Frame
from ..profile import Profile, unit_type_from_byte
from . import v7, v8

if TYPE_CHECKING:
    from ..frames import V7Frame

_LOGGER = logging.getLogger(__name__)

#: Every profile, in the order the support matrix lists them.  Includes the
#: fallback below, which the matrix mentions but does not tabulate.
ALL_PROFILES: tuple[Profile, ...] = (
    v7.HOME,
    v7.SALT,
    v7.OXY,
    v7.NET,
    v7.PROFI,
    v7.UNKNOWN,
    v8.NET,
    v8.SALT,
    v8.UNKNOWN,
)

#: Profiles no unit is *meant* to decode with: the frame did not allow the
#: proper one to be picked.  Real decoding paths, but not answers to "what
#: does my model support", so the support matrix keeps them out of its tables.
FALLBACK_PROFILES: tuple[Profile, ...] = (v7.UNKNOWN, v8.UNKNOWN)


_BY_NAME: dict[str, Profile] = {profile.name: profile for profile in ALL_PROFILES}


def profile_named(name: str | None) -> Profile | None:
    """Return the profile called ``name`` (``AsekoDevice.profile``), or None."""
    return _BY_NAME.get(name) if name else None


def profile_for(protocol: Protocol, model: AsekoDeviceType | None) -> Profile:
    """Return the profile for a known combination."""
    if protocol is Protocol.V8:
        return v8.BY_MODEL[model]
    return v7.BY_MODEL[model]


def detect_profile(frame: V7Frame | V8Frame) -> Profile:
    """Pick the profile for ``frame``: protocol, then model.

    Runs on every frame, not once at setup.
    """
    if isinstance(frame, V8Frame):
        return v8.detect(frame)
    return profile_for(Protocol.V7, unit_type_from_byte(frame.unit_type))


__all__ = [
    "ALL_PROFILES",
    "FALLBACK_PROFILES",
    "detect_profile",
    "profile_for",
    "v7",
    "v8",
]
