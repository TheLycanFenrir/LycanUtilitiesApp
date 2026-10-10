# Writing a Utility

[← Back to README](README.md)

Each utility is a folder under `utilities/`:

```
utilities/my_utility/
├── manifest.json          # id, title, description, tags, badge, runtime + schema files
├── form_schema.json       # the form the UI renders (fields, defaults, validation)
├── runtime.py             # Python hook (optional)
├── runtime.lua            # Lua hook (optional)
├── engine.py              # implementation the runtime calls (optional)
├── requirements.txt       # extra pip deps for this utility (optional)
└── assets/icons/          # icon PNGs, mirrored into the frontend icon cache
```

- `manifest.json` declares `id`, `title`, `description`, `version`, `badge`, `tags`, the `runtime` and `schema` filenames, and the `handlers` (`python` / `lua`).
- `form_schema.json` is validated by `core/schema.py`; an invalid schema marks the utility as broken rather than serving a half-rendered form.
- Runtimes receive an interop context: Python hooks get the `InteropContext`, and Lua hooks get every command bound as a native global. See [lycan_api.lua](lycan_api.lua) for the full signature stub.

## Example manifest

```json
{
  "id": "my_utility",
  "title": "My Utility",
  "description": "Does something useful.",
  "python_requirements": ["Pillow"],
  "additional_requirements": [],
  "version": "1.0.0",
  "icon": "🧰",
  "icon_file": "assets/icons/my_utility.png",
  "badge": "Beta",
  "tags": ["image", "tool"],
  "runtime": "runtime.py",
  "schema": "form_schema.json",
  "form_engine": "auto",
  "handlers": {
    "python": "runtime.py",
    "lua": "runtime.lua"
  }
}
```

## Example Lua hook

```lua
local function run(ctx)
  local text = get_form_data("watermark_text")
  if text == "" then throw_error("Missing input") end
  local result = execute_command(
    { command = "ffmpeg", args = { "-version" } },
    "probing"
  )
  status("done")
  return { ok = true, message = "finished" }
end
return run(ctx)
```

Runtimes also receive a `ctx` object; every `ctx.method(...)` is additionally exposed as a standalone global of the same name (that is what makes the `get_form_data` / `throw_error` / `execute_command` calls above work).
