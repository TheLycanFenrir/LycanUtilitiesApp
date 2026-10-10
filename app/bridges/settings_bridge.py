"""Settings / presets / history, app settings, storage, FFmpeg detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.debug_log import get_logger
from app.settings import (
    load_settings, save_settings, load_presets, save_presets,
    get_history, add_to_history, generate_unique_preset_name,
    load_app_settings, save_app_settings,
    get_storage_stats, clear_all_data, clear_all_presets, clear_all_history,
)
from app.system import detect_ffmpeg_binaries

from .envelope import ResponseStatus

_logger = get_logger(__name__)


if TYPE_CHECKING:
    class BaseApiHost:
        pass
else:
    BaseApiHost = object


class SettingsBridgeMixin(BaseApiHost):
    """Settings surface of the Api bridge."""

    def get_settings(self, tool: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool": tool}), tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "settings": load_settings(tool),
        }

    def save_settings(self, tool: str, settings: dict) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "settings": settings}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            save_settings(settings or {}, tool)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to save settings for '{tool}': {e}", exc_info=True)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def get_presets(self, tool: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool": tool}), tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "presets": load_presets(tool),
        }

    def save_presets(self, tool: str, presets: dict) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "presets": presets}), tier=_logger.DEBUG_FUNCTION)
        save_presets(presets or {}, tool)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
        }

    def delete_preset(self, tool: str, name: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "name": name}), tier=_logger.DEBUG_FUNCTION)
        presets = load_presets(tool)
        if not isinstance(name, str):
            _logger.debug_info("in if (not isinstance(name, str))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "not_found",
                "detail": "Preset does not exist.",
            }
        if name in presets:
            _logger.debug_info("in if (name in presets)", tier=_logger.DEBUG_FUNCTION)
            del presets[name]
            save_presets(presets, tool)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "deleted": name,
            }
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": ResponseStatus.FAILED,
            "code": "not_found",
            "detail": f"Preset '{name}' does not exist.",
        }

    def unique_preset_name(self, tool: str, name: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "name": name}), tier=_logger.DEBUG_FUNCTION)
        presets = load_presets(tool)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "name": generate_unique_preset_name(presets, name),
        }

    def get_history(self, category: str, key: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"category": category, "key": key}), tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "data": list(get_history(category, key)),
        }

    def add_history(self, category: str, key: str, value: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"category": category, "key": key, "value": value}), tier=_logger.DEBUG_FUNCTION)
        add_to_history(category, key, value)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
        }

    def get_app_settings(self) -> dict:
        """Load the single app-level settings document (settings.json -> 'app_settings')."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "settings": load_app_settings(),
        }

    def save_app_settings(self, settings: dict) -> dict:
        """Persist the app-level settings document, preserving all other keys."""
        _logger.debug_info("enter args=%s", ascii({"settings": settings}), tier=_logger.DEBUG_FUNCTION)
        save_app_settings(settings or {})
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
        }

    def get_storage_stats(self) -> dict:
        """Sizes and entry counts for settings/presets/history/favorites/last-used."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return get_storage_stats()

    def clear_all_data(self) -> dict:
        """Delete every persisted user-data JSON file; returns bytes freed per store."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "removed": clear_all_data(),
        }

    def clear_all_presets(self) -> dict:
        """Empty the presets file."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "removed": clear_all_presets(),
        }

    def clear_all_history(self) -> dict:
        """Empty the input-history file."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "removed": clear_all_history(),
        }

    def detect_ffmpeg(self) -> dict:
        """Scan PATH + common install roots for FFmpeg binaries."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return detect_ffmpeg_binaries()
