"""Constants for the Hegel Streaming integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "hegel_streaming"

CONF_DEVICE: Final = "device"
CONF_MAX_VOLUME: Final = "max_volume"
DEFAULT_MAX_VOLUME: Final = 100

# Full refresh as a safety net; changes arrive through the event queue in between.
SCAN_INTERVAL: Final = timedelta(seconds=30)
# How often to retry while the amp does not answer.
RECONNECT_INTERVAL: Final = 10
EVENT_POLL_TIMEOUT: Final = 25

HIFISYNC_URL: Final = "https://hifisync.com/?utm_source=home-assistant&utm_medium=integration&utm_campaign=hegel_streaming"
