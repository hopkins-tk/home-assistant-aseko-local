"""v7 profile: ASIN AQUA Oxygen."""

from __future__ import annotations

from ....models import AsekoDeviceType
from ...evidence import assumed, confirmed, not_located, observed
from ...features import (
    AirTemperature,
    AlarmMaxDisinfectionDose,
    AlarmNoFlowToProbes,
    AlarmPhDosingIneffective,
    AlarmRapidPhChange,
    AlgaecideDoseTarget,
    AlgaecideFlowRate,
    AlgaecidePumpRunning,
    BackwashDuration,
    BackwashInterval,
    BackwashRunning,
    BackwashStartTime,
    Configuration,
    DosingDelay,
    FiltrationPeriod1End,
    FiltrationPeriod1Start,
    FiltrationPeriod2End,
    FiltrationPeriod2Start,
    FiltrationRelay,
    FiltrationSchedule,
    FlocculantDoseTarget,
    FlocculantFlowRate,
    FlocculantPumpRunning,
    FlowDetectionEnabled,
    FreezeProtectionEnabled,
    HeatingControlEnabled,
    HeatingRunning,
    MaxPhDoses,
    MaxRefillTime,
    OxygenDoseTarget,
    OxygenFlowRate,
    OxygenPumpRunning,
    Ph,
    PhMinusConcentration,
    PhMinusFlowRate,
    PhMinusPumpRunning,
    PhTarget,
    PoolVolume,
    Refilling,
    SerialNumber,
    ServiceMenuOpen,
    StartupDelay,
    Timestamp,
    UnitClock,
    VariableSpeedPumpEnabled,
    WaterFlowToProbes,
    WaterLevel,
    WaterLevelHighAlarm,
    WaterLevelLowAlarm,
    WaterLevelRefillStart,
    WaterLevelRefillStop,
    WaterLevelSensorEnabled,
    WaterTemperature,
    WaterTemperatureTarget,
)
from ...frames import Protocol
from ...profile import Profile
from .common import (
    ALARMS,
    BACKWASH,
    CLOCK,
    FILTRATION,
    IDENTITY,
    MEASUREMENTS,
    SETTINGS,
    UNIT_STATE,
    WATER_LEVEL,
)

OXY = Profile(
    name="v7 OXY",
    protocol=Protocol.V7,
    model=AsekoDeviceType.OXY,
    features=(
        *IDENTITY,
        *CLOCK,
        *MEASUREMENTS,
        AirTemperature,
        Ph,
        *SETTINGS,
        OxygenDoseTarget,
        FlocculantDoseTarget,
        AlgaecideDoseTarget,
        OxygenFlowRate,
        FlocculantFlowRate,
        AlgaecideFlowRate,
        *FILTRATION,
        ServiceMenuOpen,
        PhMinusPumpRunning,
        AlgaecidePumpRunning,
        FlocculantPumpRunning,
        OxygenPumpRunning,
        *WATER_LEVEL,
        MaxRefillTime,
        MaxPhDoses,
        *UNIT_STATE,
        HeatingControlEnabled,
        FreezeProtectionEnabled,
        WaterLevelSensorEnabled,
        FlowDetectionEnabled,
        *BACKWASH,
        *ALARMS,
    ),
    overrides={
        # byte[103] is the algicide flow rate here, not the refill threshold
        WaterLevelRefillStart: "decode_v7_not_located",
        Configuration: "decode_v7_ph_and_oxy",
        AlgaecidePumpRunning: "decode_v7_oxy",
        HeatingControlEnabled: "decode_v7_not_located",
        FreezeProtectionEnabled: "decode_v7_not_located",
    },
    evidence={
        FlowDetectionEnabled: assumed(
            "byte[37] 0x02 as on SALT; set in the OXY frames (0x03)"
        ),
        WaterLevelSensorEnabled: assumed(
            "byte[37] 0x40 as on SALT; clear in the OXY frames (0x03), which fits byte[27] = 0xFE (no level sensor)"
        ),
        AirTemperature: assumed(
            "bytes 23-24 = 0xFE70 (no air probe, the SALT marker) in every captured OXY frame, so its entity has stayed disabled; the Aseko Live app shows air temperature on Oxygen units"
        ),
        AlarmNoFlowToProbes: assumed(
            "byte[13] was 0x00 in every OXY frame; confirmed on NET and HOME only"
        ),
        AlarmMaxDisinfectionDose: assumed(
            "bytes 12-13 were 0x00 in every OXY frame; HOME encoding assumed"
        ),
        AlarmPhDosingIneffective: assumed(
            "bytes 12-13 were 0x00 in every OXY frame; HOME encoding assumed"
        ),
        AlarmRapidPhChange: assumed(
            "byte[13] 0x08 from error_codes.md; never set in the OXY frames"
        ),
        AlgaecidePumpRunning: confirmed("byte[29] 0x10, 2026-04-11 Winnetoux log"),
        FreezeProtectionEnabled: not_located(
            "the ASIN AQUA Oxygen manual describes freeze protection; no OXY frame has been compared with it"
        ),
        BackwashRunning: assumed("byte[29] 0x01, confirmed on SALT"),
        BackwashDuration: observed(
            "byte[71] * 10 = 100 s on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        BackwashInterval: observed(
            "byte[68] = 0 (disabled) on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        BackwashStartTime: observed(
            "bytes 69-70 = 12:30 on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        Configuration: confirmed(
            "fixed pH + OXY Pure, the SANOSIL probe sits in the CLF slot"
        ),
        DosingDelay: observed(
            "bytes 106-107 = 120 s on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        StartupDelay: observed(
            "bytes 74-75 = 240 s on the Winnetoux OXY; not compared with the app"
        ),
        FiltrationRelay: confirmed("byte[29] 0x08 in every captured frame"),
        FiltrationSchedule: observed(
            "byte[37] = 0x03 reads nonstop while the Winnetoux OXY ran filtration 24 h; no schedule transition captured"
        ),
        FlocculantPumpRunning: confirmed(
            "byte[29] 0x20 toggles at the 19:33:52 floc event"
        ),
        AlgaecideFlowRate: confirmed("byte[103] = 60 ml/min (2026-04-11)"),
        FlocculantFlowRate: confirmed("byte[101]"),
        OxygenFlowRate: confirmed("byte[99]"),
        PhMinusFlowRate: confirmed(
            "byte[95] = 60 ml/min (Winnetoux, oxy_device_analysis.md)"
        ),
        HeatingRunning: assumed("byte[29] 0x04 per JS-DE-Tech relay_byte bit 2"),
        HeatingControlEnabled: not_located(
            "the ASIN AQUA Oxygen manual describes heating control; no OXY frame has been compared with it"
        ),
        MaxRefillTime: assumed(
            "bytes 76-77 = 3600 s on the Winnetoux OXY, plausible (60 min); verified on SALT only"
        ),
        MaxPhDoses: observed(
            "byte[115] = 30 on the Winnetoux OXY; the position is confirmed on SALT, the OXY setting was never compared"
        ),
        OxygenPumpRunning: confirmed("byte[29] 0x40, 2026-04-11 Winnetoux log"),
        Ph: observed(
            "bytes 14-15 = 7.17 on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        PhMinusConcentration: assumed("byte[112], confirmed on HOME"),
        PhMinusPumpRunning: confirmed("byte[29] 0x80, 2026-04-12 Winnetoux log"),
        PoolVolume: observed(
            "bytes 92-93 = 41 m3 on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        AlgaecideDoseTarget: confirmed("byte[72] = 15 (2026-04-11)"),
        FlocculantDoseTarget: confirmed("byte[54] = 10 (2026-04-11)"),
        OxygenDoseTarget: confirmed("byte[53] (Winnetoux, 2026-04-11)"),
        PhTarget: observed(
            "byte[52] / 10 = 7.2 on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        WaterTemperatureTarget: observed(
            "byte[55] = 25 C on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        SerialNumber: confirmed("bytes 0-3, repeated in every segment header"),
        ServiceMenuOpen: observed(
            "byte[37] bit 0x04 clear in every OXY frame; the menu never captured open"
        ),
        FiltrationPeriod1Start: observed(
            "bytes 56-57 = 08:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        FiltrationPeriod2Start: observed(
            "bytes 60-61 = 18:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        FiltrationPeriod1End: observed(
            "bytes 58-59 = 16:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        FiltrationPeriod2End: observed(
            "bytes 62-63 = 22:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        Timestamp: confirmed("bytes 6-11"),
        UnitClock: confirmed(
            "bytes 6-11, the bytes of timestamp without its fallback to Home Assistant's clock"
        ),
        VariableSpeedPumpEnabled: assumed("byte[22] 0x08, confirmed on HOME"),
        Refilling: assumed("byte[29] 0x02, confirmed on HOME and SALT"),
        WaterFlowToProbes: observed(
            "byte[28] = 0xAA on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
        WaterLevel: assumed("byte[27], confirmed on HOME"),
        WaterLevelLowAlarm: assumed(
            "byte[102] as on SALT; the captured OXY has no level sensor"
        ),
        WaterLevelRefillStop: assumed(
            "byte[104] as on SALT; the captured OXY has no level sensor"
        ),
        WaterLevelHighAlarm: assumed(
            "byte[105] as on SALT; the captured OXY has no level sensor"
        ),
        WaterLevelRefillStart: not_located(
            "byte[103] carries the algicide flow rate on OXY (confirmed, 60 ml/min), so the refill start threshold is elsewhere on an OXY with a level sensor; the captured OXY has none"
        ),
        WaterTemperature: observed(
            "bytes 25-26 = 9.5 C on the Winnetoux OXY (serial 110157165); not compared with the app"
        ),
    },
)
