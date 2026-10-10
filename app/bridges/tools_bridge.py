"""Tool cards: favorites, last-used, theme, core options, system stats."""

from __future__ import annotations

import psutil
from typing import Any, TYPE_CHECKING

from core.debug_log import get_logger
from app.settings import (
    record_used,
    toggle_favorite as _toggle_favorite,
    save_app_theme, load_app_theme,
)
from app.system import get_dropdown_core_options, get_cpu_name

from .envelope import ResponseStatus

_logger = get_logger(__name__)

if TYPE_CHECKING:
    class BaseApiHost:
        _process: Any
        _peak_ram: int
else:
    BaseApiHost = object


class ToolsBridgeMixin(BaseApiHost):
    """Tool-card / system surface of the Api bridge."""

    def open_tool(self, tool_id: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(tool_id, str) or not tool_id.strip():
            _logger.debug_info("in if (not isinstance(tool_id, str) or not tool_id.strip())", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_tool",
                "detail": "A valid tool id is required.",
            }
        tool_id = tool_id.strip()
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            record_used(tool_id)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to open tool '{tool_id}': {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def toggle_favorite(self, tool_id: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(tool_id, str) or not tool_id.strip():
            _logger.debug_info("in if (not isinstance(tool_id, str) or not tool_id.strip())", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_tool",
                "detail": "A valid tool id is required.",
            }
        tool_id = tool_id.strip()
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "favorite": _toggle_favorite(tool_id)
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to toggle favorite for '{tool_id}': {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def set_theme(self, mode: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"mode": mode}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            save_app_theme(mode)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "theme": load_app_theme()
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to set theme: {str(e)}")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def _get_core_options(self) -> list[str]:
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return get_dropdown_core_options()
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            _logger.error(f"Failed to get core options: {str(e)}")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return []

    def get_system_stats(self) -> dict:
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            cpu_percent = psutil.cpu_percent(interval=None)
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("Failed to get CPU usage")
            cpu_percent = 0.0

        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            rss = self._process.memory_info().rss
            self._peak_ram = max(self._peak_ram, rss)
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            rss = 0
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            used_pct = mem.percent
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            used_gb = total_gb = used_pct = 0.0
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "cpu_name": get_cpu_name(),
            "cpu_percent": round(float(cpu_percent), 1),
            "app_rss_mb": round(rss / (1024 ** 2), 1),
            "app_peak_mb": round(self._peak_ram / (1024 ** 2), 1),
            "sys_used_gb": round(float(used_gb), 2),
            "sys_total_gb": round(float(total_gb), 2),
            "sys_used_pct": round(float(used_pct), 1),
        }
