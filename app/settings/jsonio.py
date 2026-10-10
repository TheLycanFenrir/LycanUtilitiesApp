"""Shared JSON read/write helpers for the settings stores."""

import json
import os
from core.debug_log import get_logger

_logger = get_logger(__name__)


def _load_json(path, default):
    """Load JSON from disk, returning ``default`` if missing or corrupt."""
    _logger.debug_info("enter args=%s", ascii({"path": path, "default": default}), tier=_logger.DEBUG_LOOP)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        with open(path, 'r', encoding='utf-8') as f:
            _logger.debug_info("in with (open(path, 'r', encoding='utf-8') as f)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return json.load(f)
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return default


def _save_json(path, data):
    """Persist JSON data to disk, logging any failure without raising."""
    _logger.debug_info("enter args=%s", ascii({"path": path, "data": data}), tier=_logger.DEBUG_LOOP)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        with open(path, 'w', encoding='utf-8') as f:
            _logger.debug_info("in with (open(path, 'w', encoding='utf-8') as f)", tier=_logger.DEBUG_LOOP)
            json.dump(data, f, indent=4)
    except Exception as e:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        print(f"Failed to save {os.path.basename(path)}: {e}")
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
