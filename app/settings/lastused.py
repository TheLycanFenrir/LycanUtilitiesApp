"""Dashboard "Last Used" stamps: tool id -> launch timestamp."""

import time

from .jsonio import _load_json, _save_json
from .paths import get_lastused_path
from core.debug_log import get_logger

_logger = get_logger(__name__)


def load_last_used():
    """Load the ``{tool_id: unix timestamp}`` map from disk."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return _load_json(get_lastused_path(), {})


def get_last_used(tool_id):
    """Return the last-used unix timestamp for a tool, or None."""
    _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id}), tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return load_last_used().get(tool_id)


def record_used(tool_id):
    """Stamp a tool as launched right now and persist it for Last Used sorting."""
    _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id}), tier=_logger.DEBUG_FUNCTION)
    last_used = load_last_used()
    last_used[tool_id] = time.time()
    _save_json(get_lastused_path(), last_used)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
