"""v7 profile for a unit type nobody has mapped.

Read everything that has a generic v7
reading -- every probe, the shared-port layout most models use, the
default actuator bits -- so that the diagnostics of such a unit show as
much as the frame can be made to say.  Nothing here is verified for the
unit at hand: the coordinator keeps it out of the entity platforms and
reports it separately in diagnostics as unrecognised.

Left out are readings whose bytes mean something else on other models and
so cannot be called generic: SALT's electrolyser and salinity (bytes 20-21
are free_chlorine_mv elsewhere), the OXY dose and pump (byte[53] and bit 0x40
are chlorine elsewhere) and HOME's heating / antifreeze enables (byte[37]
0x80 is the algicide routing elsewhere).  Air temperature is left out too:
NET carries unrelated data in bytes 23-24.
"""

from __future__ import annotations

from ...evidence import assumed
from ...features import (
    AlgaecideDoseTarget,
    AlgaecideFlowRate,
    AlgaecidePumpRunning,
    ChlorineFlowRate,
    ChlorinePumpRunning,
    Configuration,
    FlocculantDoseTarget,
    FlocculantFlowRate,
    FlocculantPumpRunning,
    MaxPhDoses,
    MaxRefillTime,
    PhMinusPumpRunning,
    ServiceMenuOpen,
)
from ...frames import Protocol
from ...profile import Profile
from .common import (
    ALARMS,
    BACKWASH,
    CHLORINE_PROBES,
    DISINFECTION_SETPOINTS,
    FILTRATION,
    IDENTITY,
    MEASUREMENTS,
    SETTINGS,
    SHARED_THIRD_PUMP,
    UNIT_STATE,
    WATER_LEVEL,
)

_UNKNOWN_FEATURES = (
    *IDENTITY,
    *MEASUREMENTS,
    *CHLORINE_PROBES,
    *SETTINGS,
    *DISINFECTION_SETPOINTS,
    AlgaecideDoseTarget,
    FlocculantDoseTarget,
    ChlorineFlowRate,
    AlgaecideFlowRate,
    FlocculantFlowRate,
    *FILTRATION,
    ServiceMenuOpen,
    ChlorinePumpRunning,
    PhMinusPumpRunning,
    AlgaecidePumpRunning,
    FlocculantPumpRunning,
    *WATER_LEVEL,
    MaxRefillTime,
    MaxPhDoses,
    *UNIT_STATE,
    *BACKWASH,
    *ALARMS,
)

UNKNOWN = Profile(
    name="v7 unknown unit type",
    protocol=Protocol.V7,
    model=None,
    features=_UNKNOWN_FEATURES,
    overrides={
        Configuration: "decode_v7_all_probes",
        **SHARED_THIRD_PUMP,
    },
    # nothing is known about an unmapped unit: one reason for every entry
    evidence=dict.fromkeys(
        _UNKNOWN_FEATURES,
        assumed("unmapped unit type, read with the generic v7 reading"),
    ),
)
