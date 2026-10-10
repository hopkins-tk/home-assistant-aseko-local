"""v8 profiles: the text protocol, firmware 8.x, port 51050.

One module per model (net, salt); this package keeps only what they share
-- the header type table and the common layout in ``common`` -- and the
lookup from a model to its profile.

Values v8 does not transmit -- pump flow rates above all -- are not listed
rather than invented, with one deliberate exception: the chlorine and
pH-minus flow rates are assumed at 60 ml/min so the consumption counters
have something to integrate.
"""

from __future__ import annotations

import logging

from ....models import AsekoDeviceType
from ...frames import V8Frame
from ...profile import Profile
from .net import NET
from .salt import SALT
from .unknown import UNKNOWN

_LOGGER = logging.getLogger(__name__)

BY_MODEL: dict[AsekoDeviceType | None, Profile] = {
    AsekoDeviceType.NET: NET,
    AsekoDeviceType.SALT: SALT,
    None: UNKNOWN,
}


# Header type ranges: the product line, the rest reads like a firmware version
NET_HEADER_TYPES = range(800, 900)
SALT_HEADER_TYPES = range(100, 200)


def model_from_header_type(header_type: int) -> AsekoDeviceType | None:
    """Return the model a v8 header's type field names, or None.

    The field reads like the firmware version of a product line: 804, 805
    and 812 are NET units (812 came with firmware 8.12, PR #119), 105 an
    ASIN Aqua Salt NET.  The firmware version does not select a layout, so
    only the line picks the model: 8xx NET, 1xx SALT.  When a version ever
    needs a layout of its own, that is one more branch here.
    """
    if header_type in NET_HEADER_TYPES:
        return AsekoDeviceType.NET
    if header_type in SALT_HEADER_TYPES:
        return AsekoDeviceType.SALT
    return None


def detect(frame: V8Frame) -> Profile:
    """Return the profile for a v8 frame; the unknown one for a header type no line matches."""
    model = model_from_header_type(frame.header_type)
    if model is None:
        _LOGGER.warning(
            "Unknown v8 header type %s from serial %s: no entities are created; "
            "the diagnostics download shows the frame. Please share it at "
            "https://github.com/hopkins-tk/home-assistant-aseko-local/issues",
            frame.header_type,
            frame.serial_number,
        )
    return BY_MODEL[model]


__all__ = ["BY_MODEL", "NET", "SALT", "UNKNOWN", "detect", "model_from_header_type"]
