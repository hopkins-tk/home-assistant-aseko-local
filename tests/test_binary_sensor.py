"""The binary sensor platform: retired entities, set-up and entity states."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.aseko_local import binary_sensor as binary_sensor_module
from custom_components.aseko_local import entity as entity_module
from custom_components.aseko_local.binary_sensor import (
    BINARY_SENSORS,
    AsekoLocalBinarySensorEntity,
    async_remove_retired_entities,
)
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.models import AsekoDevice

from .test_decode_v8 import SALT_NET_106_FRAME
from .test_entity_growth import SERIAL, _coordinator, _salt_frame


@dataclass
class _RegistryEntry:
    domain: str
    unique_id: str
    entity_id: str


def test_only_retired_binary_sensors_are_removed(monkeypatch) -> None:
    entries = [
        _RegistryEntry("binary_sensor", f"{SERIAL}filtration_nonstop24", "b.nonstop"),
        _RegistryEntry("binary_sensor", f"{SERIAL}pump_running", "b.pump"),
        _RegistryEntry("sensor", f"{SERIAL}filtration_nonstop24", "s.same_suffix"),
    ]
    removed: list[str] = []
    registry = MagicMock()
    registry.async_remove.side_effect = removed.append
    monkeypatch.setattr(entity_module.er, "async_get", lambda hass: registry)
    monkeypatch.setattr(
        entity_module.er,
        "async_entries_for_config_entry",
        lambda reg, entry_id: entries,
    )

    async_remove_retired_entities(MagicMock(), MagicMock())
    assert removed == ["b.nonstop"]

    entries.remove(entries[0])  # the next set-up has nothing left to remove
    async_remove_retired_entities(MagicMock(), MagicMock())
    assert removed == ["b.nonstop"]


@pytest.mark.asyncio
async def test_setup_adds_entities_now_and_for_devices_seen_later(monkeypatch) -> None:
    retired: list[object] = []
    enabled: list[list[str]] = []
    monkeypatch.setattr(
        binary_sensor_module,
        "async_remove_retired_entities",
        lambda hass, entry: retired.append(entry),
    )
    monkeypatch.setattr(
        entity_module,
        "async_enable_entities",
        lambda hass, platform, unique_ids: enabled.append(list(unique_ids)),
    )
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(decode(_salt_frame(0xD3)))
    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator
    added: list[AsekoLocalBinarySensorEntity] = []

    await binary_sensor_module.async_setup_entry(MagicMock(), entry, added.extend)

    assert retired == [entry]
    first = len(added)
    assert first > 0
    assert all(e.unique_id.startswith(str(SERIAL)) for e in added)
    assert enabled[0]  # the quantities the unit shows are enabled
    assert entry.async_on_unload.call_count == 2
    (new_device,) = coordinator._new_device_listeners
    (new_features,) = coordinator._new_features_listeners

    new_device(AsekoDevice(serial_number=42))  # a unit with nothing to show
    assert len(added) == first

    other = decode(_salt_frame(0xD3))
    other.serial_number = 5678
    new_device(other)
    assert len(added) == 2 * first
    assert all(e.unique_id.startswith("5678") for e in added[first:])

    enabled.clear()
    new_features(other, frozenset({"backwash_running"}))
    assert enabled == [["5678backwash_active"]]
    assert len(added) == 2 * first  # enabled, not added again


def test_is_on_reads_the_device_and_is_unknown_while_none() -> None:
    description = next(d for d in BINARY_SENSORS if d.key == "service_menu")
    device = decode(_salt_frame(0xD7))  # P1, menu open
    entity = AsekoLocalBinarySensorEntity(device, _coordinator(), description)

    assert entity.is_on is True
    device.service_menu_open = False
    assert entity.is_on is False
    device.service_menu_open = None
    assert entity.is_on is None


# Exists when the unit sends its clock, but shows what the clock tracker made of it.
_READS_ANOTHER_FIELD = {"clock_out_of_sync": "clock_out_of_sync"}


def test_every_description_reads_its_own_field() -> None:
    """A copy-pasted value_fn would show one quantity under another's name."""
    for description in BINARY_SENSORS:
        field = _READS_ANOTHER_FIELD.get(description.key, description.feature)
        device = AsekoDevice()
        setattr(device, field, True)
        assert description.value_fn(device) is True, description.key
        setattr(device, field, None)
        assert description.value_fn(device) is None, description.key


def test_a_salt_net_names_its_algicide_port_for_algicide_or_aco() -> None:
    """The Salt NET port doses ALGICID or the ACO stabiliser ("Alg/Aco")."""
    description = next(d for d in BINARY_SENSORS if d.key == "algicide_pump_running")
    salt_net = AsekoLocalBinarySensorEntity(
        decode(SALT_NET_106_FRAME), _coordinator(), description
    )
    salt_v7 = AsekoLocalBinarySensorEntity(
        decode(_salt_frame(0xD3)), _coordinator(), description
    )

    assert salt_net.translation_key == "algaecide_pump_running_or_aco"
    assert salt_v7.translation_key == "algaecide_pump_running"
    # only the name changes; the unique id, and so the entity, stays
    assert salt_net.unique_id == "123456789algicide_pump_running"


@pytest.mark.parametrize("language", ["en", "cs", "de", "fr"])
def test_every_algicide_or_aco_name_is_translated(language) -> None:
    path = Path(entity_module.__file__).parent / "translations" / f"{language}.json"
    entities = json.loads(path.read_text(encoding="utf-8"))["entity"]
    keys = {key for platform in entities.values() for key in platform}

    for key in entity_module.ALGICIDE_TRANSLATION_KEYS:
        assert key in keys, key
        assert f"{key}_or_aco" in keys, key
