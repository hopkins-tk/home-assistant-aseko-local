"""v7 profiles: the 120-byte binary protocol, firmware up to 7.x, port 47524.

One module per model (salt, home, oxy, net, profi, unknown); this package
keeps only what they share -- the feature groups in ``common`` -- and the
lookup from a model to its profile.

A feature listed in a profile is one the model has; a feature missing from a
profile is one it does not have, and its field stays None so no entity is
created for it.  ``overrides`` name the reading to use
where this model's frame differs from the protocol default; everything else
uses the default reading from the feature's own file.

``evidence`` records why each entry is believed, in the words of the
captures, issues and the documents in docs/device analyzes/ that
established it, with a status from ``decoding.evidence``: ``confirmed`` means
checked against the unit's display or the Aseko Live app; ``observed`` means
seen in real frames with plausible values but not compared; ``assumed`` means
taken over from another model or the earlier decoder, with nothing
contradicting it yet (docs/evidence-rules.md has them all).  Every profile spells
its evidence out in full so that nothing is inherited from another model.
The support matrix in the docs is generated from these dictionaries.
"""

from __future__ import annotations

from ....models import AsekoDeviceType
from ...profile import Profile
from .home import HOME
from .net import NET
from .oxy import OXY
from .profi import PROFI
from .salt import SALT
from .unknown import UNKNOWN

BY_MODEL: dict[AsekoDeviceType | None, Profile] = {
    AsekoDeviceType.HOME: HOME,
    AsekoDeviceType.SALT: SALT,
    AsekoDeviceType.OXY: OXY,
    AsekoDeviceType.NET: NET,
    AsekoDeviceType.PROFI: PROFI,
    None: UNKNOWN,
}

__all__ = ["BY_MODEL", "HOME", "NET", "OXY", "PROFI", "SALT", "UNKNOWN"]
