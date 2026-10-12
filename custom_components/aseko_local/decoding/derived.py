"""Values worked out from decoded ones, never read from the frame.

A feature reports what the unit sends, decoded from its own bytes, and does
not replace it because of another live state.  Where a value only means what
a user expects in the context of another one -- the electrolyser output
while the electrolyser is off, "heating allowed" while Heating control is off
-- the user-facing value is derived here from the decoded fields, and the
decoded one keeps its own field and entity.

Each derived value names the fields it needs.  It is computed when all of
them are present in the frame and counts as present itself then; a model
whose profile lists all of them can have it.  Other fields a rule reads
(``service_menu_open`` for ``filtration_running``) are optional: absent, they
read None.  Derived values do not depend on each other.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import AsekoProfileFlag

if TYPE_CHECKING:
    from ..models import AsekoDevice


@dataclass(frozen=True)
class Derived:
    """One ``AsekoDevice`` field computed from decoded fields."""

    field: str
    requires: tuple[str, ...]
    compute: Callable[[AsekoDevice], object]
    #: Profile flags that change the rule for a model; the support matrix
    #: shows them next to the profiles that carry them.
    flags: tuple[AsekoProfileFlag, ...] = ()


def heating_allowed(device: AsekoDevice) -> bool | None:
    """Return whether Heating control is on and its condition is met right now.

    byte[78] bit 0x80 (``heating_condition_met``) is evaluated with Heating
    control off as well, so on its own it would read "allowed" with heating
    switched off.
    """
    if device.heating_control_enabled is None:
        return None
    if not device.heating_control_enabled:
        return False
    return device.heating_condition_met


def chlorine_production(device: AsekoDevice) -> int | None:
    """Return the measured electrolyser output while it runs, 0 while it does not.

    After a stop the measured value runs down over 1-3 frames
    (``chlorine_production_measured``); this one reads 0 from the first
    stopped frame.
    """
    if device.electrolysis_running is None:
        return None
    if not device.electrolysis_running:
        return 0
    return device.chlorine_production_measured


def filtration_running(device: AsekoDevice) -> bool | None:
    """Return the filtration relay, False while HOME's pump is switched off by hand.

    On a profile with ``MENU_BIT_SWITCHES_FILTRATION_OFF`` (HOME, Issue #133)
    the relay bit stays set while byte[37] bit 0x04 says the pump was switched
    off at the unit; that bit wins.  Elsewhere the relay bit as sent.
    """
    relay = device.filtration_relay
    if (
        relay
        and AsekoProfileFlag.MENU_BIT_SWITCHES_FILTRATION_OFF in device.flags
        and device.service_menu_open is True
    ):
        return False
    return relay


DERIVED: tuple[Derived, ...] = (
    Derived(
        "heating_allowed",
        ("heating_control_enabled", "heating_condition_met"),
        heating_allowed,
    ),
    Derived(
        "chlorine_production",
        ("chlorine_production_measured", "electrolysis_running"),
        chlorine_production,
    ),
    Derived(
        "filtration_running",
        ("filtration_relay",),
        filtration_running,
        flags=(AsekoProfileFlag.MENU_BIT_SWITCHES_FILTRATION_OFF,),
    ),
)


def possible(fields: frozenset[str]) -> frozenset[str]:
    """Return the derived fields a profile reading ``fields`` can have."""
    return frozenset(d.field for d in DERIVED if fields.issuperset(d.requires))


def apply(device: AsekoDevice, present: set[str]) -> None:
    """Fill the derived fields whose inputs are all in ``present``, and add them to it."""
    for derived in DERIVED:
        if present.issuperset(derived.requires):
            setattr(device, derived.field, derived.compute(device))
            present.add(derived.field)
