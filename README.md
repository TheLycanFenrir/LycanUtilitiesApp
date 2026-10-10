# Lycan Utilities

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A lightweight desktop toolkit for media and texture workflows, built around a **React (Vite)** single-page app hosted in a native **PyWebView** window. Utilities are self-contained folders — each with its own JSON form schema and a Python and/or Lua runtime — that the backend discovers, validates and runs entirely offline.

> **Version:** alpha-1.4.0
> **Author:** [TheLycanFenrir](https://github.com/TheLycanFenrir)

## Overview

Lycan Utilities pairs a modern React UI with a Python backend that performs every heavy operation — FFmpeg, Pillow, NumPy — in background worker threads. The UI talks to the backend through PyWebView's JS bridge, streaming progress, logs and status in real time. There is no web server, no sign-in and no cloud: everything runs locally on your machine.

Tools are **utilities**: a `utilities/` folder holds one directory per tool, each declaring itself through a `manifest.json`, a JSON **form schema** that the UI renders dynamically, and an executable runtime (Python, Lua, or both). The backend scans and validates every folder at startup, caches the result, and hot-reloads changed or newly added utilities.

## Key Features

- **Dynamic utility system** — drop a folder into `utilities/` and the dashboard picks it up; the React form is generated from the utility's JSON schema
- **Python & Lua runtimes** — utilities run as Python hooks and/or Lua scripts through one shared, first-class interop API (Lua support is optional and requires `lupa`)
- **Fast Boot scanner** — utilities are SHA-256 hashed and cached in `utilities_cache.json`, so unchanged tools boot instantly and edits are auto-detected
- **Graceful load errors** — a utility with a broken `manifest.json` / `form_schema.json` surfaces a dedicated error tab with a caret-framed snippet of the offending line
- **Modern React UI** — component-driven SPA with SCSS design tokens, dark/light themes, smooth transitions, live search and filtering
- **Background job system** — cancellable worker jobs that stream structured `status` / `progress` / `log` events, with async confirmation dialogs
- **Lycan Worker queue** — queue utilities and let the worker run them back-to-back, restored across restarts
- **Python Libraries store** — search PyPI, manage the app's own Python packages, and scan for known vulnerabilities (via `pip-audit`) before installing
- **Live system resource meter** — CPU, app RAM and system RAM indicators with usage meters in the status bar
- **Screen color picker** — pick pixel colors with a magnifier loupe, persisted as recent colors
- **Update checker** — checks the GitHub releases feed (falls back to a bundled test release offline)
- **Favorites & usage tracking** — per-tool favorites and "Last Used" ordering, persisted locally
- **Per-tool presets & persistence** — tool settings, presets and path history remembered between sessions
- **Native file dialogs** — OS-native open/folder dialogs routed through the bridge
- **Easter egg** — press and hold the wolf icon in the bottom-left to peek the backdrop wallpaper

### Bundled utilities

| Utility | Badge | Runtime | Notes |
| --- | --- | --- | --- |
| **Frames to Video** | Beta | Python + Lua | Image sequences → MP4 (H.264 / AV1), WebM, GIF, APNG or WEBP |
| **Image Splitter** | Beta | Python | Slice textures into grids, custom tile sizes or alpha components |
| **Texture Mipmap Generator** | Alpha | Python | Mipmap chains with optional DDS output (`DDSExporter.py`, BC1–BC7 + uncompressed) |
| **Image Watermarker** | Coming Soon | Python + Lua | Watermark images with text or logos |
| **UI / card / schema testers** | — | Python | Scaffolding utilities (`ui_tester`, `card_test`, `bad_json_test`, `bad_schema_test`, `blank_schema_test`) used to exercise the scanner, form generator and error views |

## Quick Start

```bash
git clone https://github.com/TheLycanFenrir/LycanUtilitiesApp
cd LycanUtilitiesApp
python setup_env.py
cd frontend && npm install && cd ..
python build_react_n_run.py --no-hmr
```

See [INSTALLATION.md](INSTALLATION.md) for prerequisites, the full setup and every launcher flag.

## Usage

1. Launch the app with `python build_react_n_run.py` (or `python main.py` after building).
2. Use the **search bar** to filter utilities by name, description or tag.
3. Use the **sort pills** to reorder utilities (Newest / Last Used / Alphabetical / Favorites).
4. **Click** a card to open a utility; its form is rendered from the utility's JSON schema.
5. Click the **star** on a card to favorite it.
6. Use the **☉ / ☽** button in the top-right to toggle the theme.
7. Configure the inputs and outputs and run the utility; follow progress in the in-app **Console**, which also lets you copy the log or abort the job at any time.
8. Use the **Lycan Worker** to queue utilities and run them sequentially in the background.
9. Open the **Python Libraries** store to manage the app's own packages.
10. Open **About Lycan Utilities** from the top-left menu for version and repository information.

## Documentation

- [INSTALLATION.md](INSTALLATION.md) — prerequisites, setup and the dev launcher
- [ARCHITECTURE.md](ARCHITECTURE.md) — project structure, the JS bridge and the utility runtime pipeline
- [DEVELOPMENT.md](DEVELOPMENT.md) — day-to-day development and debug logging
- [WRITING_A_UTILITY.md](WRITING_A_UTILITY.md) — authoring a new utility
- [TRANSPARENCY.md](TRANSPARENCY.md) — disclosure of AI usage in this project
- [frontend/README.md](frontend/README.md) — the React SPA
- [lycan_api.lua](lycan_api.lua) — the Lua interop API signature stub

## Asset Notice

Some UI icons, wallpapers, etc. are generated placeholders and will be replaced with custom artwork in future releases. The wolf-head mascot and status-bar glyphs are custom SVG assets.

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.

You are free to use, modify, and distribute this software under the terms of the GPLv3 license. This license requires that any derivative works you distribute also be licensed under GPLv3, keeping the source code open.

For the full license text, see the [GNU GPL v3](https://www.gnu.org/licenses/gpl-3.0.en.html) official page.
