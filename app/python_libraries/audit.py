"""Vulnerability scanning (pip-audit against the OSV/PyPI advisory database).

pip-audit runs as a subprocess (the tool needs network + its own dependency
stack). Two query shapes are used:
  * environment scan  -> ``pip-audit -l`` audits every *installed* package;
  * pre-install check -> ``pip-audit -r <file> --no-deps`` audits a pinned
    ``name==version`` candidate (exact pins are required by --no-deps).
Exit codes: 0 = no advisories, 1 = advisories found, anything else = the
run failed. Both scan results are snapshotted so "auto scan" happens at most
every few minutes instead of on every render.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

from .cache import _cache_get, _cache_put
from .constants import (
    AUDIT_TIMEOUT,
    CACHE_VULN_KEY,
    CACHE_VULN_REQ_PREFIX,
    VULN_CACHE_TTL,
    VULN_REQ_CACHE_TTL,
)
from .helpers import internet_enabled, normalize_name
from core.debug_log import get_logger

_logger = get_logger(__name__)

_audit_lock = threading.Lock()


def _parse_audit_report(report: Any) -> Dict[str, Any]:
    """Normalize a pip-audit JSON report into ``{total, affected, by_name}``."""
    _logger.debug_info("enter args=%s", ascii({"report": report}), tier=_logger.DEBUG_LOOP)
    if not isinstance(report, dict):
        _logger.debug_info("in if (not isinstance(report, dict))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "total": 0,
            "affected": [],
            "by_name": {},
        }
    deps = report.get("dependencies")
    if not isinstance(deps, list):
        _logger.debug_info("in if (not isinstance(deps, list))", tier=_logger.DEBUG_LOOP)
        deps = []
    affected: List[Dict[str, Any]] = []
    by_name: Dict[str, Dict[str, Any]] = {}
    total = 0
    for dep in deps:
        _logger.debug_info("in for (dep in deps)", tier=_logger.DEBUG_LOOP)
        if not isinstance(dep, dict) or not dep.get("name"):
            _logger.debug_info("in if (not isinstance(dep, dict) or not dep.get(\"name\"))", tier=_logger.DEBUG_LOOP)
            continue
        name = str(dep.get("name"))
        version = str(dep.get("version") or "")
        vulns = dep.get("vulns")
        if not isinstance(vulns, list):
            _logger.debug_info("in if (not isinstance(vulns, list))", tier=_logger.DEBUG_LOOP)
            vulns = []
        seen_ids: set = set()
        cleaned: List[Dict[str, Any]] = []
        for v in vulns:
            _logger.debug_info("in for (v in vulns)", tier=_logger.DEBUG_LOOP)
            if not isinstance(v, dict):
                _logger.debug_info("in if (not isinstance(v, dict))", tier=_logger.DEBUG_LOOP)
                continue
            v_id = str(v.get("id") or "")
            if v_id in seen_ids:
                _logger.debug_info("in if (v_id in seen_ids)", tier=_logger.DEBUG_LOOP)
                continue
            seen_ids.add(v_id)
            aliases = v.get("aliases")
            if not isinstance(aliases, list):
                _logger.debug_info("in if (not isinstance(aliases, list))", tier=_logger.DEBUG_LOOP)
                aliases = []
            fix_versions = v.get("fix_versions")
            if not isinstance(fix_versions, list):
                _logger.debug_info("in if (not isinstance(fix_versions, list))", tier=_logger.DEBUG_LOOP)
                fix_versions = []
            cleaned.append({
                "id": v_id,
                "aliases": [str(a) for a in aliases if isinstance(a, str)],
                "fix_versions": [str(f) for f in fix_versions if isinstance(f, str)],
                "summary": str(v.get("description") or v.get("details") or ""),
            })
        if not cleaned:
            _logger.debug_info("in if (not cleaned)", tier=_logger.DEBUG_LOOP)
            continue
        norm = normalize_name(name)
        entry = {
            "normalized": norm,
            "name": name,
            "version": version,
            "count": len(cleaned),
            "vulns": cleaned,
        }
        affected.append(entry)
        by_name[norm] = entry
        total += len(cleaned)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return {
        "total": total,
        "affected": affected,
        "by_name": by_name,
    }


def _empty_audit(state: str) -> Dict[str, Any]:
    _logger.debug_info("enter args=%s", ascii({"state": state}), tier=_logger.DEBUG_LOOP)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return {
        "ok": state == "ok",
        "state": state,
        "total": 0,
        "affected": [],
        "by_name": {},
        "fetched_at": "",
    }


def _audit_available(python: Optional[str] = None) -> bool:
    """True when ``pip-audit`` is importable in the given interpreter."""
    _logger.debug_info("enter args=%s", ascii({"python": python}), tier=_logger.DEBUG_LOOP)
    py = python or sys.executable
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        proc = subprocess.run([py, "-c", "import pip_audit"],
                              capture_output=True, text=True, timeout=20)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return proc.returncode == 0
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return False


def _run_pip_audit(python: str, requirements: Optional[List[str]],
                   timeout: int = AUDIT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """Run pip-audit and parse its JSON report. None on failure/timeout."""
    _logger.debug_info("enter args=%s", ascii({"python": python, "requirements": requirements, "timeout": timeout}), tier=_logger.DEBUG_LOOP)
    cmd = [python, "-m", "pip_audit", "--format", "json",
           "--progress-spinner", "off", "--desc", "on", "--aliases", "on"]
    tmp_path: Optional[str] = None
    if requirements:
        _logger.debug_info("in if (requirements)", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            fd, tmp_path = tempfile.mkstemp(prefix="pip-audit-", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                _logger.debug_info("in with (os.fdopen(fd, \"w\", encoding=\"utf-8\") as fh)", tier=_logger.DEBUG_LOOP)
                fh.write("\n".join(requirements) + "\n")
        except OSError:
            _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None
        cmd += ["--no-deps", "-r", tmp_path]
    else:
        _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
        cmd += ["-l"]
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        _logger.debug_info("in except (subprocess.TimeoutExpired)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    finally:
        _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
        if tmp_path is not None:
            _logger.debug_info("in if (tmp_path is not None)", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                os.unlink(tmp_path)
            except OSError:
                _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_LOOP)
                pass
    if proc.returncode not in (0, 1):
        _logger.debug_info("in if (proc.returncode not in (0, 1))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        report = json.loads(proc.stdout)
    except (TypeError, ValueError):
        _logger.debug_info("in except (TypeError, ValueError)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return _parse_audit_report(report)


def _audit_environment(python: Optional[str] = None,
                       force: bool = False) -> Dict[str, Any]:
    """Scan every installed package in ``python`` against the advisory DB.

    This is the Settings "auto scan": it runs at most once per TTL and its
    report feeds both the per-package badges in search results and the
    environment row. ``force=True`` (used by the "Scan now" button) bypasses
    the snapshot.
    """
    _logger.debug_info("enter args=%s", ascii({"python": python, "force": force}), tier=_logger.DEBUG_LOOP)
    py = python or sys.executable
    key = CACHE_VULN_KEY + normalize_name(os.path.basename(py))
    if not internet_enabled():
        _logger.debug_info("in if (not internet_enabled())", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return _empty_audit("offline")
    if not force:
        _logger.debug_info("in if (not force)", tier=_logger.DEBUG_LOOP)
        cached = _cache_get(key, VULN_CACHE_TTL)
        if isinstance(cached, dict):
            _logger.debug_info("in if (isinstance(cached, dict))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return cached
    with _audit_lock:
        _logger.debug_info("in with (_audit_lock)", tier=_logger.DEBUG_LOOP)
        if not force:
            _logger.debug_info("in if (not force)", tier=_logger.DEBUG_LOOP)
            cached = _cache_get(key, VULN_CACHE_TTL)
            if isinstance(cached, dict):
                _logger.debug_info("in if (isinstance(cached, dict))", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return cached
        if not _audit_available(py):
            _logger.debug_info("in if (not _audit_available(py))", tier=_logger.DEBUG_LOOP)
            result = _empty_audit("unavailable")
            _cache_put(key, result, VULN_CACHE_TTL)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return result
        parsed = _run_pip_audit(py, None)
        if parsed is None:
            _logger.debug_info("in if (parsed is None)", tier=_logger.DEBUG_LOOP)
            result = _empty_audit("failed")
            _cache_put(key, result, VULN_CACHE_TTL)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return result
        parsed["ok"] = True
        parsed["state"] = "ok"
        parsed["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _cache_put(key, parsed, VULN_CACHE_TTL)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return parsed


def _audit_requirement(name: str, version: str,
                       python: Optional[str] = None) -> Dict[str, Any]:
    """Advisory check for ``name==version`` performed before an install.

    ``pip-audit --no-deps`` requires exact pins; when no version is known the
    scan degrades to the environment snapshot (which may still flag the
    already-installed copy). Cached per ``name@version`` so the follow-up
    install attempt re-uses the result.
    """
    _logger.debug_info("enter args=%s", ascii({"name": name, "version": version, "python": python}), tier=_logger.DEBUG_LOOP)
    norm = normalize_name(name)
    ver = (version or "").strip()
    empty = _empty_audit("offline" if not internet_enabled() else "pending")
    if not internet_enabled() or not ver:
        _logger.debug_info("in if (not internet_enabled() or not ver)", tier=_logger.DEBUG_LOOP)
        env = _audit_environment(python=python)
        if env.get("total"):
            _logger.debug_info("in if (env.get(\"total\"))", tier=_logger.DEBUG_LOOP)
            result = dict(env)
            result.pop("by_name", None)
            result["ok"] = True
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return result
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return empty
    key = CACHE_VULN_REQ_PREFIX + norm + "@" + ver
    cached = _cache_get(key, VULN_REQ_CACHE_TTL)
    if isinstance(cached, dict):
        _logger.debug_info("in if (isinstance(cached, dict))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return cached
    py = python or sys.executable
    with _audit_lock:
        _logger.debug_info("in with (_audit_lock)", tier=_logger.DEBUG_LOOP)
        cached = _cache_get(key, VULN_REQ_CACHE_TTL)
        if isinstance(cached, dict):
            _logger.debug_info("in if (isinstance(cached, dict))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return cached
        if not _audit_available(py):
            _logger.debug_info("in if (not _audit_available(py))", tier=_logger.DEBUG_LOOP)
            result = _empty_audit("unavailable")
            _cache_put(key, result, VULN_REQ_CACHE_TTL)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return result
        parsed = _run_pip_audit(py, ["{}=={}".format(norm, ver)])
        if parsed is None:
            _logger.debug_info("in if (parsed is None)", tier=_logger.DEBUG_LOOP)
            result = _empty_audit("failed")
            _cache_put(key, result, VULN_REQ_CACHE_TTL)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return result
        parsed["ok"] = True
        parsed["state"] = "ok"
        parsed["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _cache_put(key, parsed, VULN_REQ_CACHE_TTL)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return parsed


def _summarize_audit(affected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact affected-package shape (ids + fixes) for the confirm dialog."""
    _logger.debug_info("enter args=%s", ascii({"affected": affected}), tier=_logger.DEBUG_LOOP)
    if not isinstance(affected, list):
        _logger.debug_info("in if (not isinstance(affected, list))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return []
    out: List[Dict[str, Any]] = []
    for entry in affected:
        _logger.debug_info("in for (entry in affected)", tier=_logger.DEBUG_LOOP)
        if not isinstance(entry, dict):
            _logger.debug_info("in if (not isinstance(entry, dict))", tier=_logger.DEBUG_LOOP)
            continue
        vulns = entry.get("vulns") if isinstance(entry.get("vulns"), list) else []
        out.append({
            "name": entry.get("name"),
            "version": entry.get("version"),
            "count": int(entry.get("count") or 0),
            "ids": [str(v.get("id") or "") for v in vulns],
            "fix_versions": sorted({str(f) for v in vulns
                                    for f in (v.get("fix_versions") or []) if f}),
        })
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return out


def python_audit(force: bool = False) -> Dict[str, Any]:
    """Re-run the environment vulnerability scan (Settings > "Scan now")."""
    _logger.debug_info("enter args=%s", ascii({"force": force}), tier=_logger.DEBUG_FUNCTION)
    audit = _audit_environment(force=bool(force))
    body = {
        "ok": audit.get("ok", False),
        "state": audit.get("state", ""),
        "total": int(audit.get("total") or 0),
        "affected": _summarize_audit(audit.get("affected") or []),
        "fetched_at": audit.get("fetched_at") or "",
    }
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return body
