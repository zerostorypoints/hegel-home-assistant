"""Constants for the Hegel Streaming integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "hegel_streaming"

CONF_DEVICE: Final = "device"
CONF_MAX_VOLUME: Final = "max_volume"
CONF_HIDDEN_SOURCES: Final = "hidden_sources"
CONF_SOURCE_NAMES: Final = "source_names"
CONF_SOURCES: Final = "sources"
DEFAULT_MAX_VOLUME: Final = 100

# Full refresh as a safety net; changes arrive through the event queue in between.
SCAN_INTERVAL: Final = timedelta(seconds=30)
# How often to retry while the amp does not answer.
RECONNECT_INTERVAL: Final = 10
EVENT_POLL_TIMEOUT: Final = 25
# Radio favourites change only when someone edits them in the Hegel app.
FAVORITES_INTERVAL: Final = timedelta(minutes=5)

CORE_HEGEL_URL: Final = "https://www.home-assistant.io/integrations/hegel/"
