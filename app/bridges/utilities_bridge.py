"""Utilities folder: open in explorer, live-reload change watcher."""

from __future__ import annotations

import os
import traceback
from threading import Lock, RLock
from typing import Any, Callable, TYPE_CHECKING

from core.debug_log import get_logger
from core.scanner import (
    load_utilities as _scan_utilities,
    UTILITIES_DIR as _UTILITIES_DIR,
)

from .envelope import ResponseStatus

_logger = get_logger(__name__)

if TYPE_CHECKING:
    class BaseApiHost:
        _utilities: dict[str, dict]
        _utilities_broken: dict[str, dict]
        _utilities_scan: dict
        _util_engines: dict
        _util_engine_lock: Any
        _utils_baseline: dict
        _utils_restart_pending: bool
        _utils_change_lock: Any
        _open_explorer: Callable[[str], None]
else:
    BaseApiHost = object


class UtilitiesBridgeMixin(BaseApiHost):
    """Utilities folder surface of the Api bridge."""

    _UTIL_IGNORED = {"utilities_cache.json", "util_lists_cache-lock.json"}

    def _init_utilities(self) -> None:
        """Scan utilities/ and set up the live-reload watcher baseline."""
        # Modular hub: utilities scanned from utilities/ (validated + SHA-256 cached).
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
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
        self._util_engines: dict = {}
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def open_utilities_folder(self, utility_id: str = "") -> dict:
        """Reveal the utilities folder — or one utility's folder — in the OS
        file explorer. Pass ``utility_id`` to land directly inside that
        utility's module directory instead of the utilities root."""
        _logger.debug_info("enter args=%s", ascii({"utility_id": utility_id}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            if not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR):
                _logger.debug_info("in if (not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR))", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "not_found",
                    "detail": "The utilities folder does not exist on disk.",
                    "path": _UTILITIES_DIR,
                }

            target_dir = _UTILITIES_DIR
            if utility_id:
                _logger.debug_info("in if (utility_id)", tier=_logger.DEBUG_FUNCTION)
                resolved = self._resolve_utility_dir(str(utility_id))
                if resolved and os.path.isdir(resolved):
                    _logger.debug_info("in if (resolved and os.path.isdir(resolved))", tier=_logger.DEBUG_FUNCTION)
                    target_dir = resolved
                else:
                    # Giving specific failure message if utility id is not valid
                    _logger.debug_info("in else", tier=_logger.DEBUG_FUNCTION)
                    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                    return {
                        "ok": False,
                        "reason": ResponseStatus.FAILED,
                        "code": "utility_not_found",
                        "detail": f"No installed utility with id '{utility_id}'.",
                        "utility_id": utility_id,
                    }

            self._open_explorer(target_dir)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "path": target_dir,
            }
        except Exception as e:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.error(f"Failed to open utility folder: {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(e),
            }

    def _resolve_utility_dir(self, utility_id: str) -> str | None:
        """Return the module directory for a utility id (installed or broken)."""
        _logger.debug_info("enter args=%s", ascii({"utility_id": utility_id}), tier=_logger.DEBUG_LOOP)
        for registry in (self._utilities, self._utilities_broken):
            _logger.debug_info("in for (registry in (self._utilities, self._utilities_broken))", tier=_logger.DEBUG_LOOP)
            entry = registry.get(utility_id)
            if isinstance(entry, dict):
                _logger.debug_info("in if (isinstance(entry, dict))", tier=_logger.DEBUG_LOOP)
                directory = entry.get("dir")
                if directory:
                    _logger.debug_info("in if (directory)", tier=_logger.DEBUG_LOOP)
                    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                    return str(directory)

        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None

    def _broken_descriptors(self) -> list[dict]:
        """Dashboard cards for utilities that failed to load (load-error tab)."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        result = []
        for mid, entry in self._utilities_broken.items():
            _logger.debug_info("in for (mid, entry in self._utilities_broken.items())", tier=_logger.DEBUG_LOOP)
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
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return result

    @staticmethod
    def _snapshot_utilities_dir() -> dict:
        """Cheap mtime+size snapshot of every module file under utilities/.

        The two scanner cache files and Python bytecode are excluded so the
        scanner writing its own cache can never be mistaken for a user change.
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        folders: set[str] = set()
        files: dict[str, tuple[int, int]] = {}

        if not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR):
            _logger.debug_info("in if (not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "folders": folders,
                "files": files,
            }

        for name in sorted(os.listdir(_UTILITIES_DIR)):
            _logger.debug_info("in for (name in sorted(os.listdir(_UTILITIES_DIR)))", tier=_logger.DEBUG_LOOP)
            module_dir = os.path.join(_UTILITIES_DIR, name)
            if not os.path.isdir(module_dir):
                _logger.debug_info("in if (not os.path.isdir(module_dir))", tier=_logger.DEBUG_LOOP)
                continue

            folders.add(name)

            for root, dirs, names in os.walk(module_dir):
                # Ignore cache folder and hidden folders
                _logger.debug_info("in for (root, dirs, names in os.walk(module_dir))", tier=_logger.DEBUG_LOOP)
                dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith((".", "_", "__"))]

                for fname in names:
                    _logger.debug_info("in for (fname in names)", tier=_logger.DEBUG_LOOP)
                    if fname.endswith((".pyc", ".pyo")):
                        _logger.debug_info("in if (fname.endswith((\".pyc\", \".pyo\")))", tier=_logger.DEBUG_LOOP)
                        continue

                    abs_path = os.path.join(root, fname)
                    rel = os.path.relpath(abs_path, _UTILITIES_DIR)
                    rel_normalized = rel.replace("\\", "/")

                    if rel_normalized in UtilitiesBridgeMixin._UTIL_IGNORED:
                        _logger.debug_info("in if (rel_normalized in UtilitiesBridgeMixin._UTIL_IGNORED)", tier=_logger.DEBUG_LOOP)
                        continue

                    try:
                        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                        st = os.stat(abs_path)
                        files[rel_normalized] = (st.st_mtime_ns, st.st_size)
                    except OSError:
                        _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_LOOP)
                        _logger.warning(f"Failed to list this file: {fname}")
                        continue

        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "folders": folders,
            "files": files
        }

    @staticmethod
    def _diff_utilities(before: dict, after: dict) -> list[dict]:
        _logger.debug_info("enter args=%s", ascii({"before": before, "after": after}), tier=_logger.DEBUG_LOOP)
        changes: list[dict] = []

        # Get set/dict data by safely
        old_folders = set(before.get("folders") or [])
        new_folders = set(after.get("folders") or [])
        old_files = before.get("files") or {}
        new_files = after.get("files") or {}

        # Detect any newly created folders
        for name in sorted(new_folders - old_folders):
            _logger.debug_info("in for (name in sorted(new_folders - old_folders))", tier=_logger.DEBUG_LOOP)
            changes.append({"path": f"{name}/", "kind": "add", "cause": "folder"})

        # Detect any deleted folders
        for name in sorted(old_folders - new_folders):
            _logger.debug_info("in for (name in sorted(old_folders - new_folders))", tier=_logger.DEBUG_LOOP)
            changes.append({"path": f"{name}/", "kind": "remove", "cause": "folder"})

        # Detect file changes (add, modify, delete)
        all_files = sorted(set(old_files) | set(new_files))

        for rel in all_files:
            # Forcing path using '/'
            _logger.debug_info("in for (rel in all_files)", tier=_logger.DEBUG_LOOP)
            rel_posix = rel.replace("\\", "/")
            before_stat = old_files.get(rel)
            after_stat = new_files.get(rel)

            if before_stat == after_stat:
                _logger.debug_info("in if (before_stat == after_stat)", tier=_logger.DEBUG_LOOP)
                continue

            if before_stat is not None and after_stat is not None:
                _logger.debug_info("in if (before_stat is not None and after_stat is not None)", tier=_logger.DEBUG_LOOP)
                kind = "modify"
            elif before_stat is None:
                _logger.debug_info("in elif (before_stat is None)", tier=_logger.DEBUG_LOOP)
                kind = "add"
            else:
                _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
                kind = "remove"

            # Define cause of category (extension mapping)
            ext = os.path.splitext(rel)[1].lower()
            cause_map = {
                ".py": "py",
                ".lua": "lua",
                ".json": "json"
            }
            cause = cause_map.get(ext, "asset")

            changes.append({"path": rel_posix, "kind": kind, "cause": cause})

        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return changes

    def utilities_changes(self) -> dict:
        """Poll the utilities folder and classify what changed.

        Returns ``{action: None|"restart"|"refresh", changes:[...]}``. New
        utility folders and ``.py`` edits require an app restart; json/lua/asset
        updates only need a backend rescan plus a frontend hard refresh. The
        baseline is advanced inside this call for refresh-class changes, so the
        scanner's own cache rewrite never causes a reload loop.
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        with self._utils_change_lock:
            _logger.debug_info("in with (self._utils_change_lock)", tier=_logger.DEBUG_FUNCTION)
            current = self._snapshot_utilities_dir()
            changes = self._diff_utilities(self._utils_baseline, current)

            if not changes:
                _logger.debug_info("in if (not changes)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("No changes detected")
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": True,
                    "reason": ResponseStatus.SUCCESS,
                    "action": None,
                    "changes": [],
                }

            # Check if some critical changes that requires backend restart
            requires_restart = self._utils_restart_pending or any(
                (c["kind"] == "add" and c["cause"] == "folder") or c["cause"] == "py"
                for c in changes
            )

            if requires_restart:
                _logger.debug_info("in if (requires_restart)", tier=_logger.DEBUG_FUNCTION)
                self._utils_restart_pending = True
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": True,
                    "reason": ResponseStatus.WARNING,
                    "action": "restart",
                    "changes": changes,
                }

            # Refresh-class only: rescan now so the reloaded frontend sees the
            # new manifest/schema/icons, then re-baseline post-rescan.
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
                self._utilities_scan = _scan_utilities(force_scan=True)
                self._utilities = self._utilities_scan.get("utilities") or {}
                self._utilities_broken = self._utilities_scan.get("broken") or {}
            except Exception:
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
                traceback.print_exc()

            self._utils_baseline = self._snapshot_utilities_dir()
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.WARNING,
                "action": "refresh",
                "changes": changes,
            }
