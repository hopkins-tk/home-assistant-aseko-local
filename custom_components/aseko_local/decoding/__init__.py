"""Frame decoding by device profile.

A frame is read in three steps, none of which knows about the others'
internals:

1. ``frames.parse_frame`` turns the raw bytes into a protocol-specific *view*:
   a ``V7Frame`` over the 120-byte binary layout, or a ``V8Frame`` over the
   parsed sections of the text protocol.  This is the only per-protocol
   parsing in the integration.
2. ``profiles.detect_profile`` reads protocol and model off that view and
   looks up one ``Profile``: the ordered list of features the device has,
   which *reading* each of them uses, and a few semantic flags.  Model
   knowledge lives in ``profiles/`` and nowhere else.
3. ``engine.decode`` walks the profile's plan and lets each feature's chosen
   reading read its value.  A feature is one field on ``AsekoDevice`` and
   lives in its own file under ``features/``, holding every known way to read
   that one value for both protocols.  A feature file knows nothing about
   models.  Last, ``derived`` works out the values that only mean what a
   user expects in the context of another one, from the decoded fields.

``decode`` below runs the three steps and is the entry point for everything
outside this package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import engine
from .frames import Protocol, parse_frame
from .profiles import detect_profile

if TYPE_CHECKING:
    from ..models import AsekoDevice


def decode(raw: bytes, protocol: Protocol | None = None) -> AsekoDevice:
    """Decode one frame into an ``AsekoDevice``.

    ``protocol`` is the wire format when the caller already knows it (the
    server does); without it the first bytes decide.  Raises ValueError for a
    v8 frame that cannot be parsed.
    """
    frame = parse_frame(raw, protocol)
    return engine.decode(frame, detect_profile(frame))


__all__ = ["Protocol", "decode"]
