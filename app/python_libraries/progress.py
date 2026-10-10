"""Live pip-operation progress (shared state polled by the frontend)."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from .constants import PIP_TIMEOUT
from core.debug_log import get_logger

_logger = get_logger(__name__)

# Live pip operation progress, read by the frontend via get_pypi_progress().
_progress: Dict[str, Any] = {}
_progress_lock = threading.Lock()


def _set_progress(**kw: Any) -> None:
    _logger.debug_info("enter args=%s", ascii({"kw": kw}), tier=_logger.DEBUG_LOOP)
    with _progress_lock:
        _logger.debug_info("in with (_progress_lock)", tier=_logger.DEBUG_LOOP)
        _progress.update(kw)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)


def _clear_progress() -> None:
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    with _progress_lock:
        _logger.debug_info("in with (_progress_lock)", tier=_logger.DEBUG_LOOP)
        _progress.clear()
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)


def pypi_progress() -> Optional[Dict[str, Any]]:
    """Snapshot of the currently-running pip operation, or None when idle."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    with _progress_lock:
        _logger.debug_info("in with (_progress_lock)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return dict(_progress) if _progress else None


def _bar_percent(text: str) -> Optional[int]:
    """Extract a percentage from a pip progress-bar frame, if present."""
    _logger.debug_info("enter args=%s", ascii({"text": text}), tier=_logger.DEBUG_LOOP)
    if not isinstance(text, str):
        _logger.debug_info("in if (not isinstance(text, str))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*%", text)
    if m:
        _logger.debug_info("in if (m)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return max(0, min(100, int(float(m.group(1)))))
    # "12.3/45.6 MB" style byte ratio (tqdm-style bar segments).
    m = re.search(r"\b([\d.]+)\s*([kKmMgGtT]?B)\s*/\s*([\d.]+)\s*([kKmMgGtT]?B)", text)
    if m:
        _logger.debug_info("in if (m)", tier=_logger.DEBUG_LOOP)
        units = {"": 1, "b": 1, "k": 1024, "K": 1024, "m": 1024 ** 2, "M": 1024 ** 2,
                 "g": 1024 ** 3, "G": 1024 ** 3, "t": 1024 ** 4, "T": 1024 ** 4}
        done = float(m.group(1)) * units.get(m.group(2), 1024)
        total = float(m.group(3)) * units.get(m.group(4), 1024)
        if total > 0:
            _logger.debug_info("in if (total > 0)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return max(0, min(100, int(done / total * 100)))
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return None


class _PipState:
    """Parsed progress state for a single pip run."""

    def __init__(self) -> None:
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        self.collected = 0
        self.installing_total = 0
        self.done_markers = 0
        self.downloading = ""
        self.install_done = False
        self.uninstall_done = False
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def on_line(self, text: str) -> None:
        _logger.debug_info("enter args=%s", ascii({"text": text}), tier=_logger.DEBUG_LOOP)
        stripped = text.lstrip()
        if stripped.startswith("Collecting "):
            _logger.debug_info("in if (stripped.startswith(\"Collecting \"))", tier=_logger.DEBUG_LOOP)
            self.collected += 1
            name = stripped[len("Collecting "):].split(" from ", 1)[0].strip()
            _set_progress(phase="resolving", pct=min(26, 3 + self.collected * 3),
                          status="Resolving dependencies… (collected {})".format(name))
        elif stripped.startswith("Downloading "):
            _logger.debug_info("in elif (stripped.startswith(\"Downloading \"))", tier=_logger.DEBUG_LOOP)
            self.downloading = stripped[len("Downloading "):]
            _set_progress(phase="downloading", pct=30, status="Downloading " + self.downloading)
        elif stripped.startswith("Installing collected packages: "):
            _logger.debug_info("in elif (stripped.startswith(\"Installing collected packages: \"))", tier=_logger.DEBUG_LOOP)
            items = [s.strip() for s in stripped[len("Installing collected packages: "):].split(",") if s.strip()]
            self.installing_total = len(items) or 1
            _set_progress(phase="installing", pct=72, total_packages=self.installing_total,
                          status="Installing collected packages ({})…".format(self.installing_total))
        elif stripped.startswith("Uninstalling "):
            _logger.debug_info("in elif (stripped.startswith(\"Uninstalling \"))", tier=_logger.DEBUG_LOOP)
            _set_progress(phase="uninstalling", pct=50, total_packages=1,
                          status=stripped[:-1] if stripped.endswith(":") else stripped)
        elif stripped.startswith("Successfully installed"):
            _logger.debug_info("in elif (stripped.startswith(\"Successfully installed\"))", tier=_logger.DEBUG_LOOP)
            self.install_done = True
            _set_progress(phase="done", pct=100,
                          done_packages=self.installing_total or 1,
                          total_packages=self.installing_total or 1,
                          status="Installed successfully")
        elif stripped.startswith("Successfully uninstalled"):
            _logger.debug_info("in elif (stripped.startswith(\"Successfully uninstalled\"))", tier=_logger.DEBUG_LOOP)
            self.uninstall_done = True
            _set_progress(phase="done", pct=100, done_packages=1, total_packages=1,
                          status="Uninstalled successfully")
        elif self.installing_total and _progress.get("phase") == "installing" \
                and (stripped.endswith("... done") or stripped.endswith(" - done")
                     or stripped.endswith("done")):
            _logger.debug_info("in elif (self.installing_total and _progress.get(\"phase\") == \"installing\" \\\n                and (stripped.endswith(\"... done\") or stripped.endswith(\" - done\")\n                     or stripped.endswith(\"done\")))", tier=_logger.DEBUG_LOOP)
            self.done_markers += 1
            pct = min(98, 72 + int(self.done_markers / (self.installing_total * 3) * 26))
            done = min(self.installing_total, max(1, int(pct / 100 * self.installing_total)))
            _set_progress(pct=pct, done_packages=done)
        elif stripped.startswith("Requirement already satisfied"):
            _logger.debug_info("in elif (stripped.startswith(\"Requirement already satisfied\"))", tier=_logger.DEBUG_LOOP)
            _set_progress(status="Requirement already satisfied")
        elif _progress.get("phase") == "downloading":
            _logger.debug_info("in elif (_progress.get(\"phase\") == \"downloading\")", tier=_logger.DEBUG_LOOP)
            pct = _bar_percent(text)
            if pct is not None:
                _logger.debug_info("in if (pct is not None)", tier=_logger.DEBUG_LOOP)
                _set_progress(pct=min(99, 31 + int(pct * 0.37)),
                              status="Downloading {} ({}%)".format(self.downloading, pct))
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)


def _stream_pip(python: str, args: List[str], op: str, name: str,
                batch_total: int = 1, batch_done: int = 0,
                timeout: int = PIP_TIMEOUT) -> Dict[str, Any]:
    """Run pip while streaming + parsing progress into the shared state.

    Callers pass ``--progress-bar on`` right after the subcommand so pip emits
    readable ``\\r``-separated frames (``NN% | ...``) that we parse into an
    overall percentage, and its ``Collecting …`` / ``Installing collected
    packages: …`` lines supply the package counters shown in the UI.
    """
    _logger.debug_info("enter args=%s", ascii({"python": python, "args": args, "op": op, "name": name, "batch_total": batch_total, "batch_done": batch_done, "timeout": timeout}), tier=_logger.DEBUG_LOOP)
    _set_progress(active=True, op=op, name=name, phase="resolving", pct=0,
                  batch_total=max(1, int(batch_total or 1)),
                  batch_done=max(0, int(batch_done or 0)),
                  total_packages=0, done_packages=0, status="Starting…",
                  started=time.time())
    cmd = [python, "-m", "pip", "--disable-pip-version-check", *args]
    proc = None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as exc:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        _set_progress(phase="failed", status="Could not start pip")
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "ok": False,
            "reason": str(exc),
            "code": None,
            "output": [],
        }

    state = _PipState()
    lines: List[str] = []
    buf = b""
    deadline = time.time() + timeout
    timed_out = False
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        while True:
            _logger.debug_info("in while (True)", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                chunk = os.read(proc.stdout.fileno(), 8192)
            except OSError:
                _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_LOOP)
                chunk = b""
            if not chunk:
                _logger.debug_info("in if (not chunk)", tier=_logger.DEBUG_LOOP)
                break
            if time.time() > deadline:
                _logger.debug_info("in if (time.time() > deadline)", tier=_logger.DEBUG_LOOP)
                timed_out = True
                break
            buf += chunk
            while True:
                _logger.debug_info("in while (True)", tier=_logger.DEBUG_LOOP)
                cr = buf.find(b"\r")
                nl = buf.find(b"\n")
                if cr == -1 and nl == -1:
                    _logger.debug_info("in if (cr == -1 and nl == -1)", tier=_logger.DEBUG_LOOP)
                    break
                if cr == -1:
                    _logger.debug_info("in if (cr == -1)", tier=_logger.DEBUG_LOOP)
                    idx = nl
                elif nl == -1:
                    _logger.debug_info("in elif (nl == -1)", tier=_logger.DEBUG_LOOP)
                    idx = cr
                else:
                    _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
                    idx = min(cr, nl)
                seg = buf[:idx]
                buf = buf[idx + 1:]
                seg_text = seg.decode("utf-8", "replace").strip()
                if seg_text:
                    _logger.debug_info("in if (seg_text)", tier=_logger.DEBUG_LOOP)
                    lines.append(seg_text)
                    state.on_line(seg_text)
    finally:
        _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            proc.stdout.close()
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            pass

    if timed_out:
        _logger.debug_info("in if (timed_out)", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            proc.kill()
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            pass
        _set_progress(phase="failed", status="Operation timed out")
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "ok": False,
            "reason": "timeout",
            "code": None,
            "output": lines[-60:],
        }

    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        proc.wait(timeout=15)
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            proc.kill()
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            pass
        proc.wait()
    if not state.install_done and not state.uninstall_done and proc.returncode == 0:
        # Success without a matching "Successfully …" line (rare paths).
        _logger.debug_info("in if (not state.install_done and not state.uninstall_done and proc.returncode == 0)", tier=_logger.DEBUG_LOOP)
        _set_progress(phase="done", pct=100,
                      done_packages=state.installing_total or 1,
                      total_packages=state.installing_total or 1,
                      status="Finished")
    elif proc.returncode != 0:
        _logger.debug_info("in elif (proc.returncode != 0)", tier=_logger.DEBUG_LOOP)
        _set_progress(phase="failed",
                      status="Failed (pip exit code {})".format(proc.returncode))
    _set_progress(active=False, pct=100 if proc.returncode == 0 else max(0, _progress.get("pct", 0) or 0))
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "output": lines[-60:],
    }
