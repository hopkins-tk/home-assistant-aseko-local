"""v8 profile: ASIN AQUA Net."""

from __future__ import annotations

from ....models import AsekoDeviceType, AsekoProfileFlag
from ...evidence import assumed, confirmed, derived
from ...features import (
    ChlorineFlowRate,
    ChlorinePumpRunning,
    Configuration,
    DosingDelay,
    FiltrationRelay,
    Ph,
    PhMinusFlowRate,
    PhMinusPumpRunning,
    PhTarget,
    PoolVolume,
    Redox,
    RedoxTarget,
    SerialNumber,
    StartupDelay,
    Timestamp,
    UnitClock,
    WaterFlowToProbes,
    WaterTemperature,
)
from ...frames import Protocol
from ...profile import Profile
from .common import FEATURES

NET = Profile(
    name="v8 NET",
    protocol=Protocol.V8,
    model=AsekoDeviceType.NET,
    features=FEATURES,
    flags=frozenset({AsekoProfileFlag.DELAYS_IN_MINUTES}),
    evidence={
        ChlorinePumpRunning: assumed(
            "outs[9] per the current decoder; net_v8_device_analysis.md lists outs[0] / outs[1] as candidates and no frame shows a pump running"
        ),
        Configuration: derived("a probe is installed when its ains slot is not -500"),
        DosingDelay: confirmed("areqs[18] = 2 min vs the app"),
        StartupDelay: confirmed("areqs[17] = 2 min vs the app"),
        FiltrationRelay: confirmed(
            "outs[2] = 1 while the app showed 'Pump: ON / NONSTOP' (2026-04-13)"
        ),
        ChlorineFlowRate: assumed("not transmitted, 60 ml/min taken for consumption"),
        PhMinusFlowRate: assumed("not transmitted, 60 ml/min taken for consumption"),
        Ph: confirmed(
            "ains[0] / 100 vs the app (6.49 vs 6.56, later reading), serial 110203680"
        ),
        PhMinusPumpRunning: assumed(
            "outs[8] per the current decoder; net_v8_device_analysis.md lists outs[0] / outs[1] as candidates and no frame shows a pump running"
        ),
        PoolVolume: confirmed("areqs[14] = 45 m3 vs the app"),
        Redox: confirmed(
            "ains[6] = 809 mV vs 848 mV in the app (later reading), serial 110203680"
        ),
        PhTarget: confirmed("areqs[0] / 10 = 7.4 vs the app"),
        RedoxTarget: confirmed("areqs[1] * 10 = 740 mV vs the app"),
        SerialNumber: confirmed("header token 2, serial 110203680"),
        Timestamp: confirmed(
            "ins[16] hour, ins[17] minute match the HA log; date taken from HA"
        ),
        UnitClock: confirmed("ins[16] hour, ins[17] minute match the HA log; no date"),
        WaterFlowToProbes: confirmed(
            "ins[8] = 1 while the app showed 'Water flow: YES'"
        ),
        WaterTemperature: confirmed(
            "ins[0] / 10 = 31.4 C (Sep 2025) and 18.0 C (Apr 2026) vs the app"
        ),
    },
)
