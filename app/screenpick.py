"""OS-level screen color picker.

Lets the user click anywhere on the desktop (even outside the app window) and
returns the exact pixel color under the cursor.  Windows-only: relies on a
low-level ``WH_MOUSE_LL`` hook plus a ``GetPixel`` read from the screen DC.

The bridge method ``api.screen_pick(timeout)`` keeps the app visible for the
duration of the pick so the user can click freely on any monitor.

While the pick is active:

* The system cursor is swapped to a **crosshair for the whole desktop**, and
  restored the moment the pick ends.
* A **pixel-zoom balloon** (a topmost popup) follows the cursor and shows a
  10x magnified view of the pixels under it plus the live ``#rrggbb`` color,
  updated on every mouse move.
* Every mouse button and wheel message anywhere is *consumed* by the hook
  (returns 1), client and non-client alike: nothing can be clicked, dragged
  or scrolled on screen — no accidental app launch, no window action, no
  context menu.  Mouse *movement* passes through so the cursor can aim.

A left click finishes the pick and samples that pixel, right click or ``Esc``
cancels.  A short grace period keeps the hook armed after the resolving click
so the trailing mouse-up is swallowed too and cannot trigger anything.
"""

from __future__ import annotations

import time

try:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    _WIN32 = True
except Exception:  # pragma: no cover - non-Windows runner
    user32 = None
    gdi32 = None
    _WIN32 = False

# Hook / message constants
WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_QUIT = 0x0012
VK_ESCAPE = 0x1B
CLR_INVALID = 0xFFFFFFFF
PM_REMOVE = 0x0001

# Client-area mouse messages
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_RBUTTONDBLCLK = 0x0206
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MBUTTONDBLCLK = 0x0209
WM_MOUSEWHEEL = 0x020A
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_XBUTTONDBLCLK = 0x020D
WM_MOUSEHWHEEL = 0x020E

# Non-client-area mouse messages (title bar, menu buttons, etc.)
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_NCRBUTTONDOWN = 0x00A4
WM_NCRBUTTONUP = 0x00A5
WM_NCRBUTTONDBLCLK = 0x00A6
WM_NCMBUTTONDOWN = 0x00A7
WM_NCMBUTTONUP = 0x00A8
WM_NCMBUTTONDBLCLK = 0x00A9
WM_NCXBUTTONDOWN = 0x00AB
WM_NCXBUTTONUP = 0x00AC
WM_NCXBUTTONDBLCLK = 0x00AD

# Every mouse CLICK / WHEEL message the hook may deliver, both client and
# non-client.  Mouse movement (WM_MOUSEMOVE / WM_NCMOUSEMOVE) is deliberately
# NOT in this set — the cursor must stay free to aim the picker.
_MOUSE_CONSUME_ALL = frozenset({
    WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK,
    WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK,
    WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK,
    WM_MOUSEWHEEL, WM_MOUSEHWHEEL,
    WM_XBUTTONDOWN, WM_XBUTTONUP, WM_XBUTTONDBLCLK,
    WM_NCLBUTTONDOWN, WM_NCLBUTTONUP, WM_NCLBUTTONDBLCLK,
    WM_NCRBUTTONDOWN, WM_NCRBUTTONUP, WM_NCRBUTTONDBLCLK,
    WM_NCMBUTTONDOWN, WM_NCMBUTTONUP, WM_NCMBUTTONDBLCLK,
    WM_NCXBUTTONDOWN, WM_NCXBUTTONUP, WM_NCXBUTTONDBLCLK,
})

# Mouse-LL hook struct / messages
_MSLLHOOKSTRUCT_FIELDS = [
    ("pt", wintypes.POINT),
    ("mouseData", wintypes.DWORD),
    ("flags", wintypes.DWORD),
    ("time", wintypes.DWORD),
    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
]

# Cursor / magnifier support
IDC_ARROW = 32512
IDC_CROSS = 32515
OCR_NORMAL = 32512
SPI_SETCURSORS = 0x0057
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_NCHITTEST = 0x0084
HWND_TOPMOST = ctypes.c_void_p(-1)
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SRCCOPY = 0x00CC0020
OPAQUE = 2
CROSS_ZOOM = 10
CROSS_SRC = 16
LOUPE_W = 5 + CROSS_SRC * CROSS_ZOOM + 5
LOUPE_H = 34 + CROSS_SRC * CROSS_ZOOM + 6
LOUPE_OFFSET = 26
LOUPE_READOUT_H = 34

WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LPARAM, ctypes.c_int, WPARAM, LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LPARAM, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = _MSLLHOOKSTRUCT_FIELDS


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class _PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", _RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", ctypes.c_ubyte * 32),
    ]


class _WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _setup_prototypes() -> None:
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [ctypes.POINTER(_MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
    user32.CallNextHookEx.restype = LPARAM
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.GetPixel.restype = wintypes.COLORREF
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL

    # --- global crosshair cursor ---
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
    user32.LoadCursorW.restype = ctypes.c_void_p
    user32.CopyIcon.argtypes = [ctypes.c_void_p]
    user32.CopyIcon.restype = ctypes.c_void_p
    user32.SetSystemCursor.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    user32.SetSystemCursor.restype = wintypes.BOOL
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    user32.SystemParametersInfoW.restype = wintypes.BOOL

    # --- pixel-zoom balloon window ---
    user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASS)]
    user32.RegisterClassW.restype = ctypes.c_ushort
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.DefWindowProcW.restype = LPARAM
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT), wintypes.BOOL]
    user32.InvalidateRect.restype = wintypes.BOOL
    user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_PAINTSTRUCT)]
    user32.BeginPaint.restype = wintypes.HDC
    user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_PAINTSTRUCT)]
    user32.EndPaint.restype = wintypes.BOOL
    user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(_RECT), ctypes.c_void_p]
    user32.FillRect.restype = ctypes.c_int
    gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi32.CreateSolidBrush.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.StretchBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.DWORD]
    gdi32.StretchBlt.restype = wintypes.BOOL
    gdi32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.LPCWSTR]
    gdi32.CreateFontW.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [wintypes.HDC, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.SetTextColor.restype = wintypes.COLORREF
    gdi32.MoveToEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.POINTER(wintypes.POINT)]
    gdi32.MoveToEx.restype = wintypes.BOOL
    gdi32.LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.LineTo.restype = wintypes.BOOL
    gdi32.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
    gdi32.TextOutW.restype = wintypes.BOOL


if _WIN32:
    _setup_prototypes()


def _pixel_at(x: int, y: int):
    """Return [r, g, b] for the desktop pixel at device (x, y), or None."""
    hdc = user32.GetDC(None)
    if not hdc:
        return None
    try:
        color = gdi32.GetPixel(hdc, int(x), int(y))
    finally:
        user32.ReleaseDC(None, hdc)
    if color is None or color == CLR_INVALID:
        return None
    return [color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF]


def _set_crosshair_cursor():
    """Swap the system normal cursor to a crosshair for the whole desktop.

    Returns the saved arrow icon (restore with :func:`_restore_cursor`).  The
    crosshair is applied system-wide via SetSystemCursor so every window sees
    it while the pick is active.
    """
    arrow = user32.CopyIcon(user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW)))
    cross = user32.CopyIcon(user32.LoadCursorW(None, ctypes.c_void_p(IDC_CROSS)))
    if cross:
        user32.SetSystemCursor(cross, OCR_NORMAL)
    return arrow


def _restore_cursor(saved_arrow) -> None:
    # SetSystemCursor cannot undo a prior swap; SPI_SETCURSORS reloads every
    # system cursor slot from the scheme, returning the arrow.
    if saved_arrow:
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)


class _PixelLoupe:
    """A topmost GDI popup that magnifies the pixels under the cursor and
    shows the live color.  It is created on the picking thread (which pumps
    messages) and repositioned on every mouse move seen by the hook."""

    _registered_classes = set()
    _counter = 0

    def __init__(self):
        self.hwnd = None
        self.x = 0
        self.y = 0
        self.rgb = (0, 0, 0)
        self._font = None
        self._wndproc = WNDPROC(self._proc)

    def _class_name(self):
        _PixelLoupe._counter += 1
        return "PixelLoupe_%d_%d" % (abs(id(self)), _PixelLoupe._counter)

    def create(self) -> None:
        if not _WIN32 or not user32:
            return
        cls = self._class_name()
        if cls not in _PixelLoupe._registered_classes:
            wc = _WNDCLASS()
            wc.lpfnWndProc = self._wndproc
            wc.lpszClassName = cls
            if user32.RegisterClassW(ctypes.byref(wc)):
                _PixelLoupe._registered_classes.add(cls)
        self.hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            cls, "", WS_POPUP | WS_VISIBLE,
            0, 0, LOUPE_W, LOUPE_H, None, None, None, None)
        if not self.hwnd:
            return
        pt = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            self.place(pt.x, pt.y)

    def destroy(self) -> None:
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self._font:
            gdi32.DeleteObject(self._font)
            self._font = None

    def place(self, x: int, y: int) -> None:
        """Move the balloon next to the cursor and refresh the live color."""
        self.x, self.y = int(x), int(y)
        rgb = _pixel_at(self.x, self.y)
        if rgb:
            self.rgb = tuple(rgb)
        # clamp so the balloon stays on the virtual screen
        vx = user32.GetSystemMetrics(76)
        vy = user32.GetSystemMetrics(77)
        vw = user32.GetSystemMetrics(78)
        vh = user32.GetSystemMetrics(79)
        bx = self.x + LOUPE_OFFSET
        by = self.y + LOUPE_OFFSET
        if vw > 0:
            bx = max(vx, min(bx, vx + vw - LOUPE_W))
        if vh > 0:
            by = max(vy, min(by, vy + vh - LOUPE_H))
        if self.hwnd:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, bx, by, 0, 0,
                                SWP_NOSIZE | SWP_NOACTIVATE)
            user32.InvalidateRect(self.hwnd, None, True)

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_PAINT:
            self._paint(hwnd)
            return 0
        if msg == WM_ERASEBKGND:
            return 1
        if msg == WM_NCHITTEST:
            return -1  # HTTRANSPARENT: never intercept input
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _paint(self, hwnd) -> None:
        ps = _PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            # 1px black border, white interior
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
                self._font = gdi32.CreateFontW(
                    -16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Consolas")
            if self._font:
                gdi32.SelectObject(hdc, self._font)
            gdi32.SetBkMode(hdc, OPAQUE)
            gdi32.SetTextColor(hdc, 0x00000000)
            gdi32.TextOutW(hdc, 44, 9, "#%02x%02x%02x" % (r, g, b), 7)

            # pixel zoom: source box around the cursor -> magnified area
            zoom_w = CROSS_SRC * CROSS_ZOOM
            srcdc = user32.GetDC(None)
            try:
                half = CROSS_SRC // 2
                sx = self.x - half
                sy = self.y - half
                if srcdc:
                    gdi32.StretchBlt(hdc, 5, LOUPE_READOUT_H, zoom_w, zoom_w,
                                     srcdc, sx, sy, CROSS_SRC, CROSS_SRC, SRCCOPY)
            finally:
                if srcdc:
                    user32.ReleaseDC(None, srcdc)

            # crosshair lines through the center of the zoom box
            cx = 5 + zoom_w // 2
            cy = LOUPE_READOUT_H + zoom_w // 2
            gdi32.MoveToEx(hdc, 5, cy, ctypes.byref(wintypes.POINT(0, 0)))
            gdi32.LineTo(hdc, 5 + zoom_w, cy)
            gdi32.MoveToEx(hdc, cx, LOUPE_READOUT_H, ctypes.byref(wintypes.POINT(0, 0)))
            gdi32.LineTo(hdc, cx, LOUPE_READOUT_H + zoom_w)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))


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
    if not _WIN32:
        return {"ok": False, "reason": "unsupported"}

    state = {"clicked": False, "cancel": False, "x": 0, "y": 0, "grace": 0.0}
    keep_alive = []

    loupe = _PixelLoupe()
    loupe.create()
    saved_cursor = _set_crosshair_cursor()

    @HOOKPROC
    def _mouse_proc(n_code, w_param, l_param):
        if n_code >= 0:
            if w_param in (WM_MOUSEMOVE, WM_NCMOUSEMOVE):
                # movement passes through, but keep the balloon tracking
                info = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                loupe.place(info.pt.x, info.pt.y)
                return user32.CallNextHookEx(keep_alive[0], n_code, w_param, l_param)
            if w_param in _MOUSE_CONSUME_ALL:
                if w_param == WM_LBUTTONDOWN:
                    info = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                    state["clicked"] = True
                    state["x"] = info.pt.x
                    state["y"] = info.pt.y
                    user32.PostQuitMessage(0)
                elif w_param in (WM_RBUTTONDOWN, WM_NCRBUTTONDOWN):
                    state["cancel"] = True
                    user32.PostQuitMessage(0)
                # Keep swallowing for a short grace after a resolving click so
                # the trailing mouse-UP is consumed too.
                if state["clicked"] or state["cancel"]:
                    if state["grace"] < time.monotonic() + 0.15:
                        state["grace"] = time.monotonic() + 0.15
                return 1
        return user32.CallNextHookEx(keep_alive[0], n_code, w_param, l_param)

    @HOOKPROC
    def _key_proc(n_code, w_param, l_param):
        if n_code >= 0 and w_param == WM_KEYDOWN:
            info = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if info.vkCode == VK_ESCAPE:
                state["cancel"] = True
                user32.PostQuitMessage(0)
        return user32.CallNextHookEx(keep_alive[1], n_code, w_param, l_param)

    keep_alive[:] = [_mouse_proc, _key_proc]

    mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_proc, None, 0)
    if not mouse_hook:
        loupe.destroy()
        _restore_cursor(saved_cursor)
        return {"ok": False, "reason": "hook_failed"}
    key_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _key_proc, None, 0)

    msg = _MSG()
    deadline = time.monotonic() + max(0.5, float(timeout))

    try:
        while True:
            now = time.monotonic()
            if state["clicked"] or state["cancel"]:
                if now >= state["grace"]:
                    break
            elif now >= deadline:
                break
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.005)
    finally:
        user32.UnhookWindowsHookEx(mouse_hook)
        if key_hook:
            user32.UnhookWindowsHookEx(key_hook)
        loupe.destroy()
        _restore_cursor(saved_cursor)

    if state["clicked"]:
        rgb = _pixel_at(state["x"], state["y"])
        if rgb is None:
            return {"ok": False, "reason": "read_failed"}
        return {
            "ok": True,
            "hex": "#%02x%02x%02x" % (rgb[0], rgb[1], rgb[2]),
            "rgb": rgb,
        }
    if state["cancel"] or msg.message == WM_QUIT:
        return {"ok": False, "reason": "cancelled"}
    return {"ok": False, "reason": "timeout"}