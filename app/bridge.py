"""PyWebView JS bridge: exposes the LycanTools backend to the web frontend.

Design notes
------------
* ``Api`` is installed as ``js_api`` on the PyWebView window, so JS calls
  every public method as ``window.pywebview.api.<method>(...)`` and receives a
  Promise with a JSON value (exceptions reject the Promise).
* Long-running jobs (FFmpeg / Pillow) never block the UI thread: ``start_job``
  spawns a worker thread and returns immediately.  The worker appends progress
  events to a per-job, replayable event buffer and the frontend polls it with
  ``poll(job_id, cursor)``.  Each consumer advances its own cursor, so the
  Lycan Worker popup and an attached tool tab can watch the same job without
  stealing each other's events.  All worker -> UI messaging is therefore
  thread-safe without relying on ``window.evaluate_js`` being callable from
  worker threads.
* Blocking user confirmations requested by a worker (file-count warnings,
  overwrite prompts, ...) are delivered as ``confirm`` events; the worker waits
  on a ``threading.Event`` that ``resolve_confirm`` unblocks.
* The bridge surface is split into per-section mixins under ``app/bridges/``;
  this module composes them, holds the shared instance state, the universal
  helpers, and the response-standardization pass.

Standard status envelope for every public method (enforced by
``_api_response`` from ``app/bridges/envelope.py``)::

  {"ok": True|False, "reason": "SUCCESS"|"WARNING"|"FAILED"|"INFO",
   "detail": str|None, **payload}

Machine-readable sub-codes ("not_queued", "internet_disabled", ...) travel
in the optional "code" kwarg so "reason" always stays a status token.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from collections import deque
from threading import RLock
from typing import Any

import psutil

from .bridges.common import _Job
from .bridges.envelope import _api_response
from .bridges.app_bridge import AppBridgeMixin
from .bridges.utilities_bridge import UtilitiesBridgeMixin
from .bridges.store_bridge import StoreBridgeMixin
from .bridges.tools_bridge import ToolsBridgeMixin
from .bridges.settings_bridge import SettingsBridgeMixin
from .bridges.python_libraries_bridge import PythonLibrariesBridgeMixin
from .bridges.dialog_bridge import DialogBridgeMixin
from .bridges.jobs_bridge import JobsBridgeMixin
from .bridges.runtime_bridge import RuntimeBridgeMixin
from .bridges.queue_bridge import QueueBridgeMixin


class Api(
    AppBridgeMixin,
    UtilitiesBridgeMixin,
    StoreBridgeMixin,
    ToolsBridgeMixin,
    SettingsBridgeMixin,
    PythonLibrariesBridgeMixin,
    DialogBridgeMixin,
    JobsBridgeMixin,
    RuntimeBridgeMixin,
    QueueBridgeMixin,
):
    """Everything the frontend can invoke through ``window.pywebview.api``."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        self._peak_ram = self._process.memory_info().rss
        self._jobs: dict[str, _Job] = {}
        self._pending_confirms: dict[str, dict] = {}
        self._lock = RLock()
        # Most recent job per tool. A remounted tool tab (after exiting and
        # re-entering the card) lost its console state; get_tool_job() uses this
        # to rediscover the job and replay its progress + output log via poll().
        self._recent_jobs: dict[str, str] = {}
        # Lycan Worker queue state.
        self._queue: deque[str] = deque()
        self._queue_current: str | None = None
        self._queue_process = False
        self._queue_worker_alive = False
        self._queue_history: deque[dict] = deque(maxlen=20)
        # Utilities folder scan, watcher baseline and per-utility engines.
        self._init_utilities()
        # Re-queue jobs persisted by a previous (possibly crashed) session.
        self._restore_queue()

    # ------------------------------------------------------------------ #
    #  Universal helpers (shared by every mixin via self)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _window():
        import webview
        try:
            return webview.windows[0]
        except (IndexError, TypeError):
            return None

    @staticmethod
    def _open_explorer(path: str) -> None:
        try:
            target = os.path.dirname(os.path.abspath(path)) if os.path.isfile(path) else os.path.abspath(path)
            if os.path.exists(target):
                if sys.platform.startswith("win"):
                    os.startfile(target)
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["open", target])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", target])
        except Exception:
            pass

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        lines = ["---- FFMPEG ERROR ----"]
        if hasattr(exc, "output") and exc.output:
            lines.append(str(exc.output))
        elif hasattr(exc, "stderr") and exc.stderr:
            lines.append(str(exc.stderr))
        else:
            lines.append(str(exc))
        lines.append("---- PYTHON TRACEBACK ----")
        lines.append(traceback.format_exc())
        return "\n".join(lines)

    @staticmethod
    def _js_str(value: str) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    @classmethod
    def _js_value(cls, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def _push_form_js(self, expression: str) -> bool:
        """Evaluate JS on the live window (best effort, thread-safe).

        Runtime threads push form mutations through this channel so Lua /
        Python hooks can drive the React form. When no window is attached (or
        the backend rejects the call), the mutation is simply skipped.
        """
        window = self._window()
        if window is None:
            return False
        try:
            window.evaluate_js(str(expression))
            return True
        except Exception:
            return False


# --------------------------------------------------------------------------- #
#  Response standardization pass
# --------------------------------------------------------------------------- #
# Every PUBLIC method reachable on Api (no leading underscore) is wrapped with
# _api_response so all frontend calls receive the same status envelope:
#
#   {"ok": True|False, "reason": "SUCCESS"|"WARNING"|"FAILED"|"INFO",
#    "detail": str|None, **payload}
#
# Machine-readable sub-codes live in the optional "code" kwarg. Underscored
# internals (_log, _done, _persist_queue, ...) keep their raw return values;
# they are only ever called from Python.
#
# Methods now live on the mixins, so the pass walks the full MRO (each public
# name is wrapped exactly once) instead of Api.__dict__.
_wrapped_names: set[str] = set()
for _cls in Api.__mro__:
    if _cls is object:
        continue
    for _name, _member in list(vars(_cls).items()):
        if _name.startswith("_") or _name in _wrapped_names:
            continue
        if isinstance(_member, (staticmethod, classmethod)):
            _wrapped_names.add(_name)
            _raw = _member.__func__
            if hasattr(_raw, "__wrapped__"):
                continue
            _rebound = _api_response(_raw)
            setattr(Api, _name, staticmethod(_rebound) if isinstance(_member, staticmethod)
                    else classmethod(_rebound))
        elif callable(_member):
            _wrapped_names.add(_name)
            if hasattr(_member, "__wrapped__"):
                continue
            setattr(Api, _name, _api_response(_member))
del _name, _member, _cls, _wrapped_names
