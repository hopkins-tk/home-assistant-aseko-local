"""Values worked out from decoded ones: the decoded value stays as sent beside them."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.aseko_local.binary_sensor import _build_binary_sensor_entities
from custom_components.aseko_local.coordinator import AsekoLocalDataUpdateCoordinator
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.decoding.derived import (
    DERIVED,
    chlorine_production,
    filtration_running,
    heating_allowed,
    possible,
)
from custom_components.aseko_local.decoding.features import ALL_FEATURES
from custom_components.aseko_local.decoding.profiles import ALL_PROFILES
from custom_components.aseko_local.decoding.support_matrix import render
from custom_components.aseko_local.entity import enabled_unique_ids
from custom_components.aseko_local.models import AsekoDevice, AsekoProfileFlag
from custom_components.aseko_local.sensor import _build_sensor_entities

from .test_decode_v7 import _make_base_bytes
from .test_decode_v8 import REFERENCE_FRAME, REFERENCE_FRAME_105

HOME = frozenset({AsekoProfileFlag.MENU_BIT_SWITCHES_FILTRATION_OFF})


@pytest.mark.parametrize(
    ("control", "condition", "expected"),
    [
        (True, True, True),
        (True, False, False),
        (True, None, None),
        (False, True, False),  # the bit the unit sets with heating control off
        (False, None, False),
        (None, True, None),
    ],
)
def test_heating_allowed_needs_heating_control(control, condition, expected) -> None:
    device = AsekoDevice(
        heating_control_enabled=control, heating_condition_met=condition
    )
    assert heating_allowed(device) is expected


@pytest.mark.parametrize(
    ("running", "measured", "expected"),
    [
        (True, 22, 22),
        (True, None, None),
        (False, 18, 0),  # the run-down after a stop
        (False, None, 0),
        (None, 18, None),
    ],
)
def test_chlorine_production_reads_zero_while_stopped(
    running, measured, expected
) -> None:
    device = AsekoDevice(
        electrolysis_running=running, chlorine_production_measured=measured
    )
    assert chlorine_production(device) == expected


@pytest.mark.parametrize(
    ("flags", "relay", "menu", "expected"),
    [
        (HOME, True, True, False),  # switched off by hand at the unit
        (HOME, True, False, True),
        (HOME, False, True, False),
        (HOME, None, True, None),
        (frozenset(), True, True, True),  # elsewhere the menu bit is presence only
        (frozenset(), True, None, True),  # v8: no menu bit at all
        (frozenset(), None, None, None),
    ],
)
def test_filtration_running_is_the_relay_unless_home_switched_it_off(
    flags, relay, menu, expected
) -> None:
    device = AsekoDevice(flags=flags, filtration_relay=relay, service_menu_open=menu)
    assert filtration_running(device) is expected


def test_derived_fields_are_not_read_from_the_frame() -> None:
    """A field is either decoded or derived, and a derived one only reads decoded ones."""
    decoded = {f.field for f in ALL_FEATURES}
    for derived in DERIVED:
        assert derived.field not in decoded
        assert set(derived.requires) <= decoded


def test_a_derived_value_needs_all_its_fields() -> None:
    assert possible(frozenset({"heating_condition_met"})) == frozenset()
    assert possible(
        frozenset({"heating_condition_met", "heating_control_enabled"})
    ) == {"heating_allowed"}


#: Which derived values each profile has.  A profile gets one automatically
#: when it lists all the fields the value needs; this table makes the change
#: visible: a new profile, or a feature added to one, fails here until the
#: derived values it brings are checked and written down.
EXPECTED_DERIVED = {
    "v7 HOME": {"filtration_running"},
    "v7 SALT": {"chlorine_production", "filtration_running", "heating_allowed"},
    "v7 OXY": {"filtration_running"},
    "v7 NET": set(),
    "v7 PROFI": {"filtration_running"},
    "v7 unknown unit type": {"filtration_running"},
    "v8 NET": {"filtration_running"},
    "v8 SALT": {"chlorine_production", "filtration_running"},
    "v8 unknown header type": {"filtration_running"},
}


def test_every_profile_has_the_derived_values_it_is_meant_to() -> None:
    assert {
        p.name: set(possible(p.feature_names)) for p in ALL_PROFILES
    } == EXPECTED_DERIVED


def _frame_for(profile_name: str) -> bytes:
    """Return a frame that this profile decodes."""
    if profile_name == "v8 NET":
        return REFERENCE_FRAME
    if profile_name == "v8 SALT":
        return REFERENCE_FRAME_105
    unit_type = {
        "v7 HOME": 0x02,
        "v7 SALT": 0x0E,
        "v7 OXY": 0x05,
        "v7 NET": 0x09,
        "v7 PROFI": 0x10,
        "v7 unknown unit type": 0x06,
    }[profile_name]
    data = _make_base_bytes()
    data[4] = unit_type
    return bytes(data)


@pytest.mark.parametrize(
    "profile",
    # the unknown v8 header type has no reference frame; its readings are v8 NET's
    [p for p in ALL_PROFILES if p.name != "v8 unknown header type"],
    ids=lambda p: p.name,
)
def test_each_model_fills_its_derived_values(profile) -> None:
    """Decoding a frame of the model computes every derived value it has."""
    device = decode(_frame_for(profile.name))
    assert device.profile == profile.name
    for derived in DERIVED:
        if derived.field in EXPECTED_DERIVED[profile.name]:
            assert derived.field in device.possible_features, derived.field
            if device.features.issuperset(derived.requires):
                assert derived.field in device.features, derived.field
                assert getattr(device, derived.field) == derived.compute(device)
        else:
            assert derived.field not in device.possible_features, derived.field


def test_salt_frame_carries_both_values() -> None:
    data = _make_base_bytes()  # SALT
    data[21] = 18
    data[29] = 0x08  # filtration on, electrolyser stopped
    data[37] = 0x51  # heating control off, period 1, water level
    data[78] = 0x80  # heating condition met
    device = decode(bytes(data))
    assert device.chlorine_production_measured == 18
    assert device.chlorine_production == 0
    assert device.heating_condition_met is True
    assert device.heating_allowed is False
    assert device.filtration_relay is True
    assert device.filtration_running is True
    for field in (
        "chlorine_production",
        "chlorine_production_measured",
        "heating_allowed",
        "heating_condition_met",
        "filtration_running",
        "filtration_relay",
    ):
        assert field in device.features, field
        assert field in device.possible_features, field


def test_a_derived_value_is_absent_with_an_absent_input() -> None:
    """NET has no electrolyser: neither value, nor an entity for either."""
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    device = decode(bytes(data))
    assert "chlorine_production" not in device.possible_features
    assert "chlorine_production" not in device.features


def _coordinator() -> AsekoLocalDataUpdateCoordinator:
    hass = MagicMock()
    hass.config.path.side_effect = lambda *parts: "/tmp/aseko_test/" + "/".join(parts)
    hass.async_create_task.side_effect = lambda coro, *args, **kwargs: coro.close()
    entry = MagicMock()
    entry.data = {"host": "0.0.0.0", "port": 47524}
    entry.unique_id = "test"
    return AsekoLocalDataUpdateCoordinator(hass, entry)


def test_the_decoded_entities_sit_beside_the_derived_ones() -> None:
    """The measured output and the relay start disabled; the condition bit does not."""
    device = decode(bytes(_make_base_bytes()))
    coordinator = _coordinator()
    entities = _build_sensor_entities([device], coordinator) + (
        _build_binary_sensor_entities([device], coordinator)
    )
    by_key = {e.entity_description.key: e for e in entities}
    enabled = set(enabled_unique_ids(entities))

    for key in ("electrolyzer", "pump_running", "heating_allowed"):
        assert by_key[key].unique_id in enabled, key
    assert by_key["heating_condition_met"].unique_id in enabled
    for key in ("chlorine_production_measured", "filtration_relay"):
        assert by_key[key].unique_id not in enabled, key
        assert by_key[key].entity_registry_enabled_default is False, key


def test_the_flags_a_rule_reads_are_declared_and_used() -> None:
    """A flag declared on a derived value is carried by some profile, and shown."""
    matrix = render()
    for derived in DERIVED:
        for flag in derived.flags:
            assert any(flag in p.flags for p in ALL_PROFILES), flag
    assert "v7 HOME (`MENU_BIT_SWITCHES_FILTRATION_OFF`)" in matrix
