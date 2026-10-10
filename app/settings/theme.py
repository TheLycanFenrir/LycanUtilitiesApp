"""UI theme preference (stored alongside the other settings.json keys)."""

from .jsonio import _load_json, _save_json
from .paths import get_userdata_path
from core.debug_log import get_logger

_logger = get_logger(__name__)

APP_THEME_KEY = "app_theme"
DEFAULT_THEME = "dark"
THEME_MODES = ("dark", "light")


def load_app_theme():
    """Load the saved UI theme (``dark`` or ``light``), defaulting to dark."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    data = _load_json(get_userdata_path(), {})
    value = data.get(APP_THEME_KEY, DEFAULT_THEME)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return value if value in THEME_MODES else DEFAULT_THEME


def save_app_theme(mode):
    """Persist the UI theme preference, preserving every other setting."""
    _logger.debug_info("enter args=%s", ascii({"mode": mode}), tier=_logger.DEBUG_FUNCTION)
    if mode not in THEME_MODES:
        _logger.debug_info("in if (mode not in THEME_MODES)", tier=_logger.DEBUG_FUNCTION)
        mode = DEFAULT_THEME
    data = _load_json(get_userdata_path(), {})
    data[APP_THEME_KEY] = mode
    _save_json(get_userdata_path(), data)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
