"""v7 profile: ASIN AQUA Salt."""

from __future__ import annotations

from ....models import AsekoDeviceType, AsekoProfileFlag
from ...evidence import assumed, confirmed, confirmed_on
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
    BackwashScheduleEnabled,
    BackwashStartTime,
    ChlorineDoseTarget,
    ChlorineProductionMeasured,
    Configuration,
    DosingDelay,
    ElectrodePolarity,
    ElectrolysisRunning,
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
    FreeChlorine,
    FreeChlorineTarget,
    FreezeProtectionEnabled,
    HeatingCondition,
    HeatingConditionMet,
    HeatingControlEnabled,
    HeatingLinkedToFiltration,
    HeatingRunning,
    MaxPhDoses,
    MaxRefillTime,
    Ph,
    PhMinusConcentration,
    PhMinusFlowRate,
    PhMinusPumpRunning,
    PhTarget,
    PoolVolume,
    Redox,
    RedoxTarget,
    Refilling,
    Salinity,
    SerialNumber,
    ServiceMenuOpen,
    StartupDelay,
    Timestamp,
    UnitClock,
    VariableSpeedPumpEnabled,
    VariableSpeedPumpType,
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
    DISINFECTION_SETPOINTS,
    FILTRATION,
    IDENTITY,
    MEASUREMENTS,
    SETTINGS,
    SHARED_THIRD_PUMP,
    UNIT_STATE,
    WATER_LEVEL,
)

SALT = Profile(
    name="v7 SALT",
    protocol=Protocol.V7,
    model=AsekoDeviceType.SALT,
    features=(
        *IDENTITY,
        *CLOCK,
        *MEASUREMENTS,
        AirTemperature,
        # not CHLORINE_PROBES: bytes 20-21, the free chlorine mV on NET and
        # HOME, carry salinity and chlorine production here
        Ph,
        Redox,
        FreeChlorine,
        Salinity,
        ChlorineProductionMeasured,
        ElectrolysisRunning,
        ElectrodePolarity,
        *SETTINGS,
        *DISINFECTION_SETPOINTS,
        AlgaecideDoseTarget,
        FlocculantDoseTarget,
        AlgaecideFlowRate,
        FlocculantFlowRate,
        *FILTRATION,
        ServiceMenuOpen,
        PhMinusPumpRunning,
        AlgaecidePumpRunning,
        FlocculantPumpRunning,
        *WATER_LEVEL,
        MaxRefillTime,
        MaxPhDoses,
        *UNIT_STATE,
        HeatingControlEnabled,
        HeatingLinkedToFiltration,
        FreezeProtectionEnabled,
        WaterLevelSensorEnabled,
        FlowDetectionEnabled,
        BackwashScheduleEnabled,
        HeatingCondition,
        HeatingConditionMet,
        VariableSpeedPumpType,
        *BACKWASH,
        *ALARMS,
    ),
    overrides={
        **SHARED_THIRD_PUMP,
        FreezeProtectionEnabled: "decode_v7_winter_mode",
    },
    flags=frozenset({AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY}),
    evidence={
        BackwashScheduleEnabled: confirmed(
            "byte[22] 0x10, cleared with byte[68] dropping to 0; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        FlowDetectionEnabled: confirmed(
            "byte[37] 0x02; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        HeatingConditionMet: confirmed(
            "byte[78] 0x80 follows the heating time window and the outside-temperature condition; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        HeatingCondition: confirmed(
            "byte[22] 0x01 time window, 0x02 outside temperature, 0x20 below; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        VariableSpeedPumpType: confirmed(
            "byte[78] 0x0C, every brand selected in turn; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14, and again in four clean on/off cycles with every brand, 2026-09-14 20:19-20:23"
        ),
        WaterLevelSensorEnabled: confirmed(
            "byte[37] 0x40; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        AirTemperature: confirmed(
            "two dumps from one SALT vs the unit display (Issue #155); matches the app and unit display, 2026-09-11"
        ),
        AlarmNoFlowToProbes: confirmed(
            'byte[13] 0x04 set at 2026-09-14 05:00:41, one second after the filtration pump started with no flow to the probes yet, cleared the second the flow arrived; the unit reported "there is no flow to probes" at that time; raw frames of the frame log checked (also confirmed on NET, DomSchCoding)'
        ),
        AlarmMaxDisinfectionDose: confirmed_on(
            AsekoDeviceType.HOME,
            "byte[12] 0x20 (Issue #134), byte[13] 0x01 (Issue #151)",
        ),
        AlarmPhDosingIneffective: confirmed_on(
            AsekoDeviceType.HOME, "byte[12] 0x40 (Issue #134); byte[13] 0x02 inferred"
        ),
        AlarmRapidPhChange: assumed(
            "byte[13] 0x08 from error_codes.md; never set in the own SALT dumps, 37 frames 2026-08-08..28"
        ),
        AlgaecidePumpRunning: confirmed(
            "byte[29] 0x20, 27 frames (PR #87); again on the own SALT 2026-09-14 20:59:42, a 2 s dose right after the dosing unit was changed"
        ),
        FreezeProtectionEnabled: confirmed(
            "Winter mode is byte[22] 0x04 (byte[37] 0x80 is the algicide routing here); confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        BackwashRunning: confirmed(
            "byte[29] 0x01, 2026-08-11 capture of a manual backwash"
        ),
        BackwashDuration: confirmed(
            "byte[71] * 10 matched the relay window; matches the app and unit display, 2026-09-11"
        ),
        BackwashInterval: confirmed(
            "byte[68] vs the unit's backwash settings (own SALT, the v1.8.0 backwash tracker classifies cycles against it); matches the app and unit display, 2026-09-11"
        ),
        BackwashStartTime: confirmed(
            "bytes 69-70 vs the unit's backwash settings (own SALT, v1.8.0 backwash tracker); matches the app and unit display, 2026-09-11"
        ),
        FreeChlorine: confirmed(
            "bytes 16-17 = 0.77 and 0.93 mg/l on the CLF unit of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer"
        ),
        Configuration: confirmed(
            "byte[4] missing-probe bits (0x0D CLF, 0x0E REDOX, 0x0F DOSE); matches the app and unit display, 2026-09-11"
        ),
        DosingDelay: confirmed(
            "bytes 106-107; matches the app and unit display, 2026-09-11"
        ),
        StartupDelay: confirmed(
            "bytes 74-75; matches the app and unit display, 2026-09-11"
        ),
        ElectrolysisRunning: confirmed("byte[29] 0x10, 25 frames (PR #87)"),
        ElectrodePolarity: confirmed(
            "byte[29] 0x40 = right, clear = left, switched by hand both ways; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        ChlorineProductionMeasured: confirmed(
            "byte[21] as sent (PR #87); matches the app and unit display, 2026-09-11; 0 in almost every frame with the electrolyser off, 18 of 6 546 stopped frames carried 3-25 g/h, each right after a stop and falling to 0 (marked test cases, 2026-09-13/14)"
        ),
        FiltrationRelay: confirmed("byte[29] 0x08 in every active phase (PR #87)"),
        FiltrationSchedule: confirmed(
            "0xC3 / 0xD3 / 0xF3, every transition both ways; matches the app and unit display, 2026-09-11"
        ),
        FlocculantPumpRunning: confirmed("byte[29] 0x20, Apr 3 frames"),
        AlgaecideFlowRate: confirmed(
            "byte[101] via byte[37] 0x80 (Issue #84, SALT v5.0, shows 0x13 with bit 7 clear while set to algicide: an older firmware may route differently) On the own SALT (2026-09-14 20:59-21:00) switching the third-port dosing unit to ml/h cleared byte[37] 0x80 and back to ml/m3/day set it again, frame-log markers."
        ),
        FlocculantFlowRate: confirmed(
            "byte[101] via byte[37] 0x80 clear (Issue #84, SALT v5.0, shows 0x13 with bit 7 clear while set to algicide: an older firmware may route differently) On the own SALT (2026-09-14 20:59-21:00) switching the third-port dosing unit to ml/h cleared byte[37] 0x80 and back to ml/m3/day set it again, frame-log markers."
        ),
        PhMinusFlowRate: confirmed("byte[95] (Issue #110, #115)"),
        HeatingRunning: assumed(
            "byte[29] 0x04 per JS-DE-Tech relay_byte bit 2; never set in the own SALT dumps, whose unit has heating control OFF"
        ),
        HeatingControlEnabled: confirmed(
            "byte[37] 0x08; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14"
        ),
        HeatingLinkedToFiltration: confirmed(
            "byte[38] 0x10 set and cleared with the setting on the own SALT, heating control on throughout, frame-log markers, 2026-09-14; the unit offers it only while heating control is on and sends the bit cleared while it is off (6 952 frames)"
        ),
        MaxRefillTime: confirmed(
            'bytes 76-77 in seconds, 1140 s = 19 min "Max. time of filling" on the unit display and in the Aseko Live app, 2026-09-11'
        ),
        MaxPhDoses: confirmed(
            "byte[115] followed a change of the unit's Safety Functions setting from 20 to 17 on the REDOX unit, 2026-09-12 19:47 -- and 17 appears nowhere else in that frame; 40 on the CLF unit"
        ),
        Ph: confirmed("bytes 14-15 / 100 on every model"),
        PhMinusConcentration: confirmed(
            "byte[112] = 14 then 15 % in the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        PhMinusPumpRunning: assumed(
            "byte[29] 0x80; the bit was never set in the own SALT dumps, 37 frames 2026-08-08..28"
        ),
        PoolVolume: confirmed(
            "bytes 92-93; matches the app and unit display, 2026-09-11"
        ),
        Redox: confirmed(
            "bytes 16-19 = 593..670 mV on the REDOX unit of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer"
        ),
        AlgaecideDoseTarget: confirmed(
            "byte[54] via byte[37] 0x80 (@hopkins-tk, Issue #84) (Issue #84, SALT v5.0, shows 0x13 with bit 7 clear while set to algicide: an older firmware may route differently); matches the app and unit display, 2026-09-11 On the own SALT (2026-09-14 20:59-21:00) switching the third-port dosing unit to ml/h cleared byte[37] 0x80 and back to ml/m3/day set it again, frame-log markers."
        ),
        ChlorineDoseTarget: assumed(
            "byte[53] for a DOSE unit; neither unit of the own SALT dumps, 37 frames 2026-08-08..28 is one"
        ),
        FreeChlorineTarget: confirmed(
            "byte[53] / 10 = 0.9 mg/l on the CLF unit of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer"
        ),
        FlocculantDoseTarget: confirmed(
            "byte[54] via byte[37] 0x80 clear (Issue #84, SALT v5.0, shows 0x13 with bit 7 clear while set to algicide: an older firmware may route differently) On the own SALT (2026-09-14 20:59-21:00) switching the third-port dosing unit to ml/h cleared byte[37] 0x80 and back to ml/m3/day set it again, frame-log markers."
        ),
        PhTarget: confirmed(
            "byte[52] / 10 on every model; matches the app and unit display, 2026-09-11"
        ),
        RedoxTarget: confirmed(
            "byte[53] * 10 = 670 mV on the REDOX unit of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        WaterTemperatureTarget: confirmed(
            "byte[55] = 25 C in every frame (own SALT dumps Aug 2026); the app shows --- while heating control is OFF, so the byte keeps the setpoint the app hides"
        ),
        Salinity: confirmed(
            "byte[20] / 10; matches the app and unit display, 2026-09-11"
        ),
        SerialNumber: confirmed("bytes 0-3, repeated in every segment header"),
        ServiceMenuOpen: confirmed("0xD7 / 0xF7 then the unit goes offline"),
        FiltrationPeriod1Start: confirmed(
            "bytes 56-57 changed 08:00 -> 09:00 with the timer settings during the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        FiltrationPeriod2Start: confirmed(
            "bytes 60-61 changed 18:00 -> 18:10 with the timer settings during the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        FiltrationPeriod1End: confirmed(
            "bytes 58-59 changed 18:05 / 19:00 / 21:35 with the timer settings during the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        FiltrationPeriod2End: confirmed(
            "bytes 62-63 changed 22:00 -> 23:55 with the timer settings during the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        Timestamp: confirmed("bytes 6-11"),
        UnitClock: confirmed(
            "bytes 6-11; about 5 min ahead of Home Assistant in the 2026-09-13/14 capture, matching the backwash valve opening about 5 min before the planned time"
        ),
        VariableSpeedPumpEnabled: confirmed(
            "byte[22] 0x08 is the VS Pump setting, not the run state; confirmed on the own SALT by toggling it on the unit with a frame-log marker after each change, 2026-09-13/14, and in four clean on/off cycles, one per brand, 2026-09-14 20:19-20:23"
        ),
        Refilling: confirmed(
            "byte[29] 0x02 on the own SALT, 2026-09-06 08:12-08:21: set when the water level fell to the unit's refill start (10) and cleared when it reached the refill stop (25), the level rising only while it was set; not in the earlier dumps, which caught no refill"
        ),
        WaterFlowToProbes: confirmed("byte[28] == 0xAA"),
        WaterLevel: confirmed(
            "byte[27] 14..25 cm across the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer"
        ),
        WaterLevelRefillStop: confirmed(
            "byte[104] = 25 and 35 cm on the two units of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        WaterLevelRefillStart: confirmed(
            "byte[103] = 10 and 33 cm on the two units of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        WaterLevelHighAlarm: confirmed(
            "byte[105] = 40 and 56..73 cm on the two units of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; matches the app and unit display, 2026-09-11"
        ),
        WaterLevelLowAlarm: confirmed(
            "byte[102] = 5 and 31 cm on the two units of the own SALT dumps, 37 frames 2026-08-08..28, checked against the unit by the maintainer; thresholds ordered low < on < off < high; matches the app and unit display, 2026-09-11"
        ),
        WaterTemperature: confirmed("bytes 25-26 / 10 on every model"),
    },
)
