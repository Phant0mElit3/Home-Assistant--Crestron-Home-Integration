"""Constants for the Crestron Home integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "crestron_home"

CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_NAME = "Crestron Home"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=15)

PLATFORMS = [
    "alarm_control_panel",
    "binary_sensor",
    "climate",
    "cover",
    "light",
    "lock",
    "media_player",
    "scene",
    "select",
    "sensor",
]
