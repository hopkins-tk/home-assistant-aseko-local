"""The decode loop.  Knows no bytes and no models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import AsekoDevice
from . import derived
from .presence import NOT_PRESENT

if TYPE_CHECKING:
    from .frames import V7Frame, V8Frame
    from .profile import Profile


def decode(
    frame: V7Frame | V8Frame,
    profile: Profile,
) -> AsekoDevice:
    """Fill an ``AsekoDevice`` from ``frame`` the way ``profile`` says to.

    Each feature's chosen reading gets the frame and the device as filled so
    far, so a feature listed after its dependencies can read their values.

    ``device.features`` ends up as the fields *this unit* has: the profile's
    list minus every reading that answered ``NOT_PRESENT`` (see
    ``presence``).  A field the unit has but could not read in this frame is
    in ``features`` with the value None.

    The derived values (``derived``) follow, from the fields just read; each
    is in ``features`` when all the fields it needs are.
    """
    device = AsekoDevice(
        device_type=profile.model,
        flags=profile.flags,
        profile=profile.name,
        frame_problems=getattr(frame, "problems", ()),
    )
    present: set[str] = set()
    for feature, read in profile.plan:
        value = read(frame, device)
        if value is NOT_PRESENT:
            value = None
        else:
            present.add(feature.field)
        setattr(device, feature.field, value)
    derived.apply(device, present)
    device.features = frozenset(present)
    device.present_features = device.features
    device.possible_features = profile.feature_names | derived.possible(
        profile.feature_names
    )
    return device
