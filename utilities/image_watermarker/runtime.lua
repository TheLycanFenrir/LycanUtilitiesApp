-- Image Watermarker - optional Lua hook (reference implementation).
--
-- The Core Execution Engine loads this file only when a Lua runtime (`lupa`)
-- is available; otherwise the Python hook (`runtime.py`) handles the job.
-- Every interop command is reached through the `lycan` bridge, which mirrors
-- the Python `InteropContext` one-to-one.

local function value_or(default, value)
  if value == nil or value == "" then
    return default
  end
  return value
end

-- Entry point: the engine calls `run()` when this script is the active hook.
function run()
  local source = value_or("", lycan_call("get_form_data", { "input_image" }))
  local output = value_or("", lycan_call("get_form_data", { "output_image" }))
  local text = value_or("", lycan_call("get_form_data", { "watermark_text" }))

  if source == "" then
    lycan_call("throw_error", { "Source image does not exist." })
    return { ok = false, message = "Missing source image." }
  end
  if output == "" then
    lycan_call("throw_error", { "Select an output image path first." })
    return { ok = false, message = "Missing output image." }
  end

  -- Very low alpha is a no-op watermark; treat it as an error early.
  local alpha = tonumber(value_or(40, lycan_call("get_form_data", { "watermark_alpha" })))
  if alpha <= 0 then
    lycan_call("throw_error", { "Watermark opacity must be greater than 0." })
    return { ok = false, message = "Transparent watermark." }
  end

  lycan_call("send_log_output", { "Lua hook: compositing watermark '" .. text .. "'" })
  lycan_call("progress", { 60, "Rendering watermark (Lua)..." })

  -- Delegate the pixel work to a shell command / external tool of choice here.
  lycan_call("progress", { 100, "Done" })
  return { ok = true, message = "Lua hook finished for " .. output }
end

return run()
