"""Small shared helpers: name normalization, settings gates, search engine."""

from __future__ import annotations

import re
from typing import Any

from app.settings import load_app_settings
from core.debug_log import get_logger

_logger = get_logger(__name__)

_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")

_search_tool: Any = None          # lazy import of pypi_search_caching


def normalize_name(name: str) -> str:
    """PEP 503-ish canonical form: lowercase, ``_``/``.`` become ``-``."""
    _logger.debug_info("enter args=%s", ascii({"name": name}), tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return re.sub(r"[-_.]+", "-", str(name or "").strip().lower())


def internet_enabled() -> bool:
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        general = (load_app_settings().get("general") or {})
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return bool(general.get("allow_internet", False))
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return False


def local_only_scope() -> bool:
    """The persisted scope preference (True = install only into the app env)."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        python_libraries = (load_app_settings().get("python_libraries") or {})
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return bool(python_libraries.get("local_only", True))
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return True


def _tool():
    """Lazily import the ``pypi-search-caching`` search engine. None when absent."""
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    global _search_tool
    if _search_tool is None:
        _logger.debug_info("in if (_search_tool is None)", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            import pypi_search_caching as mod
            _search_tool = mod
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            _search_tool = False
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return _search_tool or None
