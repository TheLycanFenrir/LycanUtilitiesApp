"""Locations of every persisted user-data file under ``userdata/``."""

import os
from core.debug_log import get_logger

_logger = get_logger(__name__)

# Project root: file lives at <root>/app/settings/paths.py, so walk up three
# directories (file -> settings -> app -> root).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_USERDATA_DIR = os.path.join(_PROJECT_ROOT, 'userdata')


def _get_userdata_dir():
    """Get the local user data directory, creating it on first use."""
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    if not os.path.exists(_USERDATA_DIR):
        _logger.debug_info("in if (not os.path.exists(_USERDATA_DIR))", tier=_logger.DEBUG_LOOP)
        os.makedirs(_USERDATA_DIR, exist_ok=True)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return _USERDATA_DIR


def get_userdata_path():
    """Get the path to the userdata folder settings file."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'settings.json')


def get_presets_path():
    """Get the path to the presets JSON file."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'presets.json')


def get_history_path():
    """Get the path to the history JSON file."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'history.json')


def get_favorites_path():
    """Get the path to the favorites JSON file (tool id -> starred)."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'favorites.json')


def get_lastused_path():
    """Get the path to the last-used JSON file (tool id -> unix timestamp)."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'lastused.json')


def get_worker_queue_path():
    """Get the path to the Lycan Worker queue JSON file (unstarted jobs)."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'worker_queue.json')


def get_store_dir():
    """Path to the Lycan Utilities Store data folder."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'lycan_utilities_store')


def get_store_icons_dir():
    """Path to the icons directory inside the Lycan Utilities Store folder."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(get_store_dir(), 'icons')


def get_store_fetchres_path():
    """Path to the store fetch-result file written by the online loader."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(get_store_dir(), 'lycan_utilities_store_fetchres.json')


def get_python_libraries_cache_path():
    """Path to the Settings > Python Libraries snapshot/cache file.

    Holds the last search state (query/page), last index-fetch metadata and
    last utility-dependencies snapshot, so reopening or switching away from
    the category reuses cached data instead of re-fetching from PyPI.
    """
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return os.path.join(_get_userdata_dir(), 'python_libraries_cache.json')
