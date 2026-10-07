-- Frames to Video - Lua command-composition hook.
--
-- Mirrors the Python runtime (runtime.py) through the InteropContext command
-- set: validates inputs, builds an FFmpeg concat list, composes the FFmpeg
-- command per output format and runs it via execute_command. Every interop
-- command is a first-class global function bound by core.lua_bridge.


local function value_or(default, value)
  if value == nil or value == "" then return default end
  return value
end

local function to_number(value, default)
  if value == nil or value == "" then return default end
  local n = tonumber(value)
  if n == nil then return default end
  return n
end

local function to_int(value, default, lo, hi)
  local n = tonumber(value)
  if n == nil then n = default end
  n = math.floor(n)
  if lo ~= nil then n = math.max(lo, n) end
  if hi ~= nil then n = math.min(hi, n) end
  return n
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

local function ffmpeg_available(ffmpeg)
  local output = run_capture(ffmpeg, "-version 2>&1")
  if output == nil then return false end
  return tostring(output):find("ffmpeg version", 1, true) ~= nil
end

local function probe_first_frame(ffmpeg, first_frame)
  local output = tostring(run_capture(ffmpeg, "-hide_banner -i " .. shell_quote(first_frame) .. " 2>&1"))
  local width_s, height_s = output:match("%s(%d+)x(%d+)")
  if not width_s then width_s, height_s = output:match("(%d+)x(%d+)") end
  if not width_s then
    throw_error("Could not read the first frame (no video stream detected).")
  end
  local width = tonumber(width_s)
  local height = tonumber(height_s)
  local alpha = (output:find("rgba", 1, true) ~= nil)
    or (output:find("yuva", 1, true) ~= nil)
    or (output:find("graya", 1, true) ~= nil)
    or (output:find("%(ya", 1, true) ~= nil)
    or (output:find("alpha", 1, true) ~= nil)
  return width, height, alpha
end

local function concat_list(frames_dir, fps)
  local frames = {}
  local dir = io.popen("cmd /c dir /b /a-d " .. shell_quote(frames_dir) .. " 2>nul", "r")
  if dir then
    for line in dir:lines() do
      if line ~= "" and line:sub(1, 1) ~= "." then
        frames[#frames + 1] = line
      end
    end
    dir:close()
  end
  table.sort(frames)
  if #frames == 0 then return nil, frames end

  local tmp = os.getenv("TEMP") or "."
  local path = tmp .. "\\frames-to-video-" .. os.time() .. "-" .. tostring(math.random(1000, 9999)) .. ".ffconcat"
  local fh = io.open(path, "w")
  if not fh then return nil, frames end
  fh:write("ffconcat version 1.0\n")
  local duration = string.format("%.9f", 1.0 / fps)
  local function escape_line(name)
    return ("file '%s'\n"):format(name:gsub("'", "'\\''"))
  end
  for index = 1, #frames do
    fh:write(escape_line(frames_dir .. "\\" .. frames[index]))
    fh:write("duration " .. duration .. "\n")
  end
  fh:write(escape_line(frames_dir .. "\\" .. frames[#frames]))
  fh:close()
  return path, frames
end

local function transient_path(suffix)
  return (os.getenv("TEMP") or ".") .. "\\frames-to-video-" .. os.time() .. "-"
    .. tostring(math.random(1000, 9999)) .. suffix
end

local function padded_filter(width, height, bg_hex, transparent)
  local target_w = math.floor(width / 2) * 2
  local target_h = math.floor(height / 2) * 2
  local scale = "scale=" .. target_w .. ":" .. target_h .. ":force_original_aspect_ratio=decrease"
  if transparent then
    return scale .. ",pad=" .. target_w .. ":" .. target_h .. ":(ow-iw)/2:(oh-ih)/2:color=0x000000@0"
  end
  local bg = "color=c=" .. bg_hex .. ":s=" .. target_w .. "x" .. target_h .. "[bg]"
  local vid = "[0:v]" .. scale .. "[vid]"
  local ovl = "[bg][vid]overlay=(W-w)/2:(H-h)/2:shortest=1"
  return bg .. ";" .. vid .. ";" .. ovl
end

local function prepend(base, prefix)
  for _, item in ipairs(prefix) do base[#base + 1] = item end
end

local function run_composed(ffmpeg, tail, info)
  execute_command({ command = ffmpeg, args = tail }, info)
end

-- Build the FFmpeg argv for an encode and run it. Handles all formats,
-- quality modes and optional 2-pass VBR, mirroring engine.ImageToVideo.
local function encode(ffmpeg, input_prefix, filter, fmt, is_mp4_av1,
                      use_transparency, crf_int, bitrate_val, threads,
                      q_mode, output)
  local args = {}
  prepend(args, input_prefix)
  local pass_log = nil
  local two_pass = (q_mode == "2-pass vbr")
  if two_pass then
    pass_log = (os.getenv("TEMP") or ".") .. "\\frames-to-video-2pass-" .. os.time()
  end

  if fmt == "gif" then
    error("gif handled elsewhere")
  elseif fmt == "apng" then
    args[#args + 1] = "-vf"; args[#args + 1] = filter
    args[#args + 1] = "-c:v"; args[#args + 1] = "apng"
    args[#args + 1] = "-pix_fmt"; args[#args + 1] = (use_transparency and "rgba" or "rgb24")
    args[#args + 1] = "-plays"; args[#args + 1] = "0"
    args[#args + 1] = "-threads"; args[#args + 1] = tostring(threads)
    args[#args + 1] = "-f"; args[#args + 1] = "apng"
    args[#args + 1] = output
    run_composed(ffmpeg, args, "Converting APNG...")
  elseif fmt == "webm" then
    args[#args + 1] = "-vf"; args[#args + 1] = filter
    args[#args + 1] = "-c:v"; args[#args + 1] = "libvpx-vp9"
    args[#args + 1] = "-pix_fmt"; args[#args + 1] = (use_transparency and "yuva420p" or "yuv420p")
    args[#args + 1] = "-an"
    args[#args + 1] = "-threads"; args[#args + 1] = tostring(threads)
    args[#args + 1] = "-row-mt"; args[#args + 1] = "1"
    if q_mode == "crf" then
      args[#args + 1] = "-crf"; args[#args + 1] = tostring(crf_int or 18)
      args[#args + 1] = "-b:v"; args[#args + 1] = "0"
    elseif bitrate_val then
      args[#args + 1] = "-b:v"; args[#args + 1] = tostring(bitrate_val) .. "k"
    end
    if use_transparency then
      args[#args + 1] = "-auto-alt-ref"; args[#args + 1] = "0"
    end
    if two_pass then
      local pass1 = {}
      prepend(pass1, args)
      pass1[#pass1 + 1] = "-pass"; pass1[#pass1 + 1] = "1"
      pass1[#pass1 + 1] = "-passlogfile"; pass1[#pass1 + 1] = pass_log
      pass1[#pass1 + 1] = "-f"; pass1[#pass1 + 1] = "null"
      pass1[#pass1 + 1] = "-"
      run_composed(ffmpeg, pass1, "Converting video (pass 1)...")
      progress(50, "Converting video (pass 2)...")
      args[#args + 1] = "-pass"; args[#args + 1] = "2"
      args[#args + 1] = "-passlogfile"; args[#args + 1] = pass_log
      args[#args + 1] = output
      run_composed(ffmpeg, args, "Converting video (pass 2)...")
    else
      args[#args + 1] = output
      run_composed(ffmpeg, args, "Converting video...")
    end
  elseif fmt == "mp4_av1" or fmt == "mp4_h264" then
    args[#args + 1] = "-vf"; args[#args + 1] = filter
    args[#args + 1] = "-pix_fmt"; args[#args + 1] = "yuv420p"
    args[#args + 1] = "-threads"; args[#args + 1] = tostring(threads)
    if fmt == "mp4_av1" then
      args[#args + 1] = "-c:v"; args[#args + 1] = "libsvtav1"
      args[#args + 1] = "-preset"; args[#args + 1] = "6"
      if q_mode == "crf" then
        args[#args + 1] = "-crf"; args[#args + 1] = tostring(crf_int or 30)
        args[#args + 1] = "-b:v"; args[#args + 1] = "0"
      elseif bitrate_val then
        args[#args + 1] = "-b:v"; args[#args + 1] = tostring(bitrate_val) .. "k"
      end
    else
      args[#args + 1] = "-c:v"; args[#args + 1] = "libx264"
      args[#args + 1] = "-preset"; args[#args + 1] = "medium"
      if q_mode == "crf" then
        args[#args + 1] = "-crf"; args[#args + 1] = tostring(crf_int or 18)
      elseif bitrate_val then
        args[#args + 1] = "-b:v"; args[#args + 1] = tostring(bitrate_val) .. "k"
      end
    end
    if two_pass then
      local pass1 = {}
      prepend(pass1, args)
      pass1[#pass1 + 1] = "-pass"; pass1[#pass1 + 1] = "1"
      pass1[#pass1 + 1] = "-passlogfile"; pass1[#pass1 + 1] = pass_log
      pass1[#pass1 + 1] = "-f"; pass1[#pass1 + 1] = "null"
      pass1[#pass1 + 1] = "-"
      run_composed(ffmpeg, pass1, "Converting video (pass 1)...")
      progress(50, "Converting video (pass 2)...")
      args[#args + 1] = "-pass"; args[#args + 1] = "2"
      args[#args + 1] = "-passlogfile"; args[#args + 1] = pass_log
      args[#args + 1] = "-movflags"; args[#args + 1] = "+faststart"
      args[#args + 1] = output
      run_composed(ffmpeg, args, "Converting video (pass 2)...")
    else
      args[#args + 1] = "-movflags"; args[#args + 1] = "+faststart"
      args[#args + 1] = output
      run_composed(ffmpeg, args, "Converting video...")
    end
  else -- webp
    args[#args + 1] = "-vf"; args[#args + 1] = filter
    args[#args + 1] = "-c:v"; args[#args + 1] = "libwebp"
    args[#args + 1] = "-pix_fmt"; args[#args + 1] = (use_transparency and "rgba" or "yuv420p")
    args[#args + 1] = "-loop"; args[#args + 1] = "0"
    args[#args + 1] = "-threads"; args[#args + 1] = tostring(threads)
    if q_mode == "lossless" then
      args[#args + 1] = "-lossless"; args[#args + 1] = "1"
    else
      args[#args + 1] = "-crf"; args[#args + 1] = tostring(crf_int or 18)
    end
    args[#args + 1] = output
    run_composed(ffmpeg, args, "Converting WEBP...")
  end

  if pass_log then
    os.remove(pass_log .. ".log")
    os.remove(pass_log .. ".log.mbtree")
  end
end

local function guess_ext(fmt)
  if fmt == "mp4_av1" or fmt == "mp4_h264" then return ".mp4" end
  return "." .. fmt
end

local function muted_pcalls(fn)
  local ok, err = pcall(fn)
  return ok, err
end

function run()
  local source = tostring(value_or("", get_form_data("source_folder"))):gsub("^%s+", ""):gsub("%s+$", "")
  local output_folder = tostring(value_or("", get_form_data("output_folder"))):gsub("^%s+", ""):gsub("%s+$", "")
  local fmt = tostring(value_or("mp4_h264", get_form_data("output_type"))):gsub("^%s+", ""):gsub("%s+$", "")
  local fps = to_number(get_form_data("fps"), 30)
  local crf = get_form_data("crf")
  local threads = to_int(get_form_data("threads"), 1, 1, 64)
  local transparent = tostring(value_or("false", get_form_data("transparent"))) == "true"
  local q_mode = tostring(value_or("CRF", get_form_data("quality_mode"))):lower()
  local bitrate = tonumber(value_or(0, get_form_data("bitrate")))
  local bg = tostring(value_or("black", get_form_data("background"))):lower()
  local bg_color = get_form_data("background_color")
  local open_after = tostring(value_or("false", get_form_data("open_explorer_after_conversion"))) == "true"
  local gif_colors = to_int(get_form_data("gif_color_limit"), 256, 4, 256)
  local source_mode = tostring(value_or("folder", get_form_data("source_mode"))):lower()
  local output = tostring(value_or("", get_form_data("output_file")))

  if source == "" then throw_error("Please select a source folder.") end
  if output_folder == "" then throw_error("Please select an output folder.") end
  if fps == nil or fps <= 0 then throw_error("Please enter a valid FPS value.") end

  local total_cores = available_cores() or threads
  threads = math.min(threads, total_cores)

  local desired_ext = guess_ext(fmt)
  if output == "" then
    local root = source:match("([^\\/]+)[\\/]*$") or "video"
    root = root:gsub("%.[^%.]+$", "")
    output = output_folder .. "\\" .. root .. desired_ext
  else
    local ext = output:match("%.([^%.]+)$") or ""
    if ("." .. ext:lower()) ~= desired_ext then
      output = (output:match("^(.*)%.[^%.]+$") or output) .. desired_ext
      log("Output extension adjusted to '" .. desired_ext .. "'.")
    end
  end

  local frames_dir = source
  if source_mode == "file" then
    local f = io.open(source, "r")
    if not f then throw_error("The source file '" .. source .. "' does not exist.") end
    f:close()
    frames_dir = source:match("^(.*)[\\/][^\\/]*$") or "."
    log("Using directory of source file: " .. frames_dir)
  else
    if not dir_exists(source) then throw_error("The source folder '" .. source .. "' does not exist.") end
  end

  local out_dir = output:match("^(.*)[\\/][^\\/]*$") or "."
  if not dir_exists(out_dir) then
    os.execute("cmd /c mkdir " .. shell_quote(out_dir) .. " 2>nul")
    if not dir_exists(out_dir) then throw_error("The output folder '" .. out_dir .. "' could not be created.") end
  end

  local existing = io.open(output, "r")
  if existing then
    existing:close()
    if not confirm(
      "The file '" .. output .. "' already exists. Do you want to replace it?",
      "File Exists Warning", "Replace", "Cancel"
    ) then
      log("Conversion cancelled because the output file already exists.", "warn")
      return { ok = false, message = "Cancelled by user." }
    end
  end

  if fmt == "gif" then
    if fps > 50 and not confirm(
      "GIFs with FPS over 50 may be very large and play poorly. Continue anyway?",
      "High FPS Warning", "Continue", "Cancel"
    ) then
      return { ok = false, message = "Cancelled by user." }
    end
    if fps > 100 then
      log("GIF FPS cannot exceed 100. It will be clamped to 100.", "warn")
      fps = 100
    end
  elseif fmt == "apng" then
    if fps > 50 and not confirm(
      "APNGs with FPS over 50 may be very large and play poorly. Continue anyway?",
      "High FPS Warning", "Continue", "Cancel"
    ) then
      return { ok = false, message = "Cancelled by user." }
    end
    if fps > 100 then
      log("APNG FPS cannot exceed 100. It will be clamped to 100.", "warn")
      fps = 100
    end
  end

  local crf_int = crf
  local crf_hi = 51
  if fmt == "mp4_av1" or fmt == "webm" or fmt == "webp" then crf_hi = 63 end
  if crf ~= nil and (fmt == "mp4_h264" or fmt == "mp4_av1" or fmt == "webm" or fmt == "webp") then
    crf_int = to_int(crf, crf, 0, crf_hi)
  end

  if fmt ~= "webp" and q_mode == "lossless" then q_mode = "crf" end

  local bg_hex
  if bg == "white" then
    bg_hex = "0xffffff"
  elseif bg == "custom" and bg_color ~= nil then
    local r, g, b = parse_rgb(bg_color, 0, 0, 0)
    bg_hex = string.format("0x%02x%02x%02x", r % 256, g % 256, b % 256)
  else
    bg_hex = "0x000000"
  end

  status("Checking FFmpeg...", "blue")
  local ffmpeg_cmd = resolve_ffmpeg()
  if not ffmpeg_available(ffmpeg_cmd) then
    status("FFmpeg is missing", "red")
    throw_error("FFmpeg not found. Please install it and try again.")
  end
  log("FFmpeg check passed.")

  local concat_path, frame_names = concat_list(frames_dir, fps)
  if not concat_path then
    throw_error("No frames found in folder '" .. frames_dir .. "'.")
  end
  log("Found " .. #frame_names .. " frames to convert.")

  local first = frames_dir .. "\\" .. frame_names[1]
  local width, height, has_alpha = probe_first_frame(ffmpeg_cmd, first)
  local supports_alpha = (fmt == "webm" or fmt == "apng" or fmt == "gif" or fmt == "webp")
  local use_transparency = has_alpha and supports_alpha and transparent

  local input_prefix = { "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-r", tostring(fps),
                         "-f", "concat", "-safe", "0", "-i", concat_path }

  local bitrate_val = nil
  if q_mode == "bitrate" or q_mode == "2-pass vbr" then
    bitrate_val = math.max(1, to_int(bitrate, 8000, 1, 100000000))
    local bpp = (bitrate_val * 1000) / (width * height * fps)
    if bpp > 0.3 then
      if not confirm(
        "Bitrate is too high for the given resolution and FPS that may cause the file size to be too large and issues with playback. Do you want to continue?",
        "Bitrate too high", "Continue", "Cancel"
      ) then
        os.remove(concat_path)
        return { ok = false, message = "Aborted by user." }
      end
    elseif bpp < 0.03 then
      if not confirm(
        "Bitrate is too low for the given resolution and FPS that may cause blurry video. Do you want to continue?",
        "Bitrate too low", "Continue", "Cancel"
      ) then
        os.remove(concat_path)
        return { ok = false, message = "Aborted by user." }
      end
    end
  end

  log("Starting conversion...")
  log("Source: " .. source)
  log("Output: " .. output)
  log("Format: " .. fmt)
  log("FPS: " .. tostring(fps))
  if crf_int ~= nil and q_mode ~= "lossless" then log("CRF: " .. tostring(crf_int)) end
  log("Threads: " .. tostring(threads))

  status("Converting video...", "blue")

  local palette_path = nil
  local ok, err = muted_pcalls(function()
    local filter = padded_filter(width, height, bg_hex, use_transparency)
    if fmt == "gif" then
      progress(5, "Generating palette...")
      local palette_filter = filter .. ",palettegen=max_colors=" .. gif_colors
      palette_path = transient_path(".png")
      local p_args = {}
      prepend(p_args, input_prefix)
      p_args[#p_args + 1] = "-vf"; p_args[#p_args + 1] = palette_filter
      p_args[#p_args + 1] = palette_path
      run_composed(ffmpeg_cmd, p_args, "Generating GIF palette...")
      progress(10, "Palette generated.")
      local g_args = {}
      prepend(g_args, input_prefix)
      g_args[#g_args + 1] = "-i"; g_args[#g_args + 1] = palette_path
      g_args[#g_args + 1] = "-lavfi"; g_args[#g_args + 1] = filter .. ",paletteuse"
      g_args[#g_args + 1] = "-threads"; g_args[#g_args + 1] = tostring(threads)
      g_args[#g_args + 1] = output
      run_composed(ffmpeg_cmd, g_args, "Converting GIF...")
    else
      encode(ffmpeg_cmd, input_prefix, filter, fmt, fmt == "mp4_av1",
             use_transparency, crf_int, bitrate_val, threads, q_mode, output)
    end
  end)

  os.remove(concat_path)
  if palette_path then os.remove(palette_path) end

  if not ok then
    return { ok = false, message = "Conversion failed.", reason = tostring(err) }
  end
  if aborted() then
    log("Conversion aborted by user.", "warn")
    return { ok = false, message = "Aborted by user." }
  end

  progress(100, "Video converted successfully!")
  status("Video converted successfully!", "green")
  log("Conversion completed successfully!")
  if open_after then
    open_explorer(output)
    log("Opened file explorer: " .. (output:match("^(.*)[\\/][^\\/]*$") or output))
  end
  return { ok = true, message = "Video has been converted successfully!" }
end

return run()