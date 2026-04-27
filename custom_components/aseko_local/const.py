"""Constants for Aseko Local integration."""

DOMAIN = "aseko_local"
MANUFACTURER = "Aseko"

# Binding defaults
DEFAULT_BINDING_ADDRESS = "0.0.0.0"  # noqa: S104
DEFAULT_BINDING_PORT = 47524

# Proxy defaults
DEFAULT_FORWARDER_HOST = "pool.aseko.com"
DEFAULT_FORWARDER_PORT_V7 = 47524
DEFAULT_FORWARDER_PORT_V8 = 51050

# Year offset and message sizes
YEAR_OFFSET = 2000
MESSAGE_SIZE = 120
MAX_CLF_LIMIT = 100

# Connection timeout in seconds (3x normal 10s interval)
READ_TIMEOUT = 30.0

# Bit masks
WATER_FLOW_TO_PROBES = 0xAA

# Probe missing flags
# (unfortunately seems not to be true for HOME)
PROBE_REDOX_MISSING = 0x01
PROBE_CLF_MISSING = 0x02
PROBE_DOSE_MISSING = 0x04
PROBE_OXY_MISSING = 0x08  # OXY Pure (H₂O₂) probe present on ASIN AQUA Oxygen

UNIT_TYPE_HOME = 0x02  # HOME can be CLF (0x02) or REDOX (0x03) | posibly DOSE (0x04) - no examples for DOSE
UNIT_TYPE_HOME_CLF = 0x02
UNIT_TYPE_HOME_REDOX = 0x03
UNIT_TYPE_OXY = 0x05  # ASIN AQUA Oxygen – exact match, no overlap with other types
UNIT_TYPE_NET = 0x08  # NET can be CLF (0x09) or REDOX (0x0A) or DOSE (0x0B)
UNIT_TYPE_SALT = 0x0C  # SALT can be CLF (0x0D) or REDOX (0x0E) or DOSE (0x0F)
UNIT_TYPE_PROFI = 0x10  # PROFI is 0x10 - not confirmed

UNSPECIFIED_VALUE = 0xFF
UNSPECIFIED_V8 = -500  # v8 text frame sentinel for absent/unavailable probe readings

# Config / option keys
CONF_ENABLE_RAW_LOGGING = "enable_raw_logging"
CONF_FORWARDER_ENABLED = "forwarder_enabled"
CONF_FORWARDER_HOST = "forwarder_host"
CONF_FORWARDER_PORT = "forwarder_port"
