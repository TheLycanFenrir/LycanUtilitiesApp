"""Modular runtime execution: engine loading, Lua/Python hooks, UI actions."""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
import uuid
from typing import Any, Callable, TYPE_CHECKING

from core.interop import InteropContext, InteropError
from core.lua_bridge import run_lua_script, run_lua_action

from .common import _Job
from .envelope import ResponseStatus
from core.debug_log import get_logger

_logger = get_logger(__name__)

if TYPE_CHECKING:
    class BaseApiHost:
        _util_engines: dict
        _util_engine_lock: Any
        _utilities: Any
        _lock: Any
        _recent_jobs: dict[str, str]
        _jobs: dict[str, _Job]
        _log: Callable[..., None]
        _done: Callable[..., bool]
        _status: Callable[..., None]
else:
    BaseApiHost = object


class RuntimeBridgeMixin(BaseApiHost):
    """Runtime execution surface of the Api bridge (utilities/ + interop)."""

    def _load_engine_module(self, tool: str, module_dir: str):
        """Load a utility's ``engine.py`` once, keyed by tool id."""
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "module_dir": module_dir}), tier=_logger.DEBUG_LOOP)
        cached = self._util_engines.get(tool)
        if cached is not None:
            _logger.debug_info("in if (cached is not None)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return cached
        engine_path = os.path.join(module_dir, "engine.py")
        if not os.path.isfile(engine_path):
            _logger.debug_info("in if (not os.path.isfile(engine_path))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None
        with self._util_engine_lock:
            _logger.debug_info("in with (self._util_engine_lock)", tier=_logger.DEBUG_LOOP)
            cached = self._util_engines.get(tool)
            if cached is not None:
                _logger.debug_info("in if (cached is not None)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return cached
            spec = importlib.util.spec_from_file_location(f"util_{tool}_engine", engine_path)
            if spec is None or spec.loader is None:
                _logger.debug_info("in if (spec is None or spec.loader is None)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                spec.loader.exec_module(module)
            finally:
                _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
                sys.modules.pop(spec.name, None)
            self._util_engines[tool] = module
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return module

    def _run_utility(self, job: _Job, params: dict) -> None:
        _logger.debug_info("enter args=%s", ascii({"job": job, "params": params}), tier=_logger.DEBUG_LOOP)
        util = self._utilities.get(job.tool)
        if not util or not util.get("runtime_ok"):
            _logger.debug_info("in if (not util or not util.get(\"runtime_ok\"))", tier=_logger.DEBUG_LOOP)
            self._log(job, f"No runtime available for '{job.tool}'.", "warn")
            self._done(job, False, "Runtime unavailable.", "utility missing runtime")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return
        module_dir = util.get("dir") or ""
        handlers = (util.get("manifest") or {}).get("handlers") or {}
        result = None
        lua_name = handlers.get("lua")
        # Prefer the Lua hook when it is bound and a Lua runtime is loadable.
        if lua_name and isinstance(lua_name, str) and lua_name:
            _logger.debug_info("in if (lua_name and isinstance(lua_name, str) and lua_name)", tier=_logger.DEBUG_LOOP)
            lua_path = os.path.join(module_dir, lua_name)
            if os.path.isfile(lua_path):
                _logger.debug_info("in if (os.path.isfile(lua_path))", tier=_logger.DEBUG_LOOP)
                ctx = InteropContext(self, job, params)
                cr = run_lua_script(ctx, lua_path)
                if cr.get("ok"):
                    _logger.debug_info("in if (cr.get(\"ok\"))", tier=_logger.DEBUG_LOOP)
                    result = cr.get("result")
                elif cr.get("reason") == "lua_runtime_missing":
                    _logger.debug_info("in elif (cr.get(\"reason\") == \"lua_runtime_missing\")", tier=_logger.DEBUG_LOOP)
                    self._log(job,
                              f"Lua runtime missing; falling back to the Python hook "
                              f"({util.get('runtime_path') or 'runtime.py'}).", "info")
                else:
                    # The Lua hook halted (throw_error already set status/logs).
                    _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
                    if not job.finished:
                        _logger.debug_info("in if (not job.finished)", tier=_logger.DEBUG_LOOP)
                        reason = cr.get("reason") or "Lua hook failed."
                        if cr.get("interop"):
                            _logger.debug_info("in if (cr.get(\"interop\"))", tier=_logger.DEBUG_LOOP)
                            self._done(job, False, reason, reason)
                        else:
                            _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
                            self._log(job, f"Lua hook failed: {reason}", "error")
                            self._done(job, False, "Runtime crashed.", reason)
                    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                    return
        if result is None:
            _logger.debug_info("in if (result is None)", tier=_logger.DEBUG_LOOP)
            result = self._run_python_hook(job, params, module_dir, util)
            if result is None:
                _logger.debug_info("in if (result is None)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return
        if job.finished:
            _logger.debug_info("in if (job.finished)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return
        if job.abort_event.is_set():
            _logger.debug_info("in if (job.abort_event.is_set())", tier=_logger.DEBUG_LOOP)
            self._done(job, False, "Cancelled.", None)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return
        if isinstance(result, dict) and result.get("ok"):
            _logger.debug_info("in if (isinstance(result, dict) and result.get(\"ok\"))", tier=_logger.DEBUG_LOOP)
            message = result.get("message") or "Complete."
            self._log(job, message)
            self._status(job, "Finished", "green")
            self._done(job, True, message)
        elif isinstance(result, dict):
            _logger.debug_info("in elif (isinstance(result, dict))", tier=_logger.DEBUG_LOOP)
            message = result.get("message") or "Failed."
            self._done(job, False, message, result.get("reason") or message)
        else:
            _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
            self._done(job, True, "Complete.")

    def _run_python_hook(self, job: _Job, params: dict, module_dir: str, util: dict):
        """Load and run the bound Python hook (``runtime.py``) of a utility."""
        _logger.debug_info("enter args=%s", ascii({"job": job, "params": params, "module_dir": module_dir, "util": util}), tier=_logger.DEBUG_LOOP)
        runtime_path = os.path.join(module_dir, util.get("runtime_path") or "runtime.py")
        added_path = False
        engine_mod = None
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            norm = os.path.normpath(module_dir)
            if norm and norm not in sys.path:
                _logger.debug_info("in if (norm and norm not in sys.path)", tier=_logger.DEBUG_LOOP)
                sys.path.insert(0, norm)
                added_path = True
            spec = importlib.util.spec_from_file_location(f"util_{job.tool}", runtime_path)
            if spec is None or spec.loader is None:
                _logger.debug_info("in if (spec is None or spec.loader is None)", tier=_logger.DEBUG_LOOP)
                raise RuntimeError(f"Could not load {runtime_path}")
            module = importlib.util.module_from_spec(spec)
            with self._util_engine_lock:
                _logger.debug_info("in with (self._util_engine_lock)", tier=_logger.DEBUG_LOOP)
                saved_engine = sys.modules.get("engine")
                try:
                    _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                    engine_mod = self._load_engine_module(job.tool, module_dir)
                    if engine_mod is not None:
                        _logger.debug_info("in if (engine_mod is not None)", tier=_logger.DEBUG_LOOP)
                        sys.modules["engine"] = engine_mod
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                finally:
                    _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
                    if saved_engine is not None:
                        _logger.debug_info("in if (saved_engine is not None)", tier=_logger.DEBUG_LOOP)
                        sys.modules["engine"] = saved_engine
                    else:
                        _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
                        sys.modules.pop("engine", None)
                    sys.modules.pop(spec.name, None)
                runner = getattr(module, "run", None)
                if not callable(runner):
                    _logger.debug_info("in if (not callable(runner))", tier=_logger.DEBUG_LOOP)
                    raise RuntimeError(f"{runtime_path} must define run(ctx)")
                ctx = InteropContext(self, job, params)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return runner(ctx)
        except InteropError as exc:
            _logger.debug_info("in except (InteropError)", tier=_logger.DEBUG_LOOP)
            if not job.finished:
                _logger.debug_info("in if (not job.finished)", tier=_logger.DEBUG_LOOP)
                self._done(job, False, str(exc), str(exc))
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            traceback.print_exc()
            self._log(job, f"Utility runtime crashed: {exc}", "error")
            if not job.finished:
                _logger.debug_info("in if (not job.finished)", tier=_logger.DEBUG_LOOP)
                self._done(job, False, "Runtime crashed.", str(exc) or "utility error")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None
        finally:
            _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
            if added_path:
                _logger.debug_info("in if (added_path)", tier=_logger.DEBUG_LOOP)
                try:
                    _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                    sys.path.remove(norm)
                except ValueError:
                    _logger.debug_info("in except (ValueError)", tier=_logger.DEBUG_LOOP)
                    pass

    def _get_tool_schema(self, tool_id: str) -> dict:
        """Internal schema/manifest lookup for a utility id."""
        _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id}), tier=_logger.DEBUG_LOOP)
        if not isinstance(tool_id, str):
            _logger.debug_info("in if (not isinstance(tool_id, str))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": False,
                "reason": "not_found",
            }
        util = self._utilities.get(tool_id)

        if not util:
            _logger.debug_info("in if (not util)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": False,
                "reason": "not_found",
            }

        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "ok": True,
            "manifest": util.get("manifest"),
            "form_schema": util.get("form_schema"),
            "icon_file": util.get("icon_rel") or (util.get("manifest") or {}).get("icon_file"),
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
        _logger.debug_info("enter args=%s", ascii({"tool_id": tool_id, "action_id": action_id, "params": params}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(action_id, str) or not action_id:
            _logger.debug_info("in if (not isinstance(action_id, str) or not action_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_action",
                "detail": "action_id must be a non-empty string.",
            }
        util = self._utilities.get(str(tool_id))
        if not util or not util.get("runtime_ok"):
            _logger.debug_info("in if (not util or not util.get(\"runtime_ok\"))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "not_found",
                "detail": f"No runtime available for tool '{tool_id}'.",
            }
        module_dir = util.get("dir") or ""
        handlers = (util.get("manifest") or {}).get("handlers") or {}
        params = params if isinstance(params, dict) else {}

        job = self._active_or_transient_job(str(tool_id))
        ctx = InteropContext(self, job, job.params)
        response = self._run_action_hook(str(tool_id), module_dir, util, handlers, ctx, action_id, params)
        if isinstance(response, dict) and response.get("ok"):
            _logger.debug_info("in if (isinstance(response, dict) and response.get(\"ok\"))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "result": response.get("result"),
            }
        code = "failed" if not isinstance(response, dict) else (response.get("reason") or "failed")
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": ResponseStatus.FAILED,
            "code": str(code),
            "detail": str(code),
        }

    def _active_or_transient_job(self, tool: str) -> _Job:
        """Reuse a tool's live job as the action context, else a transient one.

        A transient ``_Job`` is never spawned or polled; it only gives the
        InteropContext a place to log/confirm against when a page-level action
        arrives before (or without) a running job.
        """
        _logger.debug_info("enter args=%s", ascii({"tool": tool}), tier=_logger.DEBUG_LOOP)
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
            jid = self._recent_jobs.get(tool)
            job = self._jobs.get(jid) if jid else None
            if job is not None and not job.finished:
                _logger.debug_info("in if (job is not None and not job.finished)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return job
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return _Job(uuid.uuid4().hex, tool)

    def _run_action_hook(self, tool: str, module_dir: str, util: dict, handlers: dict,
                         ctx: InteropContext, action_id: str, params: dict) -> dict:
        """Resolve a UI action through the tool's Lua and/or Python runtime."""
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "module_dir": module_dir, "util": util, "handlers": handlers, "ctx": ctx, "action_id": action_id, "params": params}), tier=_logger.DEBUG_LOOP)
        lua_name = handlers.get("lua")
        if lua_name and isinstance(lua_name, str) and lua_name:
            _logger.debug_info("in if (lua_name and isinstance(lua_name, str) and lua_name)", tier=_logger.DEBUG_LOOP)
            lua_path = os.path.join(module_dir, lua_name)
            if os.path.isfile(lua_path):
                _logger.debug_info("in if (os.path.isfile(lua_path))", tier=_logger.DEBUG_LOOP)
                cr = run_lua_action(ctx, lua_path, action_id, params)
                if cr.get("ok"):
                    _logger.debug_info("in if (cr.get(\"ok\"))", tier=_logger.DEBUG_LOOP)
                    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                    return {
                        "ok": True,
                        "result": cr.get("result"),
                    }
                if cr.get("reason") not in ("lua_runtime_missing", "no_ui_action_handler"):
                    _logger.debug_info("in if (cr.get(\"reason\") not in (\"lua_runtime_missing\", \"no_ui_action_handler\"))", tier=_logger.DEBUG_LOOP)
                    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                    return cr
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return self._run_python_action(tool, module_dir, util, ctx, action_id, params)

    def _run_python_action(self, tool: str, module_dir: str, util: dict,
                           ctx: InteropContext, action_id: str, params: dict) -> dict:
        """Call ``on_ui_action(ctx, action_id, params)`` from the Python runtime."""
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "module_dir": module_dir, "util": util, "ctx": ctx, "action_id": action_id, "params": params}), tier=_logger.DEBUG_LOOP)
        runtime_path = os.path.join(module_dir, util.get("runtime_path") or "runtime.py")
        added_path = False
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            norm = os.path.normpath(module_dir)
            if norm and norm not in sys.path:
                _logger.debug_info("in if (norm and norm not in sys.path)", tier=_logger.DEBUG_LOOP)
                sys.path.insert(0, norm)
                added_path = True
            spec = importlib.util.spec_from_file_location(f"util_{tool}_action", runtime_path)
            if spec is None or spec.loader is None:
                _logger.debug_info("in if (spec is None or spec.loader is None)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return {
                    "ok": False,
                    "reason": "load_failed",
                }
            module = importlib.util.module_from_spec(spec)
            with self._util_engine_lock:
                _logger.debug_info("in with (self._util_engine_lock)", tier=_logger.DEBUG_LOOP)
                saved_engine = sys.modules.get("engine")
                try:
                    _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                    engine_mod = self._load_engine_module(tool, module_dir)
                    if engine_mod is not None:
                        _logger.debug_info("in if (engine_mod is not None)", tier=_logger.DEBUG_LOOP)
                        sys.modules["engine"] = engine_mod
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                finally:
                    _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
                    if saved_engine is not None:
                        _logger.debug_info("in if (saved_engine is not None)", tier=_logger.DEBUG_LOOP)
                        sys.modules["engine"] = saved_engine
                    else:
                        _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
                        sys.modules.pop("engine", None)
                    sys.modules.pop(spec.name, None)
                hook = getattr(module, "on_ui_action", None)
                if not callable(hook):
                    _logger.debug_info("in if (not callable(hook))", tier=_logger.DEBUG_LOOP)
                    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                    return {
                        "ok": False,
                        "reason": "no_ui_action_handler",
                    }
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return {
                    "ok": True,
                    "result": hook(ctx, action_id, params),
                }
        except InteropError as exc:
            _logger.debug_info("in except (InteropError)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": False,
                "reason": str(exc),
                "interop": True,
            }
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            traceback.print_exc()
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": False,
                "reason": str(exc),
            }
        finally:
            _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
            if added_path:
                _logger.debug_info("in if (added_path)", tier=_logger.DEBUG_LOOP)
                try:
                    _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                    sys.path.remove(norm)
                except ValueError:
                    _logger.debug_info("in except (ValueError)", tier=_logger.DEBUG_LOOP)
                    pass
