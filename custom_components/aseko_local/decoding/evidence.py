"""Why a profile believes it reads a value right: a status and a note.

Every feature a profile lists carries one ``Evidence``.  The status is a
closed set, so what the support matrix shows follows from the type rather
than from the first word of a sentence; the note is free text for people.
Write entries with the helpers below -- ``confirmed("...")``,
``observed("...")`` -- and see docs/evidence-rules.md for when each applies.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from ..models import AsekoDeviceType


class EvidenceStatus(Enum):
    """How far a reading has been checked."""

    #: compared with the unit display or the Aseko Live app on this model
    CONFIRMED = "confirmed"
    #: follows from the protocol itself or from confirmed values
    DERIVED = "derived"
    #: compared on the other models named, read the same way here
    CONFIRMED_ON = "confirmed on"
    #: seen repeatedly in real frames of this model, never compared
    OBSERVED = "observed"
    #: taken over from another model or an older decoder; nothing contradicts it
    ASSUMED = "assumed"
    #: the model has the value, where the frame carries it is not known
    NOT_LOCATED = "not located"


@dataclass(frozen=True)
class Evidence:
    """One evidence entry: a status, the models it was checked on, and a note."""

    status: EvidenceStatus
    note: str
    #: The models a CONFIRMED_ON entry was checked on; empty for every other status.
    models: tuple[AsekoDeviceType, ...] = ()

    def __post_init__(self) -> None:
        """Reject what the helpers cannot build: a wrong type, no note, stray models.

        Checked here as well as by a type checker, so a typo in a profile
        fails when the profile is imported.
        """
        if not isinstance(self.status, EvidenceStatus):
            msg = f"evidence status must be an EvidenceStatus, not {self.status!r}"
            raise TypeError(msg)
        if not isinstance(self.note, str):
            msg = f"evidence note must be text, not {self.note!r}"
            raise TypeError(msg)
        if not all(isinstance(model, AsekoDeviceType) for model in self.models):
            msg = f"evidence models must be AsekoDeviceType, not {self.models!r}"
            raise TypeError(msg)
        if not self.note.strip():
            msg = f"{self.status.value} evidence needs a note"
            raise ValueError(msg)
        if (self.status is EvidenceStatus.CONFIRMED_ON) != bool(self.models):
            msg = (
                "confirmed on needs the models it was checked on, and only it has them"
            )
            raise ValueError(msg)

    def confirms(self, model: AsekoDeviceType | None) -> bool:
        """Return True if this entry proves the reading for ``model``."""
        if self.status is EvidenceStatus.CONFIRMED_ON:
            return model in self.models
        return self.status in (EvidenceStatus.CONFIRMED, EvidenceStatus.DERIVED)

    def __str__(self) -> str:
        """Render as the support matrix lists it: ``status[ on MODELS]: note``."""
        label = self.status.value
        if self.models:
            label += " " + ", ".join(model.name for model in self.models)
        return f"{label}: {self.note}"


def confirmed(note: str) -> Evidence:
    """Return evidence of a check against the unit display or the app on this model."""
    return Evidence(EvidenceStatus.CONFIRMED, note)


def derived(note: str) -> Evidence:
    """Return evidence that follows from the protocol or confirmed values; say which."""
    return Evidence(EvidenceStatus.DERIVED, note)


def confirmed_on(
    models: AsekoDeviceType | Iterable[AsekoDeviceType], note: str
) -> Evidence:
    """Return evidence checked on the other ``models``, read the same way here."""
    if isinstance(models, AsekoDeviceType):
        models = (models,)
    return Evidence(EvidenceStatus.CONFIRMED_ON, note, tuple(models))


def observed(note: str) -> Evidence:
    """Return evidence seen repeatedly in real frames, never compared with the unit."""
    return Evidence(EvidenceStatus.OBSERVED, note)


def assumed(note: str) -> Evidence:
    """Return evidence taken over from another model or older decoder; say which."""
    return Evidence(EvidenceStatus.ASSUMED, note)


def not_located(note: str) -> Evidence:
    """Return evidence that the model has the value but its place is not known."""
    return Evidence(EvidenceStatus.NOT_LOCATED, note)
