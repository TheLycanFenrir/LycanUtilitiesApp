"""Pip operations: interpreter resolution, install/uninstall, environment."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, Tuple

from .audit import _audit_environment, _audit_requirement, _summarize_audit
from .cache import section_state
from .helpers import _NAME_RE, _tool, internet_enabled, local_only_scope, normalize_name
from .index import _load_names, index_info
from .installed import core_packages, installed_distributions, installed_version, is_core_package
from .metadata import latest_version
from .progress import _stream_pip
from core.debug_log import get_logger

_logger = get_logger(__name__)


def _interpreter_for(scope: str) -> Tuple[str, bool]:
    """Resolve the target interpreter for a scope.

    Returns ``(python_executable, is_base)``. ``is_base`` is True when the
    target is a different, shared (global) interpreter.
    """
    _logger.debug_info("enter args=%s", ascii({"scope": scope}), tier=_logger.DEBUG_LOOP)
    if scope == "global":
        _logger.debug_info("in if (scope == \"global\")", tier=_logger.DEBUG_LOOP)
        base = getattr(sys, "_base_executable", None) or sys.executable
        is_base = os.path.abspath(base) != os.path.abspath(sys.executable)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return base, is_base
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return sys.executable, False


def pypi_install(name: str, scope: str = "local", upgrade: bool = False,
                 confirmed: bool = False, batch_total: int = 1,
                 batch_done: int = 0, vuln_ack: bool = False) -> Dict[str, Any]:
    """Install (or upgrade) a package through pip into the target scope.

    Before anything touches the environment the candidate version is scanned
    with pip-audit. If it has known vulnerabilities the install is blocked and
    a ``vulnerabilities_found`` response is returned; the frontend then shows
    its two-step "Proceed anyway?" / "Are you sure?" confirmation and re-calls
    with ``vuln_ack=True`` to proceed.
    """
    _logger.debug_info("enter args=%s", ascii({"name": name, "scope": scope, "upgrade": upgrade, "confirmed": confirmed, "batch_total": batch_total, "batch_done": batch_done, "vuln_ack": vuln_ack}), tier=_logger.DEBUG_FUNCTION)
    norm = normalize_name(name)
    if not _NAME_RE.match(norm):
        _logger.debug_info("in if (not _NAME_RE.match(norm))", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "invalid_name",
            "name": norm,
        }
    if not internet_enabled():
        _logger.debug_info("in if (not internet_enabled())", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "internet_disabled",
        }
    if scope == "global" and not confirmed:
        # Never touch the shared/system interpreter without an explicit
        # user confirmation from the frontend.
        _logger.debug_info("in if (scope == \"global\" and not confirmed)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "confirmation_required",
        }
    python, is_base = _interpreter_for(scope)
    target_version = latest_version(norm) or (installed_version(norm) or "")
    audit = _audit_requirement(norm, target_version, python)
    if audit.get("total") and not vuln_ack:
        _logger.debug_info("in if (audit.get(\"total\") and not vuln_ack)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "vulnerabilities_found",
            "name": norm,
            "scope": "global" if is_base else "local",
            "environment": python,
            "total": int(audit.get("total") or 0),
            "state": audit.get("state") or "",
            "affected": _summarize_audit(audit.get("affected") or []),
        }
    args = ["install", "--progress-bar", "on"] + (["--upgrade"] if upgrade else []) + [norm]
    result = _stream_pip(python, args, "update" if upgrade else "install", norm,
                         batch_total=batch_total, batch_done=batch_done)
    result["name"] = norm
    result["scope"] = "global" if is_base else "local"
    result["environment"] = python
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return result


def pypi_uninstall(name: str, scope: str = "local", confirmed: bool = False,
                   batch_total: int = 1, batch_done: int = 0) -> Dict[str, Any]:
    """Uninstall a package through pip. Core packages are never removable."""
    _logger.debug_info("enter args=%s", ascii({"name": name, "scope": scope, "confirmed": confirmed, "batch_total": batch_total, "batch_done": batch_done}), tier=_logger.DEBUG_FUNCTION)
    norm = normalize_name(name)
    if not _NAME_RE.match(norm):
        _logger.debug_info("in if (not _NAME_RE.match(norm))", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "invalid_name",
            "name": norm,
        }
    if is_core_package(norm):
        _logger.debug_info("in if (is_core_package(norm))", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "core_package",
            "name": norm,
        }
    if not confirmed:
        _logger.debug_info("in if (not confirmed)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "confirmation_required",
        }
    python, is_base = _interpreter_for(scope)
    result = _stream_pip(python, ["uninstall", "--progress-bar", "on", "-y", norm],
                         "uninstall", norm, batch_total=batch_total, batch_done=batch_done)
    result["name"] = norm
    result["scope"] = "global" if is_base else "local"
    result["environment"] = python
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return result


def pip_available() -> bool:
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        proc = subprocess.run([sys.executable, "-m", "pip", "--version"],
                              capture_output=True, text=True, timeout=20)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return proc.returncode == 0
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return False


def python_environment() -> Dict[str, Any]:
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    base = getattr(sys, "_base_executable", None) or sys.executable
    in_venv = os.path.abspath(base) != os.path.abspath(sys.executable)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        version = sys.version.split()[0]
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        version = str(sys.version_info[:3])
    tool = _tool()
    idx = _load_names()
    info = index_info()
    state = section_state()
    audit = _audit_environment()
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return {
        "ok": True,
        "python_version": version,
        "executable": sys.executable,
        "base_executable": base,
        "in_venv": in_venv,
        "local_only": local_only_scope(),
        "pip_available": pip_available(),
        "installed_count": len(installed_distributions()),
        "core_packages": core_packages(),
        "search_engine": "pypi-search-caching" if tool else "unavailable",
        "search_index_size": len(idx) if idx else 0,
        "index_fetched_at": info.get("fetched_at_iso") or "",
        "index_fresh": info.get("fresh", False),
        "index_stale_recovered": info.get("stale_recovered", False),
        "state_query": state.get("query") or "",
        "state_page": int(state.get("page") or 1),
        "vuln_scan_state": str(audit.get("state") or ""),
        "vuln_total": int(audit.get("total") or 0),
        "vuln_affected": int(len(audit.get("affected") or [])),
        "vuln_fetched_at": str(audit.get("fetched_at") or ""),
    }
