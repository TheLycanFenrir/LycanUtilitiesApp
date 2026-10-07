--[[
lycan_api.lua - editor-facing API stub for Lua utility runtimes.

THIS FILE IS AN IDE STUB. It is never loaded by the runtime.

core.lua_bridge (core/lua_bridge.py) registers every interop command directly
into the script's global environment before evaluating it, so runtimes call the
commands as plain global functions, not as ctx.method(...):

    local text   = get_form_data("watermark_text")
    throw_error("Missing input")
    local result = execute_command(
        { command = "ffmpeg", args = { "-version" } },
        "probing"
    )

By keeping this file in the project root, both the Lua Language Server (VSCode
Lua extension / .luarc.json) and the JetBrains Lua / EmmyLua plugin (PyCharm)
learn the signature of every command. That removes "undefined global" false
positives and enables autocomplete + documentation for utility runtimes.

Two entry points exist and are declared in the runtime files themselves:

    ---@param ctx LycanCtx
    local function run(ctx)             -- job execution (ends `return run(ctx)`)
      ...
      return { ok = true, message = "..." }
    end

    ---@param ctx LycanCtx
    ---@param action_id string
    ---@param params table
    local function on_ui_action(ctx, action_id, params) ... end

The `ctx` parameter is a LycanCtx (declared below); every LycanCtx method is
also exposed as the standalone global of the same name.
--]]

--====================================================================
--  Return payload types
--====================================================================

--- Generic bridge result returned by most commands.
---@class LycanResult
---@field ok boolean Whether the command succeeded.
---@field message? string Human-readable summary (when present).
---@field reason? string Failure reason when ok == false.
---@field note? string Complementary note (e.g. engine auto-managed queue).
---@field result? any Nested result value (execute_py, send_ui_action).

--- Result of `execute_command`.
---@class LycanExecResult
---@field ok boolean True when the process exited with code 0.
---@field code integer Process exit code (0 = success).
---@field output string[] Captured stdout/stderr lines (1-based list).

--- One console entry returned by `get_log_output`.
---@class LycanLogEntry
---@field level string "info" | "warn" | "error"
---@field message string The logged text.

--====================================================================
--  ctx parameter type (the object passed to run / on_ui_action)
--====================================================================

---@class LycanCtx
---@field get_form_data fun(field_id: string): any
---@field get fun(field_id: string, default?: any): any
---@field get_all_form_data fun(): table<string, any>
---@field set_form_data fun(field_id: string, value: any): LycanResult
---@field set_all_form_data fun(data: table<string, any>): LycanResult
---@field add_field fun(field_schema_json: string): LycanResult
---@field delete_field fun(field_id: string): LycanResult
---@field hide_field fun(field_id: string): LycanResult
---@field unhide_field fun(field_id: string): LycanResult
---@field set_focus fun(field_id: string): LycanResult
---@field set_field_status fun(field_id: string, status: string): LycanResult
---@field send_ui_action fun(action_id: string, params?: table): LycanResult
---@field regex_validation fun(pattern: string, subject: string): boolean
---@field regex_sanitization fun(pattern: string, replacement: string, subject: string): string
---@field execute_command fun(cmd_table: table, info_string?: string): LycanExecResult
---@field execute_py fun(script_path: string, args?: table): LycanResult
---@field send_log_output fun(message: string, level?: string): LycanResult
---@field get_log_output fun(): LycanLogEntry[]
---@field progress fun(percent: number, status_text?: string): nil
---@field status fun(text: string, tone?: string): nil
---@field log fun(message: string, level?: string): LycanResult
---@field confirm fun(message: string, title?: string, yes?: string, no?: string): boolean
---@field throw_error fun(error_msg: string): nil
---@field open_explorer fun(path: string): nil
---@field wait_if_paused fun(): nil
---@field aborted fun(): boolean
---@field asset_path fun(path: string): string
---@field project_root fun(): string
---@field get_app_setting fun(key?: any): any
---@field available_cores fun(): integer
---@field add_to_queue fun(job_payload: table): LycanResult
---@field start_process fun(): LycanResult
---@field pause_process fun(): LycanResult
---@field resume_process fun(): LycanResult
local LycanCtx = nil

--====================================================================
--  Global commands (bound for every Lua runtime at load time)
--====================================================================

-- ------------------- data & state -------------------

--- Read the current value of a form field.
---@param field_id string lowercase field identifier from form_schema.json
---@return any value current value (string, number or boolean)
function get_form_data(field_id) end

--- Read a form field with an explicit fallback when it is empty/nil.
---@param field_id string lowercase field identifier
---@param default? any value returned when the field holds nil/empty
---@return any value
function get(field_id, default) end

--- Read every form field as a name->value map.
---@return table<string, any> all values keyed by field_id
function get_all_form_data() end

--- Write a single field's value and push it to the live UI.
---@param field_id string lowercase field identifier
---@param value any new value (string, number or boolean)
---@return LycanResult result
function set_form_data(field_id, value) end

--- Overwrite the whole form in one shot.
---@param data table<string, any> name->value map
---@return LycanResult result
function set_all_form_data(data) end

-- ------------------- dynamic field & UI management -------------------

--- Add a brand new field to the live form from a JSON schema string.
---@param field_schema_json string JSON fragment of a field schema
---@return LycanResult result
function add_field(field_schema_json) end

--- Remove a field from the live form.
---@param field_id string
---@return LycanResult result
function delete_field(field_id) end

--- Hide a field (it keeps its value, but stops rendering).
---@param field_id string
---@return LycanResult result
function hide_field(field_id) end

--- Un-hide a previously hidden field.
---@param field_id string
---@return LycanResult result
function unhide_field(field_id) end

--- Move the user's cursor into a field's control.
---@param field_id string
---@return LycanResult result
function set_focus(field_id) end

--- Label a field's validation status ("idle", "valid", "invalid", ...).
---@param field_id string
---@param status string status keyword shown to the user
---@return LycanResult result
function set_field_status(field_id, status) end

--- Push a UI action to the React action layer (local handlers first).
---@param action_id string e.g. "open_popup" / "close_popup" / backend hooks
---@param params? table free-form JSON payload forwarded to the handler
---@return LycanResult result
function send_ui_action(action_id, params) end

-- ------------------- string validation & sanitization -------------------

--- Check a string against a Lua/Python-compatible regex pattern.
---@param pattern string regex
---@param subject string text to test
---@return boolean matched
function regex_validation(pattern, subject) end

--- Rewrite a string with a regex substitution (`re.sub`, all occurrences).
---@param pattern string regex
---@param replacement string replacement text
---@param subject string text to rewrite
---@return string rewritten subject
function regex_sanitization(pattern, replacement, subject) end

-- ------------------- execution, logs & errors -------------------

--- Run an external process; streaming output lands in the job console.
---@param cmd_table table { command = string|string[], args = string[]|string }
---@param info_string? string optional line printed before launching
---@return LycanExecResult result exit code + captured output lines
function execute_command(cmd_table, info_string) end

--- Run a Python hook file (`run(ctx)` / `main(ctx)`), same interop bridge.
---@param script_path string absolute or asset-root-relative script path
---@param args? table extra positional arguments passed to the hook
---@return LycanResult result result.result carries the hook's return value
function execute_py(script_path, args) end

--- Append a line to the job console.
---@param message string text to write
---@param level? string "info" | "warn" | "error" (default "info")
---@return LycanResult result
function send_log_output(message, level) end

--- Fetch everything written to the job console so far.
---@return LycanLogEntry[] entries newest-last
function get_log_output() end

--- Update the job progress ring (0-100).
---@param percent number 0..100
---@param status_text? string current step label
---@return nil
function progress(percent, status_text) end

--- Set the job status text/color.
---@param text string status message
---@param tone? string "blue" | "green" | "red" | "warn" (default "blue")
---@return nil
function status(text, tone) end

--- Alias of send_log_output(message, level).
---@param message string
---@param level? string "info" | "warn" | "error"
---@return LycanResult result
function log(message, level) end

--- Ask the user a blocking yes/no question in the interface.
---@param message string question text
---@param title? string dialog title (default "Confirmation")
---@param yes? string confirm button label (default "Yes")
---@param no? string cancel button label (default "No")
---@return boolean answered_yes
function confirm(message, title, yes, no) end

--- Reveal a file or folder in the OS file manager.
---@param path string absolute path
---@return nil
function open_explorer(path) end

--- Block until a pause is lifted (or an abort is requested).
---@return nil
function wait_if_paused() end

--- Halts the runtime by raising an interop error (message shown to the user).
---@param error_msg string user-facing failure message
---@return nil  -- never returns
function throw_error(error_msg) end

--- True once the user has asked to cancel the job (poll in long loops).
---@return boolean aborted
function aborted() end

--- Resolve a path relative to the application asset root.
---@param path string
---@return string absolute path
function asset_path(path) end

--- Absolute application asset root.
---@return string path
function project_root() end

--- Read the app settings document (or one of its sections).
---@param key? string|string[] section key or key path, nil = whole document
---@return any value (table, string, number or nil)
function get_app_setting(key) end

--- Total logical CPU cores of this machine.
---@return integer cores
function available_cores() end

-- ------------------- process control & queue -------------------

--- Place a payload on the engine-managed queue (auto-run by the engine).
---@param job_payload table job parameters
---@return LycanResult result
function add_to_queue(job_payload) end

--- Signal a process start to the engine (normally auto-managed).
---@return LycanResult result
function start_process() end

--- Request a pause for the current job (engine acknowledges).
---@return LycanResult result
function pause_process() end

--- Resume the current job after a pause.
---@return LycanResult result
function resume_process() end