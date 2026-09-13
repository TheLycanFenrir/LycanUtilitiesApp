"""Lua & Python interop bridge facade.

The command table below is the single source of truth for the cross-language
command set. Python runtimes call the ``InteropContext`` methods directly;
Lua scripts (and any other embedded scripting layer) route every call through
``bridge_call`` / ``run_lua_script``.

The Lua runtime itself is optional: when ``lupa`` is not installed the loader
reports a graceful ``lua_runtime_missing`` result instead of crashing, keeping
Python-hook modules functional.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

COMMANDS: Dict[str, str] = {
    # Data & state management
    "get_form_data": "get_form_data",
    "set_form_data": "set_form_data",
    "get_all_form_data": "get_all_form_data",
    "set_all_form_data": "set_all_form_data",
    # Dynamic field & UI manipulation
    "add_field": "add_field",
    "delete_field": "delete_field",
    "hide_field": "hide_field",
    "unhide_field": "unhide_field",
    "set_focus": "set_focus",
    "set_field_status": "set_field_status",
    # String validation & sanitization
    "regex_validation": "regex_validation",
    "regex_sanitization": "regex_sanitization",
    # Execution, logs & errors
    "execute_command": "execute_command",
    "execute_py": "execute_py",
    "send_log_output": "send_log_output",
    "get_log_output": "get_log_output",
    "progress": "progress",
    "status": "status",
    "throw_error": "throw_error",
    # Process control & queue (engine auto-managed)
    "add_to_queue": "add_to_queue",
    "start_process": "start_process",
    "pause_process": "pause_process",
    "resume_process": "resume_process",
}


def bridge_call(ctx, command: str, args: Optional[list] = None) -> Dict[str, Any]:
    """Dispatch an interop command name to the matching InteropContext method.

    ``args`` is a positional argument list (Lua tables are normalized to lists
    before dispatch).
    """
    method_name = COMMANDS.get(command)
    if method_name is None:
        return {"ok": False, "reason": "unknown_command", "command": command}
    method = getattr(ctx, method_name, None)
    if method is None:
        return {"ok": False, "reason": "not_implemented", "command": command}
    try:
        result = method(*(args or []))
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "command": command}


def _lua_registered(lua, ctx) -> None:
    """Expose ``lycan.call(command, args)`` plus convenience wrappers to Lua."""
    def call_cmd(command: str, args: Optional[Any] = None):
        if args is None:
            args = []
        # lupa hands Lua tables through as _LuaTable objects; iterating them
        # yields integer key indices, so unwrap with .values() first.
        if hasattr(args, "values"):
            args = list(args.values())
        else:
            args = list(args)
        reply = bridge_call(ctx, str(command), args)
        if isinstance(reply, dict) and reply.get("ok"):
            return reply.get("result")
        return None

    globals_obj = lua.globals()
    globals_obj.lycan_call = call_cmd
    for name in ("get_form_data", "set_form_data", "get_all_form_data",
                 "set_all_form_data", "add_field", "delete_field", "hide_field",
                 "unhide_field", "set_focus", "regex_validation",
                 "regex_sanitization", "execute_command", "execute_py",
                 "send_log_output", "get_log_output", "progress", "status",
                 "throw_error"):
        def make_wrapper(command_name: str):
            def wrapper(*args):
                return call_cmd(command_name, list(args))
            return wrapper
        globals_obj[name] = make_wrapper(name)


def run_lua_script(ctx, script_path: str) -> Dict[str, Any]:
    """Execute a Lua hook against the interop context (requires ``lupa``)."""
    try:
        import os
        from lupa import LuaRuntime
    except ImportError:
        return {
            "ok": False,
            "reason": "lua_runtime_missing",
            "note": "Install 'lupa' to run Lua hooks; Python hooks remain available.",
        }
    if not os.path.isfile(str(script_path)):
        return {"ok": False, "reason": "missing_file", "path": str(script_path)}
    lua = LuaRuntime(unpack_returned_tuples=True)
    try:
        _lua_registered(lua, ctx)
        with open(script_path, "r", encoding="utf-8") as fh:
            source = fh.read()
        result = lua.execute(source)
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def run_lua_source(ctx, source: str) -> Dict[str, Any]:
    """Execute a Lua source snippet against the interop context (requires lupa)."""
    try:
        from lupa import LuaRuntime
    except ImportError:
        return {"ok": False, "reason": "lua_runtime_missing"}
    lua = LuaRuntime(unpack_returned_tuples=True)
    try:
        _lua_registered(lua, ctx)
        result = lua.execute(str(source))
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}