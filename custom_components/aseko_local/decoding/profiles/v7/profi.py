"""v7 profile: ASIN AQUA Profi: unit type 0x10, unconfirmed."""

from __future__ import annotations

from ....models import AsekoDeviceType
from ...evidence import assumed, derived
from ...features import (
    ChlorineDoseTarget,
    ChlorineFlowRate,
    ChlorinePumpRunning,
    Configuration,
    FlocculantDoseTarget,
    FlocculantFlowRate,
    FlocculantPumpRunning,
    FreeChlorineTarget,
    HeatingRunning,
    MaxPhDoses,
    MaxRefillTime,
    PhMinusConcentration,
    PhMinusPumpRunning,
    SerialNumber,
    ServiceMenuOpen,
    UnitClock,
)
from ...frames import Protocol
from ...profile import Profile
from .common import (
    ALARMS,
    BACKWASH,
    CHLORINE_PROBES,
    CLOCK,
    FILTRATION,
    IDENTITY,
    MEASUREMENTS,
    SETTINGS,
    WATER_LEVEL,
)

_PROFI_FEATURES = (
    *IDENTITY,
    *CLOCK,
    *MEASUREMENTS,
    *CHLORINE_PROBES,
    *SETTINGS,
    FreeChlorineTarget,
    ChlorineDoseTarget,
    FlocculantDoseTarget,
    ChlorineFlowRate,
    FlocculantFlowRate,
    *FILTRATION,
    ServiceMenuOpen,
    ChlorinePumpRunning,
    PhMinusPumpRunning,
    FlocculantPumpRunning,
    *WATER_LEVEL,
    MaxRefillTime,
    HeatingRunning,
    PhMinusConcentration,
    MaxPhDoses,
    *BACKWASH,
    *ALARMS,
)

# No PROFI frame has ever been captured, so this is the evidence for every
# entry; the ones below say more where the manual or the protocol does.
_NOT_CAPTURED = (
    "no real PROFI frame has been captured; layout inferred from the manual and "
    "the other models (profi_device_analysis.md)"
)

PROFI = Profile(
    name="v7 PROFI",
    protocol=Protocol.V7,
    model=AsekoDeviceType.PROFI,
    features=_PROFI_FEATURES,
    overrides={
        Configuration: "decode_v7_without_dose",
        FlocculantDoseTarget: "decode_v7_routed_by_byte37",
        FlocculantFlowRate: "decode_v7_routed_by_byte37",
    },
    evidence={
        **dict.fromkeys(_PROFI_FEATURES, assumed(_NOT_CAPTURED)),
        MaxRefillTime: assumed(
            f"{_NOT_CAPTURED}; the 2021 PROFI manual lists a max. filling time"
        ),
        FlocculantDoseTarget: assumed(
            f"{_NOT_CAPTURED}; the PROFI setpoints screen has a flocculant dose "
            "(ml/24 h m3) on its shared flocculant / algicide output"
        ),
        SerialNumber: derived(
            "bytes 0-3, repeated in every segment header -- the v7 frame layout every unit shares; no PROFI frame has been captured"
        ),
        UnitClock: assumed(
            "bytes 6-11 as on the other v7 models; no real PROFI frame has been captured"
        ),
    },
)
