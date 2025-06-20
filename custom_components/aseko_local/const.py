"""Constants for Aseko Local integration."""

DOMAIN = "aseko_local"
MANUFACTURER = "Aseko"

DEFAULT_BINDING_ADDRESS = "0.0.0.0"  # noqa: S104
DEFAULT_BINDING_PORT = 47524

YEAR_OFFSET = 2000
MESSAGE_SIZE = 120
MAX_CLF_LIMIT = 100

WATER_FLOW_TO_PROBES = 0xAA
ELECTROLYZER_RUNNING = 0x10
ELECTROLYZER_RUNNING_LEFT = 0x50
PUMP_RUNNING = 0x08

PROBE_REDOX_MISSING = 0x01
PROBE_CLF_MISSING = 0x02
PROBE_DOSE_MISSING = 0x04
PROBE_SANOSIL_MISSING = 0x08  # OXY Pure

UNSPECIFIED_VALUE = 0xFF
