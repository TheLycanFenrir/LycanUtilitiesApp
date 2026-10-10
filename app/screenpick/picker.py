"""The screen pick itself: hooks, message pump and result handling."""

from __future__ import annotations

import ctypes
import math
import time

from .loupe import _pixel_at, _restore_cursor, _set_crosshair_cursor, _PixelLoupe
from .win32 import (
    HOOKPROC,
    WH_MOUSE_LL,
    WH_KEYBOARD_LL,
    WM_KEYDOWN,
    WM_QUIT,
    VK_ESCAPE,
    PM_REMOVE,
    WM_MOUSEMOVE,
    WM_NCMOUSEMOVE,
    WM_LBUTTONDOWN,
    WM_RBUTTONDOWN,
    WM_NCRBUTTONDOWN,
    _MOUSE_CONSUME_ALL,
    _MSLLHOOKSTRUCT,
    _KBDLLHOOKSTRUCT,
    _MSG,
    _WIN32,
    user32,
)
from core.debug_log import get_logger

_logger = get_logger(__name__)


def wait_for_screen_pick(timeout: float = 8.0) -> dict:
    """Block on the next click anywhere on the desktop.

    While this runs: the system cursor is a global crosshair, a pixel-zoom
    balloon tracks the cursor, and every mouse BUTTON and WHEEL message
    anywhere is consumed so no other program, window, taskbar item or
    Start-menu button can react, scroll, or be dragged.  Mouse movement is
    unaffected.  A left click picks the pixel under the cursor and ends the
    pick; right click or ``Esc`` cancels; a timeout backs out safely.

    Returns ``{"ok": True, "hex": "#rrggbb", "rgb": [...]}`` on a successful
    pick, or ``{"ok": False, "reason": ...}`` for cancel/timeout/failure.
    """
    _logger.debug_info("enter args=%s", ascii({"timeout": timeout}), tier=_logger.DEBUG_FUNCTION)
    if not _WIN32:
        _logger.debug_info("in if (not _WIN32)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "unsupported",
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
    timeout_value = max(0.5, timeout_value)

    state = {"clicked": False, "cancel": False, "x": 0, "y": 0, "grace": 0.0}
    keep_alive = []

    loupe = _PixelLoupe()
    loupe.create()
    saved_cursor = _set_crosshair_cursor()

    @HOOKPROC
    def _mouse_proc(n_code, w_param, l_param):
        _logger.debug_info("wait_for_screen_pick._mouse_proc: enter args=%s", ascii({"n_code": n_code, "w_param": w_param, "l_param": l_param}), tier=_logger.DEBUG_LOOP)
        if n_code >= 0:
            _logger.debug_info("wait_for_screen_pick._mouse_proc: in if (n_code >= 0)", tier=_logger.DEBUG_LOOP)
            if w_param in (WM_MOUSEMOVE, WM_NCMOUSEMOVE):
                # movement passes through, but keep the balloon tracking
                _logger.debug_info("wait_for_screen_pick._mouse_proc: in if (w_param in (WM_MOUSEMOVE, WM_NCMOUSEMOVE))", tier=_logger.DEBUG_LOOP)
                info = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                loupe.place(info.pt.x, info.pt.y)
                _logger.debug_info("wait_for_screen_pick._mouse_proc: exit", tier=_logger.DEBUG_LOOP)
                return user32.CallNextHookEx(keep_alive[0], n_code, w_param, l_param)
            if w_param in _MOUSE_CONSUME_ALL:
                _logger.debug_info("wait_for_screen_pick._mouse_proc: in if (w_param in _MOUSE_CONSUME_ALL)", tier=_logger.DEBUG_LOOP)
                if w_param == WM_LBUTTONDOWN:
                    _logger.debug_info("wait_for_screen_pick._mouse_proc: in if (w_param == WM_LBUTTONDOWN)", tier=_logger.DEBUG_LOOP)
                    info = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                    state["clicked"] = True
                    state["x"] = info.pt.x
                    state["y"] = info.pt.y
                    user32.PostQuitMessage(0)
                elif w_param in (WM_RBUTTONDOWN, WM_NCRBUTTONDOWN):
                    _logger.debug_info("wait_for_screen_pick._mouse_proc: in elif (w_param in (WM_RBUTTONDOWN, WM_NCRBUTTONDOWN))", tier=_logger.DEBUG_LOOP)
                    state["cancel"] = True
                    user32.PostQuitMessage(0)
                # Keep swallowing for a short grace after a resolving click so
                # the trailing mouse-UP is consumed too.
                if state["clicked"] or state["cancel"]:
                    _logger.debug_info("wait_for_screen_pick._mouse_proc: in if (state[\"clicked\"] or state[\"cancel\"])", tier=_logger.DEBUG_LOOP)
                    if state["grace"] < time.monotonic() + 0.15:
                        _logger.debug_info("wait_for_screen_pick._mouse_proc: in if (state[\"grace\"] < time.monotonic() + 0.15)", tier=_logger.DEBUG_LOOP)
                        state["grace"] = time.monotonic() + 0.15
                _logger.debug_info("wait_for_screen_pick._mouse_proc: exit", tier=_logger.DEBUG_LOOP)
                return 1
        _logger.debug_info("wait_for_screen_pick._mouse_proc: exit", tier=_logger.DEBUG_LOOP)
        return user32.CallNextHookEx(keep_alive[0], n_code, w_param, l_param)

    @HOOKPROC
    def _key_proc(n_code, w_param, l_param):
        _logger.debug_info("wait_for_screen_pick._key_proc: enter args=%s", ascii({"n_code": n_code, "w_param": w_param, "l_param": l_param}), tier=_logger.DEBUG_LOOP)
        if n_code >= 0 and w_param == WM_KEYDOWN:
            _logger.debug_info("wait_for_screen_pick._key_proc: in if (n_code >= 0 and w_param == WM_KEYDOWN)", tier=_logger.DEBUG_LOOP)
            info = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if info.vkCode == VK_ESCAPE:
                _logger.debug_info("wait_for_screen_pick._key_proc: in if (info.vkCode == VK_ESCAPE)", tier=_logger.DEBUG_LOOP)
                state["cancel"] = True
                user32.PostQuitMessage(0)
        _logger.debug_info("wait_for_screen_pick._key_proc: exit", tier=_logger.DEBUG_LOOP)
        return user32.CallNextHookEx(keep_alive[1], n_code, w_param, l_param)

    keep_alive[:] = [_mouse_proc, _key_proc]

    mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_proc, None, 0)
    if not mouse_hook:
        _logger.debug_info("in if (not mouse_hook)", tier=_logger.DEBUG_FUNCTION)
        loupe.destroy()
        _restore_cursor(saved_cursor)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "hook_failed",
        }
    key_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _key_proc, None, 0)

    msg = _MSG()
    deadline = time.monotonic() + timeout_value

    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        while True:
            _logger.debug_info("in while (True)", tier=_logger.DEBUG_LOOP)
            now = time.monotonic()
            if state["clicked"] or state["cancel"]:
                _logger.debug_info("in if (state[\"clicked\"] or state[\"cancel\"])", tier=_logger.DEBUG_FUNCTION)
                if now >= state["grace"]:
                    _logger.debug_info("in if (now >= state[\"grace\"])", tier=_logger.DEBUG_FUNCTION)
                    break
            elif now >= deadline:
                _logger.debug_info("in elif (now >= deadline)", tier=_logger.DEBUG_FUNCTION)
                break
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                _logger.debug_info("in while (user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE))", tier=_logger.DEBUG_LOOP)
                if msg.message == WM_QUIT:
                    _logger.debug_info("in if (msg.message == WM_QUIT)", tier=_logger.DEBUG_FUNCTION)
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.005)
    finally:
        _logger.debug_info("in finally", tier=_logger.DEBUG_FUNCTION)
        user32.UnhookWindowsHookEx(mouse_hook)
        if key_hook:
            _logger.debug_info("in if (key_hook)", tier=_logger.DEBUG_FUNCTION)
            user32.UnhookWindowsHookEx(key_hook)
        loupe.destroy()
        _restore_cursor(saved_cursor)

    if state["clicked"]:
        _logger.debug_info("in if (state[\"clicked\"])", tier=_logger.DEBUG_FUNCTION)
        rgb = _pixel_at(state["x"], state["y"])
        if rgb is None:
            _logger.debug_info("in if (rgb is None)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": "read_failed",
            }
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "hex": "#%02x%02x%02x" % (rgb[0], rgb[1], rgb[2]),
            "rgb": rgb,
        }
    if state["cancel"] or msg.message == WM_QUIT:
        _logger.debug_info("in if (state[\"cancel\"] or msg.message == WM_QUIT)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "cancelled",
        }
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return {
        "ok": False,
        "reason": "timeout",
    }
