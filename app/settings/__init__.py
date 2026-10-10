"""Settings, presets, history, and dashboard state management for LycanTools Utilities.

Package facade: the public API of this module is re-exported here so callers
keep using ``from app.settings import ...`` while the implementation lives in
the domain modules next to this file.
"""

from .app_config import (
    APP_SETTINGS_KEY,
    DEFAULT_APP_SETTINGS,
    load_app_settings,
    save_app_settings,
)
from .favorites import is_favorite, load_favorites, toggle_favorite
from .lastused import get_last_used, load_last_used, record_used
from .paths import (
    get_favorites_path,
    get_history_path,
    get_lastused_path,
    get_presets_path,
    get_python_libraries_cache_path,
    get_store_dir,
    get_store_fetchres_path,
    get_store_icons_dir,
    get_userdata_path,
    get_worker_queue_path,
)
from .queue import load_worker_queue, save_worker_queue
from .storage import clear_all_data, clear_all_history, clear_all_presets, get_storage_stats
from .theme import APP_THEME_KEY, DEFAULT_THEME, THEME_MODES, load_app_theme, save_app_theme
from .tool_stores import (
    add_to_history,
    generate_unique_preset_name,
    get_history,
    load_history,
    load_presets,
    load_settings,
    save_history,
    save_presets,
    save_settings,
)

__all__ = [
    "APP_SETTINGS_KEY",
    "APP_THEME_KEY",
    "DEFAULT_APP_SETTINGS",
    "DEFAULT_THEME",
    "THEME_MODES",
    "add_to_history",
    "clear_all_data",
    "clear_all_history",
    "clear_all_presets",
    "generate_unique_preset_name",
    "get_favorites_path",
    "get_history",
    "get_history_path",
    "get_last_used",
    "get_lastused_path",
    "get_presets_path",
    "get_python_libraries_cache_path",
    "get_storage_stats",
    "get_store_dir",
    "get_store_fetchres_path",
    "get_store_icons_dir",
    "get_userdata_path",
    "get_worker_queue_path",
    "is_favorite",
    "load_app_settings",
    "load_app_theme",
    "load_favorites",
    "load_history",
    "load_last_used",
    "load_presets",
    "load_settings",
    "load_worker_queue",
    "record_used",
    "save_app_settings",
    "save_app_theme",
    "save_history",
    "save_presets",
    "save_settings",
    "save_worker_queue",
    "toggle_favorite",
]
