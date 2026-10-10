"""Storage statistics and destructive clears for every user-data store."""

import os
from typing import Any, Dict

from .jsonio import _load_json, _save_json
from .paths import (
    get_favorites_path,
    get_history_path,
    get_lastused_path,
    get_presets_path,
    get_python_libraries_cache_path,
    get_store_fetchres_path,
    get_userdata_path,
    get_worker_queue_path,
)
from .queue import load_worker_queue
from core.debug_log import get_logger

_logger = get_logger(__name__)


def _file_size(path):
    _logger.debug_info("enter args=%s", ascii({"path": path}), tier=_logger.DEBUG_LOOP)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return os.path.getsize(path)
    except OSError:
        _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return 0


def get_storage_stats():
    """Report sizes and entry counts for every persisted user-data store."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    files = {
        "settings": get_userdata_path(),
        "presets": get_presets_path(),
        "history": get_history_path(),
        "favorites": get_favorites_path(),
        "last_used": get_lastused_path(),
        "worker_queue": get_worker_queue_path(),
        "store": get_store_fetchres_path(),
        "python_libraries_cache": get_python_libraries_cache_path(),
    }
    stats: Dict[str, Any] = {
        "files": {
            label: {"exists": os.path.exists(path), "bytes": _file_size(path)}
            for label, path in files.items()
        },
        "counts": {},
    }
    counts: Dict[str, Any] = stats["counts"]
    presets = _load_json(get_presets_path(), {})
    history = _load_json(get_history_path(), {})
    counts["presets_total"] = sum(
        len(values) for values in presets.values() if isinstance(values, dict)
    )
    counts["presets_by_tool"] = {
        key: len(values) for key, values in presets.items() if isinstance(values, dict)
    }
    counts["history_entries"] = sum(
        len(entries)
        for category in history.values()
        for entries in category.values()
        if isinstance(entries, list)
    )
    counts["favorites"] = len(_load_json(get_favorites_path(), {}))
    counts["last_used"] = len(_load_json(get_lastused_path(), {}))
    counts["worker_queue"] = len(load_worker_queue())
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return stats


def clear_all_data():
    """Delete every persisted user-data JSON file; returns bytes removed per store."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    removed = {}
    for label, path in (
        ("settings", get_userdata_path()),
        ("presets", get_presets_path()),
        ("history", get_history_path()),
        ("favorites", get_favorites_path()),
        ("last_used", get_lastused_path()),
        ("worker_queue", get_worker_queue_path()),
        ("store", get_store_fetchres_path()),
        ("python_libraries_cache", get_python_libraries_cache_path()),
    ):
        _logger.debug_info("in for (label, path in (\n        (\"settings\", get_userdata_path()),\n        (\"presets\", get_presets_path()),\n        (\"history\", get_history_path()),\n        (\"favorites\", get_favorites_path()),\n        (\"last_used\", get_lastused_path()),\n        (\"worker_queue\", get_worker_queue_path()),\n        (\"store\", get_store_fetchres_path()),\n        (\"python_libraries_cache\", get_python_libraries_cache_path()),\n    ))", tier=_logger.DEBUG_LOOP)
        if os.path.exists(path):
            _logger.debug_info("in if (os.path.exists(path))", tier=_logger.DEBUG_FUNCTION)
            removed[label] = _file_size(path)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
                os.remove(path)
            except OSError:
                _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_FUNCTION)
                pass
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return removed


def clear_all_presets():
    """Empty the presets file and return the freed bytes."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    removed = _file_size(get_presets_path()) if os.path.exists(get_presets_path()) else 0
    _save_json(get_presets_path(), {})
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return removed


def clear_all_history():
    """Empty the history file and return the freed bytes."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    removed = _file_size(get_history_path()) if os.path.exists(get_history_path()) else 0
    _save_json(get_history_path(), {})
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return removed
