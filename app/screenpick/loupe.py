"""Pixel-zoom balloon window plus cursor and pixel-sampling helpers."""

from __future__ import annotations

import ctypes

from .win32 import (
    CLR_INVALID,
    CROSS_SRC,
    CROSS_ZOOM,
    IDC_ARROW,
    IDC_CROSS,
    LOUPE_H,
    LOUPE_OFFSET,
    LOUPE_READOUT_H,
    LOUPE_W,
    OCR_NORMAL,
    OPAQUE,
    SPI_SETCURSORS,
    SRCCOPY,
    SWP_NOACTIVATE,
    SWP_NOSIZE,
    WM_ERASEBKGND,
    WM_NCHITTEST,
    WM_PAINT,
    WNDPROC,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    WS_POPUP,
    WS_VISIBLE,
    HWND_TOPMOST,
    _WIN32,
    _PAINTSTRUCT,
    _RECT,
    _WNDCLASS,
    gdi32,
    user32,
    wintypes,
)
from core.debug_log import get_logger

_logger = get_logger(__name__)


def _pixel_at(x: int, y: int):
    """Return [r, g, b] for the desktop pixel at device (x, y), or None."""
    _logger.debug_info("enter args=%s", ascii({"x": x, "y": y}), tier=_logger.DEBUG_LOOP)
    hdc = user32.GetDC(None)
    if not hdc:
        _logger.debug_info("in if (not hdc)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        color = gdi32.GetPixel(hdc, int(x), int(y))
    finally:
        _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
        user32.ReleaseDC(None, hdc)
    if color is None or color == CLR_INVALID:
        _logger.debug_info("in if (color is None or color == CLR_INVALID)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return [color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF]


def _set_crosshair_cursor():
    """Swap the system normal cursor to a crosshair for the whole desktop.

    Returns the saved arrow icon (restore with :func:`_restore_cursor`).  The
    crosshair is applied system-wide via SetSystemCursor so every window sees
    it while the pick is active.
    """
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    arrow = user32.CopyIcon(user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW)))
    cross = user32.CopyIcon(user32.LoadCursorW(None, ctypes.c_void_p(IDC_CROSS)))
    if cross:
        _logger.debug_info("in if (cross)", tier=_logger.DEBUG_LOOP)
        user32.SetSystemCursor(cross, OCR_NORMAL)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return arrow


def _restore_cursor(saved_arrow) -> None:
    # SetSystemCursor cannot undo a prior swap; SPI_SETCURSORS reloads every
    # system cursor slot from the scheme, returning the arrow.
    _logger.debug_info("enter args=%s", ascii({"saved_arrow": saved_arrow}), tier=_logger.DEBUG_LOOP)
    if saved_arrow:
        _logger.debug_info("in if (saved_arrow)", tier=_logger.DEBUG_LOOP)
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)


class _PixelLoupe:
    """A topmost GDI popup that magnifies the pixels under the cursor and
    shows the live color.  It is created on the picking thread (which pumps
    messages) and repositioned on every mouse move seen by the hook."""

    _registered_classes = set()
    _counter = 0

    def __init__(self):
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        self.hwnd = None
        self.x = 0
        self.y = 0
        self.rgb = (0, 0, 0)
        self._font = None
        self._wndproc = WNDPROC(self._proc)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _class_name(self):
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        _PixelLoupe._counter += 1
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return "PixelLoupe_%d_%d" % (abs(id(self)), _PixelLoupe._counter)

    def create(self) -> None:
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        if not _WIN32 or not user32:
            _logger.debug_info("in if (not _WIN32 or not user32)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return
        cls = self._class_name()
        if cls not in _PixelLoupe._registered_classes:
            _logger.debug_info("in if (cls not in _PixelLoupe._registered_classes)", tier=_logger.DEBUG_LOOP)
            wc = _WNDCLASS()
            wc.lpfnWndProc = self._wndproc
            wc.lpszClassName = cls
            if user32.RegisterClassW(ctypes.byref(wc)):
                _logger.debug_info("in if (user32.RegisterClassW(ctypes.byref(wc)))", tier=_logger.DEBUG_LOOP)
                _PixelLoupe._registered_classes.add(cls)
        self.hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            cls, "", WS_POPUP | WS_VISIBLE,
            0, 0, LOUPE_W, LOUPE_H, None, None, None, None)
        if not self.hwnd:
            _logger.debug_info("in if (not self.hwnd)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return
        pt = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            _logger.debug_info("in if (user32.GetCursorPos(ctypes.byref(pt)))", tier=_logger.DEBUG_LOOP)
            self.place(pt.x, pt.y)

    def destroy(self) -> None:
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        if self.hwnd:
            _logger.debug_info("in if (self.hwnd)", tier=_logger.DEBUG_LOOP)
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self._font:
            _logger.debug_info("in if (self._font)", tier=_logger.DEBUG_LOOP)
            gdi32.DeleteObject(self._font)
            self._font = None
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def place(self, x: int, y: int) -> None:
        """Move the balloon next to the cursor and refresh the live color."""
        _logger.debug_info("enter args=%s", ascii({"x": x, "y": y}), tier=_logger.DEBUG_LOOP)
        self.x, self.y = int(x), int(y)
        rgb = _pixel_at(self.x, self.y)
        if rgb:
            _logger.debug_info("in if (rgb)", tier=_logger.DEBUG_LOOP)
            self.rgb = tuple(rgb)
        # clamp so the balloon stays on the virtual screen
        vx = user32.GetSystemMetrics(76)
        vy = user32.GetSystemMetrics(77)
        vw = user32.GetSystemMetrics(78)
        vh = user32.GetSystemMetrics(79)
        bx = self.x + LOUPE_OFFSET
        by = self.y + LOUPE_OFFSET
        if vw > 0:
            _logger.debug_info("in if (vw > 0)", tier=_logger.DEBUG_LOOP)
            bx = max(vx, min(bx, vx + vw - LOUPE_W))
        if vh > 0:
            _logger.debug_info("in if (vh > 0)", tier=_logger.DEBUG_LOOP)
            by = max(vy, min(by, vy + vh - LOUPE_H))
        if self.hwnd:
            _logger.debug_info("in if (self.hwnd)", tier=_logger.DEBUG_LOOP)
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, bx, by, 0, 0,
                                SWP_NOSIZE | SWP_NOACTIVATE)
            user32.InvalidateRect(self.hwnd, None, True)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _proc(self, hwnd, msg, wparam, lparam):
        _logger.debug_info("enter args=%s", ascii({"hwnd": hwnd, "msg": msg, "wparam": wparam, "lparam": lparam}), tier=_logger.DEBUG_LOOP)
        if msg == WM_PAINT:
            _logger.debug_info("in if (msg == WM_PAINT)", tier=_logger.DEBUG_LOOP)
            self._paint(hwnd)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return 0
        if msg == WM_ERASEBKGND:
            _logger.debug_info("in if (msg == WM_ERASEBKGND)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return 1
        if msg == WM_NCHITTEST:
            _logger.debug_info("in if (msg == WM_NCHITTEST)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return -1  # HTTRANSPARENT: never intercept input
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _paint(self, hwnd) -> None:
        _logger.debug_info("enter args=%s", ascii({"hwnd": hwnd}), tier=_logger.DEBUG_LOOP)
        ps = _PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            # 1px black border, white interior
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            black = gdi32.CreateSolidBrush(0x00000000)
            rect = _RECT(0, 0, LOUPE_W, LOUPE_H)
            user32.FillRect(hdc, ctypes.byref(rect), black)
            gdi32.DeleteObject(black)
            white = gdi32.CreateSolidBrush(0x00FFFFFF)
            inner = _RECT(1, 1, LOUPE_W - 1, LOUPE_H - 1)
            user32.FillRect(hdc, ctypes.byref(inner), white)
            gdi32.DeleteObject(white)

            # color readout: swatch + live hex
            r, g, b = self.rgb if self.rgb else (0, 0, 0)
            chip = _RECT(8, 8, 38, 27)
            brush = gdi32.CreateSolidBrush((b << 16) | (g << 8) | r)
            user32.FillRect(hdc, ctypes.byref(chip), brush)
            gdi32.DeleteObject(brush)
            if not self._font:
                _logger.debug_info("in if (not self._font)", tier=_logger.DEBUG_LOOP)
                self._font = gdi32.CreateFontW(
                    -16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Consolas")
            if self._font:
                _logger.debug_info("in if (self._font)", tier=_logger.DEBUG_LOOP)
                gdi32.SelectObject(hdc, self._font)
            gdi32.SetBkMode(hdc, OPAQUE)
            gdi32.SetTextColor(hdc, 0x00000000)
            gdi32.TextOutW(hdc, 44, 9, "#%02x%02x%02x" % (r, g, b), 7)

            # pixel zoom: source box around the cursor -> magnified area
            zoom_w = CROSS_SRC * CROSS_ZOOM
            srcdc = user32.GetDC(None)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                half = CROSS_SRC // 2
                sx = self.x - half
                sy = self.y - half
                if srcdc:
                    _logger.debug_info("in if (srcdc)", tier=_logger.DEBUG_LOOP)
                    gdi32.StretchBlt(hdc, 5, LOUPE_READOUT_H, zoom_w, zoom_w,
                                     srcdc, sx, sy, CROSS_SRC, CROSS_SRC, SRCCOPY)
            finally:
                _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
                if srcdc:
                    _logger.debug_info("in if (srcdc)", tier=_logger.DEBUG_LOOP)
                    user32.ReleaseDC(None, srcdc)

            # crosshair lines through the center of the zoom box
            cx = 5 + zoom_w // 2
            cy = LOUPE_READOUT_H + zoom_w // 2
            gdi32.MoveToEx(hdc, 5, cy, ctypes.byref(wintypes.POINT(0, 0)))
            gdi32.LineTo(hdc, 5 + zoom_w, cy)
            gdi32.MoveToEx(hdc, cx, LOUPE_READOUT_H, ctypes.byref(wintypes.POINT(0, 0)))
            gdi32.LineTo(hdc, cx, LOUPE_READOUT_H + zoom_w)
        finally:
            _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
            user32.EndPaint(hwnd, ctypes.byref(ps))
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
