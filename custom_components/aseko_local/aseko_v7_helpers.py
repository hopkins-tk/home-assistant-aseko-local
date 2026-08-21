"""v7 (binary 120-byte frame) decoder-specific helpers.

This module contains all knowledge that is specific to the Aseko **v7
binary frame protocol** (120 bytes, used by SALT, OXY, HOME, PROFI, NET).
It is the home of:

- ``AsekoActuatorMasks``: byte[29] bit masks per device type (pumps,
  electrolyser, backwash relay, etc.).
- ``ACTUATOR_MASKS``: the per-device-type mapping.
- ``AsekoThirdPumpSlot``: byte[37] routing constants for SALT's
  shared-port architecture.
- ``AsekoByte37Masks``: all known bitmask constants for byte[37].

The v7 decoder (``aseko_decoder.py``) imports these constants directly.
The v8 decoder (``aseko_decoder_v8.py``) **does not** use any of this
module — v8 has no byte[29] actuator bitmask.

The ``AsekoDevice`` data model in ``aseko_data.py`` is the
**protocol-agnostic target schema** consumed by the entity layer
(``sensor.py``, ``binary_sensor.py``, etc.). It must not import
byte-level knowledge from this module — see ``sensor.py``'s
``_device_has_pump`` helper for the protocol-aware pump-presence check.

See ``aseko_v8_helpers.py`` for the v8-side counterpart.
"""

from dataclasses import dataclass

from .aseko_data import AsekoDeviceType


class AsekoThirdPumpSlot:
    """Semantics of byte[37] differ by device type.

    SALT (shared physical port): routing indicator.
        Bit 7 (0x80) set → algicide configured in the single port.
        Bit 7 (0x80) clear → flocculant configured.
        Confirmed by @hopkins-tk (SALT v7.x frames, 2025) and consistent with
        @jmnemonicj (SALT v5.0, Issue #84) where 0x03 & 0x80 == 0 → flocculant.

    OXY (two independent ports): suspected pump-presence bitmap.
        Bit 0 (0x01) = flocculant pump module connected.  # unconfirmed hypothesis
        Bit 1 (0x02) = algicide pump module connected.    # unconfirmed hypothesis
        Observed 0x03 on Winnetoux's OXY (both pumps present). Requires a frame
        with only one pump connected to confirm.
        TODO: confirm OXY semantics with an asymmetric frame.

    NET / PROFI / HOME: 0xFF (UNSPECIFIED) = no third-pump port, routing not applicable.
    """

    # SALT: bit 7 → algicide in the shared port; clear → flocculant
    SALT_ALGICIDE_ROUTING: int = 0x80

    # OXY: presence bits – which pump modules are physically connected.
    # UNCONFIRMED: based solely on the single observed value 0x03 (both present).
    OXY_FLOC_PRESENT: int = 0x01
    OXY_ALGICIDE_PRESENT: int = 0x02


class AsekoByte37Masks:
    """All known bitmask constants for byte[37].

    Byte [37] is a multi-purpose configuration / status byte whose bits
    have different meanings depending on device type and firmware variant.

    Bit layout (by convention, not all bits apply to every device):

    Bit 0 (0x01): OXY flocculant-pump presence / general flag.
    Bit 1 (0x02): OXY algicide-pump presence.
    Bit 2 (0x04): HOME firmware B → manual-override active;
                  HOME firmware A → unknown / initial-state indicator.
    Bit 3 (0x08): HOME firmware A → heating-control master enable (Issue #135).
    Bit 4 (0x10): HOME firmware B → period-1 enabled.
    Bit 5 (0x20): Second filtration period enabled
                  (see ``FILTRATION_PERIOD2_ENABLED_MASK`` in const.py).
                  Also HOME firmware B → period-2 enabled.
    Bit 6 (0x40): HOME firmware A high-nibble indicator
                  (set: firmware-A encoding; clear: firmware-B encoding).
    Bit 7 (0x80): SALT shared-port routing indicator
                  (see ``AsekoThirdPumpSlot.SALT_ALGICIDE_ROUTING``).
                  HOME firmware A → antifreeze master enable (Issue #136).

    Constants are grouped by device family below.
    """

    # ── Masks applicable across multiple device types ────────────────────

    PERIOD_2_ENABLED: int = 0x20  # second filtration period enabled

    # ── HOME firmware A (high nibble 0x4/0x5, serial 110128063 ff.) ──────

    HOME_FWA_MODE_NONSTOP: int = 0x43  # nonstop 24h (exact value)
    HOME_FWA_MODE_TIMER: int = 0x53  # timer (P1 & P2, exact value)
    # 0x47 / 0x57 are transitional edit states (bit 1 set) → leave as None
    HOME_FWA_TRANSITIONAL_MASK: int = 0x02  # bit 1 → transitional

    # Heating control master enable (Issue #135).
    # Confirmed on serial 110175608 (ASIN AQUA Home REDOX, byte 4 = 0x03):
    #   0x49 → heating ON, 0x41 → heating OFF.
    HOME_FWA_HEATING_ENABLED: int = 0x08

    # Antifreeze master enable (Issue #136).
    # Confirmed on serial 110175608 (ASIN AQUA Home REDOX, byte 4 = 0x03):
    #   0x81 → antifreeze ON, 0x41 → antifreeze OFF.
    HOME_FWA_ANTIFREEZE_ENABLED: int = 0x80

    # ── HOME firmware B (high nibble 0x0/0x1/0x3, serial 110169464) ─────

    HOME_FWB_MANUAL_OVERRIDE: int = 0x04  # manual override active
    HOME_FWB_PERIOD_1_ENABLED: int = 0x10  # period 1 enabled
    HOME_FWB_PERIOD_2_ENABLED: int = 0x20  # period 2 enabled

    # ── SALT exclusive ──────────────────────────────────────────────────

    SALT_ALGICIDE_ROUTING: int = 0x80  # same as AsekoThirdPumpSlot

    # ── OXY exclusive (unconfirmed) ─────────────────────────────────────

    OXY_FLOC_PRESENT: int = 0x01
    OXY_ALGICIDE_PRESENT: int = 0x02


@dataclass(frozen=True)
class AsekoActuatorMasks:
    """Byte 29 bit masks for actuator state detection (pumps + electrolyser), per device type.

    **v7 only.** The v8 frame does not have a ``byte[29]`` actuator bitmask —
    v8 pump running states are exposed via the ``outs:`` section, and the
    v8 device-type capability is derived from the ``fncs:`` section. See
    ``aseko_v8_helpers.py`` for the v8-side counterpart.
    """

    filtration: int = 0x00
    cl: int = 0x00
    ph_minus: int = 0x00
    algicide: int = 0x00
    flocculant: int = 0x00
    oxy: int = 0x00  # unconfirmed – awaiting frame with OXY Pure pump active
    electrolyzer_running: int = 0x00
    electrolyzer_running_right: int = 0x00
    electrolyzer_running_left: int = 0x00
    # On devices with a single shared physical pump port (SALT and similar 2-3-pump
    # units), byte[37] carries a routing indicator: bit 7 set → algicide setpoint;
    # clear → flocculant setpoint (AsekoThirdPumpSlot.SALT_ALGICIDE_ROUTING).
    # Devices with 4+ independent pump ports (OXY, HOME, PROFI) do NOT use this
    # routing — algicide and flocculant have separate physical connections whose
    # setpoint byte positions are not yet confirmed from frames.
    # Set False for those devices so decode() skips the routing logic entirely.
    byte37_routes_pump_type: bool = True


ACTUATOR_MASKS: dict[AsekoDeviceType, AsekoActuatorMasks] = {
    # Masks only for V7
    AsekoDeviceType.OXY: AsekoActuatorMasks(
        filtration=0x08,  # confirmed: all captured frames
        algicide=0x10,  # confirmed: 2026-04-11 Winnetoux log – byte[29] 0x08→0x18 at algicide pump on
        flocculant=0x20,  # confirmed: toggles exactly at 19:33:52 floc event
        oxy=0x40,  # confirmed: 2026-04-11 Winnetoux log – byte[29] 0x08→0x48 at OXY pump on
        ph_minus=0x80,  # confirmed: 2026-04-12 Winnetoux log – byte[29] 0x08→0x88 at pH- pump on
        byte37_routes_pump_type=False,  # OXY byte[37] = pump-presence bitmap, not routing
    ),
    AsekoDeviceType.NET: AsekoActuatorMasks(
        # Aqua NET has no filtration output — confirmed: Issue #66
        cl=0x02,  # confirmed: Issue #66 (Aqua NET)
        ph_minus=0x01,  # confirmed: Issue #66 (Aqua NET)
    ),
    AsekoDeviceType.SALT: AsekoActuatorMasks(
        filtration=0x08,  # confirmed: April 4, 2026 – set in all active phases (PR #87)
        ph_minus=0x80,  # unconfirmed – no frame captured with pH- pump running
        # SALT third-pump slot: one physical pump, configured as algicide OR flocculant.
        # Both chemicals use the same bit: byte[29] bit 5 (0x20) when running.
        # Routing: byte[37] & 0x80 set = algicide; clear → flocculant.
        # Confirmed by @hopkins-tk 2026-04-04: 27 algicide frames (no electrolyser) → 0x28=0x08|0x20 (PR #87).
        algicide=0x20,  # confirmed: 27 frames, PR #87
        flocculant=0x20,  # confirmed: Apr 3 frames, same bit as algicide
        electrolyzer_running=0x10,  # confirmed: 25 frames → 0x18=0x08|0x10 (PR #87)
        electrolyzer_running_right=0x10,  # confirmed: same dataset
        electrolyzer_running_left=0x50,  # tentative: Apr 2 single frame 0x58=0x08|0x10|0x40
    ),
    AsekoDeviceType.HOME: AsekoActuatorMasks(
        filtration=0x08,  # uncertain
        # HOME "chlorine" pump port can be configured as Chlorine OR OXY Pure
        # (same physical port, same bit in byte[29] – routing by an unknown byte).
        # TODO: confirm which byte carries the cl/oxy routing and add oxy mask once known.
        #       Waiting for a frame with OXY pump running from a HOME device.
        cl=0x40,  # uncertain – assumed same bit for both cl and oxy variants
        ph_minus=0x80,  # uncertain
        algicide=0x20,  # uncertain
        flocculant=0x20,  # uncertain
        byte37_routes_pump_type=False,  # HOME has independent pump ports (cl/oxy, ph-, alg, floc)
    ),
    AsekoDeviceType.PROFI: AsekoActuatorMasks(
        filtration=0x08,  # uncertain
        cl=0x40,  # uncertain
        ph_minus=0x80,  # uncertain
        flocculant=0x20,  # uncertain
        byte37_routes_pump_type=False,  # PROFI has 5 independent pump ports (cl, ph-, ph+, alg, floc)
    ),
}
