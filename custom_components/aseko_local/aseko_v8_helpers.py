"""v8 (text frame on TCP port 51050) decoder-specific helpers.

This module contains all knowledge that is specific to the Aseko **v8
text frame protocol** (used by SALT NET, NET, and future revisions).
It is the home of:

- `AsekoV8CapabilityFlags`: per-device-type capability map for v8.
  The v8 frame has no `byte[29]` actuator bitmask; instead, device
  capabilities (e.g. "has CL pump", "has electrolyser cell") are
  derived from the `fncs:` section of the frame.

The v8 decoder (`aseko_decoder_v8.py`) imports these constants directly.
The v7 decoder (`aseko_decoder.py`) **does not** use any of this
module — v7 has no `fncs:` section.

The `AsekoDevice` data model in `aseko_data.py` is the
**protocol-agnostic target schema** consumed by the entity layer
(`sensor.py`, `binary_sensor.py`, etc.). It must not import
byte-level knowledge from this module — see `sensor.py`'s
`_device_has_pump` helper for the protocol-aware pump-presence check.

See `aseko_v7_helpers.py` for the v7-side counterpart.
"""

from dataclasses import dataclass
from typing import FrozenSet

from .aseko_data import AsekoDeviceType


# All v8 device types. Used by the entity layer to dispatch to the v8
# helpers instead of the v7 ACTUATOR_MASKS. Extend this set when a new
# v8-only device type is added.
V8_DEVICE_TYPES: FrozenSet[AsekoDeviceType] = frozenset(
    {
        AsekoDeviceType.SALT_NET,
    }
)


@dataclass(frozen=True)
class AsekoV8CapabilityFlags:
    """Per-device-type capability map for v8 frames.

    The v8 frame has no `byte[29]` actuator bitmask. Instead, the
    `fncs:` ("functions") section encodes which dosing pumps the
    device physically has. **The `fncs[2]` value is the source of
    truth for pump presence** — not the `outs[]` indices. This is
    critical: `outs[i] = 0` is ambiguous (pump off OR pump absent);
    only `fncs[2]` tells us which one it is.

    See `salt_net_v8_device_analysis.md` §11.5 for the full
    `fncs[2]` capability-gate interpretation.

    **This is a different shape from `AsekoActuatorMasks` (v7):**
    the v7 mask is a bitmask in `byte[29]`, while the v8 capability
    is keyed on `fncs[2]` (a small integer code). The two schemas
    do not share any field for the same physical pump, and the v7
    ACTUATOR_MASKS entry for SALT_NET is correctly all-zero — v8
    capability lives here.
    """

    # The `fncs[2]` value the device sends on the wire. Used by
    # `installed_pumps_from_fncs()` to decide which pumps are
    # physically present. None means "the v8 decoder does not yet
    # have a confirmed mapping for this device type" — in that
    # case, only pumps with explicit outs_<pump> indices are
    # considered present.
    fncs_code: int | None = None

    # The `outs[]` index for each pump's running bit. None means
    # "this pump type is not present on this device family" and the
    # entity layer should suppress the corresponding sensor entirely.
    # When the field is set, the decoder reads the bool(...) of the
    # byte at this index; see aseko_decoder_v8.py.
    #
    # Naming convention: matches `AsekoDevice.<pump>_pump_running`
    # attribute names (cl, ph_minus, ph_plus, algicide, floc, oxy)
    # so the entity layer can map pump_key → field name without
    # device-type-specific dispatch.
    outs_cl: int | None = None
    outs_ph_minus: int | None = None
    outs_ph_plus: int | None = None
    outs_algicide: int | None = None
    outs_floc: int | None = None
    outs_oxy: int | None = None

    # Note: `filtration_pump_running` is always derived from outs[2]
    # on v8 (the byte is always present, the semantics — 1=ON on NET,
    # 2=ON on SALT NET — differ but bool(...) handles both). The
    # filtration pump is not gated on capability because every v8
    # device that has a filtration schedule reports it.


# v8 capability flags. SALT_NET is the only v8 device type with a
# complete capability map today (mirovra's ASIN AQUA Salt NET, see
# Issue #131). NET v8 also uses v8 frames but its capability map is
# identical to v7 NET (CL pump + pH− pump) — see aseko_decoder_v8.py
# for the NET branch. We keep this map explicit so that a future
# SALT_NET firmware revision that adds a new pump slot has one
# obvious place to add it.
#
# `fncs_code` MUST match the wire value the device transmits. The
# two confirmed values today are:
#   fncs[2] = 1   → SALT family (SALT NET, salt-cell electrolysis,
#                   no CL pump; algicide on dedicated port)
#   fncs[2] = 3   → NET family (NET v8, has CL pump + pH− pump)
# Any other fncs[2] value is treated as "unknown" — no pumps are
# claimed present, the entity layer stays quiet.
AsekoV8_CAPABILITY_FLAGS: dict[AsekoDeviceType, AsekoV8CapabilityFlags] = {
    # ASIN AQUA Salt NET v8: dedicated pump ports, no CL pump.
    #   outs[8]  = pH− pump running        (confirmed: mirovra hex dumps)
    #   outs[11] = algicide pump running   (confirmed: mirovra Jul 16 frames)
    # See salt_net_v8_device_analysis.md §6 and §11.
    AsekoDeviceType.SALT_NET: AsekoV8CapabilityFlags(
        fncs_code=1,
        outs_ph_minus=8,  # confirmed against mirovra's hex dumps
        outs_algicide=11,  # confirmed: outs[11]=1 when algicide ON (mirovra Jul 16)
        outs_floc=11,  # same physical pump port — the motor doesn't know which chemical
        # outs_cl / outs_ph_plus / outs_oxy all default to
        # None — SALT NET does not have these pumps.
    ),
    # ASIN AQUA NET v8: same pumps as v7 NET (CL + pH−). The v8
    # decoder reads outs[8] (pH−) and outs[9] (CL) with the same
    # semantics as v7.
    AsekoDeviceType.NET: AsekoV8CapabilityFlags(
        fncs_code=3,
        outs_cl=9,
        outs_ph_minus=8,
        # outs_ph_plus / outs_algicide / outs_floc / outs_oxy all default
        # to None — NET v8 does not have these pumps.
    ),
    # SALT, HOME, OXY, PROFI are v7-only device types today. They
    # do not use v8 frames, so their v8 capability is "unknown /
    # not applicable". If a v8 firmware revision is ever released
    # for one of these, add the entry here.
}


# Per-(fncs[2], fncs[6]) pump-presence map. This is the authoritative
# table for "which pumps does a device with these fncs values have".
# The outs_<pump> indices in AsekoV8_CAPABILITY_FLAGS above are
# then used as "where do I read the on/off bit" — but the *presence*
# decision comes from here.
#
# **Why (fncs[2], fncs[6]) and not just fncs[2]?**
# `fncs[2]` distinguishes the device *family* (SALT vs. NET). Within
# a family, the pump configuration can differ — e.g. SALT NET with
# algicide vs. SALT NET with flocculant. `fncs[6]` encodes that
# pump-configuration choice. Confirmed against:
#   - SALT NET mirovra (fncs[2]=1, fncs[6]=10) → pH− + algicide
#   - NET v8 (fncs[2]=3, fncs[6]=2)              → CL + pH−
# See salt_net_v8_device_analysis.md §11.5 for context.
#
# Adding a new (fncs[2], fncs[6]) combination:
#   1. Add an entry here with the pump list.
#   2. Add the matching device type to AsekoV8_CAPABILITY_FLAGS
#      below with the same fncs_code and the matching outs_<pump>
#      indices.
#   3. Add a doc reference in salt_net_v8_device_analysis.md §11.5.
V8_FNCS_INSTALLED_PUMPS: dict[tuple[int, int], frozenset[str]] = {
    # **pH− is universally present on every Aseko device** (per Aseko
    # SALT NET documentation, Issue #131): "The first pump is always
    # pH−, fixed." It is not a fncs-gated pump — it is *always* there.
    # We therefore add `ph_minus` to every fncs-keyed set below.
    #
    # (fncs[2]=1, fncs[6]=10) → SALT family, algicide configured:
    # pH− on the fixed port + algicide on the switchable port
    # (mirovra's unit, July 2026, serial 110215844).
    (1, 10): frozenset({"ph_minus", "algicide"}),
    # (fncs[2]=1, fncs[6]=18) → SALT family, flocculant configured:
    # same physical pump 2 port, user switched chemical in the app
    # to flocculant (10 ml/h). Pump type changes the setpoint field:
    #   fncs[6]=10 → areqs[4] = algicide dose (ml/m³/day)
    #   fncs[6]=18 → areqs[3] = flocculant dose (ml/h)
    # Confirmed by mirovra Jul 19 2026, Issue #131 comment 5016380761.
    (1, 18): frozenset({"ph_minus", "floc"}),
    # (fncs[2]=3, fncs[6]=2) → NET family: CL + pH− (NET v8,
    # confirmed on serial 110203680 and 110999999).
    (3, 2): frozenset({"cl", "ph_minus"}),
}


# v8 firmware does NOT transmit per-pump flow-rate bytes
# (v7 byte[95] / byte[99] / byte[101] have no v8 equivalent). This is
# a deliberate firmware-side simplification: Aseko appears to use the
# same physical pump model across the v8 product line, and the dosing
# rate in ml/min is therefore constant and omitted from the wire
# record. The consumption tracker (consumption_tracker.py) multiplies
# `flowrate_X * duration` to convert pump-on time to mL dosed — without
# a flow-rate, the tracker has nothing to multiply. We therefore
# hardcode the same default the device firmware assumes internally.
# Issue #131 working notes: docs/temp/Issue-131-analyze.md.
V8_DEFAULT_PUMP_FLOWRATE_ML_MIN: int = 60


def installed_pumps_from_fncs(
    fncs2: int | None,
    fncs6: int | None,
    flags: AsekoV8CapabilityFlags | None,
) -> frozenset[str]:
    """Return the frozenset of pump_key strings the v8 device has,
    derived from the wire fncs values.

    **Two-tier source of truth:**
      1. **`ph_minus` is universally present on every Aseko
         device.** Per the Aseko SALT NET documentation (Issue
         #131): "The first pump is always pH−, fixed." The v8
         firmware does not gate it on `fncs[2]` because every device
         that uses v8 frames is known to have it. We always include
         `ph_minus` in the returned set, even for unrecognised
         `fncs[2]` codes.
      2. **All other pumps (CL, algicide, floc, oxy, ph_plus)** are
         gated on `fncs[2]` (and `fncs[6]`). `fncs[2]` distinguishes
         the device *family* (SALT vs. NET). Within a family, the
         pump configuration can differ — e.g. SALT NET with
         algicide vs. SALT NET with flocculant. `fncs[6]` encodes
         that pump-configuration choice.

    **The `flags` argument is used for two purposes:**
      - To confirm the `fncs[2]` value matches the device's expected
        `fncs_code` (sanity check; mismatches fall back to "unknown"
        for the fncs-gated pumps, but `ph_minus` is still claimed).
      - To filter the fncs-derived pump set against the `outs_<pump>`
        indices in the capability map: if `fncs[2]` claims a pump
        but the capability map has no `outs_<pump>` index for it,
        the pump is treated as absent (defensive — handles a
        partially-populated capability map).

    Returns:
      - `frozenset({"ph_minus"})` when fncs[2] is None or unrecognised
        (we know pH− is there, but nothing else).
      - `frozenset({"ph_minus", <other pumps>})` when fncs[2] is
        recognised.
      - `frozenset()` only in pathological cases (e.g. flags=None
        AND no fncs section).
    """
    # Tier 1: ph_minus is universal on v8 devices. Add it
    # unconditionally, then layer the fncs-derived pumps on top.
    pumps: set[str] = {"ph_minus"}

    if fncs2 is None or flags is None:
        return frozenset(pumps)
    if flags.fncs_code != fncs2:
        return frozenset(pumps)

    # Tier 2: fncs-keyed pumps. fncs6 may be None on a frame
    # without fncs[6] — treat it as "not configured".
    lookup_key = (fncs2, fncs6) if fncs6 is not None else None
    if lookup_key is not None:
        pumps.update(V8_FNCS_INSTALLED_PUMPS.get(lookup_key, frozenset()))

    # Defensive filter: if a pump is in the fncs-map but the capability
    # map has no outs_<pump> index for it, drop it. This handles
    # partially-populated capability maps.
    pump_to_field = {
        "cl": "outs_cl",
        "ph_plus": "outs_ph_plus",
        "algicide": "outs_algicide",
        "floc": "outs_floc",
        "oxy": "outs_oxy",
        # ph_minus intentionally not in the filter — it is always
        # present (tier 1) and its outs[8] index is always set in
        # any capability map that includes pH−.
    }
    filtered: set[str] = {p for p in pumps if p == "ph_minus"}
    for pump in pumps:
        if pump == "ph_minus":
            continue
        field_name = pump_to_field.get(pump)
        if field_name is None:
            continue
        if getattr(flags, field_name, None) is not None:
            filtered.add(pump)
    return frozenset(filtered)


def installed_pumps_from_flags(flags: AsekoV8CapabilityFlags) -> frozenset[str]:
    """Return the frozenset of pump_key strings this v8 device has.

    Mirrors the v7-decoder `_fill_installed_pumps` helper: the
    returned set contains the same pump_key strings as
    `AsekoDevice.<pump>_pump_running` attribute names, so the
    entity layer can iterate over `INSTALLED_PUMPS` and check
    `pump_key in device.installed_pumps` regardless of protocol.

    A pump is "installed" iff the v8 capability map declares an
    `outs_<pump>` index. None means "structurally absent" → not in
    the returned set.
    """
    pumps: set[str] = set()
    if flags.outs_cl is not None:
        pumps.add("cl")
    if flags.outs_ph_minus is not None:
        pumps.add("ph_minus")
    if flags.outs_ph_plus is not None:
        pumps.add("ph_plus")
    if flags.outs_algicide is not None:
        pumps.add("algicide")
    if flags.outs_floc is not None:
        pumps.add("floc")
    if flags.outs_oxy is not None:
        pumps.add("oxy")
    return frozenset(pumps)
