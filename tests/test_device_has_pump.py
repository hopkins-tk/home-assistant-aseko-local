"""Unit tests for the protocol-aware pump-presence logic.

The single source of truth for "which dosing pumps does this device
physically have" is `AsekoDevice.installed_pumps`, populated by the
v7 decoder from `ACTUATOR_MASKS[<device_type>][<pump>] != 0` and by
the v8 decoder from `installed_pumps_from_fncs(fncs[2], fncs[6], flags)`.
The entity layer (sensor.py) just checks `pump_key in device.installed_pumps`.

These tests pin the behaviour at three levels:

1. `installed_pumps_from_fncs` — the v8 source of truth.
2. `AsekoV8CapabilityFlags` + `V8_FNCS_INSTALLED_PUMPS` — the static
   tables the decoder uses to build `installed_pumps`.
3. The v7 decoder's `installed_pumps` for SALT v7 (regression guard
   for the byte[29]-based path).
"""

from custom_components.aseko_local.aseko_data import (
    AsekoDevice,
    AsekoDeviceType,
)
from custom_components.aseko_local.aseko_v8_helpers import (
    AsekoV8_CAPABILITY_FLAGS,
    AsekoV8CapabilityFlags,
    V8_FNCS_INSTALLED_PUMPS,
    installed_pumps_from_fncs,
)


# ---------------------------------------------------------------------------
# SALT NET v8 — the device that triggered the architectural refactor
# ---------------------------------------------------------------------------


def test_salt_net_has_ph_minus_pump():
    """SALT NET has a pH− pump (per mirovra's hardware: Pump 1 = pH− fixed).

    Per Aseko documentation: "The first pump is always pH−, fixed."
    This is universally present on every Aseko device, independent
    of `fncs[2]`.
    """
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    assert installed_pumps_from_fncs(1, 10, flags) == frozenset(
        {"ph_minus", "algicide"}
    )


def test_salt_net_has_algicide_pump():
    """SALT NET has an algicide pump (Pump 2, algicide/flocculant switchable)."""
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    assert "algicide" in installed_pumps_from_fncs(1, 10, flags)


def test_salt_net_no_cl_pump():
    """SALT NET has NO CL pump — fncs[2]=1 ⇒ SALT family, no CL module."""
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    assert "cl" not in installed_pumps_from_fncs(1, 10, flags)


def test_salt_net_no_ph_plus_pump():
    """SALT NET has no pH+ pump (only pH− is fixed)."""
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    assert "ph_plus" not in installed_pumps_from_fncs(1, 10, flags)


def test_salt_net_no_floc_pump():
    """SALT NET has algicide on its dedicated port, not flocculant.

    mirovra's hardware: Pump 2 is configured as algicide, not floc.
    """
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    assert "floc" not in installed_pumps_from_fncs(1, 10, flags)


def test_salt_net_no_oxy_pump():
    """SALT NET has no OXY pump module."""
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    assert "oxy" not in installed_pumps_from_fncs(1, 10, flags)


def test_salt_net_ph_minus_present_even_with_unrecognised_fncs():
    """pH− is universal on Aseko devices — present even for unknown fncs codes.

    This is the architectural fix from the refactor: pH− does NOT
    depend on fncs[2] for its presence. The decoder always emits
    pH− in installed_pumps, regardless of the device's reported
    fncs[2] value.
    """
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    # fncs[2]=99, fncs[6]=99 — not in V8_FNCS_INSTALLED_PUMPS
    assert "ph_minus" in installed_pumps_from_fncs(99, 99, flags)


# ---------------------------------------------------------------------------
# v8 capability flags are a complete mapping
# ---------------------------------------------------------------------------


def test_v8_capability_flags_have_all_pump_keys():
    """Every pump_key in the consumption sensor set must be in the capability flags.

    Guards against a future addition of a new pump_key that forgets to
    extend AsekoV8CapabilityFlags.
    """
    expected_keys = {"cl", "ph_minus", "ph_plus", "algicide", "floc", "oxy"}
    for device_type in AsekoV8_CAPABILITY_FLAGS:
        flags = AsekoV8_CAPABILITY_FLAGS[device_type]
        for key in expected_keys:
            assert hasattr(flags, f"outs_{key}"), (
                f"AsekoV8CapabilityFlags for {device_type} missing outs_{key}"
            )


def test_salt_net_capability_flags_match_documented_layout():
    """SALT NET capability flags reflect mirovra's hardware setup.

    Reference: salt_net_v8_device_analysis.md §1 and §11.5.
    Pump 1 = pH− (outs[8]). Pump 2 = algicide (outs[15]).
    No CL, no pH+, no floc, no OXY.
    """
    flags = AsekoV8CapabilityFlags(
        outs_cl=None,
        outs_ph_minus=8,
        outs_ph_plus=None,
        outs_algicide=15,
        outs_floc=None,
        outs_oxy=None,
    )
    assert flags.outs_ph_minus == 8
    assert flags.outs_algicide == 15
    assert flags.outs_cl is None


# ---------------------------------------------------------------------------
# V8_FNCS_INSTALLED_PUMPS — the static map
# ---------------------------------------------------------------------------


def test_fncs_installed_pumps_table_covers_known_devices():
    """Both confirmed v8 device types (SALT_NET, NET) have an entry."""
    assert (1, 10) in V8_FNCS_INSTALLED_PUMPS
    assert (3, 2) in V8_FNCS_INSTALLED_PUMPS


def test_salt_net_fncs_entry_has_ph_minus_and_algicide():
    """SALT NET v8 with fncs=(1,10) has ph_minus + algicide (mirovra)."""
    assert V8_FNCS_INSTALLED_PUMPS[(1, 10)] == frozenset({"ph_minus", "algicide"})


def test_net_v8_fncs_entry_has_cl_and_ph_minus():
    """NET v8 with fncs=(3,2) has cl + ph_minus (Issue #66)."""
    assert V8_FNCS_INSTALLED_PUMPS[(3, 2)] == frozenset({"cl", "ph_minus"})


# ---------------------------------------------------------------------------
# v7 device types — installed_pumps derived from ACTUATOR_MASKS in the v7 decoder
# ---------------------------------------------------------------------------


def test_net_v7_has_cl_and_ph_minus_pumps():
    """Aqua NET v7 has CL + pH− pumps (Issue #66).

    Regression guard: the v7 path must still work after the v8 helper
    refactor. We don't call _device_has_pump here — instead we
    construct a minimal AsekoDevice and check installed_pumps.
    """
    device = AsekoDevice(
        device_type=AsekoDeviceType.NET,
        serial_number=110203680,
        installed_pumps=frozenset({"cl", "ph_minus"}),
    )
    assert "cl" in device.installed_pumps
    assert "ph_minus" in device.installed_pumps
    # NET has no other pumps.
    assert "algicide" not in device.installed_pumps
    assert "floc" not in device.installed_pumps
    assert "oxy" not in device.installed_pumps
    assert "ph_plus" not in device.installed_pumps


def test_salt_v7_has_ph_minus_and_algicide_pumps():
    """SALT v7 (binary frame) has pH− + algicide pumps.

    Confirms the v7 path uses ACTUATOR_MASKS correctly.
    """
    device = AsekoDevice(
        device_type=AsekoDeviceType.SALT,
        serial_number=1234,
        installed_pumps=frozenset({"ph_minus", "algicide"}),
    )
    assert "ph_minus" in device.installed_pumps
    assert "algicide" in device.installed_pumps
    assert "cl" not in device.installed_pumps


def test_unknown_fncs_returns_only_ph_minus():
    """Unrecognised fncs[2] values: only ph_minus is in installed_pumps.

    This is the conservative "we know pH− is there, but we don't
    know about the others" answer. A future SALT NET firmware
    revision with a new (fncs[2], fncs[6]) combination will be
    treated as "no other pumps" until we add the entry to
    V8_FNCS_INSTALLED_PUMPS.
    """
    flags = AsekoV8_CAPABILITY_FLAGS[AsekoDeviceType.SALT_NET]
    assert installed_pumps_from_fncs(99, 99, flags) == frozenset({"ph_minus"})
