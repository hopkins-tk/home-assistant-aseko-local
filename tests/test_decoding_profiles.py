"""Tests for the profile-driven decoder: features, profiles, detection, engine.

The byte-level behaviour of every reading is covered by test_decode_v7.py
and test_decode_v8.py through decoding.decode().  What is tested here
is the machinery those facades stand on: that the registry is consistent,
that a profile cannot be built wrong, that detection picks the right profile
for the right frame, and that the device says how it was decoded.
"""

from __future__ import annotations

import logging
from dataclasses import fields

import pytest

from custom_components.aseko_local.const import UNIT_TYPE_PROFI, WATER_FLOW_TO_PROBES
from custom_components.aseko_local.decoding import decode, engine
from custom_components.aseko_local.decoding.derived import DERIVED
from custom_components.aseko_local.decoding.evidence import (
    Evidence,
    EvidenceStatus,
    assumed,
    confirmed,
    confirmed_on,
    not_located,
)
from custom_components.aseko_local.decoding.feature import Feature
from custom_components.aseko_local.decoding.features import (
    ALL_FEATURES,
    AlgaecideFlowRate,
    AlgaecidePumpRunning,
    Configuration,
    FiltrationPeriod2Start,
    FiltrationRelay,
    FiltrationSchedule,
    FlocculantPumpRunning,
    HeatingControlEnabled,
    Ph,
    PhTarget,
    ServiceMenuOpen,
)
from custom_components.aseko_local.decoding.frames import (
    Protocol,
    parse_frame,
    parse_v7,
    parse_v8,
    v7_bad_checksum_segments,
)
from custom_components.aseko_local.decoding.frames import v7 as frame_module
from custom_components.aseko_local.decoding.profile import Profile
from custom_components.aseko_local.decoding.profiles import (
    ALL_PROFILES,
    FALLBACK_PROFILES,
    detect_profile,
    profile_for,
    v7,
    v8,
)
from custom_components.aseko_local.models import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoFiltrationSchedule,
    AsekoProfileFlag,
)
from custom_components.aseko_local.sensor import device_has_pump

from .test_decode_v7 import _make_base_bytes
from .test_decode_v8 import REFERENCE_FRAME, REFERENCE_FRAME_105

DEVICE_FIELDS = {f.name for f in fields(AsekoDevice)}


def _home_bytes(byte37: int) -> bytes:
    data = _make_base_bytes()
    data[4] = 0x02  # HOME, CLF
    data[37] = byte37
    return bytes(data)


# ── the feature registry ─────────────────────────────────────────────────────


def test_every_feature_fills_one_real_field() -> None:
    """One feature, one field on AsekoDevice, no two features on the same one."""
    seen: dict[str, type[Feature]] = {}
    for feature in ALL_FEATURES:
        assert feature.field in DEVICE_FIELDS, feature.__name__
        assert feature.field not in seen, (feature.__name__, seen[feature.field])
        seen[feature.field] = feature


def test_every_frame_derived_field_has_a_feature() -> None:
    """The fields the decoder does not own are the tracker's and the profile's."""
    owned = {f.field for f in ALL_FEATURES} | {d.field for d in DERIVED}
    not_from_the_frame = {
        "device_type",  # set from the profile
        "profile",  # the name of the profile that read the frame
        "frame_problems",  # what the v8 parser could not read
        "features",
        "possible_features",  # set from the profile
        "present_features",  # the frame's features, kept apart from the sticky ones
        "flags",
        "last_seen",  # stamped by the coordinator
        "received_at",  # stamped by the server
        "last_backwash",  # BackwashTracker
        "last_scheduled_backwash",
        "last_scheduled_backwash_source",
        "last_manual_backwash",
        "last_backwash_trigger",
        "next_scheduled_backwash",
        "clock_offset",  # ClockTracker
        "clock_out_of_sync",
    }
    assert DEVICE_FIELDS - owned == not_from_the_frame


def test_default_and_named_readings() -> None:
    # the settings menu bit is v7 only; pH is read on both protocols
    assert ServiceMenuOpen.default_reading(Protocol.V7) == "decode_v7"
    assert ServiceMenuOpen.default_reading(Protocol.V8) is None
    assert ServiceMenuOpen.readings(Protocol.V7) == ("decode_v7",)
    assert ServiceMenuOpen.protocols() == (Protocol.V7,)
    assert Ph.protocols() == (Protocol.V7, Protocol.V8)


def test_unmapped_features_have_no_reading_and_no_profile() -> None:
    """pH+ is a field on the device but nothing knows how to read it yet."""
    unmapped = [f for f in ALL_FEATURES if not f.protocols()]
    assert {f.field for f in unmapped} == {
        "ph_plus_pump_running",
        "ph_plus_flow_rate",
    }
    for profile in ALL_PROFILES:
        for feature in unmapped:
            assert feature not in profile.features


# ── profiles ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.name)
def test_profile_plan_respects_dependencies(profile: Profile) -> None:
    position = {type(feature): i for i, (feature, _) in enumerate(profile.plan)}
    assert len(position) == len(profile.features)
    for feature in profile.features:
        for dependency in feature.depends_on:
            if dependency in position:
                assert position[dependency] < position[feature], (
                    profile.name,
                    feature.__name__,
                )


@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.name)
def test_profile_readings_match_its_protocol(profile: Profile) -> None:
    for feature, read in profile.plan:
        assert read.__name__.startswith(f"decode_{profile.protocol.value}")
        assert type(feature).has_reading(read.__name__)
    assert profile.feature_names <= DEVICE_FIELDS


def test_overrides_pick_the_named_reading() -> None:
    assert v7.HOME.reading_for(FiltrationSchedule) == "decode_v7"
    assert v7.HOME.reading_for(FiltrationRelay) == "decode_v7"
    assert v7.OXY.reading_for(AlgaecidePumpRunning) == "decode_v7_oxy"


def test_a_feature_absent_from_a_profile_is_a_model_without_it() -> None:
    assert FiltrationPeriod2Start not in v7.NET.features
    assert ServiceMenuOpen in v7.HOME.features
    assert "backwash_running" not in v7.NET.feature_names
    assert "backwash_running" in v7.SALT.feature_names


def test_only_salt_treats_the_menu_bit_as_presence() -> None:
    with_flag = {
        p.name
        for p in ALL_PROFILES
        if AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY in p.flags
    }
    assert with_flag == {"v7 SALT"}


def test_profile_rejects_a_feature_without_a_reading_for_its_protocol() -> None:
    with pytest.raises(ValueError, match="has no v8 reading"):
        Profile(
            name="broken",
            protocol=Protocol.V8,
            model=AsekoDeviceType.NET,
            features=(ServiceMenuOpen,),
        )


def test_profile_rejects_an_override_naming_a_missing_reading() -> None:
    with pytest.raises(ValueError, match="has no reading"):
        Profile(
            name="broken",
            protocol=Protocol.V7,
            model=AsekoDeviceType.SALT,
            features=(FiltrationSchedule,),
            overrides={FiltrationSchedule: "decode_v7_salt_special"},
        )


def test_profile_rejects_an_override_for_an_unlisted_feature() -> None:
    with pytest.raises(ValueError, match="unlisted"):
        Profile(
            name="broken",
            protocol=Protocol.V7,
            model=AsekoDeviceType.SALT,
            features=(Ph,),
            overrides={FiltrationSchedule: "decode_v7_home_a"},
        )


def test_profile_rejects_an_override_from_the_other_protocol() -> None:
    with pytest.raises(ValueError, match="is not a v8 reading"):
        Profile(
            name="broken",
            protocol=Protocol.V8,
            model=AsekoDeviceType.NET,
            features=(Ph,),
            overrides={Ph: "decode_v7"},
        )


def test_profile_orders_dependencies_ahead_whatever_the_listing_says() -> None:
    profile = Profile(
        name="reordered",
        protocol=Protocol.V7,
        model=AsekoDeviceType.SALT,
        features=(AlgaecidePumpRunning, AlgaecideFlowRate, Ph, Configuration),
    )
    order = [type(feature) for feature, _ in profile.plan]
    assert order.index(AlgaecideFlowRate) < order.index(AlgaecidePumpRunning)
    assert order.index(Configuration) < order.index(Ph)


def test_profile_detects_a_dependency_cycle() -> None:
    class A(Feature):
        field = "ph"

        def decode_v7(self, frame, device) -> None:
            return None

    class B(Feature):
        field = "redox"
        depends_on = (A,)

        def decode_v7(self, frame, device) -> None:
            return None

    A.depends_on = (B,)
    with pytest.raises(ValueError, match="cycle"):
        Profile(name="cyclic", protocol=Protocol.V7, model=None, features=(A, B))


# ── detection ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("unit_type", "expected"),
    [
        (0x0D, v7.SALT),
        (0x0E, v7.SALT),
        (0x0F, v7.SALT),
        (0x09, v7.NET),
        (0x0A, v7.NET),
        (0x0B, v7.NET),
        (0x05, v7.OXY),
        (UNIT_TYPE_PROFI, v7.PROFI),
        (0x00, v7.UNKNOWN),
        # unmapped values in between used to be taken for a neighbouring model
        (0x01, v7.UNKNOWN),
        (0x06, v7.UNKNOWN),
        (0x08, v7.UNKNOWN),
        (0x0C, v7.UNKNOWN),
        (0x11, v7.UNKNOWN),
        (0xFF, v7.UNKNOWN),
    ],
)
def test_detect_v7_model_from_byte4(unit_type: int, expected: Profile) -> None:
    data = _make_base_bytes()
    data[4] = unit_type
    assert detect_profile(parse_v7(bytes(data))) is expected


def test_detect_v8_model_from_header_type() -> None:
    assert detect_profile(parse_v8(REFERENCE_FRAME)) is v8.NET
    assert detect_profile(parse_v8(REFERENCE_FRAME_105)) is v8.SALT


@pytest.mark.parametrize(
    ("header_type", "expected"),
    [
        (804, "v8 NET"),
        (805, "v8 NET"),
        (812, "v8 NET"),
        (899, "v8 NET"),
        (105, "v8 SALT"),
        (199, "v8 SALT"),
        (999, "v8 unknown header type"),
        (42, "v8 unknown header type"),
    ],
)
def test_detect_v8_model_from_the_header_line(header_type: int, expected: str) -> None:
    """The product line picks the model, whatever the firmware version in it."""
    frame = parse_v8(REFERENCE_FRAME.replace(b" 804 ", f" {header_type} ".encode()))
    assert detect_profile(frame).name == expected


def test_parse_frame_picks_the_protocol() -> None:
    assert parse_frame(bytes(_make_base_bytes())).protocol is Protocol.V7
    assert parse_frame(REFERENCE_FRAME).protocol is Protocol.V8
    assert parse_frame(b"\n" + REFERENCE_FRAME).protocol is Protocol.V8


@pytest.mark.parametrize("byte37", [0x43, 0x53, 0x49, 0x01, 0x31, 0xFF])
def test_every_home_frame_uses_the_one_home_profile(byte37: int) -> None:
    """The old firmware A / B split was byte[37] bit 0x40, the Waterlevel setting."""
    assert detect_profile(parse_v7(_home_bytes(byte37))) is v7.HOME
    assert profile_for(Protocol.V7, AsekoDeviceType.HOME) is v7.HOME
    assert profile_for(Protocol.V7, None) is v7.UNKNOWN


@pytest.mark.parametrize(
    ("byte37", "level_meter", "flow_detection", "menu", "schedule"),
    [
        (0x43, True, True, False, AsekoFiltrationSchedule.NONSTOP_24H),  # once "A"
        (0x53, True, True, False, AsekoFiltrationSchedule.TIMER_PERIOD_1),  # once "A"
        (0x47, True, True, True, AsekoFiltrationSchedule.NONSTOP_24H),  # "transitional"
        (0x11, False, False, False, AsekoFiltrationSchedule.TIMER_PERIOD_1),  # once "B"
        (0x35, False, False, True, AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2),
    ],
)
def test_home_byte37_is_one_bit_field(
    byte37: int, level_meter: bool, flow_detection: bool, menu: bool, schedule
) -> None:
    device = decode(_home_bytes(byte37))
    assert device.water_level_sensor_enabled is level_meter
    assert device.flow_detection_enabled is flow_detection
    assert device.service_menu_open is menu
    assert device.filtration_schedule is schedule


# ── the engine, and what the device says about itself ───────────────────────


def test_decoded_device_says_how_it_was_read() -> None:
    device = decode(_home_bytes(0x43))
    assert device.device_type is AsekoDeviceType.HOME
    assert device.features <= device.possible_features
    assert device.possible_features == v7.HOME.feature_names | {"filtration_running"}
    assert "filtration_schedule" in device.features
    assert device.flags == {AsekoProfileFlag.MENU_BIT_SWITCHES_FILTRATION_OFF}

    salt = decode(bytes(_make_base_bytes()))
    assert AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY in salt.flags

    net_v8 = decode(REFERENCE_FRAME)
    assert net_v8.features <= net_v8.possible_features
    assert "ph" in net_v8.features
    assert "filtration_period_1_start" not in net_v8.features


def test_decode_detects_the_protocol_or_takes_it() -> None:
    raw = bytes(_make_base_bytes())
    assert decode(raw) == decode(raw, Protocol.V7)
    assert decode(REFERENCE_FRAME) == decode(REFERENCE_FRAME, Protocol.V8)
    frame = parse_v7(raw)
    assert decode(raw) == engine.decode(frame, detect_profile(frame))


def test_a_field_outside_the_profile_stays_none_whatever_the_frame_says() -> None:
    """NET has no filtration output; the bytes are read by nobody."""
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    device = decode(bytes(data))
    assert "filtration_period_1_start" not in device.features
    assert device.filtration_period_1_start is None
    assert device.filtration_running is None
    assert "filtration_running" not in device.possible_features


def test_home_menu_override_forces_the_pump_off() -> None:
    """The derived value says off; the relay bit stays as sent."""
    data = _make_base_bytes()
    data[4] = 0x02
    data[29] = 0x08  # relay bit says running
    data[37] = 0x15  # period 1, settings menu open
    device = decode(bytes(data))
    assert device.service_menu_open is True
    assert device.filtration_relay is True
    assert device.filtration_running is False

    data[37] = 0x11  # menu closed
    assert decode(bytes(data)).filtration_running is True


def test_the_menu_bit_does_not_switch_salt_filtration_off() -> None:
    """On SALT byte[37] 0x04 only says somebody is at the menu."""
    data = _make_base_bytes()  # SALT
    data[29] = 0x08
    data[37] = 0xD7  # period 1, settings menu open
    device = decode(bytes(data))
    assert device.service_menu_open is True
    assert device.filtration_running is True


def test_entity_layer_reads_pump_presence_off_the_device() -> None:
    data = _make_base_bytes()
    data[4] = 0x09  # NET
    data[28] = WATER_FLOW_TO_PROBES
    data[29] = 0x00
    net = decode(bytes(data))
    assert device_has_pump(net, "cl")
    assert device_has_pump(net, "ph_minus")
    assert not device_has_pump(net, "algicide")  # not a NET feature
    assert not device_has_pump(net, "ph_plus")  # nobody's feature

    salt = decode(bytes(_make_base_bytes()))  # byte[37] = 0xFF
    assert "algaecide_pump_running" in v7.SALT.feature_names  # the model has it
    assert "algaecide_pump_running" not in salt.features  # this unit's port is unrouted
    assert not device_has_pump(salt, "algicide")


# ── the three states: value, unknown, not present ───────────────────────────


def test_a_probe_the_unit_lacks_is_not_present() -> None:
    """SALT with a REDOX probe: the model reads free chlorine, this unit has none."""
    salt = decode(bytes(_make_base_bytes()))  # byte[4] = 0x0E, REDOX
    assert "free_chlorine" in v7.SALT.feature_names
    assert "free_chlorine" not in salt.features
    assert salt.free_chlorine is None
    assert "redox" in salt.features
    assert "redox_target" in salt.features
    assert "free_chlorine_target" not in salt.features


def test_a_setting_unset_on_the_unit_is_not_present() -> None:
    data = _make_base_bytes()
    data[68] = 0xFF  # backwash interval never configured
    data[76:78] = b"\xff\xff"  # max filling time not implemented
    device = decode(bytes(data))
    assert "backwash_interval" not in device.features
    assert "max_refill_time" not in device.features
    assert "backwash_running" in device.features  # the valve itself is there


def test_a_value_unknown_in_this_frame_stays_present() -> None:
    """byte[37] unset: the unit has a schedule, this frame just does not say which."""
    salt = decode(bytes(_make_base_bytes()))  # byte[37] = 0xFF
    assert "filtration_schedule" in salt.features
    assert salt.filtration_schedule is None
    assert "service_menu_open" in salt.features
    assert salt.service_menu_open is None

    home = decode(_home_bytes(0xFF))
    assert "heating_control_enabled" in home.features
    assert home.heating_control_enabled is None
    assert "service_menu_open" in home.features
    assert home.service_menu_open is None


def test_unset_byte22_and_byte78_settings_read_unknown_but_stay_present() -> None:
    """A unit with these settings always sends 0 or 1 bits; 0xFF is an odd frame.

    Every captured SALT frame carries a real value in bytes 22 and 78, so the
    entities exist; a frame with 0xFF there shows them unknown, not
    unavailable, like the byte[37] settings.
    """
    data = _make_base_bytes()  # SALT
    data[22] = 0xFF
    data[78] = 0xFF
    device = decode(bytes(data))
    fields = (
        "backwash_schedule_enabled",
        "variable_speed_pump_enabled",
        "heating_condition",
        "heating_condition_met",
        "variable_speed_pump_type",
    )
    for field in fields:
        assert getattr(device, field) is None, field
        assert field in device.features, field


def test_shared_port_routing_decides_which_chemical_is_present() -> None:
    data = _make_base_bytes()
    data[101] = 40
    data[37] = 0x43  # SALT, bit 0x80 clear: shared port routed to flocculant
    device = decode(bytes(data))
    assert "flocculant_flow_rate" in device.features
    assert "flocculant_pump_running" in device.features
    assert "algaecide_flow_rate" not in device.features
    assert "algaecide_pump_running" not in device.features

    data[37] = 0xC3  # bit 0x80 set: routed to algicide
    device = decode(bytes(data))
    assert "algaecide_flow_rate" in device.features
    assert "flocculant_flow_rate" not in device.features


def test_v8_sentinel_means_not_present() -> None:
    """v8 cannot tell an absent probe from an unreadable one; both are -500."""
    frame = REFERENCE_FRAME.replace(b"ains: 708 708", b"ains: -500 708")
    device = decode(frame)
    assert "ph" not in device.features
    assert device.ph is None
    assert "redox" in device.features


def _with_checksums(data: bytearray) -> bytearray:
    """Set bytes 39, 79 and 119 to 0xAA XOR the 39 bytes before each."""
    for start in (0, 40, 80):
        checksum = 0xAA
        for value in data[start : start + 39]:
            checksum ^= value
        data[start + 39] = checksum
    return data


def test_v7_checksum_rule_holds_for_a_valid_frame() -> None:
    data = _with_checksums(_make_base_bytes())
    assert v7_bad_checksum_segments(bytes(data)) == []


def test_v7_bad_checksum_is_logged_once_and_decoding_continues(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(frame_module, "_checksum_warned", set())
    good = _with_checksums(_make_base_bytes())
    bad = bytearray(good)
    bad[119] ^= 0x01  # break segment 3 only

    assert v7_bad_checksum_segments(bytes(bad)) == [2]

    with caplog.at_level(logging.DEBUG, logger=frame_module.__name__):
        expected = decode(bytes(good))
        assert not [r for r in caplog.records if "checksum" in r.getMessage()]

        first = decode(bytes(bad))
        second = decode(bytes(bad))

    # Same values as the intact frame: the checksum changes nothing.
    assert first == expected
    assert second == expected
    levels = [r.levelno for r in caplog.records if "checksum" in r.getMessage()]
    assert levels == [logging.WARNING, logging.DEBUG]


def test_profiles_leave_out_what_the_model_does_not_have() -> None:
    """Chemicals a model cannot dose are not listed, so they get no entity.

    A SALT makes its chlorine by electrolysis: no chlorine pump on v7 or v8
    (the Aseko Live app gives Salt units pH-, algicide and an electrode, but
    no chlorine canister).  NET doses pH and chlorine only and has no heater;
    PROFI doses flocculant but not algicide.
    """
    assert "chlorine_flow_rate" not in v7.SALT.feature_names
    assert "chlorine_pump_running" not in v7.SALT.feature_names
    assert "chlorine_flow_rate" not in v8.SALT.feature_names
    assert "chlorine_pump_running" not in v8.SALT.feature_names
    assert "chlorine_pump_running" in v8.NET.feature_names

    for field in (
        "algaecide_dose_target",
        "flocculant_dose_target",
        "algaecide_flow_rate",
        "flocculant_flow_rate",
        "water_temperature_target",
    ):
        assert field not in v7.NET.feature_names, field

    assert "algaecide_flow_rate" not in v7.PROFI.feature_names
    assert "flocculant_flow_rate" in v7.PROFI.feature_names


def test_v8_salt_frame_gets_no_chlorine_counter_inputs() -> None:
    device = decode(REFERENCE_FRAME_105)
    assert device.device_type == AsekoDeviceType.SALT
    assert "chlorine_pump_running" not in device.features
    assert "chlorine_flow_rate" not in device.features
    assert device.chlorine_flow_rate is None


def test_not_located_reading_keeps_the_value_unknown_but_present() -> None:
    """A value the model has but nobody has found in the frame yet.

    Every feature accepts ``decode_v7_not_located``; it reads None, so the
    device lists the field (the entity exists) and the value stays unknown.
    """
    assert v7.OXY.reading_for(HeatingControlEnabled) == "decode_v7_not_located"
    assert "decode_v7_not_located" not in HeatingControlEnabled.readings()

    data = _make_base_bytes()
    data[4] = 0x05  # OXY
    device = decode(bytes(data))
    for field in ("heating_control_enabled", "freeze_protection_enabled"):
        assert field in device.features, field
        assert getattr(device, field) is None, field


def test_salt_settings_found_with_marked_test_cases() -> None:
    """byte[22] / byte[37] / byte[78] flags toggled one at a time on an ASIN AQUA Salt."""
    data = _make_base_bytes()  # SALT
    data[37] = 0xDB  # flow detection, heating control, period 1, level meter, algicide
    data[22] = 0x3A  # backwash schedule, below, outside temperature, VS pump on
    data[78] = 0x85  # heating condition met, Pentair / Dab
    data[29] = 0x50  # electrolysis running, right polarity
    device = decode(bytes(data))
    assert device.flow_detection_enabled is True
    assert device.water_level_sensor_enabled is True
    assert device.heating_control_enabled is True
    assert device.backwash_schedule_enabled is True
    assert device.freeze_protection_enabled is False
    assert device.variable_speed_pump_enabled is True
    assert device.heating_condition.value == "outside_temperature_below"
    assert device.heating_condition_met is True
    assert device.heating_allowed is True
    assert device.variable_speed_pump_type.value == "pentair_dab"
    assert device.electrode_polarity.value == "right"

    data[22] = 0x05  # time window, winter mode
    data[78] = 0x49  # winter, Hayward
    data[29] = 0x10  # running, left
    device = decode(bytes(data))
    assert device.heating_condition.value == "time_window"
    assert device.freeze_protection_enabled is True
    assert device.backwash_schedule_enabled is False
    assert device.heating_condition_met is False
    assert device.heating_allowed is False
    assert device.variable_speed_pump_type.value == "hayward"
    assert device.electrode_polarity.value == "left"


def test_profile_rejects_a_feature_whose_dependency_is_not_listed() -> None:
    """A pH target without the probe configuration would silently read nothing."""
    with pytest.raises(ValueError, match="needs Configuration"):
        Profile(
            name="broken",
            protocol=Protocol.V7,
            model=AsekoDeviceType.SALT,
            features=(PhTarget,),
        )


def test_an_optional_dependency_may_be_left_out() -> None:
    """v8 reads the flocculant pump without the v7 flow rate."""
    profile = Profile(
        name="flocculant pump only",
        protocol=Protocol.V8,
        model=AsekoDeviceType.SALT,
        features=(FlocculantPumpRunning,),
    )
    assert profile.feature_names == {"flocculant_pump_running"}


def test_a_profile_cannot_be_changed_in_memory() -> None:
    """The plan is built once from overrides and evidence; they stay read-only."""
    with pytest.raises(TypeError):
        v7.HOME.overrides[FiltrationSchedule] = "decode_v7"  # type: ignore[index]
    with pytest.raises(TypeError):
        v7.HOME.evidence[FiltrationSchedule] = confirmed("nothing")  # type: ignore[index]


def test_every_feature_of_a_model_profile_has_evidence() -> None:
    """docs/evidence-rules.md: every listed feature says why it is believed."""
    missing = {
        profile.name: [f.field for f in profile.features if f not in profile.evidence]
        for profile in ALL_PROFILES
        if profile not in FALLBACK_PROFILES
    }
    assert {name: fields for name, fields in missing.items() if fields} == {}


def test_fallback_profiles_have_evidence_for_every_feature_too() -> None:
    for profile in FALLBACK_PROFILES:
        assert set(profile.features) == set(profile.evidence), profile.name


def _ph_profile(
    evidence: object, overrides: dict | None = None, model=AsekoDeviceType.SALT
) -> Profile:
    return Profile(
        name="evidence check",
        protocol=Protocol.V7,
        model=model,
        features=(Configuration, Ph),
        overrides=overrides or {},
        evidence={Ph: evidence},
    )


def test_evidence_must_be_an_evidence_entry() -> None:
    """A plain string would dodge the status check; it fails at import instead."""
    with pytest.raises(TypeError, match="must be an Evidence"):
        _ph_profile("confirmed: typo-proof")


def test_confirmed_on_the_profiles_own_model_is_refused() -> None:
    with pytest.raises(ValueError, match="own model is confirmed"):
        _ph_profile(confirmed_on(AsekoDeviceType.SALT, "byte[14]"))
    _ph_profile(confirmed_on(AsekoDeviceType.HOME, "byte[14]"))  # another model: fine


def test_not_located_evidence_goes_with_a_not_located_reading_only() -> None:
    with pytest.raises(ValueError, match="not_located"):
        _ph_profile(not_located("the manual shows it"))
    with pytest.raises(ValueError, match="not_located"):
        _ph_profile(assumed("as on OXY"), overrides={Ph: "decode_v7_not_located"})
    _ph_profile(
        not_located("the manual shows it"), overrides={Ph: "decode_v7_not_located"}
    )


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: confirmed(" "), "needs a note"),
        (lambda: Evidence(EvidenceStatus.CONFIRMED_ON, "byte[14]"), "confirmed on"),
        (
            lambda: Evidence(
                EvidenceStatus.OBSERVED, "byte[14]", (AsekoDeviceType.HOME,)
            ),
            "confirmed on",
        ),
    ],
)
def test_an_evidence_entry_is_checked_when_it_is_made(make, message) -> None:
    with pytest.raises(ValueError, match=message):
        make()


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: Evidence("typo", "byte[14]"), "EvidenceStatus"),
        (lambda: Evidence(EvidenceStatus.OBSERVED, None), "text"),
        (
            lambda: Evidence(EvidenceStatus.CONFIRMED_ON, "byte[14]", ("HOME",)),
            "AsekoDeviceType",
        ),
    ],
)
def test_an_evidence_entry_of_the_wrong_type_is_refused(make, message) -> None:
    """Audit C2: without a type checker a typo still fails at import."""
    with pytest.raises(TypeError, match=message):
        make()
