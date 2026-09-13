"""Lua & Python interop bridge facade.

Lua scripts call every command as a first-class, native-like global function.
The bridge registers each ``InteropContext`` method directly into the Lua
global environment via ``lua.globals()`` assignment -- no dispatcher, no
``lycan_call``-style string wrappers::

    lua.globals().throw_error = ...        ->  throw_error(msg)
    lua.globals().execute_command = ...    ->  execute_command(cmd_table, info)
    lua.globals().get_form_data = ...      ->  local data = get_form_data(field_id)

Each command maps one-to-one onto the Python ``InteropContext`` method of the
same name; Lua arguments are positional (or named, for record tables).

The Lua runtime itself is optional: when ``lupa`` is not installed the loader
reports a graceful ``lua_runtime_missing`` result instead of crashing, keeping
Python-hook modules functional.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

# Single source of truth for the cross-language command set. Every name is a
# public ``InteropContext`` method exposed to Lua as a global function.
COMMANDS: List[str] = [
    # Data & state management
    "get_form_data",
    "set_form_data",
    "get_all_form_data",
    "set_all_form_data",
    # Dynamic field & UI manipulation
    "add_field",
    "delete_field",
    "hide_field",
    "unhide_field",
    "set_focus",
    "set_field_status",
    # String validation & sanitization
    "regex_validation",
    "regex_sanitization",
    # Execution, logs & errors
    "execute_command",
    "execute_py",
    "send_log_output",
    "get_log_output",
    "progress",
    "status",
    "throw_error",
    # Process control & queue (engine auto-managed)
    "add_to_queue",
    "start_process",
    "pause_process",
    "resume_process",
]

# Additional ``InteropContext`` helpers bound as first-class globals too.
EXTRA_COMMANDS: List[str] = [
    "get",
    "log",
    "confirm",
    "open_explorer",
    "wait_if_paused",
    "asset_path",
    "project_root",
]


def _to_python(value: Any) -> Any:
    """Coerce a Lua-side value into a plain Python value.

    lupa passes Lua tables through as ``_LuaTable`` wrappers whose iteration
    yields keys (1-based integer indices for list-like tables). Recursively
    unwrap them so ``InteropContext`` receives ordinary dicts/lists.
    """
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    try:
        keys = list(value)
    except TypeError:
        return value
    if keys and all(isinstance(key, int) and key >= 1 for key in keys):
        return [_to_python(value[index]) for index in range(1, len(keys) + 1)]
    return {str(key): _to_python(value[key]) for key in keys}


def _to_lua(lua, value: Any) -> Any:
    """Convert a Python return value into a native Lua object.

    lupa otherwise hands nested containers back as lazy Python proxies (0-based
    indexing). Recursively building real Lua tables keeps results native-like:
    Lua sees ``{ok=true, code=0, output={"line"}}`` with 1-based indexing.
    """
    if isinstance(value, dict):
        return lua.table_from(
            {str(key): _to_lua(lua, item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return lua.table(*[_to_lua(lua, item) for item in value])
    return value


def _bind_method(lua, method: Callable) -> Callable:
    """Wrap an ``InteropContext`` method with Lua<->Python value handling."""

    def wrapped(*args: Any) -> Any:
        cargs = tuple(_to_python(arg) for arg in args)
        return _to_lua(lua, method(*cargs))

    return wrapped


def register_commands(lua, ctx) -> None:
    """Bind every bridge command directly into the Lua global environment.

    Direct global binding mandate: each command becomes a native-like global
    ``python_function`` via ``lua.globals()<name> = callable`` assignment, so
    Lua scripts call ``throw_error(msg)``, ``execute_command(cmd_table, info)``,
    ``get_form_data(field_id)`` directly -- no dispatcher, no string wrapper.
    """
    globals_obj = lua.globals()
    for name in COMMANDS + EXTRA_COMMANDS:
        method = getattr(ctx, name, None)
        if callable(method):
            globals_obj[name] = _bind_method(lua, method)
    globals_obj["aborted"] = lambda: bool(ctx.aborted)


def run_lua_script(ctx, script_path: str) -> Dict[str, Any]:
    """Execute a Lua hook against the interop context (requires ``lupa``)."""
    import os
    try:
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
        register_commands(lua, ctx)
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
        register_commands(lua, ctx)
        result = lua.execute(str(source))
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}