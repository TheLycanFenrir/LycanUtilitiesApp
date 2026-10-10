"""App identity, dashboard, window lifecycle and external links."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from typing import Any, Callable, TYPE_CHECKING

from core.debug_log import get_logger
from core.scanner import descriptor as _util_descriptor
from app.info import APP_TITLE, APP_SUBTITLE, MAIN_CONTRIBUTOR, VERSION, HOME_VIEW_ID, GITHUB_REPOSITORY_URL
from app.settings import load_app_theme, load_favorites, load_last_used
from app.updates import check_for_updates as run_update_check

from .envelope import ResponseStatus

_logger = get_logger(__name__)

if TYPE_CHECKING:
    class BaseApiHost:
        _window: Callable[[], Any]
        _utilities: dict[str, dict]
        _broken_descriptors: Callable[[], list[dict]]
        get_system_stats: Callable[[], dict]
else:
    BaseApiHost = object


class AppBridgeMixin(BaseApiHost):
    """App / dashboard surface of the Api bridge."""

    def _get_app(self) -> dict:
        """Internal app identity payload (nested under ``app`` by get_dashboard)."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "title": APP_TITLE,
            "subtitle": APP_SUBTITLE,
            "version": VERSION,
            "contributor": MAIN_CONTRIBUTOR,
            "github_url": GITHUB_REPOSITORY_URL,
            "home_view": HOME_VIEW_ID,
        }

    def open_external_link(self, url: str) -> dict:
        """Open a URL in the user's default system browser.

        Never navigates the internal PyWebView window; the frontend must route
        all external links through this bridge method.
        """
        _logger.debug_info("enter args=%s", ascii({"url": url}), tier=_logger.DEBUG_FUNCTION)
        clean_url = str(url or "").strip()

        if not clean_url.startswith(("http://", "https://")):
            _logger.debug_info("in if (not clean_url.startswith((\"http://\", \"https://\")))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_url",
                "detail": "URL must start with http:// or https://",
            }
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            webbrowser.open(clean_url, new=2)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Cannot open external URL link '{clean_url}': {e}", exc_info=True)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def quit_app(self) -> dict:
        """Close the native window. Runs in the UI thread."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            window = self._window()
            if window is None:
                _logger.debug_info("in if (window is None)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "no_window",
                    "detail": "No native window is available.",
                }
            window.destroy()
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to quit app, please end task this app to force quit: {e}", exc_info=True)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def restart_app(self) -> dict:
        """Close the window and relaunch a completely fresh app instance.

        A detached copy of the entry point is spawned first, then this window
        is destroyed, so the new process boots a clean WebView / JS context.
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            window = self._window()
            if window is None:
                _logger.debug_info("in if (window is None)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "no_window",
                    "detail": "No native window is available.",
                }

            # project root = parent of app/bridges/ (this file: app/bridges/app_bridge.py)
            root = str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            executable = sys.executable

            # Handle frozen (py2app, py2exe, etc.)
            if not getattr(sys, "frozen", False):
                _logger.debug_info("in if (not getattr(sys, \"frozen\", False))", tier=_logger.DEBUG_FUNCTION)
                if sys.platform.startswith("win"):
                    _logger.debug_info("in if (sys.platform.startswith(\"win\"))", tier=_logger.DEBUG_FUNCTION)
                    pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
                    if os.path.exists(pythonw):
                        _logger.debug_info("in if (os.path.exists(pythonw))", tier=_logger.DEBUG_FUNCTION)
                        executable = pythonw
                command = [executable, os.path.join(root, "main.py")]
            else:
                _logger.debug_info("in else", tier=_logger.DEBUG_FUNCTION)
                command = [executable]

            # Platform-specific flags
            popen_kwargs: dict = {
                "cwd": root,
                "close_fds": True,
            }

            # Check if it's windows and set the creation flags
            if sys.platform.startswith("win"):
                _logger.debug_info("in if (sys.platform.startswith(\"win\"))", tier=_logger.DEBUG_FUNCTION)
                popen_kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
            else:
                # Process isolation for other platforms (e.g. Linux, MacOS)
                _logger.debug_info("in else", tier=_logger.DEBUG_FUNCTION)
                popen_kwargs["start_new_session"] = True

            # Spawn a detached process
            subprocess.Popen(
                command,
                **popen_kwargs
            )

            # Close the old window
            window.destroy()
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to restart app: {e}", exc_info=True)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def check_for_updates(self) -> dict:
        """Check the GitHub release feed for a newer version."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return run_update_check()
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to retrieve updates: {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def open_devtools(self) -> dict:
        """Open the native developer tools / web inspector window.

        PyWebView exposes ``show_devtools()`` on its WebView2 (Edge
        Chromium) windows; older backends fall back to an unsupported
        result so the frontend can show a graceful message.
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            window = self._window()
            if window is None:
                _logger.debug_info("in if (window is None)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "no_window",
                    "detail": "No native window is available.",
                }

            if hasattr(window, "show_devtools") and callable(window.show_devtools):
                _logger.debug_info("in if (hasattr(window, \"show_devtools\") and callable(window.show_devtools))", tier=_logger.DEBUG_FUNCTION)
                window.show_devtools()
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": True,
                    "reason": ResponseStatus.SUCCESS
                }

            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "unsupported",
                "detail": "Developer tools are not supported on this window.",
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to open devtools: {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def _get_tools(self) -> list[dict]:
        """Internal tool hub: every validated utility from utilities/."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return self._util_descriptors()

    def _util_descriptors(self) -> list[dict]:
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return [_util_descriptor(entry) for entry in self._utilities.values()]

    def get_dashboard(self) -> dict:
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            favorites = load_favorites()
            last_used = load_last_used()
            tools = []

            for desc in self._util_descriptors():
                _logger.debug_info("in for (desc in self._util_descriptors())", tier=_logger.DEBUG_LOOP)
                mid = desc.get("id")
                item = dict(desc)
                item["favorite"] = bool(favorites.get(mid, False))
                item["last_used"] = last_used.get(mid)
                item["coming_soon"] = not bool(desc.get("has_runtime"))
                tools.append(item)

            tools.extend(self._broken_descriptors())
            system = self.get_system_stats()

            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "tools": tools,
                "theme": load_app_theme(),
                "app": self._get_app(),
                "cpu_name": system.get("cpu_name", "Unknown CPU")
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            _logger.error(f"Failed to retrieve dashboard data: {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }
