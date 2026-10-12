"""What every v7 profile shares: the feature groups the device modules list.

A group is a convenience for reading the lists, not a concept the decoder
knows.  Nothing model-specific belongs here.
"""

from __future__ import annotations

from ...features import (
    AlarmMaxDisinfectionDose,
    AlarmNoFlowToProbes,
    AlarmPhDosingIneffective,
    AlarmRapidPhChange,
    AlgaecideDoseTarget,
    AlgaecideFlowRate,
    BackwashDuration,
    BackwashInterval,
    BackwashRunning,
    BackwashStartTime,
    ChlorineDoseTarget,
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
    FreeChlorine,
    FreeChlorineMv,
    FreeChlorineTarget,
    HeatingRunning,
    Ph,
    PhMinusConcentration,
    PhMinusFlowRate,
    PhTarget,
    PoolVolume,
    Redox,
    RedoxTarget,
    Refilling,
    SerialNumber,
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
    WaterTemperature,
    WaterTemperatureTarget,
)

# ---------------------------------------------------------------------------
# Feature groups shared between profiles.  A group is a convenience for
# reading the lists below, not a concept the decoder knows.
# ---------------------------------------------------------------------------

IDENTITY = (SerialNumber, Configuration, Timestamp)
# Every model that sends its own clock; not NET, whose bytes 6-11 are 0xFF.
CLOCK = (UnitClock,)
MEASUREMENTS = (WaterTemperature, WaterFlowToProbes)
CHLORINE_PROBES = (Ph, Redox, FreeChlorine, FreeChlorineMv)
SETTINGS = (
    PhTarget,
    WaterTemperatureTarget,
    PoolVolume,
    StartupDelay,
    DosingDelay,
    PhMinusFlowRate,
)
ALARMS = (
    AlarmPhDosingIneffective,
    AlarmMaxDisinfectionDose,
    AlarmNoFlowToProbes,
    AlarmRapidPhChange,
)
FILTRATION = (
    FiltrationPeriod1Start,
    FiltrationPeriod1End,
    FiltrationPeriod2Start,
    FiltrationPeriod2End,
    FiltrationSchedule,
    FiltrationRelay,
)
BACKWASH = (BackwashInterval, BackwashStartTime, BackwashDuration, BackwashRunning)
WATER_LEVEL = (
    WaterLevel,
    WaterLevelLowAlarm,
    WaterLevelRefillStart,
    WaterLevelRefillStop,
    WaterLevelHighAlarm,
    Refilling,
)
UNIT_STATE = (HeatingRunning, VariableSpeedPumpEnabled, PhMinusConcentration)

# The disinfection setpoint family on chlorine units: byte[53] is one of
# these three depending on the installed probes, each answers only when it
# is the one that applies.
DISINFECTION_SETPOINTS = (FreeChlorineTarget, RedoxTarget, ChlorineDoseTarget)

# Algicide / flocculant on a single shared port, routed by byte[37] bit 0x80.
SHARED_THIRD_PUMP = {
    AlgaecideDoseTarget: "decode_v7_routed_by_byte37",
    FlocculantDoseTarget: "decode_v7_routed_by_byte37",
    AlgaecideFlowRate: "decode_v7_routed_by_byte37",
    FlocculantFlowRate: "decode_v7_routed_by_byte37",
}
