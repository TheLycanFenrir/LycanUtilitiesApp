-- Image Watermarker - Lua command-composition hook.
--
-- Composites a text watermark onto an image with FFmpeg's drawtext filter.
-- Mirrors the Python runtime's behavior (anchor positions, alpha, color,
-- auto font sizing, date stamp) but expresses it as a single composed command
-- run through `execute_command`. Every interop command is a first-class global
-- function bound by core.lua_bridge; the Python hook (runtime.py) stays bound
-- as the fallback implementation when lupa is unavailable.


local function value_or(default, value)
  if value == nil or value == "" then return default end
  return value
end

local function parse_rgb(value, default_r, default_g, default_b)
  local r, g, b = default_r, default_g, default_b
  if type(value) == "table" then
    r = tonumber(value[1]) or r
    g = tonumber(value[2]) or g
    b = tonumber(value[3]) or b
  elseif type(value) == "string" then
    local list = tostring(value)
    list = list:gsub("^%[", ""):gsub("%]$", ""):gsub("%s", "")
    local first, second, third = list:match("^(%-?%d+),(%-?%d+),?(%-?%d*)$")
    if first then
      r = tonumber(first) or r
      g = tonumber(second) or g
      if third and third ~= "" then b = tonumber(third) or b end
    end
  end
  return r, g, b
end

local function shell_quote(path)
  return '"' .. tostring(path):gsub('"', '\\"') .. '"'
end

local function read_command_output(cmd)
  local pipe = io.popen(cmd, "r")
  if not pipe then return nil end
  local all = pipe:read("*a")
  pipe:close()
  return all or ""
end

-- Run a program for probing and capture its output. Uses cmd's canonical
-- "outer quote" rule so both bare PATH names and quoted executables with
-- spaces are handled.
local function run_capture(program, tail)
  return read_command_output('cmd /c ""' .. tostring(program) .. '" ' .. tail .. '"')
end

local function dir_exists(path)
  local probe = "cmd /c cd /d " .. shell_quote(path) .. " 2>nul && echo 1 || echo 0"
  local out = tostring(read_command_output(probe))
  return (out:gsub("%s", "") == "1")
end

-- Escape a literal string embedded inside a drawtext filter option. Colons,
-- backslashes, percent signs and single quotes all need protection because the
-- whole option body is parsed by FFmpeg's filter parser.
local function filter_escape(value)
  local out = tostring(value)
  out = out:gsub("\\", "\\\\")
  out = out:gsub("'", "\\'")
  out = out:gsub("%:", "\\:")
  out = out:gsub("%%", "%%%%")
  return out
end

local ANCHORS = {
  top_left      = { x = "20",               y = "20" },
  top_center    = { x = "(w-text_w)/2",     y = "20" },
  top_right     = { x = "w-text_w-20",      y = "20" },
  middle_left   = { x = "20",               y = "(h-text_h)/2" },
  center        = { x = "(w-text_w)/2",     y = "(h-text_h)/2" },
  middle_right  = { x = "w-text_w-20",      y = "(h-text_h)/2" },
  bottom_left   = { x = "20",               y = "h-text_h-20" },
  bottom_center = { x = "(w-text_w)/2",     y = "h-text_h-20" },
  bottom_right  = { x = "w-text_w-20",      y = "h-text_h-20" },
}

local function resolve_ffmpeg()
  local settings = get_app_setting() or {}
  local ffmpeg = settings["ffmpeg"] or {}
  if type(ffmpeg) ~= "table" then ffmpeg = {} end
  local use_system = true
  if ffmpeg["use_system_path"] ~= nil then
    use_system = tostring(ffmpeg["use_system_path"]) ~= "false"
  end
  local configured = tostring(value_or("", ffmpeg["path"])):gsub("^%s+", ""):gsub("%s+$", "")
  if use_system then return "ffmpeg" end
  if configured == "" then
    throw_error("ffmpeg is not configured. Set its location in Settings -> FFmpeg.")
  end
  local f = io.open(configured, "r")
  if f then
    f:close()
    if configured:lower():match("%.exe$") then return configured end
    return configured
  end
  local exe = io.open(configured .. "\\ffmpeg.exe", "r")
  if exe then exe:close() return configured .. "\\ffmpeg.exe" end
  local bin = io.open(configured .. "\\ffmpeg", "r")
  if bin then bin:close() return configured .. "\\ffmpeg" end
  throw_error("ffmpeg not found at the configured path '" .. configured .. "'. Update it in Settings -> FFmpeg.")
end

local function first_font()
  local candidates = {
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
  }
  for _, candidate in ipairs(candidates) do
    local f = io.open(candidate, "r")
    if f then
      f:close()
      return candidate
    end
  end
  return nil
end

local function probe_width(ffmpeg, source)
  local out = tostring(run_capture(ffmpeg, "-hide_banner -i " .. shell_quote(source) .. " 2>&1"))
  local width_s = out:match("%s(%d+)x%d+")
  if not width_s then width_s = out:match("(%d+)x%d+") end
  if not width_s then return nil end
  return tonumber(width_s)
end

function run()
  local source = tostring(value_or("", get_form_data("input_image"))):gsub("^%s+", ""):gsub("%s+$", "")
  local output = tostring(value_or("", get_form_data("output_image"))):gsub("^%s+", ""):gsub("%s+$", "")
  local text = tostring(value_or("", get_form_data("watermark_text"))):gsub("^%s+", ""):gsub("%s+$", "")
  local include_date = tostring(value_or("true", get_form_data("date_stamp"))) == "true"

  if source == "" then throw_error("Source image does not exist.") end
  if output == "" then throw_error("Select an output image path first.") end

  local alpha = tonumber(value_or(40, get_form_data("watermark_alpha"))) or 40
  alpha = math.max(0, math.min(100, math.floor(alpha)))
  if alpha <= 0 then throw_error("Watermark opacity must be greater than 0.") end

  if include_date then
    text = text .. "  " .. os.date("%Y-%m-%d")
    text = text:gsub("^%s+", ""):gsub("%s+$", "")
  end
  if text == "" then throw_error("Watermark text is empty.") end

  local r, g, b = parse_rgb(get_form_data("watermark_color"), 255, 255, 255)
  local alpha_01 = string.format("%.2f", alpha / 100)

  local ffmpeg_cmd = resolve_ffmpeg()
  local width = probe_width(ffmpeg_cmd, source)
  local font_px = tonumber(value_or(0, get_form_data("font_size"))) or 0
  if width and font_px <= 0 then
    font_px = math.max(12, math.floor(width * 0.055))
  end
  if font_px <= 0 then font_px = 64 end

  local font = first_font()
  local fontfile = ""
  if font then
    local path = font:gsub("\\", "/")
    fontfile = "fontfile='" .. filter_escape(path) .. "'"
  end

  local pos_key = tostring(value_or("bottom_right", get_form_data("watermark_position"))):lower():gsub("%s+", "_")
  local anchor = ANCHORS[pos_key] or ANCHORS.bottom_right

  local text_esc = filter_escape(text)
  local option_text = {
    "text='" .. text_esc .. "'",
    "fontcolor=0x" .. string.format("%02x%02x%02x", r % 256, g % 256, b % 256) .. "@" .. alpha_01,
    "bordercolor=0x000000@" .. alpha_01,
    "borderw=2",
  }
  if fontfile ~= "" then option_text[#option_text + 1] = fontfile end
  option_text[#option_text + 1] = "fontsize=" .. tostring(font_px)
  option_text[#option_text + 1] = "x=" .. anchor.x
  option_text[#option_text + 1] = "y=" .. anchor.y

  local drawtext = "drawtext=" .. table.concat(option_text, ":")

  local out_dir = output:match("^(.*)[\\/][^\\/]*$") or "."
  if not dir_exists(out_dir) then
    os.execute("cmd /c mkdir " .. shell_quote(out_dir) .. " 2>nul")
    if not dir_exists(out_dir) then throw_error("The output folder '" .. out_dir .. "' could not be created.") end
  end

  progress(30, "Rendering watermark...")
  status("Applying watermark...", "blue")
  execute_command(
    { command = ffmpeg_cmd, args = { "-y", "-hide_banner", "-loglevel", "error", "-nostats",
                                     "-i", source, "-vf", drawtext, output } },
    "Watermarking image..."
  )

  progress(100, "Done")
  return { ok = true, message = "Saved watermarked image to " .. output }
end

return run()