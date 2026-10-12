"""Tests that new setpoint sensors have translations."""

import json
from pathlib import Path

import pytest

CORE_KEYS = [
    "filtration_period_1_start",
    "filtration_period_1_end",
    "filtration_period_2_start",
    "filtration_period_2_end",
    "pool_volume",
    "startup_delay",
    "dosing_delay",
]

TRANSLATIONS_DIR = Path("custom_components/aseko_local/translations")


def _sensor_names(locale: str) -> dict:
    data = json.loads((TRANSLATIONS_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return data["entity"]["sensor"]


@pytest.mark.parametrize("locale", ["en", "cs"])
@pytest.mark.parametrize("key", CORE_KEYS)
def test_core_sensor_has_translation(locale: str, key: str) -> None:
    names = _sensor_names(locale)
    assert key in names, f"{key} missing in {locale}.json"
    assert names[key].get("name"), f"{key} has no name in {locale}.json"
