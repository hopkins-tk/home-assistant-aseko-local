"""The third state of a value: this unit does not have it.

A reading can answer in three ways, and the entity layer needs to tell them
apart:

* a value -- the unit has the quantity and this is it;
* ``None`` -- the unit has the quantity, but its value is unknown right now
  (the settings byte is unset in this frame, a section is short, ...);
* ``NOT_PRESENT`` -- *this unit* does not have the quantity at all: the
  probe is not installed, the shared pump port is configured for the other
  chemical, the setting was never made, the input reports "not fitted".

The engine records the first two in ``AsekoDevice.features`` and stores
None for the third, so a field missing from ``features`` means "no entity",
and a field in ``features`` that reads None means "entity, state unknown".
Whether a model has a quantity at all is the profile's call; whether this
particular unit has it is the reading's.
"""

from __future__ import annotations

from typing import Final


class NotPresent:
    """Type of the ``NOT_PRESENT`` sentinel."""

    __slots__ = ()

    def __repr__(self) -> str:
        """Show the sentinel by name."""
        return "NOT_PRESENT"

    def __bool__(self) -> bool:
        """Count as false, like None, in a plain truth test."""
        return False


NOT_PRESENT: Final = NotPresent()
