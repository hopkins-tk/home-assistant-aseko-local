"""The unit of decoding: one field on ``AsekoDevice``, every way to read it.

A ``Feature`` subclass names exactly one target field and carries the known
readings of that field as methods:

* ``decode_v7`` / ``decode_v8`` are the *default* reading for each protocol.
  A feature that has no reading for a protocol simply does not define the
  method, and no profile of that protocol may list it.
* Any further ``decode_<protocol>_<name>`` method is a named *reading* a
  profile can select instead of the default, for the models whose frame is
  encoded differently.  The feature file does not know which models those
  are; the profile does.
* ``decode_<protocol>_not_located`` exists on every feature: the model has
  the value (its menu or manual shows it) but nobody has found where the
  frame carries it yet.  It always reads None, so the entity exists and shows
  "unknown", and the support matrix lists it as a place to look.

Every reading receives the frame view and the partially decoded device, so
a feature may read fields decoded before it.  Which fields those are is
declared in ``depends_on`` and honoured by the profile's ordering, never
checked at run time: a wrong order fails loudly at import, not quietly in
the field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from .frames import Protocol

#: The reading a profile selects for a value its model has but whose place in
#: the frame is not known yet, one per protocol.
NOT_LOCATED = frozenset(f"decode_{p.value}_not_located" for p in Protocol)

if TYPE_CHECKING:
    from ..models import AsekoDevice
    from .frames import V7Frame, V8Frame


class Feature:
    """One target value and every known way to read it."""

    #: Name of the ``AsekoDevice`` field this feature fills.
    field: ClassVar[str]

    #: Features whose values this one reads off the device.  The profile
    #: orders its plan so these are decoded first.
    depends_on: ClassVar[tuple[type[Feature], ...]] = ()
    #: The part of ``depends_on`` a profile may leave out: the default
    #: reading copes without it, only a named reading uses it.  Everything
    #: else in ``depends_on`` must be listed, or the profile fails to build.
    optional_depends_on: ClassVar[tuple[type[Feature], ...]] = ()

    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> object:
        """Default reading from a v7 frame.  Absent when v7 has none."""
        raise NotImplementedError

    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> object:
        """Default reading from a v8 frame.  Absent when v8 has none."""
        raise NotImplementedError

    def decode_v7_not_located(self, frame: V7Frame, device: AsekoDevice) -> None:
        """Read nothing: the model has this value, but where v7 carries it is not known yet."""
        return

    def decode_v8_not_located(self, frame: V8Frame, device: AsekoDevice) -> None:
        """Read nothing: the model has this value, but where v8 carries it is not known yet."""
        return

    # -- introspection used by profiles ------------------------------------

    @classmethod
    def default_reading(cls, protocol: Protocol) -> str | None:
        """Name of the default reading for ``protocol``, or None if there is none."""
        name = f"decode_{protocol.value}"
        return name if cls.has_reading(name) else None

    @classmethod
    def has_reading(cls, name: str) -> bool:
        """Return True if ``name`` is a reading this feature actually defines.

        The ``not_located`` readings count for every feature, so a profile can
        select them, but ``readings`` leaves them out: they are not a way the
        feature knows to read the frame.
        """
        if name in NOT_LOCATED:
            return True
        own = getattr(cls, name, None)
        base = getattr(Feature, name, None)
        return callable(own) and own is not base

    @classmethod
    def readings(cls, protocol: Protocol | None = None) -> tuple[str, ...]:
        """All readings this feature defines, optionally for one protocol."""
        prefix = "decode_" if protocol is None else f"decode_{protocol.value}"
        return tuple(
            sorted(
                name
                for name in dir(cls)
                if name.startswith(prefix)
                and name not in NOT_LOCATED
                and cls.has_reading(name)
            )
        )

    @classmethod
    def protocols(cls) -> tuple[Protocol, ...]:
        """Protocols this feature has at least one reading for."""
        return tuple(p for p in Protocol if cls.readings(p))
