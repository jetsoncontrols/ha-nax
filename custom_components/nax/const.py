from typing import Any

DOMAIN = "nax"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

STORAGE_VERSION = 1
STORAGE_LAST_INPUT_KEY = "last_input"
STORAGE_LAST_AES67_STREAM_KEY = "last_aes67_stream"
STORAGE_LAST_BTS_STREAM_KEY = "last_bts_stream"


def safe_get(data: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts, returning default if any key is missing or value is not a dict."""
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
    if isinstance(data, str):
        return default
    return data
