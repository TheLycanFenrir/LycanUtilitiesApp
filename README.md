# Lycan Utilities

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A lightweight desktop toolkit for media and texture workflows, built around a **React (Vite)** single-page app hosted in a native **PyWebView** window. Convert image sequences into video, split large textures, and generate mipmap chains — all offline, from a single clean dashboard.

> **Version:** 1.3.0
> **Author:** [TheLycanFenrir](https://github.com/TheLycanFenrir)

## Overview

Lycan Utilities pairs a modern React UI with a Python backend that performs every heavy operation — FFmpeg, Pillow, NumPy — in background worker threads. The UI talks to the backend through PyWebView's JS bridge, streaming progress, logs and status in real time. There is no web server, no sign-in and no cloud: everything runs locally on your machine.

## Key Features

- **Modern React UI** — component-driven SPA with SCSS design tokens, dark/light themes, smooth transitions, live search and filtering
- **Favorites & usage tracking** — per-tool favorites and "Last Used" ordering, persisted locally
- **Per-tool presets & persistence** — tool settings, presets and path history remembered between sessions
- **Native file dialogs** — OS-native open/folder dialogs routed through the bridge
- **Background job system** — cancellable worker jobs that stream structured `status` / `progress` / `log` events, with async confirmation dialogs
- **Live system resource meter** — CPU, app RAM and system RAM indicators with usage meters in the status bar
- **Media tools**:
  - **Frames to Video** *(Beta)* — image sequences → MP4 (H.264 / AV1), WebM, GIF, APNG or WEBP, with full FPS, quality and background control
  - **Image Splitter** *(Beta)* — slice textures into grids, custom tile sizes or alpha components
  - **Texture Mipmap Generator** *(Alpha)* — mipmap chains for texture workflows, with optional DDS output
  - **Video / Audio Merger** *(Coming Soon)* — combine a video and an audio track into one file
- **DDS Exporter** — standalone DDS encoder (BC1–BC7, uncompressed) shipped in `api/DDSExporter.py`
- **Easter egg** — press and hold the wolf icon in the bottom-left to peek the backdrop wallpaper

## Installation

### Prerequisites

- **Python 3.10+** (developed against 3.13)
- **Node.js 20.19+** (or 22.12+) with **npm** — required to build the frontend
- **FFmpeg** — must be available in `PATH` for Frames to Video
- **Git**

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/TheLycanFenrir/LycanUtilitiesApp
cd LycanUtilitiesApp

# 2. Python backend (creates .venv, installs/updates dependencies)
python setup_env.py

# 3. Frontend dependencies
cd frontend
npm install
cd ..

# 4. Build the React bundle and launch the app
python build_react_n_run.py
```

`setup_env.py` automates the contributor environment:

- Creates the isolated `.venv` when it is missing (checks for Python 3.10+ first)
- Detects missing or outdated packages against `requirements.txt` and (re)installs as needed
- Reports when everything is already up to date

Useful flags:

```bash
python setup_env.py --check           # dry run: report only, change nothing
python setup_env.py --recreate        # rebuild .venv from scratch
python setup_env.py --python py-3.13  # pick a specific base interpreter
python setup_env.py --venv DIR        # custom virtualenv location
```

`build_react_n_run.py` builds the React app with Vite, then starts the PyWebView window:

```bash
python build_react_n_run.py --no-build   # skip the rebuild, launch only
python build_react_n_run.py --debug      # enable WebView2 developer tools
```

Manual route (equivalent):

```bash
python -m venv .venv
# activate it, then:
.\.venv\Scripts\Activate.ps1            # Windows (PowerShell)
.\.venv\Scripts\activate.bat            # Windows (Cmd)
source .venv/bin/activate               # macOS / Linux
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python main.py
```

## Usage

1. Launch the app with `python build_react_n_run.py` (or `python main.py` after building).
2. Use the **search bar** to filter tools by name, description or tag.
3. Use the **sort pills** to reorder tools (Newest / Last Used / Alphabetical / Favorites).
4. **Click** a card to open a tool.
5. Click the **star** on a card to favorite it.
6. Use the **☉ / ☽** button in the top-right to toggle the theme.
7. Configure the inputs and outputs, hit **Start Conversion**, and follow progress in the in-app **Console** — which also lets you copy the log or abort the job at any time.
8. Open **About Lycan Utilities** from the top-left menu for version and repository information.

## Project Structure

```
LycanUtilitiesApp/
├── main.py                        # PyWebView entry point
├── build_react_n_run.py           # Builds the React app, then launches the UI
├── setup_env.py                   # Bootstrap: venv creation + dependency installer
├── requirements.txt               # Python dependencies
├── app/                           # PyWebView bridge & app metadata
│   ├── bridge.py                  # JS ↔ Python API (js_api), job runner, system stats
│   └── info.py                    # Version, tool registry, constants
├── api/                           # Media/texture backends (pure Python, no UI)
│   ├── FrameToVideo.py            # Image sequence → video (FFmpeg)
│   ├── ImageSplitter.py           # Grid / tile / alpha-component splitting (Pillow + NumPy)
│   ├── TextureMipMapGenerator.py  # Mipmap chains, optional DDS export
│   └── DDSExporter.py             # Standalone DDS encoder (BC1–BC7, uncompressed)
├── utils/                         # Settings & system helpers
│   ├── settings.py                # Favorites, presets, history, theme (JSON)
│   └── system.py                  # CPU detection, core enumeration
├── frontend/                      # React SPA (Vite + SCSS)
│   ├── index.html                 # Vite entry
│   ├── vite.config.js             # Build configuration
│   ├── src/
│   │   ├── main.jsx               # React bootstrap
│   │   ├── App.jsx                # Shell wiring & routing
│   │   ├── shell/                 # Topbar, Statusbar, About modal, bridge actions, icons
│   │   ├── tabs/                  # Per-tool pages (Frames to Video, ...)
│   │   ├── components/            # Reusable UI (preset bar, FPS dropdown, easter egg)
│   │   ├── hooks/                 # PyWebView bridge, job console, form persistence
│   │   ├── scss/                  # Design tokens, themes, per-module partials
│   │   └── utils/                 # Path helpers
│   └── public/assets/             # Icons, favicon, wallpaper
└── userdata/                      # Local user state (created on first run)
    ├── favorites.json
    ├── history.json
    ├── lastused.json
    ├── presets.json
    └── settings.json
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  PyWebView Window (WebView2 / WebKit / Cocoa)                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  React SPA (production bundle in frontend/dist)               │  │
│  │  • Shell: topbar, statusbar, modals, toasts                   │  │
│  │  • Dashboard, tool tabs, console, presets                     │  │
│  │  • async/await ↔ window.pywebview.api.*                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          │ JS Bridge (window.pywebview.api)         │
│                          ▼                                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Python Backend (app.bridge.Api)                              │  │
│  │  • Dashboard, favorites, last-used, theme                      │  │
│  │  • Settings, presets, history persistence                      │  │
│  │  • Native dialogs + system stats                               │  │
│  │  • Job system: start_job → poll → events                       │  │
│  │      • Frames → Video (FFmpeg)                                 │  │
│  │      • Image Splitter (Pillow + NumPy)                         │  │
│  │      • Texture Mipmaps (Pillow + NumPy / imageio)              │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

- The frontend never blocks: long operations run through the `start_job` + poll sequence.
- Backend workers push structured events (`log`, `status`, `progress`, `confirm`, `done`) into per-job queues.
- Confirmation dialogs (overwrite prompts, file-count warnings) are async — the worker emits `confirm`, the UI shows a modal, and `resolve_confirm` unblocks the worker.
- External links are always opened in the system browser through the bridge, never inside the window.

## Development

- `npm run build` inside `frontend/` produces the production bundle. `npm run dev` starts the Vite dev server for frontend iteration, but note that a plain browser has no `window.pywebview` bridge — launch the full app with `build_react_n_run.py` to exercise backend calls.
- The bridge surface (every method the frontend can call) is documented in `app/bridge.py`.

## Asset Notice

Some UI icons, wallpapers, etc. are generated placeholders and will be replaced with custom artwork in future releases. The wolf-head mascot and status-bar glyphs are custom SVG assets.

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.

You are free to use, modify, and distribute this software under the terms of the GPLv3 license. This license requires that any derivative works you distribute also be licensed under GPLv3, keeping the source code open.

For the full license text, see the [GNU GPL v3](https://www.gnu.org/licenses/gpl-3.0.en.html) official page.