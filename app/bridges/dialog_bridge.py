"""Native file/folder/save dialogs and desktop color picking."""

from __future__ import annotations

import math

import webview
from typing import Any, Callable, Optional, TYPE_CHECKING

from .envelope import ResponseStatus
from core.debug_log import get_logger

_logger = get_logger(__name__)

_IMAGE_FILE_TYPES = ("Images (*.png;*.jpg;*.jpeg;*.webp;*.tga;*.tiff;*.bmp)",)
_ALL_FILE_TYPES = ("All files (*.*)",)

if TYPE_CHECKING:
    class BaseApiHost:
        _window: Callable[[], Any]
else:
    BaseApiHost = object


class DialogBridgeMixin(BaseApiHost):
    """Native dialog surface of the Api bridge."""

    def open_dialog(self, kind: str = "file", initial_directory: str = "",
                    save_filename: str = "", allow_multiple: bool = False,
                    file_types: Optional[list] = None) -> dict:
        """Open a native open/folder/save dialog.

        Returns the standard envelope with a ``paths`` list:
        ``{"ok": True, "paths": [...]}``. Closing the dialog without picking
        anything reports ``reason: "cancelled"`` with an empty ``paths`` list.

        ``initial_directory`` is sourced directly from the active UI field
        (smart browse memory): the picker starts inside the directory the
        field already points at, or falls back to the OS default when empty.
        """
        _logger.debug_info("enter args=%s", ascii({"kind": kind, "initial_directory": initial_directory, "save_filename": save_filename, "allow_multiple": allow_multiple, "file_types": file_types}), tier=_logger.DEBUG_FUNCTION)
        window = self._window()

        if window is None:
            _logger.debug_info("in if (window is None)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "no_window",
                "detail": "No native window is available for a dialog.",
            }
        kind = str(kind or "file").lower()
        dialog_type = {
            "file": webview.FileDialog.OPEN,
            "folder": webview.FileDialog.FOLDER,
            "save": webview.FileDialog.SAVE,
        }.get(kind, webview.FileDialog.OPEN)

        if isinstance(file_types, (list, tuple)) and file_types:
            _logger.debug_info("in if (isinstance(file_types, (list, tuple)) and file_types)", tier=_logger.DEBUG_FUNCTION)
            types = tuple(str(item) for item in file_types)
        else:
            _logger.debug_info("in else", tier=_logger.DEBUG_FUNCTION)
            types = _ALL_FILE_TYPES if kind == "file" else tuple()
        result = window.create_file_dialog(
            dialog_type=dialog_type,
            directory=str(initial_directory or ""),
            allow_multiple=bool(allow_multiple) and kind == "file",
            save_filename=str(save_filename or ""),
            file_types=types,
        )
        if result is None:
            _logger.debug_info("in if (result is None)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.INFO,
                "code": "cancelled",
                "detail": "Dialog closed without a selection.",
                "paths": []
            }
        if isinstance(result, str):
            _logger.debug_info("in if (isinstance(result, str))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "paths": [result]
            }
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "paths": list(result)
        }

    def screen_pick(self, timeout: float = 8.0) -> dict:
        """Pick a pixel color from anywhere on the desktop.

        A low-level mouse hook watches for a left click anywhere on any
        monitor (even while another app is foreground) and returns the exact
        pixel under the cursor. Right-click or ``Esc`` cancels without picking.

        While the pick is in progress the hook *consumes* every mouse message
        on the whole desktop (buttons, wheel, movement — client and
        non-client), so nothing can react: no accidental app launch, no
        taskbar / Start-menu trigger, no context menu, and the host app itself
        stays inert. The moment the pick resolves the hook is removed and the
        desktop is fully interactive again. The window itself is never
        touched: hiding or re-laying-out the host window during a pick is what
        made the app appear to close, and the global hook needs no window help.
        """
        _logger.debug_info("enter args=%s", ascii({"timeout": timeout}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            from app.screenpick import wait_for_screen_pick
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "unsupported",
                "detail": "Screen picking is not available in this build.",
            }
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            timeout_value = float(timeout)
        except (TypeError, ValueError):
            _logger.debug_info("in except (TypeError, ValueError)", tier=_logger.DEBUG_FUNCTION)
            timeout_value = 8.0
        if not math.isfinite(timeout_value) or timeout_value <= 0:
            _logger.debug_info("in if (not math.isfinite(timeout_value) or timeout_value <= 0)", tier=_logger.DEBUG_FUNCTION)
            timeout_value = 8.0
        timeout_value = min(timeout_value, 60.0)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return wait_for_screen_pick(timeout_value)
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "failed",
                "detail": "Screen picking failed.",
            }
