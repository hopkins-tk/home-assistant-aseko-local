"""One decoder file per field on ``AsekoDevice``.

``ALL_FEATURES`` lists every feature the integration knows, whether or not
any profile currently uses it.  Profiles import the classes they list from
here; the support-matrix generator walks this list to report what each
profile does and does not read.
"""

from __future__ import annotations

from ..feature import Feature
from .air_temperature import AirTemperature
from .alarm_max_disinfection_dose import AlarmMaxDisinfectionDose
from .alarm_no_flow_to_probes import AlarmNoFlowToProbes
from .alarm_ph_dosing_ineffective import AlarmPhDosingIneffective
from .alarm_rapid_ph_change import AlarmRapidPhChange
from .algaecide_dose_target import AlgaecideDoseTarget
from .algaecide_flow_rate import AlgaecideFlowRate
from .algaecide_pump_running import AlgaecidePumpRunning
from .backwash_duration import BackwashDuration
from .backwash_interval import BackwashInterval
from .backwash_running import BackwashRunning
from .backwash_schedule_enabled import BackwashScheduleEnabled
from .backwash_start_time import BackwashStartTime
from .chlorine_dose_target import ChlorineDoseTarget
from .chlorine_flow_rate import ChlorineFlowRate
from .chlorine_production_measured import ChlorineProductionMeasured
from .chlorine_pump_running import ChlorinePumpRunning
from .configuration import Configuration
from .dosing_delay import DosingDelay
from .electrode_polarity import ElectrodePolarity
from .electrolysis_running import ElectrolysisRunning
from .filtration_period_1_end import FiltrationPeriod1End
from .filtration_period_1_start import FiltrationPeriod1Start
from .filtration_period_2_end import FiltrationPeriod2End
from .filtration_period_2_start import FiltrationPeriod2Start
from .filtration_relay import FiltrationRelay
from .filtration_schedule import FiltrationSchedule
from .flocculant_dose_target import FlocculantDoseTarget
from .flocculant_flow_rate import FlocculantFlowRate
from .flocculant_pump_running import FlocculantPumpRunning
from .flow_detection_enabled import FlowDetectionEnabled
from .free_chlorine import FreeChlorine
from .free_chlorine_mv import FreeChlorineMv
from .free_chlorine_target import FreeChlorineTarget
from .freeze_protection_enabled import FreezeProtectionEnabled
from .heating_condition import HeatingCondition
from .heating_condition_met import HeatingConditionMet
from .heating_control_enabled import HeatingControlEnabled
from .heating_linked_to_filtration import HeatingLinkedToFiltration
from .heating_running import HeatingRunning
from .max_ph_doses import MaxPhDoses
from .max_refill_time import MaxRefillTime
from .oxygen_dose_target import OxygenDoseTarget
from .oxygen_flow_rate import OxygenFlowRate
from .oxygen_pump_running import OxygenPumpRunning
from .ph import Ph
from .ph_minus_concentration import PhMinusConcentration
from .ph_minus_flow_rate import PhMinusFlowRate
from .ph_minus_pump_running import PhMinusPumpRunning
from .ph_plus_flow_rate import PhPlusFlowRate
from .ph_plus_pump_running import PhPlusPumpRunning
from .ph_target import PhTarget
from .pool_volume import PoolVolume
from .redox import Redox
from .redox_target import RedoxTarget
from .refilling import Refilling
from .salinity import Salinity
from .serial_number import SerialNumber
from .service_menu_open import ServiceMenuOpen
from .startup_delay import StartupDelay
from .timestamp import Timestamp
from .unit_clock import UnitClock
from .variable_speed_pump_enabled import VariableSpeedPumpEnabled
from .variable_speed_pump_type import VariableSpeedPumpType
from .water_flow_to_probes import WaterFlowToProbes
from .water_level import WaterLevel
from .water_level_high_alarm import WaterLevelHighAlarm
from .water_level_low_alarm import WaterLevelLowAlarm
from .water_level_refill_start import WaterLevelRefillStart
from .water_level_refill_stop import WaterLevelRefillStop
from .water_level_sensor_enabled import WaterLevelSensorEnabled
from .water_temperature import WaterTemperature
from .water_temperature_target import WaterTemperatureTarget

ALL_FEATURES: tuple[type[Feature], ...] = (
    WaterLevelSensorEnabled,
    FlowDetectionEnabled,
    BackwashScheduleEnabled,
    HeatingConditionMet,
    HeatingCondition,
    VariableSpeedPumpType,
    AirTemperature,
    AlarmNoFlowToProbes,
    AlarmMaxDisinfectionDose,
    AlarmPhDosingIneffective,
    AlarmRapidPhChange,
    AlgaecidePumpRunning,
    FreezeProtectionEnabled,
    BackwashRunning,
    BackwashDuration,
    BackwashInterval,
    BackwashStartTime,
    FreeChlorine,
    FreeChlorineMv,
    ChlorinePumpRunning,
    Configuration,
    DosingDelay,
    StartupDelay,
    ElectrolysisRunning,
    ElectrodePolarity,
    ChlorineProductionMeasured,
    FiltrationRelay,
    FiltrationSchedule,
    FiltrationPeriod1Start,
    FiltrationPeriod2Start,
    FiltrationPeriod1End,
    FiltrationPeriod2End,
    FlocculantPumpRunning,
    AlgaecideFlowRate,
    ChlorineFlowRate,
    FlocculantFlowRate,
    OxygenFlowRate,
    PhMinusFlowRate,
    PhPlusFlowRate,
    HeatingRunning,
    HeatingControlEnabled,
    HeatingLinkedToFiltration,
    MaxRefillTime,
    MaxPhDoses,
    OxygenPumpRunning,
    Ph,
    PhMinusConcentration,
    PhMinusPumpRunning,
    PhPlusPumpRunning,
    PoolVolume,
    Redox,
    AlgaecideDoseTarget,
    ChlorineDoseTarget,
    FreeChlorineTarget,
    FlocculantDoseTarget,
    OxygenDoseTarget,
    PhTarget,
    RedoxTarget,
    WaterTemperatureTarget,
    Salinity,
    SerialNumber,
    ServiceMenuOpen,
    Timestamp,
    UnitClock,
    VariableSpeedPumpEnabled,
    Refilling,
    WaterFlowToProbes,
    WaterLevel,
    WaterLevelRefillStop,
    WaterLevelRefillStart,
    WaterLevelHighAlarm,
    WaterLevelLowAlarm,
    WaterTemperature,
)

__all__ = [
    "ALL_FEATURES",
    "AirTemperature",
    "AlarmMaxDisinfectionDose",
    "AlarmNoFlowToProbes",
    "AlarmPhDosingIneffective",
    "AlarmRapidPhChange",
    "AlgaecideDoseTarget",
    "AlgaecideFlowRate",
    "AlgaecidePumpRunning",
    "BackwashDuration",
    "BackwashInterval",
    "BackwashRunning",
    "BackwashScheduleEnabled",
    "BackwashStartTime",
    "ChlorineDoseTarget",
    "ChlorineFlowRate",
    "ChlorineProductionMeasured",
    "ChlorinePumpRunning",
    "Configuration",
    "DosingDelay",
    "ElectrodePolarity",
    "ElectrolysisRunning",
    "FiltrationPeriod1End",
    "FiltrationPeriod1Start",
    "FiltrationPeriod2End",
    "FiltrationPeriod2Start",
    "FiltrationRelay",
    "FiltrationSchedule",
    "FlocculantDoseTarget",
    "FlocculantFlowRate",
    "FlocculantPumpRunning",
    "FlowDetectionEnabled",
    "FreeChlorine",
    "FreeChlorineMv",
    "FreeChlorineTarget",
    "FreezeProtectionEnabled",
    "HeatingCondition",
    "HeatingConditionMet",
    "HeatingControlEnabled",
    "HeatingLinkedToFiltration",
    "HeatingRunning",
    "MaxPhDoses",
    "MaxRefillTime",
    "OxygenDoseTarget",
    "OxygenFlowRate",
    "OxygenPumpRunning",
    "Ph",
    "PhMinusConcentration",
    "PhMinusFlowRate",
    "PhMinusPumpRunning",
    "PhPlusFlowRate",
    "PhPlusPumpRunning",
    "PhTarget",
    "PoolVolume",
    "Redox",
    "RedoxTarget",
    "Refilling",
    "Salinity",
    "SerialNumber",
    "ServiceMenuOpen",
    "StartupDelay",
    "Timestamp",
    "UnitClock",
    "VariableSpeedPumpEnabled",
    "VariableSpeedPumpType",
    "WaterFlowToProbes",
    "WaterLevel",
    "WaterLevelHighAlarm",
    "WaterLevelLowAlarm",
    "WaterLevelRefillStart",
    "WaterLevelRefillStop",
    "WaterLevelSensorEnabled",
    "WaterTemperature",
    "WaterTemperatureTarget",
]
