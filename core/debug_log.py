"""Ready-to-use leveled debug logging, independent of any bridge module.

Usage
-----
    from core.debug_log import DebugLogger, get_logger

    logger = get_logger(__name__)          # or DebugLogger("my.module")
    logger.debug_info("detail %s", value)
    logger.info("started")
    logger.warning("suspicious")
    logger.error("failed")
    logger.fatal("unrecoverable")

``debug_info`` inspects the call stack (via :mod:`inspect`) and prefixes each
message with the calling ``Class.method`` (or bare function) name, e.g.
``SettingsBridgeMixin.get_settings: enter``. Call sites therefore pass only the
bare message. At module/global scope, or when the frame cannot be inspected,
the message is logged unchanged.

Severity levels (class attributes on DebugLogger, also exported at module level):
    DEBUG_INFO, INFO, WARNING, ERROR, FATAL

``debug_info`` is additionally tiered by verbosity so a developer can dial the
noise up or down without touching call sites:

    0  DEBUG_OFF        disable ``debug_info`` output completely
    1  DEBUG_IMPORTANT  important / one-shot events and direct UI responses
    2  DEBUG_FUNCTION   public method enter/exit and branch tracing
    3  DEBUG_LOOP       internal/hot helpers, per-iteration and polled paths
    4  DEBUG_ALL        every ``debug_info`` call

Each ``debug_info`` call declares its tier (default :data:`DEFAULT_DEBUG_TIER`)
and is emitted only when ``tier <= DEBUG_INFO_LEVEL``. Control the active tier
through the ``DEBUG_INFO_LEVEL`` module constant, the
``LYCANTOOLS_DEBUG_LEVEL`` environment variable, or :func:`set_debug_info_level`.
The default level is :data:`DEBUG_IMPORTANT`, so tracing is quiet until a
developer opts in (e.g. ``LYCANTOOLS_DEBUG_LEVEL=2`` for public API traces,
``3`` to also see internal helpers and per-poll hot paths).

Console output is colorized per level when the terminal supports ANSI escapes:

    grey (debug) / white (info) / yellow (warning) / red (error) / bold red (fatal)

Colors are enabled automatically on macOS/Linux TTYs, and on Windows by
turning on virtual terminal (VT) processing for the console — Windows 10+
cmd/PowerShell/Windows Terminal all render ANSI natively after that; older
consoles and redirected output silently stay plain. ``NO_COLOR`` disables
colors, ``FORCE_COLOR`` forces them, ``TERM=dumb`` disables them.

The class wraps the stdlib ``logging`` module. A console handler is attached
once per logger (idempotent), so importing and calling it "just works" with
no setup. Use ``set_level`` / ``add_file`` for extra control (file output
is never colorized).
"""

from __future__ import annotations

import inspect
import logging
import os
import re
import sys
import threading
from typing import Optional

# Level names exported for ``from core.debug_log import DEBUG_INFO, ...``.
DEBUG_INFO = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
FATAL = logging.CRITICAL

# --------------------------------------------------------------------------- #
#  ``debug_info`` verbosity tiers
# --------------------------------------------------------------------------- #
# ``debug_info`` output is gated by a single tier, ``DEBUG_INFO_LEVEL``. Every
# ``debug_info`` call declares how noisy it is (its ``tier``) and is emitted only
# when ``tier <= DEBUG_INFO_LEVEL``; ``0`` silences ``debug_info`` entirely.
DEBUG_OFF = 0        # disable debug_info output completely
DEBUG_IMPORTANT = 1  # important / one-shot events and direct UI responses
DEBUG_FUNCTION = 2   # public method enter/exit and branch tracing
DEBUG_LOOP = 3       # internal/hot helpers, per-iteration and polled paths
DEBUG_ALL = 4        # every debug_info call

#: Tier assumed when a ``debug_info`` call does not pass ``tier=``.
DEFAULT_DEBUG_TIER = DEBUG_IMPORTANT


def _env_debug_info_level(default: int) -> int:
    """Read ``LYCANTOOLS_DEBUG_LEVEL`` (clamped to 0-4), else ``default``."""
    raw = os.environ.get("LYCANTOOLS_DEBUG_LEVEL")
    if raw is None:
        return default
    try:
        return max(DEBUG_OFF, min(DEBUG_ALL, int(raw)))
    except (TypeError, ValueError):
        return default


#: Active ``debug_info`` tier. Override with ``LYCANTOOLS_DEBUG_LEVEL`` or
#: :func:`set_debug_info_level`. ``0`` disables ``debug_info`` completely.
DEBUG_INFO_LEVEL = _env_debug_info_level(DEBUG_IMPORTANT)


def get_debug_info_level() -> int:
    """Return the active ``debug_info`` tier (0-4)."""
    return DEBUG_INFO_LEVEL


def set_debug_info_level(level: int) -> int:
    """Set the active ``debug_info`` tier (0 disables it); clamped to 0-4."""
    global DEBUG_INFO_LEVEL
    DEBUG_INFO_LEVEL = max(DEBUG_OFF, min(DEBUG_ALL, int(level)))
    return DEBUG_INFO_LEVEL


def is_debug_info_enabled(tier: int = DEFAULT_DEBUG_TIER) -> bool:
    """Return ``True`` if ``debug_info(..., tier=tier)`` would be emitted."""
    try:
        tier = int(tier)
    except (TypeError, ValueError):
        tier = DEFAULT_DEBUG_TIER
    return DEBUG_INFO_LEVEL != DEBUG_OFF and tier <= DEBUG_INFO_LEVEL


_CALLER_PREFIX_RE = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*): ")


def _already_labeled(msg: str, label: str) -> bool:
    """True if ``msg`` already starts with a ``label:``-style prefix.

    Compares the final dotted segment, so a manually written nested qualname
    such as ``_api_response.wrapper:`` still matches the auto-detected
    ``wrapper`` and is left untouched (no double-prefixing).
    """
    match = _CALLER_PREFIX_RE.match(msg)
    if match is None:
        return False
    existing = match.group(1)
    return existing == label or existing.rsplit(".", 1)[-1] == label.rsplit(".", 1)[-1]


def _code_of(attr):
    """Return the ``__code__`` behind a (possibly class/staticmethod) attribute."""
    if attr is None:
        return None
    inner = getattr(attr, "__func__", attr)
    return getattr(inner, "__code__", None)


def _describe_caller(frame) -> str:
    """Best-effort ``Class.method`` / ``function`` label for a stack frame.

    Resolves the *defining* class via the instance MRO (so a method inherited
    from a mixin reports the mixin, not the concrete subclass). Returns ``""``
    when no useful context exists (frame inspection failed, module/global
    scope, or no function name) so callers can fall back to the raw message.
    """
    if frame is None:
        return ""
    code = getattr(frame, "f_code", None)
    if code is None:
        return ""
    func = code.co_name
    if not func or func == "<module>":
        return ""

    local = frame.f_locals
    owner = local.get("self")
    if owner is None:
        owner = local.get("cls")

    owner_name = ""
    if owner is not None:
        cls = owner if isinstance(owner, type) else type(owner)
        for klass in cls.__mro__:
            if _code_of(klass.__dict__.get(func)) is code:
                owner_name = klass.__name__
                break
    return f"{owner_name}.{func}" if owner_name else func


_CONSOLE_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_CONSOLE_DATE = "%H:%M:%S"

# Per-level ANSI SGR prefixes (bright palette so every shade stays readable
# on the dark background used by terminals on every OS).
_LEVEL_COLORS = {
    DEBUG_INFO: "\x1b[90m",   # grey
    INFO: "\x1b[97m",         # white
    WARNING: "\x1b[93m",      # yellow
    ERROR: "\x1b[91m",        # red
    FATAL: "\x1b[1;91m",      # bold red
}
_RESET = "\x1b[0m"

_config_lock = threading.Lock()
_configured_roots: set[str] = set()


def _enable_windows_vt() -> bool:
    """Ask the Win32 console host to interpret ANSI escapes (Windows 10+).

    Sets ENABLE_VIRTUAL_TERMINAL_PROCESSING on the stdout handle so cmd,
    PowerShell and Windows Terminal render ANSI natively. Older consoles,
    pythonw (no console) and redirected handles reject the call and color is
    skipped instead of printing raw escape garbage. Always True off Windows.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # Declare signatures explicitly: HANDLE is a pointer-sized value and
        # ctypes would otherwise truncate it through the default c_int restype.
        kernel32.GetStdHandle.argtypes = [ctypes.c_int]
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.GetConsoleMode.restype = ctypes.c_int
        kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.SetConsoleMode.restype = ctypes.c_int

        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if not handle:
            return False
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False  # pipe/file/no-console: ANSI would not be rendered
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        if not mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            if not kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING):
                return False
        return True
    except Exception:
        return False


def _color_enabled(stream) -> bool:
    """Decide once whether ANSI colors may be emitted on ``stream``.

    macOS/Linux TTYs need nothing extra; Windows additionally requires
    working VT processing (see ``_enable_windows_vt``). Honors the
    NO_COLOR / FORCE_COLOR conventions and ``TERM=dumb``; redirected
    (non-TTY) output stays plain.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    forced = bool(os.environ.get("FORCE_COLOR"))
    if os.name == "nt" and not _enable_windows_vt() and not forced:
        return False
    if forced:
        return True
    try:
        return bool(stream.isatty())
    except Exception:
        return False


class _ColorFormatter(logging.Formatter):
    """Colors the whole formatted line (timestamp, level, name, message and
    any traceback) with the record's level color; plain when colors are off."""

    def __init__(self, fmt: str, datefmt: str, enabled: bool) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._enabled = enabled

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        color = _LEVEL_COLORS.get(record.levelno)
        if not (self._enabled and color):
            return line
        return f"{color}{line}{_RESET}"


class DebugLogger:
    """Leveled logger with ``debug_info``/``info``/``warning``/``error``/``fatal``."""

    DEBUG_INFO = DEBUG_INFO
    INFO = INFO
    WARNING = WARNING
    ERROR = ERROR
    FATAL = FATAL
    DEBUG_OFF = DEBUG_OFF
    DEBUG_IMPORTANT = DEBUG_IMPORTANT
    DEBUG_FUNCTION = DEBUG_FUNCTION
    DEBUG_LOOP = DEBUG_LOOP
    DEBUG_ALL = DEBUG_ALL

    def __init__(self, name: str = "app", level: int = DEBUG_INFO) -> None:
        self.name = name
        self._logger = logging.getLogger(name)
        self._ensure_handler()
        self.set_level(level)

    # ------------------------------------------------------------------ #
    #  Configuration
    # ------------------------------------------------------------------ #
    def _ensure_handler(self) -> None:
        """Attach one console handler to the 'debug_log' logger tree (idempotent).

        Child loggers keep ``propagate=True`` so records bubble up to the
        single handler on the tree root; the root itself never propagates to
        the stdlib root logger (no duplicate output).
        """
        with _config_lock:
            if "root" not in _configured_roots:
                handler = logging.StreamHandler(sys.stdout)
                handler.setFormatter(_ColorFormatter(
                    _CONSOLE_FMT, _CONSOLE_DATE, _color_enabled(sys.stdout)))
                tree_root = logging.getLogger("debug_log")
                tree_root.addHandler(handler)
                tree_root.setLevel(DEBUG_INFO)
                tree_root.propagate = False
                _configured_roots.add("root")
        # Parent this logger to the configured tree root (records reach its
        # handler via normal propagation; the formatter prints this logger's
        # own name).
        if self.name != "debug_log":
            self._logger.parent = logging.getLogger("debug_log")

    def set_level(self, level: int) -> None:
        self._logger.setLevel(int(level))

    def add_file(self, path: str, level: Optional[int] = None) -> None:
        """Also write records to ``path`` (UTF-8, appended)."""
        handler = logging.FileHandler(path, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        if level is not None:
            handler.setLevel(int(level))
        self._logger.addHandler(handler)

    # ------------------------------------------------------------------ #
    #  Leveled output
    # ------------------------------------------------------------------ #
    def debug_info(self, msg: str, *args, tier: int = DEFAULT_DEBUG_TIER, **kwargs) -> None:
        """DEBUG_INFO: verbose diagnostics, gated by ``tier`` / ``DEBUG_INFO_LEVEL``.

        ``tier`` (0-4, default :data:`DEFAULT_DEBUG_TIER`) declares how noisy
        this message is; it is emitted only when ``tier <= DEBUG_INFO_LEVEL``
        and ``DEBUG_INFO_LEVEL`` is non-zero. See the module docstring for the
        meaning of each tier.

        The caller's ``Class.method`` (or bare function) name is detected from
        the stack via :mod:`inspect` and prepended automatically, so call sites
        need not hardcode it. At module/global scope, or when the frame cannot
        be inspected, the raw message is logged unchanged. A message that
        already begins with the detected label is left as-is, so partially
        migrated call sites never double-prefix.
        """
        if not is_debug_info_enabled(tier):
            return
        frame = inspect.currentframe()
        try:
            label = _describe_caller(frame.f_back if frame is not None else None)
        finally:
            del frame
        if label and isinstance(msg, str) and not _already_labeled(msg, label):
            msg = f"{label}: {msg}"
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        """INFO: normal operational milestones."""
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        """WARNING: something unexpected but recoverable."""
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        """ERROR: an operation failed."""
        self._logger.error(msg, *args, **kwargs)

    def fatal(self, msg: str, *args, **kwargs) -> None:
        """FATAL: the app cannot continue."""
        self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        """ERROR plus the current traceback (call inside an ``except`` block)."""
        self._logger.exception(msg, *args, **kwargs)

    def debug_info_enabled(self, tier: int = DEFAULT_DEBUG_TIER) -> bool:
        """True if a ``debug_info`` call at ``tier`` would actually be logged."""
        return is_debug_info_enabled(tier) and self._logger.isEnabledFor(DEBUG_INFO)


_registry: dict[str, DebugLogger] = {}
_registry_lock = threading.Lock()


def get_logger(name: str = "app", level: int = DEBUG_INFO) -> DebugLogger:
    """Return a module-scoped :class:`DebugLogger` (cached per name).

    ``level`` applies only on first creation; afterwards use
    ``logger.set_level(...)`` to change it.
    """
    with _registry_lock:
        logger = _registry.get(name)
        if logger is None:
            logger = DebugLogger(name, level)
            _registry[name] = logger
        return logger
