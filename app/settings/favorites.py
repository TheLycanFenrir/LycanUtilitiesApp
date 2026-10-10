"""Dashboard favorites: which tools are starred."""

from .jsonio import _load_json, _save_json
from .paths import get_favorites_path
from core.debug_log import get_logger

_logger = get_logger(__name__)


def load_favorites():
    """Load the ``{tool_id: bool}`` favorites map from disk."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return _load_json(get_favorites_path(), {})


def is_favorite(tool_id):
    """Return True if the given tool is currently starred."""
    _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id}), tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return bool(load_favorites().get(tool_id, False))


def toggle_favorite(tool_id):
    """Flip the starred state of a tool, persist it, and return the new state.

    Un-starring removes the entry so the stored map only keeps favorites, in
    the order each one was added (newest last).
    """
    _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id}), tier=_logger.DEBUG_FUNCTION)
    favorites = load_favorites()
    if bool(favorites.get(tool_id, False)):
        _logger.debug_info("in if (bool(favorites.get(tool_id, False)))", tier=_logger.DEBUG_FUNCTION)
        favorites.pop(tool_id, None)
        state = False
    else:
        _logger.debug_info("in else", tier=_logger.DEBUG_FUNCTION)
        favorites[tool_id] = True
        state = True
    _save_json(get_favorites_path(), favorites)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return state
