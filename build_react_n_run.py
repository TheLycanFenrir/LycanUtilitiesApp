"""Build the React frontend and launch Lycan Utilities with a dev watch loop.

Runs the frontend and the PyWebView application, choosing between a Vite
development server with instant HMR or a production build with a restart
watcher.

HMR mode (default)
------------------
Starts the Vite dev server (``npm run dev``) and launches the app against it.
Vite provides hot module replacement out of the box: saving ``.scss`` /
``.jsx`` / ``.js`` / ``.css`` updates the running window instantly, without a
rebuild and without losing app state. Python changes restart the app.

Build + watch mode (``--no-hmr``)
---------------------------------
Runs ``npm run build`` then starts the app against ``frontend/dist/``.

* **Frontend** (``.scss`` / ``.jsx`` / ``.css`` / ``.js`` under ``frontend``):
  after a 5-second quiet period a hot reload is triggered — the bundle is
  rebuilt and the app is relaunched so the new bundle is picked up.
* **Python** (``.py`` anywhere, excluding vendored dirs): after a 5-second
  quiet period the app is force-restarted.

The 5-second delay is a debounce: it restarts counting from the last change,
so rapid consecutive saves only trigger one reload.

Usage
-----
    python build_react_n_run.py                         dev server + HMR + restart watcher
    python build_react_n_run.py --no-hmr                build + restart watcher
    python build_react_n_run.py --debug                 enable WebView2 devtools
    python build_react_n_run.py --no-watch              run once (dist bundle), no watcher
    python build_react_n_run.py --no-build              skip the initial build
"""

import argparse
import os
import platform
import subprocess
import sys
import time
import urllib.request

IS_WINDOWS = platform.system() == "Windows"

# HMR / Vite dev server settings.
VITE_PORT = os.environ.get("LYCAN_VITE_PORT", "5173")
VITE_URL = os.environ.get("LYCAN_FRONTEND_URL") or f"http://localhost:{VITE_PORT}"
VITE_READY_TIMEOUT_SECONDS = 60.0

# Change detection settings.
WATCH_DEBOUNCE_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 0.5

FE_EXTENSIONS = {".scss", ".jsx", ".js", ".css"}
PY_EXTENSIONS = {".py"}
WATCH_EXTENSIONS = FE_EXTENSIONS | PY_EXTENSIONS

# Directories that are never scanned for changes.
IGNORE_DIRS = {
    ".venv",
    "node_modules",
    "dist",
    ".git",
    ".idea",
    "__pycache__",
    ".opencode",
    "web.old",
}


def project_root():
    return os.path.dirname(os.path.abspath(__file__))


def log(message, prefix="[*]"):
    print(f"{prefix} {message}", flush=True)


def find_npm():
    """Locate the npm executable."""
    npm = "npm.cmd" if IS_WINDOWS else "npm"
    for candidate in (npm, "npm"):
        try:
            r = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0:
                return candidate
        except FileNotFoundError:
            continue
    return None


def find_python():
    """Use the project venv python if available, otherwise the current interpreter."""
    root = project_root()
    if IS_WINDOWS:
        venv_python = os.path.join(root, ".venv", "Scripts", "python.exe")
    else:
        venv_python = os.path.join(root, ".venv", "bin", "python")
    if os.path.isfile(venv_python):
        return venv_python
    return sys.executable


def build_frontend():
    root = project_root()
    frontend_dir = os.path.join(root, "frontend")

    if not os.path.isfile(os.path.join(frontend_dir, "package.json")):
        log("frontend/package.json not found — skipping build.")
        return True

    npm = find_npm()
    if npm is None:
        log("npm not found on PATH. Install Node.js and try again.")
        return False

    log(f"Building React frontend (npm run build) in {frontend_dir} ...")
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=frontend_dir,
    )
    if result.returncode != 0:
        log("npm run build failed.")
        return False

    dist_index = os.path.join(frontend_dir, "dist", "index.html")
    if not os.path.isfile(dist_index):
        log("frontend/dist/index.html not found after build.")
        return False

    log("React build complete.")
    return True


def start_app(debug=False, frontend="react", frontend_url=None):
    """Launch the app as a child process and return the Popen handle."""
    root = project_root()
    python = find_python()
    main_py = os.path.join(root, "main.py")

    env = os.environ.copy()
    env["LYCAN_FRONTEND"] = frontend
    if frontend_url:
        env["LYCAN_FRONTEND_URL"] = frontend_url

    cmd = [python, main_py]
    if debug:
        cmd.append("--debug")

    log(f"Launching app with React frontend ({frontend}) ...")
    log(f"  python: {python}")
    log(f"  cmd:    {' '.join(cmd)}")

    return subprocess.Popen(cmd, cwd=root, env=env)


def start_vite_dev():
    """Start the Vite dev server and return the Popen handle."""
    root = project_root()
    frontend_dir = os.path.join(root, "frontend")
    npm = find_npm()
    if npm is None:
        log("npm not found on PATH. Install Node.js and try again.")
        return None
    log(f"Starting Vite dev server (npm run dev -- --port {VITE_PORT} --strictPort) in {frontend_dir} ...")
    return subprocess.Popen(
        [npm, "run", "dev", "--", "--port", VITE_PORT, "--strictPort"],
        cwd=frontend_dir,
    )


def vite_is_ready(url=VITE_URL, timeout=VITE_READY_TIMEOUT_SECONDS):
    """Poll the dev server until it starts answering HTTP requests."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def terminate_app(proc):
    """Forcefully stop a running child process."""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=8)


def scan_watched(root):
    """Snapshot mtimes of every watched file under the project root."""
    snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in WATCH_EXTENSIONS:
                continue
            path = os.path.join(dirpath, filename)
            try:
                snapshot[path] = os.stat(path).st_mtime_ns
            except OSError:
                snapshot[path] = None
    return snapshot


def run_hmr(debug=False):
    """Run Vite dev server + app; SCSS/JSX hot-reload via Vite; restart on .py."""
    root = project_root()
    log("HMR mode enabled — SCSS/JSX changes hot-reload instantly via Vite.", "[~]")
    log(f"  dev server: {VITE_URL}", "[~]")
    log("  .py changes -> force restart the app (5s debounce)", "[~]")
    log("Press Ctrl+C to stop.", "[~]")

    vite = start_vite_dev()
    if vite is None:
        sys.exit(1)
    if not vite_is_ready():
        log("Vite dev server did not become ready in time.", "[!]")
        terminate_app(vite)
        sys.exit(1)
    log("Vite dev server is listening.", "[~]")

    proc = start_app(debug, frontend="dev", frontend_url=VITE_URL)
    snapshot = scan_watched(root)
    py_dirty = False
    py_since = 0.0

    try:
        while proc.poll() is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            if vite.poll() is not None:
                log("Vite dev server stopped unexpectedly.", "[!]")
                terminate_app(proc)
                sys.exit(1)

            now = time.time()
            current = scan_watched(root)

            for path in set(snapshot) | set(current):
                if snapshot.get(path) == current.get(path):
                    continue
                if os.path.splitext(path)[1].lower() not in PY_EXTENSIONS:
                    continue
                if not py_dirty:
                    log(f"Detected change: {path}", "[~]")
                    log(f"Python changed — force restarting app in {WATCH_DEBOUNCE_SECONDS:g}s ...", "[~]")
                py_dirty = True
                py_since = now

            snapshot = current

            if py_dirty and now - py_since >= WATCH_DEBOUNCE_SECONDS:
                py_dirty = False
                log("Force restarting app ...", "[~]")
                terminate_app(proc)
                proc = start_app(debug, frontend="dev", frontend_url=VITE_URL)
                snapshot = scan_watched(root)
    except KeyboardInterrupt:
        log("Stopping ...", "[-]")
    finally:
        terminate_app(proc)
        terminate_app(vite)

    code = proc.returncode
    log(f"App exited with code {code}.")
    sys.exit(code if code is not None else 0)


def run_watch(debug=False):
    """Run the app while watching for frontend and python changes."""
    root = project_root()
    log("Watch mode enabled (5s debounce).", "[~]")
    log("  .scss/.jsx/.js/.css changes -> hot reload (rebuild + reload)", "[~]")
    log("  .py changes                   -> force restart the app", "[~]")
    log("Press Ctrl+C to stop.", "[~]")

    proc = start_app(debug)
    snapshot = scan_watched(root)
    fe_dirty = py_dirty = False
    fe_since = py_since = 0.0

    try:
        while proc.poll() is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            now = time.time()
            current = scan_watched(root)

            for path in set(snapshot) | set(current):
                if snapshot.get(path) == current.get(path):
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext in PY_EXTENSIONS:
                    if not py_dirty:
                        log(f"Detected change: {path}", "[~]")
                        log(f"Python changed — force restarting app in {WATCH_DEBOUNCE_SECONDS:g}s ...", "[~]")
                    py_dirty = True
                    py_since = now
                elif ext in FE_EXTENSIONS:
                    if not fe_dirty:
                        log(f"Detected change: {path}", "[~]")
                        log(f"Frontend changed — hot reload in {WATCH_DEBOUNCE_SECONDS:g}s ...", "[~]")
                    fe_dirty = True
                    fe_since = now

            snapshot = current

            if py_dirty and now - py_since >= WATCH_DEBOUNCE_SECONDS:
                py_dirty = False
                if fe_dirty:
                    fe_dirty = False
                    log("Frontend also changed — rebuilding bundle first.", "[~]")
                    build_frontend()
                log("Force restarting app ...", "[~]")
                terminate_app(proc)
                proc = start_app(debug)
                snapshot = scan_watched(root)
            elif fe_dirty and now - fe_since >= WATCH_DEBOUNCE_SECONDS:
                fe_dirty = False
                log("Hot reload: rebuilding frontend bundle ...", "[~]")
                if build_frontend():
                    log("Relaunching app to load the new bundle ...", "[~]")
                    terminate_app(proc)
                    proc = start_app(debug)
                    snapshot = scan_watched(root)
    except KeyboardInterrupt:
        log("Stopping ...", "[-]")
    finally:
        terminate_app(proc)

    code = proc.returncode
    log(f"App exited with code {code}.")
    sys.exit(code if code is not None else 0)


def run_app(debug=False):
    """Launch the app once (used by --no-watch)."""
    root = project_root()
    python = find_python()
    main_py = os.path.join(root, "main.py")

    env = os.environ.copy()
    env["LYCAN_FRONTEND"] = "react"

    cmd = [python, main_py]
    if debug:
        cmd.append("--debug")

    log(f"Launching app with React frontend ...")
    log(f"  python: {python}")
    log(f"  cmd:    {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=root, env=env)
    sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="skip the npm build step and launch directly",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable WebView2 developer tools",
    )
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="disable the dev watch loop and run the app once",
    )
    parser.add_argument(
        "--no-hmr",
        action="store_true",
        help="disable the Vite dev server; use build + restart watcher instead",
    )
    args = parser.parse_args()

    if not args.no_build and not args.no_hmr:
        # HMR mode does not need a production build.
        log("Skipping production build (HMR mode uses the Vite dev server).", "[~]")

    if args.no_watch:
        if not args.no_build:
            if not build_frontend():
                sys.exit(1)
        run_app(debug=args.debug)
    elif args.no_hmr:
        if not args.no_build:
            if not build_frontend():
                sys.exit(1)
        run_watch(debug=args.debug)
    else:
        run_hmr(debug=args.debug)


if __name__ == "__main__":
    main()