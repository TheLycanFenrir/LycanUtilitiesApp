"""Lycan Utilities - PyWebView bootstrap entry point.

Launches the web frontend in a native window backed by the ``app.bridge.Api``
JS bridge.  Run with ``LYCANTOOLS_DEBUG=1`` (or ``--debug``) to enable the
WebView2 developer tools.
"""

import ctypes
import inspect
import os
import sys
import traceback

from app.info import APP_TITLE, MAIN_CONTRIBUTOR, VERSION

# CONFIGURATION
# Last applied datetime (ISO 8601): user-provided runtime
CURRENT_DATETIME = "2026-09-05T18:58:24.850+07:00"

if sys.platform == "win32":
    try:
        shell32 = ctypes.windll.shell32
        set_app_id = getattr(shell32, "SetCurrentProcessExplicitAppUserModelID")
        if set_app_id is not None:
            set_app_id(f"{MAIN_CONTRIBUTOR}.FramesToVideo.Conventer.{VERSION}")
    except (AttributeError, OSError, WindowsError) as exc:
        print("Failed to set application ID.", exc)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _resolve_path(*parts: str) -> str:
    return os.path.join(PROJECT_ROOT, *parts)


def _notify_user(title: str, text: str) -> None:
    """Show a native message box fallback for startup errors."""
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except Exception:
        print(f"[{title}] {text}")

def run() -> None:
    """Start the PyWebView window hosting the SPA frontend."""
    import webview

    from app.bridge import Api

    frontend = os.environ.get("LYCAN_FRONTEND", "react")
    if frontend == "dev":
        # Dev / HMR mode: load the Vite dev server instead of a built bundle.
        app_url = os.environ.get("LYCAN_FRONTEND_URL", "http://localhost:5173")
    elif frontend == "react":
        app_url = _resolve_path("frontend", "dist", "index.html")
    else:
        index_html = _resolve_path("web.old", "index.html")
        app_url = index_html
    icon_path = _resolve_path("frontend", "public", "assets", "favicon.ico")

    icon = icon_path if os.path.exists(icon_path) else None
    window_kwargs = dict(
        title=APP_TITLE,
        url=app_url,
        js_api=Api(),
        width=1280,
        height=820,
        min_size=(600, 640),
        background_color="#121212",
    )
    # pywebview exposes the window icon through create_window only in newer
    # releases; older versions accept it on webview.start(). Probe the
    # signature so startup never breaks across pywebview versions.
    if icon and "icon" in inspect.signature(webview.create_window).parameters:
        window_kwargs["icon"] = icon
    webview.create_window(**window_kwargs)

    debug = "--debug" in sys.argv
    debug = debug or os.environ.get("LYCANTOOLS_DEBUG") == "1"

    webview.start(debug=True, icon=icon)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        _notify_user("Application Error", traceback.format_exc())
        sys.exit(1)