"""Cross-language interop command set exposed to Lua scripts and Python hooks.

Every command in the standardized bridge is implemented here and handed to a
module runtime as ``InteropContext``. Form-field reads resolve synchronously
from the job's parameter snapshot (plus any in-process overlays written with
``set_form_data``); writes are pushed to the live UI through the global
``window.__lycanForm`` bridge when a native window is available.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import threading
import traceback

from typing import Any, Dict, List, Optional


class InteropError(Exception):
    """Raised by ``throw_error``: halts the runtime with an explicit message."""


class InteropContext:
    """Per-job bridge handed to a mod runtime as ``ctx``."""

    def __init__(self, api, job, params: Dict[str, Any]) -> None:
        self._api = api
        self._job = job
        self._params = dict(params or {})
        self._overlay: Dict[str, Any] = {}
        self._asset_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    #  Data & state
    # ------------------------------------------------------------------ #
    def get_form_data(self, field_id: str):
        with self._lock:
            if field_id in self._overlay:
                return self._overlay[field_id]
            return self._params.get(field_id)

    def set_form_data(self, field_id: str, value: Any) -> dict:
        with self._lock:
            self._overlay[field_id] = value
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.set_form_data"
            f"({self._api._js_str(field_id)}, {self._api._js_value(value)})"
        )
        return {"ok": True}

    def get_all_form_data(self) -> dict:
        with self._lock:
            data = dict(self._params)
            data.update(self._overlay)
            return data

    def set_all_form_data(self, data_table: dict) -> dict:
        if not isinstance(data_table, dict):
            return {"ok": False, "reason": "expected_object"}
        with self._lock:
            self._params.update(data_table)
            self._overlay = {}
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.set_all_form_data("
            f"{self._api._js_value(data_table)})"
        )
        return {"ok": True}

    def get(self, field_id: str, default: Any = None):
        value = self.get_form_data(field_id)
        return default if value is None else value

    # ------------------------------------------------------------------ #
    #  Dynamic field manipulation
    # ------------------------------------------------------------------ #
    def add_field(self, field_schema_json: str) -> dict:
        return self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.add_field("
            f"{self._api._js_str(field_schema_json)})"
        ) and {"ok": True}

    def delete_field(self, field_id: str) -> dict:
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.delete_field("
            f"{self._api._js_str(field_id)})"
        )
        return {"ok": True}

    def hide_field(self, field_id: str) -> dict:
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.hide_field("
            f"{self._api._js_str(field_id)})"
        )
        return {"ok": True}

    def unhide_field(self, field_id: str) -> dict:
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.unhide_field("
            f"{self._api._js_str(field_id)})"
        )
        return {"ok": True}

    def set_focus(self, field_id: str) -> dict:
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.set_focus("
            f"{self._api._js_str(field_id)})"
        )
        return {"ok": True}

    def set_field_status(self, field_id: str, status: str) -> dict:
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.set_field_status("
            f"{self._api._js_str(field_id)}, {self._api._js_str(status)})"
        )
        return {"ok": True}

    def send_ui_action(self, action_id: str, params: Any = None) -> dict:
        """Push a UI action to the live front-end action layer.

        The React side registers action handlers (``uiActions.js``); the
        runtime keeps a neutral string/JSON contract so neither Lua nor Python
        hooks need to know anything about the UI beyond an action id. When no
        native window is attached the action is simply skipped.
        """
        payload = {} if params is None else params
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "expected_object"}
        self._api._push_form_js(
            f"window.__lycanForm && window.__lycanForm.invoke_ui_action("
            f"{self._api._js_str(str(action_id))}, {self._api._js_value(payload)})"
        )
        return {"ok": True}

    # ------------------------------------------------------------------ #
    #  String validation & sanitization
    # ------------------------------------------------------------------ #
    @staticmethod
    def regex_validation(pattern: str, string: str) -> bool:
        try:
            return bool(re.match(pattern, str(string)))
        except re.error:
            return False

    @staticmethod
    def regex_sanitization(pattern: str, replacement: str, string: str) -> str:
        try:
            return re.sub(pattern, replacement, str(string))
        except re.error:
            return str(string)

    # ------------------------------------------------------------------ #
    #  Execution, logs & errors
    # ------------------------------------------------------------------ #
    def execute_command(self, cmd_table: Any, info_string: Optional[str] = None) -> dict:
        args = self._coerce_cmd(cmd_table)
        if not args:
            return {"ok": False, "reason": "empty_command"}
        if info_string:
            self._api._log(self._job, str(info_string))
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            self.throw_error(f"Could not launch command: {exc}")
            return {"ok": False, "reason": str(exc)}
        output: List[str] = []
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    if self._job.abort_event.is_set():
                        proc.terminate()
                        break
                    line = line.rstrip("\n")
                    if line:
                        output.append(line)
                        self._api._log(self._job, line)
            exit_code: Optional[int] = proc.wait()
        except Exception as exc:
            exit_code = proc.poll()
            self._api._log(self._job, f"command error: {exc}", "warn")
        result = {"ok": exit_code == 0, "code": exit_code, "output": output}
        if exit_code not in (0, None):
            self.throw_error(f"Command exited with code {exit_code}")
        return result

    def execute_py(self, script_path: str, args: Optional[list] = None) -> dict:
        path = os.path.abspath(os.path.join(self._asset_root, script_path)) \
            if not os.path.isabs(script_path) else script_path
        if not os.path.isfile(path):
            self.throw_error(f"Python hook not found: {path}")
            return {"ok": False, "reason": "missing_file"}
        try:
            spec = importlib.util.spec_from_file_location("mod_hook_" + str(id(self)), path)
            if spec is None or spec.loader is None:
                return {"ok": False, "reason": "load_failed"}
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            hook = getattr(module, "run", None) or getattr(module, "main", None)
            if hook is None:
                return {"ok": False, "reason": "no_run_entry"}
            if isinstance(args, list) and args:
                result = hook(self, *args)
            else:
                result = hook(self)
            return {"ok": True, "result": result}
        except InteropError:
            raise
        except Exception as exc:
            traceback.print_exc()
            self.throw_error(f"Python hook failed: {exc}")
            return {"ok": False, "reason": str(exc)}

    def send_log_output(self, message: str, level: str = "info") -> dict:
        self._api._log(self._job, message, level)
        return {"ok": True}

    def get_log_output(self) -> list:
        logs = []
        with self._job.ev_lock:
            for _seq, payload in self._job.events:
                if payload.get("kind") == "log":
                    logs.append({"level": payload.get("level", "info"), "message": payload.get("message", "")})
        return logs

    def throw_error(self, error_msg: str) -> None:
        self._api._status(self._job, str(error_msg), "red")
        self._api._log(self._job, str(error_msg), "error")
        raise InteropError(str(error_msg))

    def progress(self, percent: float, status_text: Optional[str] = None) -> None:
        self._api._progress(self._job, float(percent), status_text)

    def status(self, text: str, tone: str = "blue") -> None:
        self._api._status(self._job, text, tone)

    def log(self, message: str, level: str = "info") -> dict:
        """Alias of ``send_log_output``: append a line to the job's console log."""
        return self.send_log_output(str(message), level)

    def confirm(self, message: str, title: str = "Confirmation",
                yes: str = "Yes", no: str = "No") -> bool:
        """Ask the user a blocking yes/no question in the UI."""
        return bool(self._api._confirm(self._job, str(message), title=title, yes=yes, no=no))

    def open_explorer(self, path: str) -> None:
        """Reveal a file or folder in the OS file manager."""
        self._api._open_explorer(str(path))

    @property
    def abort_event(self):
        """The job's abort ``threading.Event`` (set when the user cancels)."""
        return self._job.abort_event

    @property
    def pause_event(self):
        """The job's pause ``threading.Event`` (set while the user pauses)."""
        return self._job.pause_event

    @property
    def aborted(self) -> bool:
        """True once the user has requested cancellation of this job."""
        return self._job.abort_event.is_set()

    def wait_if_paused(self) -> None:
        """Block the runtime until a pause is lifted (or an abort is requested)."""
        self._api._wait_if_paused(self._job)

    # ------------------------------------------------------------------ #
    #  Process control & queue (engine auto-managed)
    # ------------------------------------------------------------------ #
    def add_to_queue(self, job_payload: dict) -> dict:
        return {"ok": True, "note": "auto-managed by engine"}

    def start_process(self) -> dict:
        return {"ok": True, "note": "auto-managed by engine"}

    def pause_process(self) -> dict:
        self._api._log(self._job, "Pause requested by runtime.", "warn")
        return {"ok": True}

    def resume_process(self) -> dict:
        return {"ok": True}

    def asset_path(self, path: str) -> str:
        return os.path.join(self._asset_root, path)

    def project_root(self) -> str:
        return self._asset_root

    def get_app_setting(self, key: Any = None):
        """Return the app-level settings document (or one of its sections).

        Exposes app configuration (FFmpeg binary, theme, ...) to runtimes that
        need to resolve external tooling, e.g. a Lua hook locating FFmpeg the
        same way the Python engine does.
        """
        try:
            from app.settings import load_app_settings
            data = load_app_settings() or {}
        except Exception:
            data = {}
        if key is None:
            return data
        if isinstance(key, list) and all(isinstance(item, str) for item in key):
            value = data
            for part in key:
                if not isinstance(value, dict) or part not in value:
                    return None
                value = value[part]
            return value
        if isinstance(key, str):
            return data.get(key)
        return None

    @staticmethod
    def available_cores() -> int:
        """Total logical CPU cores of this machine."""
        try:
            from app.system import get_available_cores
            return int(get_available_cores() or 1)
        except Exception:
            return 1

    @staticmethod
    def _coerce_cmd(cmd_table: Any) -> List[str]:
        if isinstance(cmd_table, dict):
            cmd = cmd_table.get("cmd", cmd_table.get("command", ""))
            if isinstance(cmd, str):
                base = [cmd]
            elif isinstance(cmd, list):
                base = list(cmd)
            else:
                base = []
            args = cmd_table.get("args", cmd_table.get("arguments", []))
            if isinstance(args, str):
                args = [args]
            return [str(item) for item in list(base) + list(args) if item not in (None, "")]
        if isinstance(cmd_table, list):
            return [str(item) for item in cmd_table]
        if isinstance(cmd_table, str):
            return cmd_table.split(" ")
        return []