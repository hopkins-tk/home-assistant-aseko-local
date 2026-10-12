"""v8 profile for a header type that names no known model.

Reads the layout every v8 unit seen so far shares, so the diagnostics of
such a unit show as much as the frame can say.  Nothing here is verified for
the unit at hand: the coordinator keeps it out of the entity platforms and
reports it in diagnostics as unrecognised, like the v7 unknown unit type.
"""

from __future__ import annotations

from ...evidence import assumed
from ...frames import Protocol
from ...profile import Profile
from .common import FEATURES

UNKNOWN = Profile(
    name="v8 unknown header type",
    protocol=Protocol.V8,
    model=None,
    features=FEATURES,
    evidence=dict.fromkeys(
        FEATURES, assumed("unknown header type, read with the common v8 layout")
    ),
)
