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

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from collections import deque
from threading import Event, Lock, RLock, Thread
from typing import Any, Optional

import psutil

from core.interop import InteropContext, InteropError
from core.lua_bridge import run_lua_script, run_lua_action
from core.scanner import (
    load_utilities as _scan_utilities,
    descriptor as _util_descriptor,
    UTILITIES_DIR as _UTILITIES_DIR,
    ICON_TARGET_DIR as _FRONTEND_ICON_DIR,
)
from app.settings import (
    load_settings, save_settings, load_presets, save_presets,
    get_history, add_to_history, generate_unique_preset_name,
    load_favorites, toggle_favorite, record_used,
    load_app_theme, save_app_theme,
    load_app_settings, save_app_settings,
    get_storage_stats, clear_all_data, clear_all_presets, clear_all_history,
    load_worker_queue, save_worker_queue,
    get_store_fetchres_path, get_store_icons_dir,
)
from app.system import (
    get_dropdown_core_options, get_cpu_name,
    detect_ffmpeg_binaries,
)
from app.info import APP_TITLE, APP_SUBTITLE, MAIN_CONTRIBUTOR, VERSION, HOME_VIEW_ID, GITHUB_REPOSITORY_URL
from app.updates import check_for_updates as run_update_check
from app.python_libraries import (
    python_environment as _py_environment,
    pypi_search as _pypi_search,
    pypi_install as _pypi_install,
    pypi_uninstall as _pypi_uninstall,
    refresh_pypi_index as _refresh_pypi_index,
    utility_dependencies as _utility_dependencies,
    pypi_progress as _pypi_progress,
    python_audit as _pypi_audit,
)

# The Lycan Utilities Store catalog is NOT hardcoded: it is sourced from the
# persisted fetch-result file (userdata/lycan_utilities_store/lycan_utilities_store_fetchres.json)
# which the online loader rebuilds from each utility folder's manifest,
# utility_description.json and synced icon. On offline reads the same file
# becomes the source of truth so the UI always has a real fetch artifact.
_STORE_FREE_MARKET = True


_IMAGE_FILE_TYPES = ("Images (*.png;*.jpg;*.jpeg;*.webp;*.tga;*.tiff;*.bmp)",)
_ALL_FILE_TYPES = ("All files (*.*)",)

# Events retained per job for replay. Consumers poll with a cursor, so even a
# late-attaching surface (Worker popup, tool tab) sees recent output.
EVENT_BUFFER_MAX = 2000

# How long a finished job stays in self._jobs so a tool tab attaching after
# completion can still replay its log/progress. get_queue() prunes past this.
_FINISHED_JOB_GRACE = 120.0


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


def _tool_title(tool: str, utilities: Optional[dict] = None) -> str:
    title = None
    if utilities:
        util = utilities.get(tool)
        if util:
            title = (util.get("manifest") or {}).get("title")
    return title or tool


def _tool_icon_file(tool: str, utilities: Optional[dict] = None) -> str:
    icon = ""
    if utilities and utilities.get(tool):
        util = utilities.get(tool)
        icon = util.get("icon_rel") or ""
    return icon or ""


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
        # Modular hub: utilities scanned from utilities/ (validated + SHA-256 cached).
        self._utilities_scan = _scan_utilities()
        self._utilities: dict[str, dict] = self._utilities_scan.get("utilities") or {}
        # Utilities that failed validation/loading, surfaced as dashboard error
        # cards that open the load-error tab.
        self._utilities_broken: dict[str, dict] = self._utilities_scan.get("broken") or {}
        # Live-reload baseline of the utilities folder. When the folder, a .py
        # file changes a restart is needed; json/lua/asset changes only need a
        # hard refresh (backend rescans + frontend reloads). The baseline is
        # re-snapshot after every refresh-class rescan so the scanner's own
        # cache writes never re-trigger a reload loop.
        self._utils_baseline = self._snapshot_utilities_dir()
        self._utils_restart_pending = False
        self._utils_change_lock = Lock()
        # Per-utility engine modules (named "engine" inside each utility folder).
        # Loaded once per utility; sys.modules["engine"] is temporarily bound to
        # the right one while its runtime executes, then restored.
        self._util_engine_lock = RLock()
        self._util_engines: dict[str, Any] = {}
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
        """Tool hub: every validated utility from utilities/."""
        return self._util_descriptors()

    def _util_descriptors(self) -> list[dict]:
        return [_util_descriptor(entry) for entry in self._utilities.values()]

    def get_dashboard(self) -> dict:
        favorites = load_favorites()
        from app.settings import load_last_used
        last_used = load_last_used()
        tools = []
        for desc in self._util_descriptors():
            mid = desc["id"]
            item = dict(desc)
            item["favorite"] = bool(favorites.get(mid, False))
            item["last_used"] = last_used.get(mid)
            item["coming_soon"] = not bool(desc.get("has_runtime"))
            tools.append(item)
        tools.extend(self._broken_descriptors())
        system = self.get_system_stats()
        return {
            "tools": tools,
            "theme": load_app_theme(),
            "app": self.get_app(),
            "cpu_name": system["cpu_name"],
        }

    # ------------------------------------------------------------------ #
    #  Utilities folder: open, live-reload watcher
    # ------------------------------------------------------------------ #
    _UTIL_IGNORED = {"utilities_cache.json", "util_lists_cache-lock.json"}

    def open_utilities_folder(self, utility_id: str = "") -> dict:
        """Reveal the utilities folder — or one utility's folder — in the OS
        file explorer. Pass ``utility_id`` to land directly inside that
        utility's module directory instead of the utilities root."""
        if not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR):
            return {"ok": False, "reason": "not_found", "path": _UTILITIES_DIR}
        if utility_id:
            resolved = self._resolve_utility_dir(str(utility_id))
            if resolved and os.path.isdir(resolved):
                self._open_explorer(resolved)
                return {"ok": True, "path": resolved}
        self._open_explorer(_UTILITIES_DIR)
        return {"ok": True, "path": _UTILITIES_DIR}

    def _resolve_utility_dir(self, utility_id: str) -> str | None:
        """Return the module directory for a utility id (installed or broken)."""
        entry = self._utilities.get(utility_id)
        if isinstance(entry, dict) and entry.get("dir"):
            return str(entry["dir"])
        broken = self._utilities_broken.get(utility_id)
        if isinstance(broken, dict) and broken.get("dir"):
            return str(broken["dir"])
        return None

    def _broken_descriptors(self) -> list[dict]:
        """Dashboard cards for utilities that failed to load (load-error tab)."""
        result = []
        for mid, entry in self._utilities_broken.items():
            result.append({
                "id": entry.get("id") or mid,
                "title": entry.get("title") or mid,
                "description": "This utility failed to load. Open it to see the parser errors.",
                "icon": "\u26a0\ufe0f",
                "icon_file": "",
                "badge": "Error",
                "tags": [],
                "version": "",
                "form_schema": None,
                "has_runtime": False,
                "runtime_file": None,
                "coming_soon": False,
                "favorite": False,
                "last_used": None,
                "has_error": True,
                "error_messages": list(entry.get("errors") or []),
                "error_file": str(entry.get("source") or ""),
                "error_snippet": list(entry.get("snippet") or []),
                "error_snippet_lines": list(entry.get("snippet_lines") or []),
            })
        return result

    # ------------------------------------------------------------------ #
    #  Lycan Utilities Store
    # ------------------------------------------------------------------ #
    def _store_installed_ids(self) -> set[str]:
        """Ids that are locally installed (valid utilities in utilities/)."""
        return set(self._utilities.keys())

    @staticmethod
    def _store_load_json(path: str):
        """Best-effort JSON read for store data (manifest/description/fetchres)."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _store_load_manifest(module_dir: str) -> dict:
        """Read a utility manifest.json for the store catalog (broken ones ignored)."""
        data = Api._store_load_json(os.path.join(module_dir, "manifest.json"))
        return data if isinstance(data, dict) else {}

    def _store_load_description(self, folder: str) -> dict:
        """Read utilities/<folder>/utility_description.json for the store listing."""
        if not _UTILITIES_DIR:
            return {}
        data = self._store_load_json(os.path.join(_UTILITIES_DIR, folder, "utility_description.json"))
        return data if isinstance(data, dict) else {}

    def _store_sync_icons(self, items: list[dict]) -> None:
        """Mirror each utility's icon into the store's userdata icons folder.

        Icons are sourced from the scanner-synced frontend mirror
        (frontend/public/assets/.cache/icons) and copied into
        userdata/lycan_utilities_store/icons/<id><ext> so the store keeps its
        own persisted icon store (no heroicon names anywhere).
        """
        icons_dir = get_store_icons_dir()
        try:
            os.makedirs(icons_dir, exist_ok=True)
        except OSError:
            return
        for item in items:
            icon = item.get("icon") or ""
            if not icon.startswith("assets/"):
                continue
            src = os.path.join(_FRONTEND_ICON_DIR, os.path.basename(icon))
            if not os.path.isfile(src):
                continue
            ext = os.path.splitext(src)[1] or ".png"
            target = os.path.join(icons_dir, str(item["id"]) + ext)
            try:
                if not os.path.exists(target):
                    shutil.copy2(src, target)
            except OSError:
                continue

    def _store_fetch_items(self) -> list[dict]:
        """Build the store catalog from the real utilities directory.

        Each entry merges the utility's manifest.json with its
        ``utility_description.json`` (when present) and the scanner-synced
        icon path. This is the data that gets persisted as the fetch result.
        """
        items: list[dict] = []
        if not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR):
            return items
        installed = self._store_installed_ids()
        for name in sorted(os.listdir(_UTILITIES_DIR)):
            module_dir = os.path.join(_UTILITIES_DIR, name)
            if not os.path.isdir(module_dir):
                continue
            manifest = self._store_load_manifest(module_dir)
            description = self._store_load_description(name)
            mid = str(manifest.get("id") or name)
            descriptor = self._utilities.get(mid) or {}
            items.append({
                "id": mid,
                "title": description.get("title") or manifest.get("title") or mid,
                "description": description.get("description") or manifest.get("description") or "",
                "icon": descriptor.get("icon_rel") or "",
                "version": str(manifest.get("version") or "1.0.0"),
                "credits": description.get("credits") or "Lycan Utilities",
                "size_estimate": description.get("size_estimate") or "~2 MB",
                "installed": mid in installed,
            })
        return items

    def _store_write_fetchres(self, payload: dict) -> None:
        """Persist the fetched catalog to userdata/lycan_utilities_store/."""
        try:
            os.makedirs(os.path.dirname(get_store_fetchres_path()), exist_ok=True)
            with open(get_store_fetchres_path(), "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        except OSError:
            # Persistence is best-effort; a failing disk never blocks the store UI.
            pass

    def _store_read_fetchres(self) -> dict:
        """Load the last fetched catalog snapshot from disk (may be {}})."""
        if not os.path.isfile(get_store_fetchres_path()):
            return {}
        data = self._store_load_json(get_store_fetchres_path())
        return data if isinstance(data, dict) else {}

    def get_utilities_store(self) -> dict:
        """Return the Lycan Utilities Store catalog.

        * Online fetch (``general.allow_internet``): the catalog is rebuilt
          from utilities/ folders plus their utility_description.json files,
          icons are mirrored into userdata/lycan_utilities_store/icons/, and
          the result is persisted to ``lycan_utilities_store_fetchres.json``.
        * Offline: the last persisted fetch-result is used and filtered to
          locally installed utilities (no download).
        """
        general = (load_app_settings().get("general") or {})
        internet = bool(general.get("allow_internet", False))
        installed = self._store_installed_ids()

        if internet:
            items = self._store_fetch_items()
            self._store_sync_icons(items)
            previous = self._store_read_fetchres()
            payload = {
                "ok": True,
                "internet": True,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "items": items,
                "actions": previous.get("actions") or [],
            }
            self._store_write_fetchres(payload)
            return payload

        payload = self._store_read_fetchres()
        items = [entry for entry in payload.get("items") or [] if entry.get("id") in installed]
        return {
            "ok": True,
            "internet": False,
            "fetched_at": payload.get("fetched_at") or "",
            "items": items,
        }

    def store_download(self, item_id: str) -> dict:
        """Simulate downloading/updating a store utility.

        This is a demo store; the action is recorded in the persisted fetch
        result and reported back. Downloads require internet access.
        """
        general = (load_app_settings().get("general") or {})
        if not general.get("allow_internet", False):
            return {"ok": False, "reason": "internet_disabled"}
        entry = next((e for e in self._store_fetch_items() if e["id"] == item_id), None)
        if not entry:
            return {"ok": False, "reason": "not_found"}
        existing = self._store_read_fetchres()
        installed = self._store_installed_ids()
        is_update = item_id in installed
        actions = list(existing.get("actions") or [])
        actions.append({
            "item_id": item_id,
            "action": "update" if is_update else "download",
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        if len(actions) > 50:
            actions = actions[-50:]
        existing["actions"] = actions
        self._store_write_fetchres(dict(existing))
        return {
            "ok": True,
            "item_id": item_id,
            "action": "update" if is_update else "download",
            "free": bool(_STORE_FREE_MARKET),
            "version": entry.get("version"),
        }

    def store_learn_more(self, item_id: str) -> dict:
        """Return the full details card for a store item from real catalog data."""
        entry = next((e for e in self._store_fetch_items() if e["id"] == item_id), None)
        if not entry:
            return {"ok": False, "reason": "not_found"}
        return {
            "ok": True,
            "title": entry["title"],
            "description": entry["description"],
            "version": entry["version"],
            "free": bool(_STORE_FREE_MARKET),
            "credits": entry.get("credits") or "Lycan Utilities",
            "size_estimate": entry.get("size_estimate") or "~2 MB",
        }

    @staticmethod
    def _snapshot_utilities_dir() -> dict:
        """Cheap mtime+size snapshot of every module file under utilities/.

        The two scanner cache files and Python bytecode are excluded so the
        scanner writing its own cache can never be mistaken for a user change.
        """
        folders: set[str] = set()
        files: dict[str, tuple] = {}
        if not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR):
            return {"folders": folders, "files": files}
        for name in sorted(os.listdir(_UTILITIES_DIR)):
            module_dir = os.path.join(_UTILITIES_DIR, name)
            if not os.path.isdir(module_dir):
                continue
            folders.add(name)
            for root, dirs, names in os.walk(module_dir):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fname in names:
                    if fname.endswith(".pyc"):
                        continue
                    rel = os.path.relpath(os.path.join(root, fname), _UTILITIES_DIR)
                    if rel.replace("\\", "/") in Api._UTIL_IGNORED:
                        continue
                    try:
                        st = os.stat(os.path.join(root, fname))
                        files[rel] = (st.st_mtime_ns, st.st_size)
                    except OSError:
                        continue
        return {"folders": folders, "files": files}

    @staticmethod
    def _diff_utilities(before: dict, after: dict) -> list[dict]:
        changes: list[dict] = []
        old_folders = set(before.get("folders") or [])
        new_folders = set(after.get("folders") or [])
        old_files = before.get("files") or {}
        new_files = after.get("files") or {}
        for name in sorted(new_folders - old_folders):
            changes.append({"path": name + os.sep, "kind": "add", "cause": "folder"})
        for name in sorted(old_folders - new_folders):
            changes.append({"path": name + os.sep, "kind": "remove", "cause": "folder"})
        for rel in sorted(set(old_files) | set(new_files)):
            before_stat = old_files.get(rel)
            after_stat = new_files.get(rel)
            if before_stat == after_stat:
                continue
            kind = "modify" if before_stat is not None and after_stat is not None else (
                "add" if before_stat is None else "remove"
            )
            ext = os.path.splitext(rel)[1].lower()
            cause = ("py" if ext == ".py"
                     else "lua" if ext == ".lua"
                     else "json" if ext == ".json"
                     else "asset")
            changes.append({"path": rel, "kind": kind, "cause": cause})
        return changes[:40]

    def utilities_changes(self) -> dict:
        """Poll the utilities folder and classify what changed.

        Returns ``{action: None|"restart"|"refresh", changes:[...]}``. New
        utility folders and ``.py`` edits require an app restart; json/lua/asset
        updates only need a backend rescan plus a frontend hard refresh. The
        baseline is advanced inside this call for refresh-class changes, so the
        scanner's own cache rewrite never causes a reload loop.
        """
        with self._utils_change_lock:
            current = self._snapshot_utilities_dir()
            changes = self._diff_utilities(self._utils_baseline, current)
            if not changes:
                return {"action": None, "changes": []}
            requires_restart = self._utils_restart_pending or any(
                (c["kind"] == "add" and c["cause"] == "folder") or c["cause"] == "py"
                for c in changes
            )
            if requires_restart:
                self._utils_restart_pending = True
                return {"action": "restart", "changes": changes}
            # Refresh-class only: rescan now so the reloaded frontend sees the
            # new manifest/schema/icons, then re-baseline post-rescan.
            try:
                self._utilities_scan = _scan_utilities(force_scan=True)
                self._utilities = self._utilities_scan.get("utilities") or {}
                self._utilities_broken = self._utilities_scan.get("broken") or {}
            except Exception:
                traceback.print_exc()
            self._utils_baseline = self._snapshot_utilities_dir()
            return {"action": "refresh", "changes": changes}

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
    #  Python Libraries (Settings store + pip management)
    # ------------------------------------------------------------------ #
    def get_python_libraries(self, force: bool = False) -> dict:
        """Settings > Python Libraries: interpreter info and per-utility deps.

        The dependency status is cached (see ``utility_dependencies``) so
        reopening or switching away from the category reuses the last fetch;
        pass ``force=True`` right after an install/uninstall to recompute.
        """
        try:
            env = _py_environment()
        except Exception as exc:
            env = {"ok": False, "reason": str(exc)}
        try:
            utilities = _utility_dependencies(self._utilities, force=bool(force))
        except Exception as exc:
            utilities = [{"error": str(exc)}]
        return {
            "ok": True,
            "environment": env,
            "utilities": utilities,
        }

    def get_pypi_progress(self) -> Optional[dict]:
        """Live progress of the current pip install/uninstall, if any."""
        try:
            return _pypi_progress()
        except Exception:
            return None

    def pypi_audit(self, force: bool = False) -> dict:
        """Settings > Python Libraries: re-run the vulnerability scan.

        Audits every installed package via pip-audit against the OSV/PyPI
        advisory database and returns ``{ok, state, total, affected,
        fetched_at}``. ``force=True`` bypasses the snapshot cache (the UI's
        "Scan now" button).
        """
        try:
            return _pypi_audit(force=bool(force))
        except Exception as exc:
            return {"ok": False, "state": "failed", "reason": str(exc)}

    def pypi_search(self, query: str, page: int = 1, per_page: int = 12,
                    force: bool = False) -> dict:
        """Search the cached PyPI Simple index; one enriched page of results.

        ``force=True`` bypasses the result snapshot cache (used after
        install/uninstall so installed/outdated badges refresh).
        """
        try:
            return _pypi_search(str(query), page, per_page, force=bool(force))
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def refresh_pypi_index(self, force: bool = True) -> dict:
        """Download/refresh the official PyPI Simple index cache used by search."""
        try:
            return _refresh_pypi_index(force=bool(force))
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def pypi_install(self, package: str, scope: str = "local",
                     upgrade: bool = False, confirmed: bool = False,
                     batch_total: int = 1, batch_done: int = 0,
                     vuln_ack: bool = False) -> dict:
        """Install/upgrade a Python package via pip.

        * scope local (default): the app's own .venv (immediately importable).
        * scope global: the base/system interpreter (requires ``confirmed``).
        * batch_total/batch_done: overall progress across a bulk install.
        * vuln_ack: the candidate was pre-scanned with pip-audit and the user
          confirmed the two-step "Proceed anyway?" prompt.
        """
        try:
            return _pypi_install(str(package), scope=str(scope),
                                 upgrade=bool(upgrade), confirmed=bool(confirmed),
                                 batch_total=int(batch_total or 1),
                                 batch_done=int(batch_done or 0),
                                 vuln_ack=bool(vuln_ack))
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def pypi_uninstall(self, package: str, scope: str = "local",
                       confirmed: bool = False, batch_total: int = 1,
                       batch_done: int = 0) -> dict:
        """Uninstall a Python package via pip (core app packages are protected)."""
        try:
            return _pypi_uninstall(str(package), scope=str(scope),
                                   confirmed=bool(confirmed),
                                   batch_total=int(batch_total or 1),
                                   batch_done=int(batch_done or 0))
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

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
            from app.screenpick import wait_for_screen_pick
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
        """Return the run-loop for a utility id, or None if unsupported."""
        util = self._utilities.get(tool)
        if util and util.get("runtime_ok"):
            return self._run_utility
        return None

    def _spawn_run(self, job: _Job) -> None:
        thread = Thread(target=self._runner_for(job.tool), args=(job, job.params), daemon=True)
        thread.start()

    # ------------------------------------------------------------------ #
    #  Modular runtime execution (utilities/ + interop bridge)
    # ------------------------------------------------------------------ #
    def _load_engine_module(self, tool: str, module_dir: str):
        """Load a utility's ``engine.py`` once, keyed by tool id."""
        cached = self._util_engines.get(tool)
        if cached is not None:
            return cached
        engine_path = os.path.join(module_dir, "engine.py")
        if not os.path.isfile(engine_path):
            return None
        with self._util_engine_lock:
            cached = self._util_engines.get(tool)
            if cached is not None:
                return cached
            spec = importlib.util.spec_from_file_location(f"util_{tool}_engine", engine_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                sys.modules.pop(spec.name, None)
            self._util_engines[tool] = module
            return module

    def _run_utility(self, job: _Job, params: dict) -> None:
        util = self._utilities.get(job.tool)
        if not util or not util.get("runtime_ok"):
            self._log(job, f"No runtime available for '{job.tool}'.", "warn")
            self._done(job, False, "Runtime unavailable.", "utility missing runtime")
            return
        module_dir = util.get("dir")
        handlers = (util.get("manifest") or {}).get("handlers") or {}
        result = None
        lua_name = handlers.get("lua")
        # Prefer the Lua hook when it is bound and a Lua runtime is loadable.
        if lua_name and isinstance(lua_name, str) and lua_name:
            lua_path = os.path.join(module_dir, lua_name)
            if os.path.isfile(lua_path):
                ctx = InteropContext(self, job, params)
                cr = run_lua_script(ctx, lua_path)
                if cr.get("ok"):
                    result = cr.get("result")
                elif cr.get("reason") == "lua_runtime_missing":
                    self._log(job,
                              f"Lua runtime missing; falling back to the Python hook "
                              f"({util.get('runtime_path') or 'runtime.py'}).", "info")
                else:
                    # The Lua hook halted (throw_error already set status/logs).
                    if not job.finished:
                        reason = cr.get("reason") or "Lua hook failed."
                        if cr.get("interop"):
                            self._done(job, False, reason, reason)
                        else:
                            self._log(job, f"Lua hook failed: {reason}", "error")
                            self._done(job, False, "Runtime crashed.", reason)
                    return
        if result is None:
            result = self._run_python_hook(job, params, module_dir, util)
            if result is None:
                return
        if job.finished:
            return
        if job.abort_event.is_set():
            self._done(job, False, "Cancelled.", None)
            return
        if isinstance(result, dict) and result.get("ok"):
            message = result.get("message") or "Complete."
            self._log(job, message)
            self._status(job, "Finished", "green")
            self._done(job, True, message)
        elif isinstance(result, dict):
            message = result.get("message") or "Failed."
            self._done(job, False, message, result.get("reason") or message)
        else:
            self._done(job, True, "Complete.")

    def _run_python_hook(self, job: _Job, params: dict, module_dir: str, util: dict):
        """Load and run the bound Python hook (``runtime.py``) of a utility."""
        runtime_path = os.path.join(module_dir, util.get("runtime_path") or "runtime.py")
        added_path = False
        engine_mod = None
        try:
            norm = os.path.normpath(module_dir)
            if norm and norm not in sys.path:
                sys.path.insert(0, norm)
                added_path = True
            spec = importlib.util.spec_from_file_location(f"util_{job.tool}", runtime_path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Could not load {runtime_path}")
            module = importlib.util.module_from_spec(spec)
            with self._util_engine_lock:
                saved_engine = sys.modules.get("engine")
                try:
                    engine_mod = self._load_engine_module(job.tool, module_dir)
                    if engine_mod is not None:
                        sys.modules["engine"] = engine_mod
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                finally:
                    if saved_engine is not None:
                        sys.modules["engine"] = saved_engine
                    else:
                        sys.modules.pop("engine", None)
                    sys.modules.pop(spec.name, None)
                runner = getattr(module, "run", None)
                if not callable(runner):
                    raise RuntimeError(f"{runtime_path} must define run(ctx)")
                ctx = InteropContext(self, job, params)
                return runner(ctx)
        except InteropError as exc:
            if not job.finished:
                self._done(job, False, str(exc), str(exc))
            return None
        except Exception as exc:
            traceback.print_exc()
            self._log(job, f"Utility runtime crashed: {exc}", "error")
            if not job.finished:
                self._done(job, False, "Runtime crashed.", str(exc) or "utility error")
            return None
        finally:
            if added_path:
                try:
                    sys.path.remove(norm)
                except ValueError:
                    pass

    def get_tool_schema(self, tool_id: str) -> dict:
        util = self._utilities.get(tool_id)
        if not util:
            return {"ok": False, "reason": "not_found"}
        return {
            "ok": True,
            "manifest": util.get("manifest"),
            "form_schema": util.get("form_schema"),
            "icon_file": util.get("icon_rel") or util.get("manifest", {}).get("icon_file"),
            "has_runtime": bool(util.get("runtime_ok")),
            "runtime_file": util.get("runtime_path"),
        }

    def ui_action(self, tool_id: str, action_id: str, params: Any = None) -> dict:
        """Dispatch a UI action to a utility runtime's action handler.

        Declarative UI nodes that carry an ``actionId`` route through the
        frontend action layer (``uiActions.js``) to this bridge method. The
        action is handed to the runtime's ``on_ui_action(ctx, action_id, params)``
        hook — a Python ``runtime.py`` / ``engine.py`` function or a Lua
        ``on_ui_action`` global — with an InteropContext bound to the tool's
        live job when one exists, so calls like ``ctx.log`` / ``ctx.set_form_data``
        still land in the active job. Return values and errors round-trip to
        the awaiting Promise.
        """
        if not isinstance(action_id, str) or not action_id:
            return {"ok": False, "reason": "invalid_action"}
        util = self._utilities.get(str(tool_id))
        if not util or not util.get("runtime_ok"):
            return {"ok": False, "reason": "not_found"}
        module_dir = util.get("dir")
        handlers = (util.get("manifest") or {}).get("handlers") or {}
        params = params if isinstance(params, dict) else {}

        job = self._active_or_transient_job(str(tool_id))
        ctx = InteropContext(self, job, job.params)
        response = self._run_action_hook(str(tool_id), module_dir, util, handlers, ctx, action_id, params)
        if isinstance(response, dict) and response.get("ok"):
            return {"ok": True, "result": response.get("result")}
        reason = "failed" if not isinstance(response, dict) else (response.get("reason") or "failed")
        return {"ok": False, "reason": reason}

    def _active_or_transient_job(self, tool: str) -> _Job:
        """Reuse a tool's live job as the action context, else a transient one.

        A transient ``_Job`` is never spawned or polled; it only gives the
        InteropContext a place to log/confirm against when a page-level action
        arrives before (or without) a running job.
        """
        with self._lock:
            jid = self._recent_jobs.get(tool)
            job = self._jobs.get(jid) if jid else None
            if job is not None and not job.finished:
                return job
        return _Job(uuid.uuid4().hex, tool)

    def _run_action_hook(self, tool: str, module_dir: str, util: dict, handlers: dict,
                         ctx: InteropContext, action_id: str, params: dict) -> dict:
        """Resolve a UI action through the tool's Lua and/or Python runtime."""
        lua_name = handlers.get("lua")
        if lua_name and isinstance(lua_name, str) and lua_name:
            lua_path = os.path.join(module_dir, lua_name)
            if os.path.isfile(lua_path):
                cr = run_lua_action(ctx, lua_path, action_id, params)
                if cr.get("ok"):
                    return {"ok": True, "result": cr.get("result")}
                if cr.get("reason") not in ("lua_runtime_missing", "no_ui_action_handler"):
                    return cr
        return self._run_python_action(tool, module_dir, util, ctx, action_id, params)

    def _run_python_action(self, tool: str, module_dir: str, util: dict,
                           ctx: InteropContext, action_id: str, params: dict) -> dict:
        """Call ``on_ui_action(ctx, action_id, params)`` from the Python runtime."""
        runtime_path = os.path.join(module_dir, util.get("runtime_path") or "runtime.py")
        added_path = False
        try:
            norm = os.path.normpath(module_dir)
            if norm and norm not in sys.path:
                sys.path.insert(0, norm)
                added_path = True
            spec = importlib.util.spec_from_file_location(f"util_{tool}_action", runtime_path)
            if spec is None or spec.loader is None:
                return {"ok": False, "reason": "load_failed"}
            module = importlib.util.module_from_spec(spec)
            with self._util_engine_lock:
                saved_engine = sys.modules.get("engine")
                try:
                    engine_mod = self._load_engine_module(tool, module_dir)
                    if engine_mod is not None:
                        sys.modules["engine"] = engine_mod
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                finally:
                    if saved_engine is not None:
                        sys.modules["engine"] = saved_engine
                    else:
                        sys.modules.pop("engine", None)
                    sys.modules.pop(spec.name, None)
                hook = getattr(module, "on_ui_action", None)
                if not callable(hook):
                    return {"ok": False, "reason": "no_ui_action_handler"}
                return {"ok": True, "result": hook(ctx, action_id, params)}
        except InteropError as exc:
            return {"ok": False, "reason": str(exc), "interop": True}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "reason": str(exc)}
        finally:
            if added_path:
                try:
                    sys.path.remove(norm)
                except ValueError:
                    pass

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
                    "tool_title": _tool_title(job.tool, self._utilities),
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
            job.label = f"{_tool_title(tool, self._utilities)} \u00b7 {job.id[:6]}"
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
            job.label = f"{_tool_title(tool, self._utilities)} \u00b7 {job_id[:6]}"
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
                        "tool_title": _tool_title(job.tool, self._utilities),
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
                        "tool_title": _tool_title(job.tool, self._utilities),
                        "icon_file": _tool_icon_file(job.tool, self._utilities),
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
                            "tool_title": _tool_title(job.tool, self._utilities),
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
                        "tool_title": _tool_title(job.tool, self._utilities),
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