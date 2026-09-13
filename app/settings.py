"""Settings, presets, history, and dashboard state management for LycanTools Utilities."""

import os
import json
import time

_USERDATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'userdata'
)


def _get_userdata_dir():
    """Get the local user data directory, creating it on first use."""
    if not os.path.exists(_USERDATA_DIR):
        os.makedirs(_USERDATA_DIR, exist_ok=True)
    return _USERDATA_DIR


def get_userdata_path():
    """Get the path to the userdata folder settings file."""
    return os.path.join(_get_userdata_dir(), 'settings.json')


def get_presets_path():
    """Get the path to the presets JSON file."""
    return os.path.join(_get_userdata_dir(), 'presets.json')


def get_history_path():
    """Get the path to the history JSON file."""
    return os.path.join(_get_userdata_dir(), 'history.json')


def get_favorites_path():
    """Get the path to the favorites JSON file (tool id -> starred)."""
    return os.path.join(_get_userdata_dir(), 'favorites.json')


def get_lastused_path():
    """Get the path to the last-used JSON file (tool id -> unix timestamp)."""
    return os.path.join(_get_userdata_dir(), 'lastused.json')


def _load_json(path, default):
    """Load JSON from disk, returning ``default`` if missing or corrupt."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    """Persist JSON data to disk, logging any failure without raising."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Failed to save {os.path.basename(path)}: {e}")


def load_favorites():
    """Load the ``{tool_id: bool}`` favorites map from disk."""
    return _load_json(get_favorites_path(), {})


def is_favorite(tool_id):
    """Return True if the given tool is currently starred."""
    return bool(load_favorites().get(tool_id, False))


def toggle_favorite(tool_id):
    """Flip the starred state of a tool, persist it, and return the new state.

    Un-starring removes the entry so the stored map only keeps favorites, in
    the order each one was added (newest last).
    """
    favorites = load_favorites()
    if bool(favorites.get(tool_id, False)):
        favorites.pop(tool_id, None)
        state = False
    else:
        favorites[tool_id] = True
        state = True
    _save_json(get_favorites_path(), favorites)
    return state


def load_last_used():
    """Load the ``{tool_id: unix timestamp}`` map from disk."""
    return _load_json(get_lastused_path(), {})


def get_last_used(tool_id):
    """Return the last-used unix timestamp for a tool, or None."""
    return load_last_used().get(tool_id)


def record_used(tool_id):
    """Stamp a tool as launched right now and persist it for Last Used sorting."""
    last_used = load_last_used()
    last_used[tool_id] = time.time()
    _save_json(get_lastused_path(), last_used)


def save_settings(settings, utility_key):
    """Save UI settings to JSON file for a specific utility."""
    try:
        settings_path = get_userdata_path()
        # Load existing settings
        all_settings = {}
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                all_settings = json.load(f)
        # Update settings for this utility
        all_settings[utility_key] = settings
        # Save back
        with open(settings_path, 'w') as f:
            json.dump(all_settings, f, indent=4)
    except Exception as e:
        print(f"Failed to save settings: {e}")


def load_settings(utility_key):
    """Load UI settings from JSON file for a specific utility."""
    try:
        settings_path = get_userdata_path()
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                all_settings = json.load(f)
                return all_settings.get(utility_key)
    except Exception as e:
        print(f"Failed to load settings: {e}")
    return None


def save_presets(presets, utility_key):
    """Save presets to JSON file for a specific utility."""
    try:
        presets_path = get_presets_path()
        # Load existing presets
        all_presets = {}
        if os.path.exists(presets_path):
            with open(presets_path, 'r') as f:
                all_presets = json.load(f)
        # Update presets for this utility
        all_presets[utility_key] = presets
        # Save back
        with open(presets_path, 'w') as f:
            json.dump(all_presets, f, indent=4)
    except Exception as e:
        print(f"Failed to save presets: {e}")


def load_presets(utility_key):
    """Load presets from JSON file for a specific utility."""
    try:
        presets_path = get_presets_path()
        if os.path.exists(presets_path):
            with open(presets_path, 'r') as f:
                all_presets = json.load(f)
                return all_presets.get(utility_key, {})
    except Exception as e:
        print(f"Failed to load presets: {e}")
    return {}


def get_worker_queue_path():
    """Get the path to the Lycan Worker queue JSON file (unstarted jobs)."""
    return os.path.join(_get_userdata_dir(), 'worker_queue.json')


def load_worker_queue():
    """Load the persisted Lycan Worker queue as a list of ``job`` entries."""
    data = _load_json(get_worker_queue_path(), {})
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return jobs if isinstance(jobs, list) else []


def save_worker_queue(entries):
    """Persist the pending/running Lycan Worker queue to disk."""
    _save_json(get_worker_queue_path(), {"jobs": [e for e in entries or [] if isinstance(e, dict)]})


def load_history():
    """Load history from JSON file."""
    try:
        history_path = get_history_path()
        if os.path.exists(history_path):
            with open(history_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Failed to load history: {e}")
    return {}


def save_history(history):
    """Save history to JSON file."""
    try:
        history_path = get_history_path()
        with open(history_path, 'w') as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"Failed to save history: {e}")


def add_to_history(category: str, key: str, value: str, max_entries: int = 20):
    """Add a value to history with max entries limit."""
    history = load_history()
    
    if category not in history:
        history[category] = {}
    if key not in history[category]:
        history[category][key] = []
    
    # Remove if already exists (move to front)
    if value in history[category][key]:
        history[category][key].remove(value)
    
    # Add to front
    history[category][key].insert(0, value)
    
    # Limit entries
    if len(history[category][key]) > max_entries:
        history[category][key] = history[category][key][:max_entries]
    
    save_history(history)


def get_history(category: str, key: str) -> list:
    """Get history for a specific category and key."""
    history = load_history()
    return history.get(category, {}).get(key, [])


def generate_unique_preset_name(presets, name):
    """Generate a unique preset name with suffix if needed."""
    if not name:
        name = "Unnamed"
    
    if name not in presets:
        return name
    
    suffix = 0
    while f"{name} ({suffix})" in presets:
        suffix += 1
    return f"{name} ({suffix})"


APP_SETTINGS_KEY = "app_settings"

DEFAULT_APP_SETTINGS = {
    "version": 1,
    "ffmpeg": {
        "path": "",
        "use_system_path": True,
    },
    "color_picking": {
        "max_recents": 25,
        "default_format": "rgb",
    },
    "general": {
        "theme": "",
        "allow_internet": False,
        "check_updates_automatically": False,
    },
}


def _merge_settings(base, patch):
    """Deep-merge a patch dict over a base dict without mutating either."""
    out = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_settings(out[key], value)
        else:
            out[key] = value
    return out


def load_app_settings():
    """Load the single app-level settings document (settings.json -> 'app_settings').

    Only the app-level key is read, so per-tool UI settings and ``app_theme``
    are left untouched. Stored values are merged over defaults so newly added
    keys always resolve to something sensible.
    """
    data = _load_json(get_userdata_path(), {})
    stored = data.get(APP_SETTINGS_KEY)
    if not isinstance(stored, dict):
        stored = {}
    return _merge_settings(DEFAULT_APP_SETTINGS, stored)


def save_app_settings(settings):
    """Persist the app-level settings document, preserving every other key."""
    data = _load_json(get_userdata_path(), {})
    data[APP_SETTINGS_KEY] = settings if isinstance(settings, dict) else {}
    _save_json(get_userdata_path(), data)


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def get_storage_stats():
    """Report sizes and entry counts for every persisted user-data store."""
    files = {
        "settings": get_userdata_path(),
        "presets": get_presets_path(),
        "history": get_history_path(),
        "favorites": get_favorites_path(),
        "last_used": get_lastused_path(),
        "worker_queue": get_worker_queue_path(),
    }
    stats = {
        "files": {
            label: {"exists": os.path.exists(path), "bytes": _file_size(path)}
            for label, path in files.items()
        },
        "counts": {},
    }
    presets = _load_json(get_presets_path(), {})
    history = _load_json(get_history_path(), {})
    stats["counts"]["presets_total"] = sum(
        len(values) for values in presets.values() if isinstance(values, dict)
    )
    stats["counts"]["presets_by_tool"] = {
        key: len(values) for key, values in presets.items() if isinstance(values, dict)
    }
    stats["counts"]["history_entries"] = sum(
        len(entries)
        for category in history.values()
        for entries in category.values()
        if isinstance(entries, list)
    )
    stats["counts"]["favorites"] = len(_load_json(get_favorites_path(), {}))
    stats["counts"]["last_used"] = len(_load_json(get_lastused_path(), {}))
    stats["counts"]["worker_queue"] = len(load_worker_queue())
    return stats


def clear_all_data():
    """Delete every persisted user-data JSON file; returns bytes removed per store."""
    removed = {}
    for label, path in (
        ("settings", get_userdata_path()),
        ("presets", get_presets_path()),
        ("history", get_history_path()),
        ("favorites", get_favorites_path()),
        ("last_used", get_lastused_path()),
        ("worker_queue", get_worker_queue_path()),
    ):
        if os.path.exists(path):
            removed[label] = _file_size(path)
            try:
                os.remove(path)
            except OSError:
                pass
    return removed


def clear_all_presets():
    """Empty the presets file and return the freed bytes."""
    removed = _file_size(get_presets_path()) if os.path.exists(get_presets_path()) else 0
    _save_json(get_presets_path(), {})
    return removed


def clear_all_history():
    """Empty the history file and return the freed bytes."""
    removed = _file_size(get_history_path()) if os.path.exists(get_history_path()) else 0
    _save_json(get_history_path(), {})
    return removed


APP_THEME_KEY = "app_theme"
DEFAULT_THEME = "dark"
THEME_MODES = ("dark", "light")


def load_app_theme():
    """Load the saved UI theme (``dark`` or ``light``), defaulting to dark."""
    data = _load_json(get_userdata_path(), {})
    value = data.get(APP_THEME_KEY, DEFAULT_THEME)
    return value if value in THEME_MODES else DEFAULT_THEME


def save_app_theme(mode):
    """Persist the UI theme preference, preserving every other setting."""
    if mode not in THEME_MODES:
        mode = DEFAULT_THEME
    data = _load_json(get_userdata_path(), {})
    data[APP_THEME_KEY] = mode
    _save_json(get_userdata_path(), data)
