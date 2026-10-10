"""Per-utility keyed stores: UI settings, presets and input history.

Each store is a ``{utility_key: ...}`` mapping persisted in its own JSON file
(``settings.json``, ``presets.json``, ``history.json``) so every utility keeps
its saved state isolated from the others.
"""

import json
import os

from .paths import get_history_path, get_presets_path, get_userdata_path
from core.debug_log import get_logger

_logger = get_logger(__name__)


def save_settings(settings, utility_key):
    """Save UI settings to JSON file for a specific utility."""
    _logger.debug_info("enter args=%s", ascii({"settings": settings, "utility_key": utility_key}), tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        settings_path = get_userdata_path()
        # Load existing settings
        all_settings = {}
        if os.path.exists(settings_path):
            _logger.debug_info("in if (os.path.exists(settings_path))", tier=_logger.DEBUG_FUNCTION)
            with open(settings_path, 'r') as f:
                _logger.debug_info("in with (open(settings_path, 'r') as f)", tier=_logger.DEBUG_FUNCTION)
                all_settings = json.load(f)
        # Update settings for this utility
        all_settings[utility_key] = settings
        # Save back
        with open(settings_path, 'w') as f:
            _logger.debug_info("in with (open(settings_path, 'w') as f)", tier=_logger.DEBUG_FUNCTION)
            json.dump(all_settings, f, indent=4)
    except Exception as e:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        print(f"Failed to save settings: {e}")
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)


def load_settings(utility_key):
    """Load UI settings from JSON file for a specific utility."""
    _logger.debug_info("enter args=%s", ascii({"utility_key": utility_key}), tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        settings_path = get_userdata_path()
        if os.path.exists(settings_path):
            _logger.debug_info("in if (os.path.exists(settings_path))", tier=_logger.DEBUG_FUNCTION)
            with open(settings_path, 'r') as f:
                _logger.debug_info("in with (open(settings_path, 'r') as f)", tier=_logger.DEBUG_FUNCTION)
                all_settings = json.load(f)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return all_settings.get(utility_key)
    except Exception as e:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        print(f"Failed to load settings: {e}")
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return None


def save_presets(presets, utility_key):
    """Save presets to JSON file for a specific utility."""
    _logger.debug_info("enter args=%s", ascii({"presets": presets, "utility_key": utility_key}), tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        presets_path = get_presets_path()
        # Load existing presets
        all_presets = {}
        if os.path.exists(presets_path):
            _logger.debug_info("in if (os.path.exists(presets_path))", tier=_logger.DEBUG_FUNCTION)
            with open(presets_path, 'r') as f:
                _logger.debug_info("in with (open(presets_path, 'r') as f)", tier=_logger.DEBUG_FUNCTION)
                all_presets = json.load(f)
        # Update presets for this utility
        all_presets[utility_key] = presets
        # Save back
        with open(presets_path, 'w') as f:
            _logger.debug_info("in with (open(presets_path, 'w') as f)", tier=_logger.DEBUG_FUNCTION)
            json.dump(all_presets, f, indent=4)
    except Exception as e:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        print(f"Failed to save presets: {e}")
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)


def load_presets(utility_key):
    """Load presets from JSON file for a specific utility."""
    _logger.debug_info("enter args=%s", ascii({"utility_key": utility_key}), tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        presets_path = get_presets_path()
        if os.path.exists(presets_path):
            _logger.debug_info("in if (os.path.exists(presets_path))", tier=_logger.DEBUG_FUNCTION)
            with open(presets_path, 'r') as f:
                _logger.debug_info("in with (open(presets_path, 'r') as f)", tier=_logger.DEBUG_FUNCTION)
                all_presets = json.load(f)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return all_presets.get(utility_key, {})
    except Exception as e:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        print(f"Failed to load presets: {e}")
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return {}


def generate_unique_preset_name(presets, name):
    """Generate a unique preset name with suffix if needed."""
    _logger.debug_info("enter args=%s", ascii({"presets": presets, "name": name}), tier=_logger.DEBUG_FUNCTION)
    if not isinstance(presets, dict):
        _logger.debug_info("in if (not isinstance(presets, dict))", tier=_logger.DEBUG_FUNCTION)
        presets = {}
    if not isinstance(name, str):
        _logger.debug_info("in if (not isinstance(name, str))", tier=_logger.DEBUG_FUNCTION)
        name = ""
    if not name:
        _logger.debug_info("in if (not name)", tier=_logger.DEBUG_FUNCTION)
        name = "Unnamed"

    if name not in presets:
        _logger.debug_info("in if (name not in presets)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return name

    suffix = 0
    while f"{name} ({suffix})" in presets:
        _logger.debug_info("in while (f\"{name} ({suffix})\" in presets)", tier=_logger.DEBUG_LOOP)
        suffix += 1
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return f"{name} ({suffix})"


def load_history():
    """Load history from JSON file."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        history_path = get_history_path()
        if os.path.exists(history_path):
            _logger.debug_info("in if (os.path.exists(history_path))", tier=_logger.DEBUG_FUNCTION)
            with open(history_path, 'r') as f:
                _logger.debug_info("in with (open(history_path, 'r') as f)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return json.load(f)
    except Exception as e:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        print(f"Failed to load history: {e}")
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return {}


def save_history(history):
    """Save history to JSON file."""
    _logger.debug_info("enter args=%s", ascii({"history": history}), tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        history_path = get_history_path()
        with open(history_path, 'w') as f:
            _logger.debug_info("in with (open(history_path, 'w') as f)", tier=_logger.DEBUG_FUNCTION)
            json.dump(history, f, indent=4)
    except Exception as e:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        print(f"Failed to save history: {e}")
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)


def add_to_history(category: str, key: str, value: str, max_entries: int = 20):
    """Add a value to history with max entries limit."""
    _logger.debug_info("enter args=%s", ascii({"category": category, "key": key, "value": value, "max_entries": max_entries}), tier=_logger.DEBUG_FUNCTION)
    history = load_history()

    if category not in history:
        _logger.debug_info("in if (category not in history)", tier=_logger.DEBUG_FUNCTION)
        history[category] = {}
    if key not in history[category]:
        _logger.debug_info("in if (key not in history[category])", tier=_logger.DEBUG_FUNCTION)
        history[category][key] = []

    # Remove if already exists (move to front)
    if value in history[category][key]:
        _logger.debug_info("in if (value in history[category][key])", tier=_logger.DEBUG_FUNCTION)
        history[category][key].remove(value)

    # Add to front
    history[category][key].insert(0, value)

    # Limit entries
    if len(history[category][key]) > max_entries:
        _logger.debug_info("in if (len(history[category][key]) > max_entries)", tier=_logger.DEBUG_FUNCTION)
        history[category][key] = history[category][key][:max_entries]

    save_history(history)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)


def get_history(category: str, key: str) -> list:
    """Get history for a specific category and key."""
    _logger.debug_info("enter args=%s", ascii({"category": category, "key": key}), tier=_logger.DEBUG_FUNCTION)
    history = load_history()
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return history.get(category, {}).get(key, [])
