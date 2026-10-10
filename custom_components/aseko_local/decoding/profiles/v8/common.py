"""What every v8 profile shares: the frame layout.

Every v8 frame observed so far uses the same layout regardless of the
header's type field, so the device modules take ``FEATURES`` as it is or
leave out what their model does not have.
"""

from __future__ import annotations

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

FEATURES = (
    SerialNumber,
    Configuration,
    Timestamp,
    UnitClock,
    WaterTemperature,
    WaterFlowToProbes,
    Ph,
    Redox,
    FiltrationRelay,
    PhMinusPumpRunning,
    ChlorinePumpRunning,
    PhMinusFlowRate,
    ChlorineFlowRate,
    PhTarget,
    RedoxTarget,
    PoolVolume,
    StartupDelay,
    DosingDelay,
)
