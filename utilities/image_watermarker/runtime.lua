-- Image Watermarker - optional Lua hook (reference implementation).
--
-- The Core Execution Engine loads this file only when a Lua runtime (`lupa`)
-- is available; otherwise the Python hook (`runtime.py`) handles the job.
-- Every interop command is a first-class, native-like global function bound
-- directly into this script's environment via `lua.globals()` assignment,
-- mirroring the Python `InteropContext` one-to-one.

local function value_or(default, value)
  if value == nil or value == "" then
    return default
  end
  return value
end

-- Entry point: the engine calls `run()` when this script is the active hook.
function run()
  local source = value_or("", get_form_data("input_image"))
  local output = value_or("", get_form_data("output_image"))
  local text = value_or("", get_form_data("watermark_text"))

  if source == "" then
    throw_error("Source image does not exist.")
  end
  if output == "" then
    throw_error("Select an output image path first.")
  end

  -- Very low alpha is a no-op watermark; treat it as an error early.
  local alpha = tonumber(value_or(40, get_form_data("watermark_alpha")))
  if alpha <= 0 then
    throw_error("Watermark opacity must be greater than 0.")
  end

  status("Preparing watermark '" .. text .. "'")
  send_log_output("Lua hook: compositing watermark '" .. text .. "'")

  -- Delegation through the standard command-table form.
  progress(30, "Running conversion stage...")
  local result = execute_command(
    { command = "cmd", args = { "/c", "echo", "watermark:", text } },
    "Converting video"
  )
  if not result.ok then
    throw_error("Command failed with code " .. tostring(result.code))
  end

  progress(100, "Done")
  return { ok = true, message = "Lua hook finished for " .. output }
end

return run()