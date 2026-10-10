# Installation

[← Back to README](README.md)

## Prerequisites

- **Python 3.10+** (developed against 3.13)
- **Node.js 20.19+** (or 22.12+) with **npm** — required to build/run the frontend
- **FFmpeg** — must be available in `PATH` for Frames to Video
- **Git**

## Setup

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
python build_react_n_run.py --no-hmr
```

`setup_env.py` automates the contributor environment:

- Creates the isolated `.venv` when it is missing (checks for Python 3.10+ first)
- Detects missing or outdated packages against `requirements.txt` and (re)installs as needed
- Reports when everything is already up to date

Useful flags:

```bash
python setup_env.py --check              # dry run: report only, change nothing
python setup_env.py --recreate           # rebuild .venv from scratch
python setup_env.py --python py-3.13     # pick a specific base interpreter
python setup_env.py --venv DIR           # custom virtualenv location
python setup_env.py --requirements FILE  # alternate requirements file
```

## Launching

`build_react_n_run.py` is the dev launcher. By default it starts the **Vite dev server** (instant HMR) and launches the app against it, restarting the app when Python files change:

```bash
python build_react_n_run.py              # Vite dev server + HMR + restart watcher (default)
python build_react_n_run.py --no-hmr     # build dist/ + restart watcher instead of the dev server
python build_react_n_run.py --no-watch   # run once, no watcher
python build_react_n_run.py --no-build   # skip the initial build
python build_react_n_run.py --debug      # enable WebView2 developer tools
python build_react_n_run.py --debug-level=2   # debug_info verbosity tier (0 off .. 4 all)
```

## Manual route (equivalent)

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

> **Lua runtimes** are optional. `lupa` is not installed by default; add it (`pip install lupa`) to run the `.lua` hooks. Without it, Python hooks keep working and Lua utilities report a graceful `lua_runtime_missing` result.
