from homeassistant.const import UnitOfVolume
from .aseko_data import AsekoPumpType


"""Constants for Aseko Local integration."""

DOMAIN = "aseko_local"
MANUFACTURER = "Aseko"

# Binding defaults
DEFAULT_BINDING_ADDRESS = "0.0.0.0"  # noqa: S104
DEFAULT_BINDING_PORT = 47524

# Proxy defaults
DEFAULT_FORWARDER_HOST = "pool.aseko.com"
DEFAULT_FORWARDER_PORT = 47524

# Year offset and message sizes
YEAR_OFFSET = 2000
MESSAGE_SIZE = 120
MAX_CLF_LIMIT = 100

# Bit masks
WATER_FLOW_TO_PROBES = 0xAA
ELECTROLYZER_RUNNING = 0x10
ELECTROLYZER_RUNNING_LEFT = 0x50
PUMP_RUNNING = 0x08

# Probe missing flags
PROBE_REDOX_MISSING = 0x01
PROBE_CLF_MISSING = 0x02
PROBE_DOSE_MISSING = 0x04
PROBE_SANOSIL_MISSING = 0x08  # OXY Pure

UNIT_TYPE_SALT = 0x0C  # SALT can be 0x0D or 0x0E
UNIT_TYPE_HOME = 0x04  # HOME can be 0x05 or 0x06
UNIT_TYPE_NET = 0x08  # NET can be 0x09 or 0x0A
UNIT_TYPE_PROFI = 0x08  # PROFI is 0x08

UNSPECIFIED_VALUE = 0xFF

# Config / option keys
CONF_ENABLE_RAW_LOGGING = "enable_raw_logging"
CONF_FORWARDER_ENABLED = "forwarder_enabled"
CONF_FORWARDER_HOST = "forwarder_host"
CONF_FORWARDER_PORT = "forwarder_port"
