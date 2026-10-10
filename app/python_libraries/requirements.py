"""Per-utility dependency status (manifest requirements + requirements.txt)."""

from __future__ import annotations

import os
import re
import shutil
from typing import Any, Dict, List

from app.settings import load_app_settings

from .cache import _cache_get, _cache_put
from .constants import CACHE_UTILS_PREFIX, UTIL_CACHE_TTL
from .helpers import normalize_name
from .installed import _compare_versions, installed_distributions
from .metadata import latest_version
from core.debug_log import get_logger

_logger = get_logger(__name__)


def _external_status(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Report whether a non-Python (external) requirement is satisfiable."""
    _logger.debug_info("enter args=%s", ascii({"entry": entry}), tier=_logger.DEBUG_LOOP)
    if not isinstance(entry, dict):
        _logger.debug_info("in if (not isinstance(entry, dict))", tier=_logger.DEBUG_LOOP)
        entry = {}
    name = str(entry.get("name") or "")
    required = bool(entry.get("required", True))
    lower = name.lower()
    if lower in ("ffmpeg", "ffprobe"):
        _logger.debug_info("in if (lower in (\"ffmpeg\", \"ffprobe\"))", tier=_logger.DEBUG_LOOP)
        settings = (load_app_settings() or {})
        ffmpeg = settings.get("ffmpeg") or {}
        configured = bool(ffmpeg.get("path"))
        base_ok = bool(shutil.which("ffmpeg") or shutil.which("ffprobe"))
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "name": name,
            "type": str(entry.get("type") or "external"),
            "required": required,
            "satisfied": configured or base_ok,
            "note": "App FFmpeg setting or system PATH" if (configured or base_ok)
                    else "No FFmpeg installation found",
        }
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return {
        "name": name,
        "type": str(entry.get("type") or "external"),
        "required": required,
        "satisfied": None,
        "note": "Not checked",
    }


def parse_requirements_file(module_dir: str) -> List[str]:
    """Names declared in a utility's ``requirements.txt`` (may be empty)."""
    _logger.debug_info("enter args=%s", ascii({"module_dir": module_dir}), tier=_logger.DEBUG_FUNCTION)
    if not isinstance(module_dir, (str, os.PathLike)):
        _logger.debug_info("in if (not isinstance(module_dir, (str, os.PathLike)))", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return []
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        with open(os.path.join(module_dir, "requirements.txt"), "r", encoding="utf-8") as fh:
            _logger.debug_info("in with (open(os.path.join(module_dir, \"requirements.txt\"), \"r\", encoding=\"utf-8\") as fh)", tier=_logger.DEBUG_FUNCTION)
            lines = fh.read().splitlines()
    except (OSError, ValueError):
        _logger.debug_info("in except (OSError, ValueError)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return []
    names: List[str] = []
    for line in lines:
        _logger.debug_info("in for (line in lines)", tier=_logger.DEBUG_LOOP)
        token = line.split("#", 1)[0].strip()
        if not token:
            _logger.debug_info("in if (not token)", tier=_logger.DEBUG_FUNCTION)
            continue
        raw = re.split(r"[<>=!~\s]", token, 1)[0].strip()
        if raw:
            _logger.debug_info("in if (raw)", tier=_logger.DEBUG_FUNCTION)
            names.append(normalize_name(raw))
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return names


def _compute_utility_dependencies(utilities: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Installed/missing/outdated status for every utility's requirements.

    ``utilities`` mirrors the bridge's ``self._utilities`` map: each value has
    ``manifest`` and ``dir`` keys.
    """
    _logger.debug_info("enter args=%s", ascii({"utilities": utilities}), tier=_logger.DEBUG_LOOP)
    installed = installed_distributions()
    result: List[Dict[str, Any]] = []
    for tool, entry in (utilities or {}).items():
        _logger.debug_info("in for (tool, entry in (utilities or {}).items())", tier=_logger.DEBUG_LOOP)
        manifest = (entry or {}).get("manifest") or {}
        module_dir = (entry or {}).get("dir") or ""
        python_reqs = manifest.get("python_requirements")
        if not isinstance(python_reqs, list):
            _logger.debug_info("in if (not isinstance(python_reqs, list))", tier=_logger.DEBUG_LOOP)
            python_reqs = parse_requirements_file(module_dir)
        additional = manifest.get("additional_requirements")
        if not isinstance(additional, list):
            _logger.debug_info("in if (not isinstance(additional, list))", tier=_logger.DEBUG_LOOP)
            additional = []

        requirements: List[Dict[str, Any]] = []
        for req in python_reqs:
            _logger.debug_info("in for (req in python_reqs)", tier=_logger.DEBUG_LOOP)
            if not isinstance(req, str) or not req.strip():
                _logger.debug_info("in if (not isinstance(req, str) or not req.strip())", tier=_logger.DEBUG_LOOP)
                continue
            norm = normalize_name(req)
            version = installed.get(norm)
            latest = latest_version(norm)
            state = "missing" if version is None else (
                "outdated" if latest and _compare_versions(version, latest) is True
                else "installed")
            requirements.append({
                "name": str(req),
                "normalized": norm,
                "installed": version is not None,
                "installed_version": version or "",
                "latest_version": latest,
                "state": state,
            })

        additional_statuses = [_external_status(item) for item in additional
                               if isinstance(item, dict)]
        result.append({
            "id": str(manifest.get("id") or tool),
            "title": str(manifest.get("title") or manifest.get("id") or tool),
            "requirements": requirements,
            "additional_requirements": additional_statuses,
            "requirements_file": os.path.isfile(os.path.join(module_dir, "requirements.txt")),
        })
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return result


def utility_dependencies(utilities: Dict[str, Dict[str, Any]],
                         force: bool = False) -> List[Dict[str, Any]]:
    """Cached wrapper around ``_compute_utility_dependencies``.

    The status snapshot is persisted so switching sections or reopening the
    category reuses the last fetch within the TTL instead of re-querying the
    PyPI metadata for every requirement (the rate-limit protection). Pass
    ``force=True`` right after an install/uninstall to recompute it.
    """
    _logger.debug_info("enter args=%s", ascii({"utilities": utilities, "force": force}), tier=_logger.DEBUG_FUNCTION)
    sig = ",".join(sorted(((utilities or {}).keys())))
    key = CACHE_UTILS_PREFIX + sig
    if not force:
        _logger.debug_info("in if (not force)", tier=_logger.DEBUG_FUNCTION)
        cached = _cache_get(key, UTIL_CACHE_TTL)
        if isinstance(cached, list):
            _logger.debug_info("in if (isinstance(cached, list))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return cached
    result = _compute_utility_dependencies(utilities)
    _cache_put(key, result, UTIL_CACHE_TTL)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return result
