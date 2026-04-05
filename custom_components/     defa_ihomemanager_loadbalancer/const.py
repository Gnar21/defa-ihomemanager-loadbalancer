DOMAIN = "defa_ihomemanager_loadbalancer"

CONF_IHM_HOST = "ihomemanager_host"
CONF_IHM_PORT = "ihomemanager_port"
CONF_IHM_UNIT = "ihomemanager_unit"

CONF_DEFA_HOST = "defa_host"
CONF_DEFA_PORT = "defa_port"
CONF_DEFA_UNIT = "defa_unit"

# Defaults from your setup / device protocols
DEFAULT_IHM_HOST = "192.168.1.42"
DEFAULT_IHM_PORT = 502
DEFAULT_IHM_UNIT = 247

DEFAULT_DEFA_HOST = "192.168.1.56"
DEFAULT_DEFA_PORT = 502
DEFAULT_DEFA_UNIT = 255

# Polling
DEFAULT_SCAN_INTERVAL = 10  # seconds (also used as keepalive cadence)

# Control defaults
DEFAULT_FUSE_A = 20.0
DEFAULT_MARGIN_A = 2.0
DEFAULT_NORMAL_MAX_A = 16.0
DEFAULT_MIN_A = 6.0

# Eco per phase (configurable)
DEFAULT_ECO_GRID_LIMIT_A = 2.0
DEFAULT_GRID_POWER_SIGN = 1  # can be flipped (-1) if your sign convention differs

# Anti-fladder defaults
DEFAULT_DEADBAND_A = 1.0
DEFAULT_RAMP_A_PER_MIN = 2.0
DEFAULT_MIN_UP_INTERVAL_S = 60
