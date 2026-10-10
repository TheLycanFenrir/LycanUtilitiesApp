"""The single app-level settings document (stored under ``app_settings``)."""

from .jsonio import _load_json, _save_json
from .paths import get_userdata_path
from core.debug_log import get_logger

_logger = get_logger(__name__)

APP_SETTINGS_KEY = "app_settings"

DEFAULT_APP_SETTINGS = {
    "version": 1,
    "ffmpeg": {
        "path": "",
        "use_system_path": True,
    },
    "color_picking": {
        "max_recents": 25,
        "default_format": "rgb",
    },
    "general": {
        "theme": "",
        "allow_internet": False,
        "check_updates_automatically": False,
    },
    "python_libraries": {
        # Recommended: only ever install into the app's own (local) Python
        # environment. Disabling this installs into the base/system Python.
        "local_only": True,
    },
}


def _merge_settings(base, patch):
    """Deep-merge a patch dict over a base dict without mutating either."""
    _logger.debug_info("enter args=%s", ascii({"base": base, "patch": patch}), tier=_logger.DEBUG_LOOP)
    out = dict(base)
    for key, value in (patch or {}).items():
        _logger.debug_info("in for (key, value in (patch or {}).items())", tier=_logger.DEBUG_LOOP)
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            _logger.debug_info("in if (isinstance(value, dict) and isinstance(out.get(key), dict))", tier=_logger.DEBUG_LOOP)
            out[key] = _merge_settings(out[key], value)
        else:
            _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
            out[key] = value
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return out


def load_app_settings():
    """Load the single app-level settings document (settings.json -> 'app_settings').

    Only the app-level key is read, so per-tool UI settings and ``app_theme``
    are left untouched. Stored values are merged over defaults so newly added
    keys always resolve to something sensible.
    """
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    data = _load_json(get_userdata_path(), {})
    stored = data.get(APP_SETTINGS_KEY)
    if not isinstance(stored, dict):
        _logger.debug_info("in if (not isinstance(stored, dict))", tier=_logger.DEBUG_FUNCTION)
        stored = {}
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return _merge_settings(DEFAULT_APP_SETTINGS, stored)


def save_app_settings(settings):
    """Persist the app-level settings document, preserving every other key."""
    _logger.debug_info("enter args=%s", ascii({"settings": settings}), tier=_logger.DEBUG_FUNCTION)
    data = _load_json(get_userdata_path(), {})
    data[APP_SETTINGS_KEY] = settings if isinstance(settings, dict) else {}
    _save_json(get_userdata_path(), data)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
