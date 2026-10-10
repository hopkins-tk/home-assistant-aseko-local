"""The committed support matrix must match the profiles it is generated from."""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.aseko_local.decoding import support_matrix
from custom_components.aseko_local.decoding.evidence import (
    Evidence,
    assumed,
    confirmed,
    confirmed_on,
    derived,
    observed,
)
from custom_components.aseko_local.decoding.features import ALL_FEATURES, SerialNumber
from custom_components.aseko_local.decoding.frames import Protocol
from custom_components.aseko_local.decoding.profile import Profile
from custom_components.aseko_local.decoding.profiles import ALL_PROFILES
from custom_components.aseko_local.decoding.support_matrix import render
from custom_components.aseko_local.models import AsekoDeviceType

MATRIX = Path(__file__).resolve().parent.parent / "docs" / "support_matrix.md"


def test_support_matrix_is_up_to_date() -> None:
    """Regenerate with ``python scripts/generate_support_matrix.py``."""
    assert MATRIX.read_text(encoding="utf-8") == render()


def test_every_profile_and_field_is_in_the_matrix() -> None:
    text = render()

    for profile in ALL_PROFILES:
        assert profile.name.split(" ", 1)[1] in text
    for feature in ALL_FEATURES:
        assert f"`{feature.field}`" in text


def _status_for(evidence: Evidence | None, model: AsekoDeviceType) -> str:
    profile = Profile(
        name=f"v7 {model.name}",
        protocol=Protocol.V7,
        model=model,
        features=(SerialNumber,),
        evidence={SerialNumber: evidence} if evidence else {},
    )
    return support_matrix._status(profile, SerialNumber)


SALT, HOME, NET = AsekoDeviceType.SALT, AsekoDeviceType.HOME, AsekoDeviceType.NET


@pytest.mark.parametrize(
    ("evidence", "model", "mark"),
    [
        (confirmed("against the unit"), SALT, "✅"),
        (derived("from confirmed values"), SALT, "✅"),
        (confirmed_on(HOME, "byte[14]"), SALT, "❓"),  # another model's proof
        (confirmed_on((NET, SALT), "byte[14]"), HOME, "❓"),
        (observed("plausible in 28 frames"), SALT, "👁"),
        (assumed("as on OXY"), SALT, "❓"),
        (None, SALT, "❓"),  # a fallback profile may leave an entry out
    ],
)
def test_the_evidence_status_decides_the_mark(evidence, model, mark) -> None:
    """docs/evidence-rules.md: a confirmation counts only for the model it names."""
    assert _status_for(evidence, model) == mark


def test_confirmed_on_counts_in_the_named_models_column() -> None:
    """The support matrix tables list every model; the named one gets the tick."""
    evidence = confirmed_on((NET, SALT), "byte[14]")
    assert evidence.confirms(SALT)
    assert evidence.confirms(NET)
    assert not evidence.confirms(HOME)
    assert str(evidence) == "confirmed on NET, SALT: byte[14]"
