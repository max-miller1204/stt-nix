import os
import logging

try:
    import tomllib
except ImportError:
    import tomli as tomllib

log = logging.getLogger(__name__)

def _default_device() -> str:
    try:
        import ctranslate2
        if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
            return "cuda"
    except Exception:
        pass
    return "cpu"


DEFAULT_CONFIG = {
    "transcription": {
        "backend": "local",
        "model": "base",
        "language": "en",
        "device": "auto",
        "compute_type": "auto",
    },
    "groq": {
        "api_key": "",
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
    },
    "output": {
        "paste_delay_ms": 100,
        "paste_key": "ctrl+v",
    },
    "hotkey": {
        "enabled": False,
        "key": "KEY_RIGHTALT",
        "mode": "hold",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def config_path() -> str:
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(xdg, "stt-nix", "config.toml")


def load_config() -> dict:
    path = config_path()
    if os.path.exists(path):
        log.info("Loading config from %s", path)
        with open(path, "rb") as f:
            user = tomllib.load(f)
        return _deep_merge(DEFAULT_CONFIG, user)
    log.info("No config found at %s, using defaults", path)
    return DEFAULT_CONFIG.copy()
