"""Low-level Win32 FFI plumbing for the screen picker.

Holds every ctypes constant, struct, callback type and prototype setup the
picker and the pixel-zoom balloon need. All Windows-only definitions are
guarded so this module (and therefore the ``app.screenpick`` package) imports
cleanly on non-Windows platforms, where :func:`app.screenpick.wait_for_screen_pick`
reports ``unsupported``.
"""

from __future__ import annotations

import ctypes
from core.debug_log import get_logger

_logger = get_logger(__name__)

try:
    from ctypes import wintypes
    _WIN32 = hasattr(ctypes, "windll")
except Exception:  # pragma: no cover - non-Windows runner
    wintypes = None
    _WIN32 = False

user32 = ctypes.windll.user32 if _WIN32 else None
gdi32 = ctypes.windll.gdi32 if _WIN32 else None

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

if _WIN32:
    WPARAM = ctypes.c_size_t
    LPARAM = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LPARAM, ctypes.c_int, WPARAM, LPARAM)
    WNDPROC = ctypes.WINFUNCTYPE(LPARAM, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

    # Mouse-LL hook struct / messages
    _MSLLHOOKSTRUCT_FIELDS = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

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
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
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
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    _setup_prototypes()
else:
    # Safe placeholders so sibling modules import cleanly off-Windows; every
    # consumer is behind the _WIN32 early-return in wait_for_screen_pick().
    WPARAM = LPARAM = None
    HOOKPROC = WNDPROC = None
    _MSLLHOOKSTRUCT = _KBDLLHOOKSTRUCT = None
    _RECT = _MSG = _PAINTSTRUCT = _WNDCLASS = None
