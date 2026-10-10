"""Persistent snapshot cache (survives section switches and app restarts)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

from .constants import CACHE_STATE_KEY
from core.debug_log import get_logger

_logger = get_logger(__name__)

_cache_mem: Any = None
_cache_lock = threading.Lock()
_cache_path_set = False
_cache_path_held: Optional[str] = None


def _cache_path() -> str:
    """Path to the Settings > Python Libraries cache/snapshot file."""
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    global _cache_path_set, _cache_path_held
    if not _cache_path_set:
        _logger.debug_info("in if (not _cache_path_set)", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            from app.settings import get_python_libraries_cache_path
            _cache_path_held = get_python_libraries_cache_path()
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            _cache_path_held = None
        _cache_path_set = True
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return _cache_path_held or ""


def _cache_memload() -> Dict[str, Any]:
    """Load the persistent cache document (thread-safe, lazy)."""
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    global _cache_mem
    if _cache_mem is None:
        _logger.debug_info("in if (_cache_mem is None)", tier=_logger.DEBUG_LOOP)
        doc: Dict[str, Any] = {}
        path = _cache_path()
        if path:
            _logger.debug_info("in if (path)", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                with open(path, "r", encoding="utf-8") as fh:
                    _logger.debug_info("in with (open(path, \"r\", encoding=\"utf-8\") as fh)", tier=_logger.DEBUG_LOOP)
                    doc = json.load(fh)
            except Exception:
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
                doc = {}
        _cache_mem = doc if isinstance(doc, dict) else {}
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return _cache_mem


def _cache_save() -> None:
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    path = _cache_path()
    if not path:
        _logger.debug_info("in if (not path)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        with open(path, "w", encoding="utf-8") as fh:
            _logger.debug_info("in with (open(path, \"w\", encoding=\"utf-8\") as fh)", tier=_logger.DEBUG_LOOP)
            json.dump(_cache_mem, fh)
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        pass


def _cache_get(key: str, ttl: float = 0) -> Optional[Any]:
    """Return a cached value if still within ``ttl`` seconds, else None."""
    _logger.debug_info("enter args=%s", ascii({"key": key, "ttl": ttl}), tier=_logger.DEBUG_LOOP)
    if not isinstance(key, str):
        _logger.debug_info("in if (not isinstance(key, str))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    with _cache_lock:
        _logger.debug_info("in with (_cache_lock)", tier=_logger.DEBUG_LOOP)
        entry = _cache_memload().get(key)
    if not isinstance(entry, dict) or "data" not in entry:
        _logger.debug_info("in if (not isinstance(entry, dict) or \"data\" not in entry)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        ts = float(entry.get("ts") or 0)
    except (TypeError, ValueError):
        _logger.debug_info("in except (TypeError, ValueError)", tier=_logger.DEBUG_LOOP)
        ts = 0.0
    if ttl and time.time() - ts > float(ttl):
        _logger.debug_info("in if (ttl and time.time() - ts > float(ttl))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return entry["data"]


def _cache_put(key: str, data: Any, ttl: float = 0) -> None:
    _logger.debug_info("enter args=%s", ascii({"key": key, "data": data, "ttl": ttl}), tier=_logger.DEBUG_LOOP)
    if not isinstance(key, str):
        _logger.debug_info("in if (not isinstance(key, str))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return
    with _cache_lock:
        _logger.debug_info("in with (_cache_lock)", tier=_logger.DEBUG_LOOP)
        _cache_memload()[key] = {"ts": time.time(), "ttl": ttl, "data": data}
        _cache_save()


def _cache_section_state() -> Dict[str, Any]:
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    entry = _cache_get(CACHE_STATE_KEY)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return entry if isinstance(entry, dict) else {}


def section_state() -> Dict[str, Any]:
    """Last-used query/page for the Python Libraries category (for restoring UI)."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    state = _cache_section_state()
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return {
        "query": str(state.get("query") or ""),
        "page": int(state.get("page") or 1),
    }


def _remember_search_state(query: str, page: int) -> None:
    _logger.debug_info("enter args=%s", ascii({"query": query, "page": page}), tier=_logger.DEBUG_LOOP)
    _cache_put(CACHE_STATE_KEY, {"query": query, "page": int(page or 1)})
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
