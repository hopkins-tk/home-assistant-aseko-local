"""v7 profile: ASIN AQUA Home.

HOME once had two profiles, for a "firmware A / B" split that turned out to
be bit 0x40 of byte[37] -- the Waterlevel setting.  One profile covers both.
"""

from __future__ import annotations

from ....models import AsekoDeviceType, AsekoProfileFlag
from ...evidence import assumed, confirmed, confirmed_on, not_located, observed
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
    ChlorineFlowRate,
    ChlorinePumpRunning,
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
    FreeChlorine,
    FreeChlorineMv,
    FreeChlorineTarget,
    FreezeProtectionEnabled,
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
    CHLORINE_PROBES,
    CLOCK,
    DISINFECTION_SETPOINTS,
    FILTRATION,
    IDENTITY,
    MEASUREMENTS,
    SETTINGS,
    UNIT_STATE,
    WATER_LEVEL,
)

_HOME_FEATURES = (
    *IDENTITY,
    *CLOCK,
    *MEASUREMENTS,
    AirTemperature,
    *CHLORINE_PROBES,
    *SETTINGS,
    *DISINFECTION_SETPOINTS,
    AlgaecideDoseTarget,
    FlocculantDoseTarget,
    ChlorineFlowRate,
    AlgaecideFlowRate,
    FlocculantFlowRate,
    *FILTRATION,
    ChlorinePumpRunning,
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
    ServiceMenuOpen,
    WaterLevelSensorEnabled,
    FlowDetectionEnabled,
    BackwashScheduleEnabled,
    VariableSpeedPumpType,
    *BACKWASH,
    *ALARMS,
)

HOME = Profile(
    name="v7 HOME",
    protocol=Protocol.V7,
    model=AsekoDeviceType.HOME,
    features=_HOME_FEATURES,
    overrides={
        Configuration: "decode_v7_by_unit_type_byte",
        # four independent pump ports like OXY: algicide is bit 0x10, not the
        # 0x20 flocculant bit, which counted both chemicals for one pump
        AlgaecidePumpRunning: "decode_v7_oxy",
        # byte[103] is the refill start threshold here; where HOME sends the
        # algicide flow rate is not known
        AlgaecideFlowRate: "decode_v7_not_located",
    },
    flags=frozenset({AsekoProfileFlag.MENU_BIT_SWITCHES_FILTRATION_OFF}),
    evidence={
        BackwashScheduleEnabled: observed(
            "byte[22] 0x10 set on serial 110128063 with backwash every 3 days (0x90); confirmed on an ASIN AQUA Salt (2026-09-13)"
        ),
        FlowDetectionEnabled: confirmed_on(
            AsekoDeviceType.SALT,
            "byte[37] 0x02 (2026-09-13); on HOME 0x43 / 0x53 have it set and Issue #135's 0x41 / 0x45 / 0x49 clear",
        ),
        VariableSpeedPumpType: confirmed(
            "byte[78] 0x22 / 0x26 / 0x2a for Speck-Uwe / Pentair-Dab / Hayward (Issue #137); the same bits on an ASIN AQUA Salt (2026-09-13/14)"
        ),
        WaterLevelSensorEnabled: confirmed_on(
            AsekoDeviceType.SALT,
            "byte[37] 0x40 (2026-09-13); set in every frame of the level-meter HOME units (once 'firmware A'), clear on serial 110169464 (once 'firmware B')",
        ),
        AirTemperature: assumed(
            "bytes 23-24 = 0xFE70 (no air probe, the SALT marker) in every captured HOME frame, so its entity has stayed disabled; the Aseko Live app shows air temperature on HOME units"
        ),
        AlarmNoFlowToProbes: confirmed_on(
            AsekoDeviceType.NET, "byte[13] 0x04 (DomSchCoding, NET frame)"
        ),
        AlarmMaxDisinfectionDose: confirmed(
            "byte[12] 0x20 (Issue #134), byte[13] 0x01 (Issue #151)"
        ),
        AlarmPhDosingIneffective: confirmed(
            "byte[12] 0x40 (Issue #134); byte[13] 0x02 inferred"
        ),
        AlarmRapidPhChange: assumed(
            "byte[13] 0x08 was set on serial 110128063 with no matching alarm known in the app"
        ),
        AlgaecidePumpRunning: assumed(
            "byte[29] 0x10 as on OXY, which has the same four independent pump ports (0x20 is the flocculant); read only once the algicide flow rate is located, so no state yet"
        ),
        FreezeProtectionEnabled: confirmed(
            "byte[37] 0x80, serial 110175608 (Issue #136)"
        ),
        BackwashRunning: assumed("byte[29] 0x01, confirmed on SALT"),
        BackwashDuration: confirmed(
            "byte[71] * 10 = 120 s vs '02:00 min' in Aseko Live, serial 110128063"
        ),
        BackwashInterval: confirmed(
            "byte[68] = 3 vs 'every 3 days' in Aseko Live, serial 110128063"
        ),
        BackwashStartTime: confirmed(
            "bytes 69-70 = 21:00 vs Aseko Live, serial 110128063"
        ),
        FreeChlorine: confirmed(
            "bytes 16-17 = 0.00 mg/l vs Aseko Live, serial 110128063 (2026-04-28)"
        ),
        FreeChlorineMv: confirmed("bytes 20-21 = 2 mV, serial 110128063 (2026-04-28)"),
        ChlorinePumpRunning: assumed("byte[29] 0x40, port may be chlorine or OXY Pure"),
        Configuration: confirmed(
            "byte[4] exact sub-type, 0x02 CLF / 0x03 REDOX (Issue #110)"
        ),
        DosingDelay: confirmed(
            "bytes 106-107 = 240 s vs '4 min' in Aseko Live, serial 110128063"
        ),
        StartupDelay: confirmed(
            "bytes 74-75 = 480 s vs '8 min' in Aseko Live, serial 110128063"
        ),
        FiltrationRelay: confirmed(
            "byte[29] 0x08; stays set while the pump is switched off by hand, which byte[37] 0x04 shows (Issue #133)"
        ),
        FiltrationSchedule: confirmed(
            "byte[37] 0x10 / 0x20, 0x01 / 0x11 / 0x31 on serial 110169464 (Issue #133); the values once read as firmware A (0x43 nonstop, 0x53 timer) are the same bits with Waterlevel (0x40) and Flow detection (0x02) set"
        ),
        FlocculantPumpRunning: assumed("byte[29] 0x20 as on OXY (confirmed there)"),
        AlgaecideFlowRate: not_located(
            "byte[103] was read as the algicide flow rate (Issues #110, #115), but bytes 102-105 are the water level thresholds -- confirmed on SALT against the unit (2026-09-11) and 13 / 33 / 55 / 100 cm in order on serial 110128063; the captured OXY sends its algicide flow rate there, and has no level sensor connected"
        ),
        ChlorineFlowRate: confirmed(
            "byte[99], serials 110071590 / 110128063 (Issues #110, #115)"
        ),
        FlocculantFlowRate: confirmed("byte[101], Issues #110, #115"),
        PhMinusFlowRate: observed(
            "byte[95] = 60 on serial 110128063; Aseko Live lists the pH- pump but the rate was not compared; the position is confirmed on SALT"
        ),
        HeatingRunning: assumed(
            "byte[29] 0x04 per JS-DE-Tech relay_byte bit 2; no HOME frame with the heater running (open item 9)"
        ),
        HeatingControlEnabled: confirmed(
            "byte[37] 0x08, serial 110175608 (Issue #135); the same bit on an ASIN AQUA Salt (2026-09-13)"
        ),
        Redox: assumed(
            "bytes 16-19 as on SALT (bytes 18-19 when not 0xFFFF); no REDOX HOME frame with the app's value"
        ),
        RedoxTarget: assumed(
            "byte[53] x 10 mV as on SALT; no REDOX HOME frame compared"
        ),
        ChlorineDoseTarget: assumed(
            "byte[53] with a DOSE unit type, as on NET; no DOSE HOME frame captured"
        ),
        HeatingLinkedToFiltration: assumed(
            "byte[38] 0x10 as on SALT (confirmed there, 2026-09-14); no HOME frame compared"
        ),
        MaxRefillTime: assumed(
            "bytes 76-77 = 10800 s on serial 110128063, plausible (180 min); verified on SALT only"
        ),
        MaxPhDoses: observed(
            "byte[115] = 20 on serial 110128063; the position is confirmed on SALT, the HOME setting was never compared"
        ),
        Ph: confirmed(
            "bytes 14-15 = 6.29 vs 6.56 in Aseko Live (later reading), serial 110128063"
        ),
        PhMinusConcentration: confirmed("byte[112], serial 110175608 (Issue #139)"),
        PhMinusPumpRunning: assumed("byte[29] 0x80"),
        PoolVolume: confirmed("bytes 92-93 = 60 m3 vs Aseko Live, serial 110128063"),
        AlgaecideDoseTarget: confirmed("byte[72], serial 110128063 (2026-04-28)"),
        FreeChlorineTarget: confirmed(
            "byte[53] / 10 = 0.3 mg/l vs Aseko Live, serial 110128063"
        ),
        FlocculantDoseTarget: confirmed("byte[54], serial 110128063 (2026-04-28)"),
        PhTarget: confirmed("byte[52] / 10 = 7.0 vs Aseko Live, serial 110128063"),
        WaterTemperatureTarget: confirmed(
            "byte[55] is the heating setpoint on serial 110175608 (Issue #135); 25 C with heating disabled on 110128063"
        ),
        SerialNumber: confirmed("bytes 0-3, repeated in every segment header"),
        ServiceMenuOpen: confirmed(
            "byte[37] 0x04 as a standing pump override (Issue #133); the 0x47 / 0x57 values once called a transitional edit state are the same bit"
        ),
        FiltrationPeriod1Start: confirmed(
            "bytes 56-57 = 08:00 last-configured, serial 110128063 (Issues #110, #133)"
        ),
        FiltrationPeriod2Start: confirmed(
            "bytes 60-61 = 18:00 last-configured, serial 110128063 (Issues #110, #133)"
        ),
        FiltrationPeriod1End: confirmed(
            "bytes 58-59 = 16:00 last-configured, serial 110128063 (Issues #110, #133)"
        ),
        FiltrationPeriod2End: confirmed(
            "bytes 62-63 = 22:00 last-configured, serial 110128063 (Issues #110, #133)"
        ),
        Timestamp: confirmed("bytes 6-11"),
        UnitClock: confirmed(
            "bytes 6-11, the bytes of timestamp without its fallback to Home Assistant's clock"
        ),
        VariableSpeedPumpEnabled: confirmed("byte[22] 0x08, serial 110175608"),
        Refilling: confirmed("byte[29] 0x02 (DomSchCoding #100)"),
        WaterFlowToProbes: confirmed(
            "byte[28] != 0xAA while Aseko Live showed 'NO', serial 110128063"
        ),
        WaterLevel: confirmed("byte[27] (domin211, Issue #110)"),
        WaterLevelRefillStop: confirmed(
            "byte[104] (domin211, DomSchCoding, Issue #110)"
        ),
        WaterLevelRefillStart: confirmed_on(
            AsekoDeviceType.SALT,
            "byte[103], bytes 102-105 are the level thresholds (SALT 2026-09-11 against the unit); 33 cm on serial 110128063 sits between the low alarm 13 and the refill stop 55",
        ),
        WaterLevelHighAlarm: confirmed("byte[105] (domin211, Issue #110)"),
        WaterLevelLowAlarm: confirmed("byte[102] (domin211, Issue #110)"),
        WaterTemperature: confirmed(
            "bytes 25-26 = 37.9 C vs 38.2 C in Aseko Live (later reading), serial 110128063"
        ),
    },
)
