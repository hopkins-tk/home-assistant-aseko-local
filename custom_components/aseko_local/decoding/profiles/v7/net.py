"""v7 profile: ASIN AQUA Net: measurement and dosing only, no filter, no valve."""

from __future__ import annotations

from ....models import AsekoDeviceType
from ...evidence import assumed, confirmed, observed
from ...features import (
    AlarmMaxDisinfectionDose,
    AlarmNoFlowToProbes,
    AlarmPhDosingIneffective,
    AlarmRapidPhChange,
    ChlorineDoseTarget,
    ChlorineFlowRate,
    ChlorinePumpRunning,
    Configuration,
    DosingDelay,
    FreeChlorine,
    FreeChlorineMv,
    FreeChlorineTarget,
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
    WaterFlowToProbes,
    WaterTemperature,
)
from ...frames import Protocol
from ...profile import Profile
from .common import (
    ALARMS,
    CHLORINE_PROBES,
    DISINFECTION_SETPOINTS,
    IDENTITY,
    MEASUREMENTS,
)

NET = Profile(
    name="v7 NET",
    protocol=Protocol.V7,
    model=AsekoDeviceType.NET,
    features=(
        *IDENTITY,
        *MEASUREMENTS,
        *CHLORINE_PROBES,
        PhTarget,
        PoolVolume,
        StartupDelay,
        DosingDelay,
        PhMinusFlowRate,
        *DISINFECTION_SETPOINTS,
        ChlorineFlowRate,
        ChlorinePumpRunning,
        PhMinusPumpRunning,
        *ALARMS,
    ),
    overrides={
        ChlorinePumpRunning: "decode_v7_net",
        PhMinusPumpRunning: "decode_v7_net",
    },
    evidence={
        AlarmNoFlowToProbes: confirmed("byte[13] 0x04 (DomSchCoding, NET frame)"),
        AlarmMaxDisinfectionDose: assumed(
            "byte[12] is 0x00 on NET; HOME encodings assumed"
        ),
        AlarmPhDosingIneffective: assumed(
            "byte[12] is 0x00 on NET; HOME encodings assumed"
        ),
        AlarmRapidPhChange: assumed(
            "byte[13] 0x08 from error_codes.md; never set on NET"
        ),
        FreeChlorine: confirmed("bytes 16-17 / 100"),
        FreeChlorineMv: confirmed("bytes 20-21"),
        Redox: assumed(
            "protocol default, bytes 18-19 (16-17 when 18-19 are 0xFFFF); no REDOX NET frame captured"
        ),
        ChlorinePumpRunning: confirmed("byte[29] 0x02 (Issue #66)"),
        Configuration: confirmed(
            "byte[4] missing-probe bits (0x09 CLF, 0x0A REDOX, 0x0B DOSE)"
        ),
        DosingDelay: observed(
            "bytes 106-107 on the Issue #66 NET; not compared with the app"
        ),
        StartupDelay: assumed(
            "bytes 74-75 = 0xFFFF (not filled in) on the Issue #66 NET frame and on the ChemDoserProxy NET frame"
        ),
        ChlorineFlowRate: confirmed("byte[99] (net_device_analysis.md)"),
        PhMinusFlowRate: confirmed("byte[95] (Issue #110, #115)"),
        Ph: confirmed("bytes 14-15 / 100 (Issue #66 frames)"),
        PhMinusPumpRunning: confirmed("byte[29] 0x01 (Issue #66)"),
        PoolVolume: observed(
            "bytes 92-93 on the Issue #66 NET; not compared with the app"
        ),
        ChlorineDoseTarget: observed(
            "byte[53] = 5 ml/m3/h in DOSE mode (2026-04-07 capture); not compared with the app"
        ),
        FreeChlorineTarget: observed(
            "byte[53] / 10 on the Issue #66 NET; not compared with the app"
        ),
        PhTarget: confirmed("byte[52] / 10 (Issue #66 frames)"),
        RedoxTarget: assumed("byte[53] * 10 on a REDOX NET; no such frame captured"),
        SerialNumber: confirmed("bytes 0-3, repeated in every segment header"),
        Timestamp: assumed(
            "bytes 6-11 are 0xFF on every NET frame, Home Assistant's clock is used instead"
        ),
        WaterFlowToProbes: confirmed("byte[28] == 0xAA (Issue #66 frames)"),
        WaterTemperature: confirmed("bytes 25-26 / 10 (Issue #66 frames)"),
    },
)
