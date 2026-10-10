# Architecture

[← Back to README](README.md)

## Project Structure

```
LycanUtilitiesApp/
├── main.py                        # PyWebView entry point (window bootstrap)
├── build_react_n_run.py           # Dev launcher: Vite HMR / build + restart watcher
├── setup_env.py                   # Bootstrap: venv creation + dependency installer
├── requirements.txt               # Python dependencies
├── lycan_api.lua                  # IDE stub for the Lua interop API (never loaded at runtime)
├── app/                           # Backend application layer
│   ├── bridge.py                  # Composes the JS bridge (Api) from the mixins
│   ├── info.py                    # Version, title and contributor metadata
│   ├── updates.py                 # GitHub release update check
│   ├── bridges/                   # JS bridge mixins (installed as js_api)
│   │   ├── envelope.py            #   status envelope + _api_response wrapper
│   │   ├── common.py              #   shared job model / helpers
│   │   ├── app_bridge.py          #   window, theme, devtools, dashboard
│   │   ├── utilities_bridge.py    #   utility scan, descriptors, runtime dispatch
│   │   ├── store_bridge.py        #   utility store browsing
│   │   ├── tools_bridge.py        #   tool opening + system stats
│   │   ├── settings_bridge.py     #   app settings + per-tool stores
│   │   ├── python_libraries_bridge.py  # Python Libraries store
│   │   ├── dialog_bridge.py       #   native file / folder dialogs
│   │   ├── jobs_bridge.py         #   start_job / poll / events / confirm
│   │   ├── queue_bridge.py        #   Lycan Worker job queue
│   │   └── runtime_bridge.py      #   Lua / Python hook dispatch
│   ├── settings/                  # Persisted app state (JSON)
│   │   ├── app_config.py          #   the single app-level settings document
│   │   ├── paths.py, jsonio.py    #   path resolution + read/write helpers
│   │   ├── favorites.py, lastused.py, theme.py
│   │   ├── queue.py               #   queued worker jobs
│   │   ├── storage.py, tool_stores.py  # per-tool settings/preset stores
│   ├── python_libraries/          # Python Libraries store backend
│   │   ├── index.py, cache.py     #   PyPI simple-index search + metadata cache
│   │   ├── installed.py, pipops.py, requirements.py, metadata.py
│   │   ├── audit.py               #   pip-audit vulnerability scanning
│   │   └── progress.py, helpers.py, constants.py
│   ├── system/                    # cpu.py (CPU/core detection), ffmpeg.py
│   └── screenpick/                # picker.py, loupe.py, win32.py (color picker)
├── core/                          # Framework internals
│   ├── scanner.py                 # Utility scan + utilities_cache.json compiler
│   ├── schema.py                  # manifest.json / form_schema.json validation
│   ├── interop.py                 # InteropContext: commands exposed to runtimes
│   ├── lua_bridge.py              # Lua runtime + command binding (requires lupa)
│   └── debug_log.py               # Tiered debug logging (debug_info levels 0-4)
├── utilities/                     # One self-contained folder per utility
│   ├── frames_to_video/           #   manifest.json + form_schema.json + runtime(.py/.lua)
│   ├── image_splitter/
│   ├── texture_mipmap/            #   includes DDSExporter.py (BC1–BC7 + uncompressed)
│   ├── image_watermarker/         #   Coming Soon
│   ├── card_test/, ui_tester/, bad_json_test/, bad_schema_test/, blank_schema_test/
│   ├── utilities_cache.json       #   compiled scan cache (SHA-256 fast boot)
│   └── util_lists_cache-lock.json #   record of the last recompile
├── frontend/                      # React SPA (Vite + SCSS)
│   ├── index.html                 # Vite entry
│   ├── vite.config.js             # Build configuration
│   ├── public/assets/             # Icons, favicon, wallpaper, .cache/icons
│   └── src/
│       ├── main.jsx               # React bootstrap
│       ├── App.jsx                # Shell wiring & routing
│       ├── tabs/                  # HomeDashboard, FormTool, UtilityErrorTab
│       ├── components/            # ConsolePanel, FormGenerator, PresetBar, UtilityCardList, ...
│       ├── contexts/              # FormState, Modal, Theme, Toast, Zoom
│       ├── hooks/                 # usePyWebView, useJobConsole, usePersistentForm
│       ├── styles/                # design tokens, themes, per-module partials
│       └── utils/                 # color, emoji, form, icons, paths, platform, validate
└── userdata/                      # Local user state (created on first run)
    ├── favorites.json
    ├── history.json
    ├── lastused.json
    ├── presets.json
    ├── settings.json
    ├── worker_queue.json
    └── python_libraries_cache.json
```

## Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  PyWebView Window (WebView2 / WebKit / Cocoa)                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  React SPA (Vite bundle, or the dev server in HMR mode)       │  │
│  │  • Shell: topbar, statusbar, modals, toasts                   │  │
│  │  • Dashboard, utility tabs, dynamic forms, console, queue     │  │
│  │  • async/await ↔ window.pywebview.api.*                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          │ JS Bridge (window.pywebview.api)         │
│                          ▼                                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Python Backend (app.bridge.Api — composed from mixins)       │  │
│  │  • Standard envelope: {ok, reason, detail, **payload}         │  │
│  │  • Utility scanner + SHA-256 cache + schema validation        │  │
│  │  • Job system: start_job → poll(job_id, cursor) → events      │  │
│  │  • Python Libraries store, settings, dialogs, system stats    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          │ InteropContext (core.interop)            │
│                          ▼                                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Utility Runtime (per utility: runtime.py and/or runtime.lua) │  │
│  │  • Lua commands bound as native globals (core.lua_bridge)     │  │
│  │  • execute_command → FFmpeg / Pillow / NumPy work             │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Design notes

- The frontend never blocks: long operations run through the `start_job` + `poll` sequence. Each consumer advances its own cursor, so the Lycan Worker popup and an attached utility tab can watch the same job without stealing each other's events.
- Backend workers push structured events (`log`, `status`, `progress`, `confirm`, `done`) into per-job, replayable buffers.
- Confirmation dialogs (overwrite prompts, file-count warnings) are async — the worker emits `confirm`, the UI shows a modal, and `resolve_confirm` unblocks the worker.
- Every public bridge method (no leading underscore) is wrapped with `_api_response`, so all frontend calls receive the same status envelope; machine-readable sub-codes travel in the optional `code` field.
- External links are always opened in the system browser through the bridge, never inside the window.
- Utility discovery is cache-first: `core/scanner.py` hashes each utility's manifest/schema/runtime files with SHA-256 and recompiles `utilities_cache.json` only when something changed (Fast Boot). Broken utilities are reported through a separate error channel instead of failing startup.
