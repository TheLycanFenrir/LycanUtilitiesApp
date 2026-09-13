"""PyWebView JS bridge: exposes the LycanTools backend to the web frontend.

Design notes
------------
* ``apiclass.Api`` is installed as ``js_api`` on the PyWebView window, so JS calls
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
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, Thread
from typing import Any, Optional

import psutil

from api.FrameToVideo import ImageToVideo
from api.ImageSplitter import (
    ImageSplitter,
    ExportSettings as ImageExportSettings,
    SplitStatus,
    SplitAbortedError,
)
from api.TextureMipMapGenerator import (
    TextureMipMapGenerator,
    TextureExportSettings,
    MipStatus,
)
from utils.settings import (
    load_settings, save_settings, load_presets, save_presets,
    get_history, add_to_history, generate_unique_preset_name,
    load_favorites, toggle_favorite, record_used,
    load_app_theme, save_app_theme,
    load_app_settings, save_app_settings,
    get_storage_stats, clear_all_data, clear_all_presets, clear_all_history,
    load_worker_queue, save_worker_queue,
)
from utils.system import (
    get_dropdown_core_options, get_available_cores, get_cpu_name,
    detect_ffmpeg_binaries,
)
from app.info import APP_TITLE, APP_SUBTITLE, MAIN_CONTRIBUTOR, VERSION, TOOLS, HOME_VIEW_ID, GITHUB_REPOSITORY_URL
from app.updates import check_for_updates as run_update_check


_IMAGE_FILE_TYPES = ("Images (*.png;*.jpg;*.jpeg;*.webp;*.tga;*.tiff;*.bmp)",)
_ALL_FILE_TYPES = ("All files (*.*)",)

# Events retained per job for replay. Consumers poll with a cursor, so even a
# late-attaching surface (Worker popup, tool tab) sees recent output.
EVENT_BUFFER_MAX = 2000

# How long a finished job stays in self._jobs so a tool tab attaching after
# completion can still replay its log/progress. get_queue() prunes past this.
_FINISHED_JOB_GRACE = 120.0


_OUTPUT_EXTENSIONS = {
    "mp4_h264": ".mp4",
    "mp4_av1": ".mp4",
    "webm": ".webm",
    "gif": ".gif",
    "apng": ".apng",
    "webp": ".webp",
}

_CRF_RANGES = {
    "mp4_h264": (0, 51),
    "mp4_av1": (0, 63),
    "webm": (0, 63),
    "webp": (0, 63),
    "gif": (None, None),
    "apng": (None, None),
}


def _clamp_crf(crf: Any, lo: Optional[int], hi: Optional[int]) -> Any:
    try:
        val = int(crf)
    except (ValueError, TypeError):
        return crf
    if lo is not None and hi is not None:
        return max(lo, min(val, hi))
    if hi is not None:
        return min(val, hi)
    if lo is not None:
        return max(val, lo)
    return val


class _Job:
    """One running or queued background task."""

    __slots__ = (
        "id", "tool", "params", "abort_event", "pause_event", "events",
        "event_seq", "ev_lock", "last_progress", "progress_pct", "status_text",
        "finished", "finished_at", "queued", "outcome", "label", "restored",
        "pending_confirm",
    )

    def __init__(self, job_id: str, tool: str, params: Optional[dict] = None) -> None:
        self.id = job_id
        self.tool = tool
        self.params: dict = dict(params or {})
        self.abort_event = Event()
        self.pause_event = Event()
        # Replayable event buffer: (sequence, payload) pairs. Consumers poll
        # with a cursor and only receive events newer than it, so multiple
        # surfaces (Worker popup, attached tool tab) can watch one job without
        # draining each other's events.
        self.events: deque = deque(maxlen=EVENT_BUFFER_MAX)
        self.event_seq = 0
        self.ev_lock = Lock()
        self.last_progress = 0.0
        self.progress_pct = 0.0
        self.status_text = ""
        self.finished = False
        # Monotonic timestamp set by _done(); used to prune finished jobs.
        self.finished_at = 0.0
        # Token of the confirmation currently awaiting an answer (if any).
        # poll() only replays a confirm while it is still pending, so a surface
        # attaching after the prompt was answered never sees a stale confirm.
        self.pending_confirm: Optional[str] = None
        # Queue bookkeeping: True until the worker dequeues the job.
        self.queued = False
        # Final result: "ok" | "error" | "cancelled" (set by _done).
        self.outcome: Optional[str] = None
        self.label = ""
        # True when the job was restored from the on-disk queue after a restart.
        self.restored = False


def _tool_title(tool: str) -> str:
    return next((t.get("title") or t.get("id") for t in TOOLS if t.get("id") == tool), tool)


def _tool_icon_file(tool: str) -> str:
    return next((t.get("icon_file") or "" for t in TOOLS if t.get("id") == tool), "")


class Api:
    """Everything the frontend can invoke through ``window.pywebview.api``."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        self._peak_ram = self._process.memory_info().rss
        self._jobs: dict[str, _Job] = {}
        self._pending_confirms: dict[str, dict] = {}
        self._lock = Lock()
        # Most recent job per tool. A remounted tool tab (after exiting and
        # re-entering the card) lost its console state; get_tool_job() uses this
        # to rediscover the job and replay its progress + output log via poll().
        self._recent_jobs: dict[str, str] = {}
        # Lycan Worker queue state.
        self._queue: deque[str] = deque()
        self._queue_current: Optional[str] = None
        self._queue_process = False
        self._queue_worker_alive = False
        self._queue_history: deque[dict] = deque(maxlen=20)
        self._restore_queue()

    # ------------------------------------------------------------------ #
    #  App / dashboard
    # ------------------------------------------------------------------ #
    def get_app(self) -> dict:
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
        if not url or not url.startswith(("http://", "https://")):
            return {"ok": False, "reason": "invalid_url"}
        try:
            import webbrowser
            webbrowser.open(url, new=2)
            return {"ok": True}
        except Exception:
            return {"ok": False, "reason": "failed"}

    def quit_app(self) -> dict:
        """Close the native window. Runs in the UI thread."""
        try:
            window = self._window()
            if window is None:
                return {"ok": False, "reason": "no_window"}
            window.destroy()
            return {"ok": True}
        except Exception:
            return {"ok": False, "reason": "failed"}

    def restart_app(self) -> dict:
        """Close the window and relaunch a completely fresh app instance.

        A detached copy of the entry point is spawned first, then this window
        is destroyed, so the new process boots a clean WebView / JS context.
        """
        try:
            window = self._window()
            if window is None:
                return {"ok": False, "reason": "no_window"}
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            executable = sys.executable
            if not getattr(sys, "frozen", False):
                pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
                if os.path.exists(pythonw):
                    executable = pythonw
                command = [executable, os.path.join(root, "main.py")]
            else:
                command = [executable]
            creationflags = 0
            if sys.platform.startswith("win"):
                creationflags = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
            subprocess.Popen(command, cwd=root, creationflags=creationflags, close_fds=True)
            window.destroy()
            return {"ok": True}
        except Exception:
            return {"ok": False, "reason": "failed"}

    def check_for_updates(self) -> dict:
        """Check the GitHub release feed for a newer version."""
        try:
            return run_update_check()
        except Exception:
            return {"ok": False, "reason": "failed"}

    def open_devtools(self) -> dict:
        """Open the native developer tools / web inspector window.

        PyWebView exposes ``show_devtools()`` on its WebView2 (Edge
        Chromium) windows; older backends fall back to an unsupported
        result so the frontend can show a graceful message.
        """
        try:
            window = self._window()
            if window is None:
                return {"ok": False, "reason": "no_window"}
            show = getattr(window, "show_devtools", None)
            if callable(show):
                show()
                return {"ok": True}
            return {"ok": False, "reason": "unsupported"}
        except Exception:
            return {"ok": False, "reason": "failed"}

    def get_tools(self) -> list[dict]:
        return [dict(t) for t in TOOLS]

    def get_dashboard(self) -> dict:
        favorites = load_favorites()
        last_used = {}
        from utils.settings import load_last_used
        last_used = load_last_used()
        tools = []
        for t in TOOLS:
            item = dict(t)
            item["favorite"] = bool(favorites.get(t["id"], False))
            item["last_used"] = last_used.get(t["id"])
            tools.append(item)
        system = self.get_system_stats()
        return {
            "tools": tools,
            "theme": load_app_theme(),
            "app": self.get_app(),
            "cpu_name": system["cpu_name"],
        }

    def open_tool(self, tool_id: str) -> dict:
        record_used(tool_id)
        return {"ok": True}

    def toggle_favorite(self, tool_id: str) -> dict:
        return {"favorite": toggle_favorite(tool_id)}

    def set_theme(self, mode: str) -> dict:
        save_app_theme(mode)
        return {"theme": load_app_theme()}

    def get_core_options(self) -> list[str]:
        return get_dropdown_core_options()

    def get_system_stats(self) -> dict:
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
        except Exception:
            cpu_percent = 0.0
        try:
            rss = self._process.memory_info().rss
            self._peak_ram = max(self._peak_ram, rss)
        except Exception:
            rss = 0
        try:
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            used_pct = mem.percent
        except Exception:
            used_gb = total_gb = used_pct = 0.0
        return {
            "cpu_name": get_cpu_name(),
            "cpu_percent": round(float(cpu_percent), 1),
            "app_rss_mb": round(rss / (1024 ** 2), 1),
            "app_peak_mb": round(self._peak_ram / (1024 ** 2), 1),
            "sys_used_gb": round(float(used_gb), 2),
            "sys_total_gb": round(float(total_gb), 2),
            "sys_used_pct": round(float(used_pct), 1),
        }

    # ------------------------------------------------------------------ #
    #  Settings / presets / history
    # ------------------------------------------------------------------ #
    def get_settings(self, tool: str) -> Optional[dict]:
        return load_settings(tool)

    def save_settings(self, tool: str, settings: dict) -> dict:
        save_settings(settings or {}, tool)
        return {"ok": True}

    def get_presets(self, tool: str) -> dict:
        return load_presets(tool)

    def save_presets(self, tool: str, presets: dict) -> dict:
        save_presets(presets or {}, tool)
        return {"ok": True}

    def delete_preset(self, tool: str, name: str) -> dict:
        presets = load_presets(tool)
        if name in presets:
            del presets[name]
            save_presets(presets, tool)
            return {"ok": True, "deleted": name}
        return {"ok": False, "reason": "not_found"}

    def unique_preset_name(self, tool: str, name: str) -> dict:
        presets = load_presets(tool)
        return {"name": generate_unique_preset_name(presets, name)}

    def get_history(self, category: str, key: str) -> list[str]:
        return get_history(category, key)

    def add_history(self, category: str, key: str, value: str) -> dict:
        add_to_history(category, key, value)
        return {"ok": True}

    # ------------------------------------------------------------------ #
    #  App settings / data management
    # ------------------------------------------------------------------ #
    def get_app_settings(self) -> dict:
        """Load the single app-level settings document (settings.json -> 'app_settings')."""
        return load_app_settings()

    def save_app_settings(self, settings: dict) -> dict:
        """Persist the app-level settings document, preserving all other keys."""
        save_app_settings(settings or {})
        return {"ok": True}

    def get_storage_stats(self) -> dict:
        """Sizes and entry counts for settings/presets/history/favorites/last-used."""
        return get_storage_stats()

    def clear_all_data(self) -> dict:
        """Delete every persisted user-data JSON file; returns bytes freed per store."""
        return {"removed": clear_all_data()}

    def clear_all_presets(self) -> dict:
        """Empty the presets file."""
        return {"removed": clear_all_presets()}

    def clear_all_history(self) -> dict:
        """Empty the input-history file."""
        return {"removed": clear_all_history()}

    def detect_ffmpeg(self) -> dict:
        """Scan PATH + common install roots for FFmpeg binaries."""
        return detect_ffmpeg_binaries()

    # ------------------------------------------------------------------ #
    #  Native dialogs
    # ------------------------------------------------------------------ #
    @staticmethod
    def _window():
        import webview
        try:
            return webview.windows[0]
        except (IndexError, TypeError):
            return None

    def open_dialog(self, kind: str = "file", initial_directory: str = "",
                    save_filename: str = "", allow_multiple: bool = False,
                    file_types: Optional[list] = None) -> Optional[list]:
        """Open a native open/folder/save dialog. Returns a list of paths or None.

        ``initial_directory`` is sourced directly from the active UI field
        (smart browse memory): the picker starts inside the directory the
        field already points at, or falls back to the OS default when empty.
        """
        import webview
        window = self._window()
        if window is None:
            return None
        kind = (kind or "file").lower()
        dialog_type = {
            "file": webview.FileDialog.OPEN,
            "folder": webview.FileDialog.FOLDER,
            "save": webview.FileDialog.SAVE,
        }.get(kind, webview.FileDialog.OPEN)
        types = tuple(file_types) if file_types else (
            _ALL_FILE_TYPES if kind == "file" else tuple()
        )
        try:
            result = window.create_file_dialog(
                dialog_type=dialog_type,
                directory=initial_directory or "",
                allow_multiple=allow_multiple and kind == "file",
                save_filename=save_filename or "",
                file_types=types,
            )
        except Exception:
            return None
        if result is None:
            return None
        if isinstance(result, str):
            return [result]
        return list(result)

    # ------------------------------------------------------------------ #
    #  Screen color picking
    # ------------------------------------------------------------------ #
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
        try:
            from utils.screenpick import wait_for_screen_pick
        except Exception:
            return {"ok": False, "reason": "unsupported"}
        try:
            return wait_for_screen_pick(float(timeout))
        except Exception:
            return {"ok": False, "reason": "failed"}

    # ------------------------------------------------------------------ #
    #  Jobs
    # ------------------------------------------------------------------ #
    def _runner_for(self, tool: str):
        """Return the run-loop method for a tool id, or None if unsupported."""
        return {
            "frames_to_video": self._run_frames_to_video,
            "image_splitter": self._run_image_splitter,
            "texture_mipmap": self._run_texture_mipmap,
        }.get(tool)

    def _spawn_run(self, job: _Job) -> None:
        thread = Thread(target=self._runner_for(job.tool), args=(job, job.params), daemon=True)
        thread.start()

    def start_job(self, tool: str, params: dict) -> dict:
        with self._lock:
            self._prune_finished_jobs()
            job = _Job(uuid.uuid4().hex, tool, params)
            self._jobs[job.id] = job
            self._recent_jobs[tool] = job.id
        record_used(tool)
        runner = self._runner_for(tool)
        if runner is None:
            self._log(job, f"Tool '{tool}' has no backend handler yet.", "warn")
            self._done(job, False, "Not implemented.", "unsupported tool")
            return {"job_id": job.id, "ok": False, "tool": tool}
        self._spawn_run(job)
        return {"job_id": job.id, "ok": True, "tool": tool}

    def get_tool_job(self, tool: str) -> dict:
        """Return the most recent live/replayable job for a tool, if any.

        Exiting and re-entering a tool tab unmounts it, wiping its console
        state (progress percent, output log, job id). The backend still holds
        the job with its replayable event buffer for a grace window after it
        finishes; this method lets the remounted tab rediscover the job and
        re-attach via poll(job_id, 0), restoring the log and percent. An
        explicit focus is handled by the frontend's own attach path.
        """
        with self._lock:
            self._prune_finished_jobs()
            jid = self._recent_jobs.get(tool)
            if not jid:
                return {"ok": True, "job_id": None}
            job = self._jobs.get(jid)
            if job is None or job.queued:
                return {"ok": True, "job_id": None}
            return {
                "ok": True,
                "job_id": job.id,
                "tool": job.tool,
                "progress": int(round(job.progress_pct)),
                "status_text": job.status_text or "",
                "finished": job.finished,
                "outcome": job.outcome,
            }

    def poll(self, job_id: str, cursor: int = 0) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            return {"done": True, "events": [], "cursor": 0}
        try:
            cur = max(0, int(cursor))
        except (TypeError, ValueError):
            cur = 0
        events = []
        new_cursor = cur
        with job.ev_lock:
            # A confirm event is only meaningful while its prompt is pending;
            # surface it to one consumer, never replay an already-answered one.
            pending = job.pending_confirm
            for seq, payload in job.events:
                if seq > cur and not (payload.get("kind") == "confirm" and payload.get("token") != pending):
                    events.append(payload)
            if events:
                new_cursor = job.events[-1][0]
        # Never pop the job here: a finished job stays available (until the
        # grace-period prune in get_queue()) so a tab attaching after completion
        # can still replay its log/progress events.
        return {"done": job.finished, "events": events, "cursor": new_cursor}

    def abort_job(self, job_id: str) -> dict:
        """Abort a running job, or remove a queued job from the worker queue."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return {"ok": False, "reason": "not_found"}
            if job.queued:
                self._queue = deque(jid for jid in self._queue if jid != job_id)
                self._jobs.pop(job_id, None)
                self._queue_history.appendleft({
                    "job_id": job.id,
                    "tool": job.tool,
                    "tool_title": _tool_title(job.tool),
                    "label": job.label or "",
                    "outcome": "aborted",
                })
                removed = True
            else:
                removed = False
        if removed:
            self._persist_queue()
            return {"ok": True, "reason": "removed_from_queue"}
        job.abort_event.set()
        return {"ok": True}

    # Backwards-compatible aliases for the "conversion" naming.
    def abort_conversion(self, job_id: str) -> dict:
        return self.abort_job(job_id)

    def pause_job(self, job_id: str) -> dict:
        """Cooperatively pause a running job at its next checkpoint."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.queued or job.finished:
            return {"ok": False, "reason": "not_running"}
        job.pause_event.set()
        self._status(job, "Paused", "warn")
        return {"ok": True}

    def pause_conversion(self, job_id: str) -> dict:
        return self.pause_job(job_id)

    def resume_job(self, job_id: str) -> dict:
        """Resume a paused job."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.queued or job.finished:
            return {"ok": False, "reason": "not_running"}
        job.pause_event.clear()
        self._status(job, "Working...", "accent")
        return {"ok": True}

    def resume_conversion(self, job_id: str) -> dict:
        return self.resume_job(job_id)

    # ------------------------------------------------------------------ #
    #  Lycan Worker queue
    # ------------------------------------------------------------------ #
    def enqueue_job(self, tool: str, params: dict) -> dict:
        """Queue a job configuration for the Lycan Worker without starting it."""
        if self._runner_for(tool) is None:
            return {"ok": False, "reason": "unsupported_tool", "tool": tool}
        with self._lock:
            job = _Job(uuid.uuid4().hex, tool, params)
            job.queued = True
            job.label = f"{_tool_title(tool)} \u00b7 {job.id[:6]}"
            self._jobs[job.id] = job
            self._queue.append(job.id)
        record_used(tool)
        self._persist_queue()
        return {"job_id": job.id, "ok": True, "tool": tool}

    def update_queued_job(self, job_id: str, params: dict) -> dict:
        """Replace the parameters of a pending (not yet started) job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.queued or job_id not in self._queue:
                return {"ok": False, "reason": "not_queued"}
            job.params = dict(params or {})
        self._persist_queue()
        return {"ok": True}

    def get_queued_job(self, job_id: str) -> dict:
        """Return the stored configuration of a pending job (for editing)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.queued:
                return {"ok": False, "reason": "not_found"}
            return {
                "ok": True,
                "job_id": job.id,
                "tool": job.tool,
                "params": dict(job.params),
            }

    def rename_job(self, job_id: str, name: str) -> dict:
        """Rename a pending job via user input.

        An empty name becomes "Unnamed". If the resulting name collides with
        another pending job, a numeric suffix "(0)", "(1)", ... is appended.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.queued or job_id not in self._queue:
                return {"ok": False, "reason": "not_queued"}
            base = str(name or "").strip() or "Unnamed"
            taken = {
                self._jobs[jid].label
                for jid in self._queue
                if jid != job_id and self._jobs.get(jid) is not None
            }
            label = base
            suffix = 0
            while label in taken:
                label = f"{base} ({suffix})"
                suffix += 1
            job.label = label
        self._persist_queue()
        return {"ok": True, "label": label}

    def reorder_job(self, job_id: str, to_index: int) -> dict:
        """Move a pending job to another position in the queue."""
        with self._lock:
            if job_id not in self._queue:
                return {"ok": False, "reason": "not_queued"}
            items = list(self._queue)
            idx = items.index(job_id)
            items.pop(idx)
            try:
                to_index = int(to_index)
            except (ValueError, TypeError):
                to_index = idx
            to_index = max(0, min(len(items), to_index))
            items.insert(to_index, job_id)
            self._queue = deque(items)
        self._persist_queue()
        return {"ok": True, "index": to_index}

    def dequeue_job(self, job_id: str) -> dict:
        """Remove a pending (not yet started) job from the queue."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.queued or job_id not in self._queue:
                return {"ok": False, "reason": "not_queued"}
            self._queue = deque(jid for jid in self._queue if jid != job_id)
            self._jobs.pop(job_id, None)
        self._persist_queue()
        return {"ok": True}

    def clear_queue(self) -> dict:
        """Remove every pending job and reset the worker history."""
        with self._lock:
            removed = len(self._queue)
            for jid in list(self._queue):
                self._jobs.pop(jid, None)
            self._queue.clear()
            self._queue_history.clear()
        self._persist_queue()
        return {"ok": True, "removed": removed}

    def start_queue(self) -> dict:
        """Begin processing the queued jobs sequentially on a worker thread."""
        with self._lock:
            if not self._queue:
                return {"ok": False, "reason": "empty"}
            self._queue_process = True
            if not self._queue_worker_alive:
                self._queue_worker_alive = True
                Thread(target=self._queue_worker, daemon=True).start()
        return {"ok": True}

    def stop_queue(self) -> dict:
        """Stop launching new jobs from the queue; the current job finishes."""
        with self._lock:
            self._queue_process = False
        return {"ok": True}

    def _persist_queue(self) -> None:
        """Snapshot every unfinished job (pending + current) to disk.

        On a crash or force-close the persisted entries are restored as
        incomplete, user-runnable jobs on the next launch.
        """
        entries = []
        with self._lock:
            for jid in list(self._queue):
                job = self._jobs.get(jid)
                if job is not None:
                    entries.append({"job_id": job.id, "tool": job.tool,
                                    "params": dict(job.params)})
            cid = self._queue_current
            if cid is not None:
                job = self._jobs.get(cid)
                if job is not None:
                    entries.append({"job_id": job.id, "tool": job.tool,
                                    "params": dict(job.params)})
        save_worker_queue(entries)

    def _restore_queue(self) -> None:
        """Re-queue jobs persisted by a previous (possibly crashed) session."""
        restored = []
        for entry in load_worker_queue():
            try:
                job_id = str(entry["job_id"])
                tool = str(entry["tool"])
                params = dict(entry.get("params") or {})
            except (KeyError, TypeError, ValueError):
                continue
            if not job_id or self._runner_for(tool) is None:
                continue
            if job_id in self._jobs:
                continue
            job = _Job(job_id, tool, params)
            job.queued = True
            job.restored = True
            job.label = f"{_tool_title(tool)} \u00b7 {job_id[:6]}"
            self._jobs[job.id] = job
            self._queue.append(job.id)
            restored.append(job_id)
        if restored:
            print(f"Lycan Worker: restored {len(restored)} incomplete job(s) from a previous session.")

    def _queue_state(self) -> str:
        """Derive the worker status: empty | idle | running | success | failed | aborted."""
        if self._queue_current is not None:
            return "running"
        if self._queue:
            return "idle"
        if self._queue_history:
            return self._queue_history[0]["outcome"]
        return "empty"

    def _prune_finished_jobs(self, grace: float = _FINISHED_JOB_GRACE) -> None:
        """Drop finished jobs whose replay grace period has lapsed.

        Caller must hold self._lock. Finished jobs are intentionally kept a
        while so a tool tab attaching after completion can still replay their
        log/progress events; this sweep bounds the growth of self._jobs.
        """
        now = time.monotonic()
        for jid, job in list(self._jobs.items()):
            if job.finished and job.finished_at and now - job.finished_at > grace:
                del self._jobs[jid]
                if self._recent_jobs.get(job.tool) == jid:
                    self._recent_jobs.pop(job.tool, None)

    def get_queue(self) -> dict:
        """Snapshot of the Lycan Worker queue for the header dropdown."""
        with self._lock:
            self._prune_finished_jobs()
            current = None
            cid = self._queue_current
            if cid is not None:
                job = self._jobs.get(cid)
                if job is not None:
                    current = {
                        "job_id": job.id,
                        "tool": job.tool,
                        "tool_title": _tool_title(job.tool),
                        "label": job.label or "",
                        "progress": int(round(job.progress_pct)),
                        "status_text": job.status_text or "",
                        "paused": job.pause_event.is_set(),
                    }
            pending = []
            for jid in self._queue:
                job = self._jobs.get(jid)
                if job is not None:
                    pending.append({
                        "job_id": job.id,
                        "tool": job.tool,
                        "tool_title": _tool_title(job.tool),
                        "icon_file": _tool_icon_file(job.tool),
                        "label": job.label or "",
                        "restored": job.restored,
                    })
            return {
                "state": self._queue_state(),
                "processing": self._queue_process,
                "current": current,
                "pending": pending,
                "history": list(self._queue_history),
                "total": (1 if current else 0) + len(pending),
            }

    def _queue_worker(self) -> None:
        """Worker loop: run queued jobs one at a time until stopped or drained.

        ``_queue_worker_alive`` is ALWAYS cleared on the way out. An unexpected
        exception here can therefore never wedge the queue (otherwise Start
        Queue would permanently refuse to spawn a fresh worker while the UI
        stays stuck showing a "running" job).
        """
        while True:
            try:
                with self._lock:
                    if not self._queue_process or not self._queue:
                        self._queue_worker_alive = False
                        return
                    job_id = self._queue.popleft()
                    job = self._jobs.get(job_id)
                    if job is None:
                        continue
                    job.queued = False
                    self._queue_current = job_id
                    self._recent_jobs[job.tool] = job_id
                self._persist_queue()
                runner = self._runner_for(job.tool)
                if runner is None:
                    with self._lock:
                        self._queue_current = None
                        self._queue_history.appendleft({
                            "job_id": job.id, "tool": job.tool,
                            "tool_title": _tool_title(job.tool),
                            "label": job.label or "", "outcome": "failed",
                        })
                        self._jobs.pop(job.id, None)
                    self._persist_queue()
                    continue
                thread = Thread(target=runner, args=(job, job.params), daemon=True)
                thread.start()
                thread.join()
                if not job.finished:
                    # The run method exited without recording a result (unexpected
                    # exception); mark the job failed so the worker can proceed.
                    self._done(job, False, "Job ended unexpectedly.", "runner exited")
                outcome = {"ok": "success", "error": "failed", "cancelled": "aborted"}.get(
                    job.outcome or "cancelled", "failed")
                with self._lock:
                    self._queue_current = None
                    self._queue_history.appendleft({
                        "job_id": job.id, "tool": job.tool,
                        "tool_title": _tool_title(job.tool),
                        "label": job.label or "", "outcome": outcome,
                    })
                # Keep the finished job in self._jobs so a tab attaching after
                # completion can still replay its log/progress; get_queue()
                # prunes finished jobs after a grace period.
                self._persist_queue()
            except Exception as exc:
                # Never leave the queue wedged: restore a stoppable, restartable
                # state and mark the interrupted job (if any) as failed.
                traceback.print_exc()
                with self._lock:
                    current_id = self._queue_current
                    self._queue_process = False
                    self._queue_current = None
                    self._queue_worker_alive = False
                if current_id is not None:
                    with self._lock:
                        cur = self._jobs.get(current_id)
                        if cur is not None and not cur.finished:
                            self._done(cur, False, "Queue worker stopped unexpectedly.",
                                       str(exc) or "queue worker error")
                self._persist_queue()
                return

    def resolve_confirm(self, token: str, accepted: bool) -> dict:
        with self._lock:
            entry = self._pending_confirms.pop(token, None)
        if entry is not None:
            entry["value"] = bool(accepted)
            entry["event"].set()
            return {"ok": True}
        return {"ok": False, "reason": "not_found"}

    # ------------------------------------------------------------------ #
    #  Emitters (safe from any thread)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _emit(job: _Job, payload: dict) -> None:
        with job.ev_lock:
            job.event_seq += 1
            job.events.append((job.event_seq, payload))

    def _log(self, job: _Job, message: str, level: str = "info") -> None:
        self._emit(job, {"kind": "log", "level": level, "message": str(message)})

    def _status(self, job: _Job, text: str, tone: str = "blue") -> None:
        job.status_text = str(text)
        self._emit(job, {"kind": "status", "text": str(text), "tone": tone})

    def _progress(self, job: _Job, percent: float, status_text: Optional[str] = None) -> None:
        now = time.monotonic()
        if status_text is not None:
            job.status_text = str(status_text)
            self._emit(job, {"kind": "status", "text": str(status_text), "tone": "blue"})
        job.progress_pct = float(percent)
        if now - job.last_progress < 0.10:
            return
        job.last_progress = now
        self._emit(job, {"kind": "progress", "percent": int(max(0, min(100, percent)))})

    def _done(self, job: _Job, ok: bool, message: str, error: Optional[str] = None) -> None:
        self._emit(job, {
            "kind": "done",
            "ok": bool(ok),
            "message": str(message),
            "error": error,
        })
        job.outcome = "ok" if ok else ("cancelled" if error is None else "error")
        # Keep the job around until the frontend polls and drains its events;
        # poll() removes it lazily once the queue is empty. Popping immediately
        # would drop every queued event (logs, progress and done) for fast jobs.
        job.finished = True
        job.finished_at = time.monotonic()

    def _wait_if_paused(self, job: _Job) -> None:
        """Block the worker while the job is paused (used at bridge checkpoints)."""
        while job.pause_event.is_set():
            if job.abort_event.is_set():
                raise RuntimeError("ABORTED_BY_USER")
            time.sleep(0.1)

    def _confirm(self, job: _Job, message: str, *, title: str = "Confirmation",
                 yes: str = "Yes", no: str = "No") -> bool:
        """Ask the frontend to show a blocking confirmation on behalf of a worker.

        Queue jobs show their prompts inside the Worker popup; direct tool jobs
        show them in the console. Either way the wait is bounded: an Abort raises
        immediately and an unanswered prompt times out as a safe "No", so the
        queue can never hang forever on a confirmation nobody can answer.
        """
        confirm_timeout = 120.0
        token = uuid.uuid4().hex
        entry = {"event": Event(), "value": False}
        with self._lock:
            self._pending_confirms[token] = entry
        self._emit(job, {
            "kind": "confirm",
            "token": token,
            "title": title,
            "message": str(message),
            "yes": yes,
            "no": no,
        })
        job.pending_confirm = token
        try:
            deadline = time.monotonic() + confirm_timeout
            while not entry["event"].wait(0.2):
                if job.abort_event.is_set():
                    raise RuntimeError("ABORTED_BY_USER")
                if time.monotonic() > deadline:
                    self._emit(job, {"kind": "log", "level": "warn",
                                     "message": "Confirmation timed out; treated as 'No'."})
                    break
            value = bool(entry["value"])
        finally:
            with self._lock:
                self._pending_confirms.pop(token, None)
            job.pending_confirm = None
        return value

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

    # ------------------------------------------------------------------ #
    #  Frames -> Video
    # ------------------------------------------------------------------ #
    def _run_frames_to_video(self, job: _Job, p: dict) -> None:
        source = str(p.get("source_folder", "")).strip()
        output = str(p.get("output_file", "")).strip()
        fmt = str(p.get("output_type", "mp4_h264"))
        fps = p.get("fps", 30)
        crf = p.get("crf")
        threads = int(p.get("threads", 1) or 1)
        transparent = bool(p.get("transparent", False))
        q_mode = str(p.get("quality_mode", "crf")).lower()
        bitrate = p.get("bitrate")
        bg = p.get("background_color") or [0, 0, 0]
        gif_colors = int(p.get("gif_color_limit", 256) or 256)
        open_after = bool(p.get("open_explorer_after_conversion", False))
        try:
            total_cores = get_available_cores()
            threads = max(1, min(int(threads), total_cores))
        except Exception:
            threads = 1

        if not source:
            self._log(job, "Please select a source folder.", "error")
            self._done(job, False, "Missing source folder.", "Missing source folder.")
            return
        if not output:
            self._log(job, "Please select an output file.", "error")
            self._done(job, False, "Missing output file.", "Missing output file.")
            return
        try:
            fps_val = float(fps)
            if fps_val <= 0:
                raise ValueError()
        except Exception:
            self._log(job, "Please enter a valid FPS value.", "error")
            self._done(job, False, "Invalid FPS.", "Invalid FPS value.")
            return

        desired_ext = _OUTPUT_EXTENSIONS.get(fmt, ".mp4")
        root, ext = os.path.splitext(output)
        if ext.lower() != desired_ext:
            output = root + desired_ext
            self._log(job, f"Output extension adjusted to '{desired_ext}'.")

        source_mode = str(p.get("source_mode", "folder")).lower()
        if source_mode == "file":
            if not os.path.isfile(source):
                self._log(job, f"The source file '{source}' does not exist.", "error")
                self._done(job, False, "Source file does not exist.", "missing source file")
                return
            frames_dir = os.path.dirname(source) or "."
            self._log(job, f"Using directory of source file: {frames_dir}")
        else:
            if not os.path.isdir(source):
                self._log(job, f"The source folder '{source}' does not exist.", "error")
                self._done(job, False, "Source folder does not exist.", "missing source folder")
                return
            frames_dir = source

        try:
            all_files = [f for f in os.listdir(frames_dir) if not f.startswith(".")]
            total_frames = len(all_files)
        except Exception:
            total_frames = None

        out_dir = os.path.dirname(output) or "."
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
                self._log(job, f"Created output folder: {out_dir}")
            except Exception:
                self._log(job, f"The output folder '{out_dir}' could not be created.", "error")
                self._done(job, False, "Output folder does not exist.", "missing output folder")
                return
        if os.path.exists(output):
            if not self._confirm(job, f"The file '{output}' already exists. Do you want to replace it?",
                                 title="File Exists Warning", yes="Replace", no="Cancel"):
                self._log(job, "Conversion cancelled because the output file already exists.", "warn")
                self._done(job, False, "Cancelled by user.", None)
                return

        # GIF / APNG safety prompts
        if fmt == "gif":
            gif_colors = max(4, min(gif_colors, 256))
            if fps_val > 50:
                if not self._confirm(job, "GIFs with FPS over 50 may be very large and play poorly. Continue anyway?",
                                     title="High FPS Warning", yes="Continue", no="Cancel"):
                    self._done(job, False, "Cancelled by user.", None)
                    return
            if fps_val > 100:
                self._log(job, "GIF FPS cannot exceed 100. It will be clamped to 100.", "warn")
                fps_val = 100.0
            if total_frames is not None and total_frames > 300:
                if not self._confirm(job, f"GIF with {total_frames} frames may produce a very large file. Consider using WebM instead. Continue with GIF?",
                                     title="Many Frames Warning", yes="Continue", no="Cancel"):
                    self._done(job, False, "Cancelled by user.", None)
                    return
        if fmt == "apng":
            if fps_val > 50:
                if not self._confirm(job, "APNGs with FPS over 50 may be very large and play poorly. Continue anyway?",
                                     title="High FPS Warning", yes="Continue", no="Cancel"):
                    self._done(job, False, "Cancelled by user.", None)
                    return
            if fps_val > 100:
                self._log(job, "APNG FPS cannot exceed 100. It will be clamped to 100.", "warn")
                fps_val = 100.0
            if total_frames is not None and total_frames > 100:
                if not self._confirm(job, f"APNG with {total_frames} frames may produce a very large file. Consider using WebM instead. Continue with APNG?",
                                     title="Many Frames Warning", yes="Continue", no="Cancel"):
                    self._done(job, False, "Cancelled by user.", None)
                    return

        # CRF handling
        crf_int = crf
        lo, hi = _CRF_RANGES.get(fmt, (None, None))
        if crf is not None and fmt in ("mp4_h264", "mp4_av1", "webm", "webp"):
            try:
                crf_int = int(crf)
            except (ValueError, TypeError):
                self._log(job, "Please enter a valid integer CRF value.", "error")
                self._done(job, False, "Invalid CRF value.", "Invalid CRF value.")
                return
            crf_int = _clamp_crf(crf_int, 0, hi)

        # Bitrate sanity check
        bitrate_val = None
        if q_mode in ("bitrate", "2-pass vbr"):
            try:
                bitrate_val = int(bitrate)
                if bitrate_val <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                bitrate_val = 8000
            try:
                w, h = ImageToVideo.get_dimensions_from_first_frame_static(frames_dir)
                self._check_bitrate(job, bitrate_val, w, h, fps_val)
            except Exception as exc:
                self._log(job, f"Could not validate bitrate: {exc}", "warn")

        try:
            bg_color = (int(bg[0] or 0), int(bg[1] or 0), int(bg[2] or 0))
        except Exception:
            bg_color = (0, 0, 0)

        self._log(job, "Starting conversion...")
        self._log(job, f"Source: {source}")
        self._log(job, f"Output: {output}")
        self._log(job, f"Format: {fmt}")
        self._log(job, f"FPS: {fps_val}")
        if crf_int is not None and q_mode != "lossless":
            self._log(job, f"CRF: {crf_int}")
        self._log(job, f"Threads: {threads}")

        try:
            self._status(job, "Checking FFmpeg...", "blue")
            ImageToVideo.ffmpeg_checker()
            self._log(job, "FFmpeg check passed.")
        except Exception as exc:
            self._status(job, "FFmpeg is missing", "red")
            self._log(job, str(exc), "error")
            self._done(job, False, "FFmpeg not found.", str(exc))
            return

        self._status(job, "Converting video...", "blue")
        try:
            ImageToVideo.frames_to_video(
                frames_dir, output, fmt, transparent, float(fps_val), crf_int,
                progress_callback=lambda pct: self._progress(job, pct,
                                                             f"Converting frames to video... {pct}%"),
                amount_threads=threads,
                abort_event=job.abort_event,
                pause_event=job.pause_event,
                gif_max_colors=gif_colors if fmt == "gif" else None,
                apng_transparent=transparent,
                gif_transparent=transparent,
                webp_transparent=transparent,
                background_color=bg_color,
                quality_mode=q_mode,
                bitrate=bitrate_val,
            )
            if job.abort_event.is_set():
                self._status(job, "Conversion aborted by user.", "orange")
                self._log(job, "Conversion aborted by user.", "warn")
                self._done(job, False, "Aborted by user.", None)
                return
            self._progress(job, 100, "Video converted successfully!")
            self._status(job, "Video converted successfully!", "green")
            self._log(job, "Conversion completed successfully!")
            if open_after:
                self._open_explorer(output)
                self._log(job, f"Opened file explorer: {os.path.dirname(output)}")
            self._done(job, True, "Video has been converted successfully!")
        except Exception as exc:
            self._log(job, "ERROR: Conversion failed!", "error")
            if "ABORTED_BY_USER" in str(exc):
                self._status(job, "Conversion aborted by user.", "orange")
                self._log(job, "Conversion aborted by user.", "warn")
                self._done(job, False, "Aborted by user.", None)
            else:
                detail = self._format_exception(exc)
                self._log(job, detail, "error")
                self._status(job, "Error occurred during conversion", "red")
                self._done(job, False, "Conversion failed.", detail)

    def _check_bitrate(self, job: _Job, bitrate_bps, width, height, fps) -> None:
        total_pixels = width * height
        try:
            if total_pixels > 0 and fps > 0:
                bpp = (bitrate_bps * 1000) / (total_pixels * fps)
                if bpp > 0.3:
                    if not self._confirm(
                            job,
                            "Bitrate is too high for the given resolution and FPS that may cause the file size to be too large and issues with playback. Do you want to continue?",
                            title="Bitrate too high",
                            yes="Continue", no="Cancel"):
                        raise RuntimeError("ABORTED_BY_USER")
                elif bpp < 0.03:
                    if not self._confirm(
                            job,
                            "Bitrate is too low for the given resolution and FPS that may cause blurry video. Do you want to continue?",
                            title="Bitrate too low",
                            yes="Continue", no="Cancel"):
                        raise RuntimeError("ABORTED_BY_USER")
        except (FileNotFoundError, OSError):
            pass

    # ------------------------------------------------------------------ #
    #  Image Splitter
    # ------------------------------------------------------------------ #
    def _run_image_splitter(self, job: _Job, p: dict) -> None:
        source = str(p.get("source", "")).strip()
        out = str(p.get("output", "")).strip()
        mode = str(p.get("mode", "grid"))
        fmt = str(p.get("image_format", "png")).lower()
        source_mode = str(p.get("source_mode", "single"))
        if not source or not out:
            self._log(job, "Source and output must be set.", "error")
            self._done(job, False, "Missing source or output.", "Missing source or output.")
            return

        try:
            quality = int(p.get("quality", 95))
            quality = max(1, min(100, quality))
        except (ValueError, TypeError):
            quality = 95
        try:
            compress_level = int(p.get("png_compress_level", 6))
            compress_level = max(0, min(9, compress_level))
        except (ValueError, TypeError):
            compress_level = 6
        try:
            bleed_radius = int(p.get("bleed_radius", 0) or 0)
            bleed_radius = max(0, bleed_radius)
        except (ValueError, TypeError):
            bleed_radius = 0

        export = ImageExportSettings(
            image_format=fmt,
            quality=quality,
            png_compress_level=compress_level,
            discard_blank_tiles=bool(p.get("discard_blank_tiles", False)),
            tga_compression=str(p.get("tga_compression", "none")),
            tiff_compression=str(p.get("tiff_compression", "none")),
            bleed_radius=bleed_radius,
        )

        save_executor = ThreadPoolExecutor(max_workers=4)
        splitter = ImageSplitter(
            callback=lambda status: self._split_status(job, status),
            callback_executor=None,
            abort_event=job.abort_event,
            pause_event=job.pause_event,
            save_executor=save_executor,
            confirm_callback=lambda msg: self._confirm(job, msg, title="File Count Warning",
                                                       yes="Proceed", no="Cancel"),
        )

        def run_file(path: str) -> tuple[int, int]:
            if mode == "grid":
                rows = int(p.get("rows", 1) or 1)
                cols = int(p.get("columns", 1) or 1)
                res_mode = str(p.get("resolution_mode", "allow_variation") or "allow_variation")
                pad_mode = str(p.get("padding_mode", "edge") or "edge")
                result = splitter.split_grid(path, out, rows, cols,
                                             resolution_mode=res_mode, padding_mode=pad_mode,
                                             export=export,
                                             naming_template=str(p.get("naming_template",
                                                                       "{basename}_r{row}_c{col}_w{width}_h{height}.{ext}")))
            elif mode == "tile_size":
                tw = int(p.get("tile_width", 512) or 512)
                th = int(p.get("tile_height", 512) or 512)
                res_mode = str(p.get("resolution_mode", "allow_variation") or "allow_variation")
                pad_mode = str(p.get("padding_mode", "edge") or "edge")
                result = splitter.split_dimensions(path, out, tw, th,
                                                   resolution_mode=res_mode, padding_mode=pad_mode,
                                                   export=export,
                                                   naming_template=str(p.get("naming_template",
                                                                             "{basename}_r{row}_c{col}_w{width}_h{height}.{ext}")))
            else:  # alpha_components
                alpha = int(p.get("alpha_threshold", 0) or 0)
                result = splitter.split_transparent_components(
                    path, out, alpha_threshold=alpha, export=export,
                    naming_template=str(p.get("naming_template", "{basename}_tile_{index}.{ext}")))
            return len(result.tiles), 0

        try:
            if source_mode == "bulk":
                if not os.path.isdir(source):
                    self._log(job, f"Error: Source folder does not exist: {source}", "error")
                    self._done(job, False, "Source folder does not exist.", "missing source folder")
                    return
                image_files = [f for f in os.listdir(source)
                               if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".tga", ".tiff", ".bmp"))]
                if not image_files:
                    self._log(job, "Error: No image files found in source folder", "error")
                    self._done(job, False, "No image files found.", "no image files")
                    return
                self._log(job, f"Found {len(image_files)} images to process")
                for idx, img_file in enumerate(image_files, 1):
                    self._wait_if_paused(job)
                    if job.abort_event.is_set():
                        self._log(job, "Abort requested; stopping bulk processing.", "warn")
                        break
                    img_path = os.path.join(source, img_file)
                    self._log(job, f"Processing {idx}/{len(image_files)}: {img_file}")
                    try:
                        run_file(img_path)
                        self._log(job, f"Completed {idx}/{len(image_files)}: {img_file}")
                    except SplitAbortedError:
                        raise
                    except Exception as exc:
                        self._log(job, f"Error processing {img_file}: {exc}", "error")
                        self._log(job, traceback.format_exc(), "error")
                self._log(job, f"Bulk split complete. Processed {len(image_files)} images.")
            else:
                if not os.path.isfile(source):
                    self._log(job, f"Error: Source file does not exist: {source}", "error")
                    self._done(job, False, "Source file does not exist.", "missing source file")
                    return
                self._log(job, "Starting split...")
                run_file(source)
                self._log(job, "Split complete.")

            if job.abort_event.is_set():
                self._log(job, "Split operation aborted by user.", "warn")
                self._status(job, "Split operation aborted by user.", "orange")
                self._done(job, False, "Aborted by user.", None)
                return
            self._progress(job, 100, "Split complete!")
            if p.get("open_explorer_after_conversion", False):
                self._open_explorer(out)
            self._status(job, "Split completed successfully!", "green")
            self._done(job, True, "Split completed successfully!")
        except SplitAbortedError as exc:
            if job.abort_event.is_set():
                self._status(job, "Split aborted.", "orange")
                self._done(job, False, "Aborted by user.", None)
            else:
                self._log(job, f"Split aborted: {exc}", "warn")
                self._status(job, "Split aborted.", "orange")
                self._done(job, False, "Split aborted.", str(exc))
        except Exception as exc:
            self._log(job, f"Error: {exc}", "error")
            self._log(job, traceback.format_exc(), "error")
            if job.abort_event.is_set():
                self._log(job, "Split operation aborted by user.", "warn")
                self._status(job, "Split operation aborted by user.", "orange")
                self._done(job, False, "Aborted by user.", None)
            else:
                self._status(job, "Split failed.", "red")
                self._done(job, False, "Split failed.", str(exc))
        finally:
            try:
                if job.abort_event.is_set():
                    save_executor.shutdown(wait=False, cancel_futures=True)
                else:
                    save_executor.shutdown(wait=True)
            except Exception:
                pass

    def _split_status(self, job: _Job, status: SplitStatus) -> None:
        event = str(status.event).lower()
        if event in {"warning", "error", "aborted", "completed", "complete", "finished", "failed"}:
            msg = f"[{status.event}] {status.message}"
            if status.total:
                msg += f" ({status.completed}/{status.total})"
            self._log(job, msg, "error" if event == "error" else
                      ("warn" if event in {"warning", "aborted", "failed"} else "info"))
            if status.total:
                self._progress(job, status.completed / status.total * 100)
        elif status.total:
            self._progress(job, status.completed / status.total * 100)

    # ------------------------------------------------------------------ #
    #  Texture Mipmap
    # ------------------------------------------------------------------ #
    def _run_texture_mipmap(self, job: _Job, p: dict) -> None:
        source = str(p.get("source", "")).strip()
        out = str(p.get("output", "")).strip()
        source_mode = str(p.get("source_mode", "single"))
        if not source or not out:
            self._log(job, "Source and output must be set.", "error")
            self._done(job, False, "Missing source or output.", "Missing source or output.")
            return

        fmt = str(p.get("image_format", "png")).lower()
        try:
            quality = int(p.get("quality", 95))
            quality = max(1, min(100, quality))
        except (ValueError, TypeError):
            quality = 95
        try:
            compress_level = int(p.get("png_compress_level", 6))
            compress_level = max(0, min(9, compress_level))
        except (ValueError, TypeError):
            compress_level = 6

        export = TextureExportSettings(
            image_format=fmt,
            quality=quality,
            png_compress_level=compress_level,
            retain_alpha=bool(p.get("retain_alpha", True)),
            tga_compression=str(p.get("tga_compression", "none")),
            tiff_compression=str(p.get("tiff_compression", "none")),
        )

        gen = TextureMipMapGenerator(callback=lambda st: self._mip_status(job, st),
                                     abort_event=job.abort_event,
                                     pause_event=job.pause_event)
        naming = str(p.get("naming_template", "{texture_name}_mip{level}.{ext}"))
        normal_map = bool(p.get("normal_map", False))
        npot_mode = str(p.get("npot_mode", "none") or "none")
        res_filter = str(p.get("resample_filter", "lanczos") or "lanczos")
        export_dds = bool(p.get("export_dds", False))

        def run_file(path: str) -> None:
            gen.export(path, out, normal_map=normal_map, npot_mode=npot_mode,
                       resample_filter=res_filter, export=export,
                       naming_template=naming, export_dds=export_dds)

        try:
            if source_mode == "bulk":
                if not os.path.isdir(source):
                    self._log(job, f"Error: Source folder does not exist: {source}", "error")
                    self._done(job, False, "Source folder does not exist.", "missing source folder")
                    return
                image_files = [f for f in os.listdir(source)
                               if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".tga", ".tiff", ".bmp"))]
                if not image_files:
                    self._log(job, "Error: No image files found in source folder", "error")
                    self._done(job, False, "No image files found.", "no image files")
                    return
                self._log(job, f"Found {len(image_files)} textures to process")
                for idx, img_file in enumerate(image_files, 1):
                    self._wait_if_paused(job)
                    if job.abort_event.is_set():
                        self._log(job, "Abort requested; stopping bulk processing.", "warn")
                        break
                    img_path = os.path.join(source, img_file)
                    self._log(job, f"Processing {idx}/{len(image_files)}: {img_file}")
                    try:
                        run_file(img_path)
                        self._log(job, f"Completed {idx}/{len(image_files)}: {img_file}")
                    except Exception as exc:
                        self._log(job, f"Error processing {img_file}: {exc}", "error")
                self._log(job, f"Bulk mipmap generation complete. Processed {len(image_files)} textures.")
            else:
                if not os.path.isfile(source):
                    self._log(job, f"Error: Source file does not exist: {source}", "error")
                    self._done(job, False, "Source file does not exist.", "missing source file")
                    return
                self._log(job, "Starting mipmap generation...")
                run_file(source)
                self._log(job, "Mipmap generation complete.")

            if job.abort_event.is_set():
                self._log(job, "Mipmap generation aborted by user.", "warn")
                self._status(job, "Mipmap generation aborted by user.", "orange")
                self._done(job, False, "Aborted by user.", None)
                return
            self._progress(job, 100, "Mipmap generation complete!")
            if p.get("open_explorer_after_conversion", False):
                self._open_explorer(out)
            self._status(job, "Mipmaps generated successfully!", "green")
            self._done(job, True, "Mipmap generation completed successfully!")
        except Exception as exc:
            if job.abort_event.is_set() or "ABORTED_BY_USER" in str(exc):
                self._log(job, "Mipmap generation aborted by user.", "warn")
                self._status(job, "Mipmap generation aborted by user.", "orange")
                self._done(job, False, "Aborted by user.", None)
                return
            self._log(job, f"Error: {exc}", "error")
            self._log(job, traceback.format_exc(), "error")
            self._status(job, "Mipmap generation failed.", "red")
            self._done(job, False, "Mipmap generation failed.", str(exc))

    def _mip_status(self, job: _Job, status: MipStatus) -> None:
        event = str(status.event).lower()
        if event in {"level_saved", "level_generated"}:
            self._log(job, f"[{status.event}] Level {status.level}: {status.message} Size={status.size[0]}x{status.size[1]}")
        elif event == "dds_fallback":
            self._log(job, f"[{status.event}] {status.message}", "warn")
        else:
            self._log(job, repr(status))

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
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