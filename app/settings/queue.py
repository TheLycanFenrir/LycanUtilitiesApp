"""Lycan Worker queue persistence (pending/running job entries)."""

from .jsonio import _load_json, _save_json
from .paths import get_worker_queue_path
from core.debug_log import get_logger

_logger = get_logger(__name__)


def load_worker_queue():
    """Load the persisted Lycan Worker queue as a list of ``job`` entries."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    data = _load_json(get_worker_queue_path(), {})
    jobs = data.get("jobs") if isinstance(data, dict) else None
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return jobs if isinstance(jobs, list) else []


def save_worker_queue(entries):
    """Persist the pending/running Lycan Worker queue to disk."""
    _logger.debug_info("enter args=%s", ascii({"entries": entries}), tier=_logger.DEBUG_FUNCTION)
    _save_json(get_worker_queue_path(), {"jobs": [e for e in entries or [] if isinstance(e, dict)]})
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
