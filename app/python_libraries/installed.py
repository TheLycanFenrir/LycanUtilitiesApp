"""Installed state (the running interpreter's environment)."""

from __future__ import annotations

import importlib.metadata
import os
import re
from typing import Dict, List, Optional, Tuple

from .helpers import normalize_name
from core.debug_log import get_logger

_logger = get_logger(__name__)


def installed_version(name: str) -> Optional[str]:
    """Version of ``name`` in the current environment, or None when missing."""
    _logger.debug_info("enter args=%s", ascii({"name": name}), tier=_logger.DEBUG_FUNCTION)
    norm = normalize_name(name)
    if not norm:
        _logger.debug_info("in if (not norm)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return importlib.metadata.version(norm)
    except (importlib.metadata.PackageNotFoundError, ValueError):
        _logger.debug_info("in except (importlib.metadata.PackageNotFoundError, ValueError)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return None


def installed_distributions() -> Dict[str, str]:
    """``{normalized-name: version}`` for every distribution in this env."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    result: Dict[str, str] = {}
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        for dist in importlib.metadata.distributions():
            _logger.debug_info("in for (dist in importlib.metadata.distributions())", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
                name = normalize_name(dist.metadata["Name"])
            except Exception:
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
                continue
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
                result[name] = str(dist.version)
            except Exception:
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
                result[name] = ""
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
        pass
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return result


def core_packages() -> List[str]:
    """Names that must never be uninstalled (app requirements + essentials)."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    names = {"pip", "setuptools", "wheel"}
    # Project root: this file lives at <root>/app/python_libraries/installed.py,
    # so walk up three directories (file -> python_libraries -> app -> root).
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    req_path = os.path.join(root, "requirements.txt")
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        with open(req_path, "r", encoding="utf-8") as fh:
            _logger.debug_info("in with (open(req_path, \"r\", encoding=\"utf-8\") as fh)", tier=_logger.DEBUG_FUNCTION)
            for line in fh:
                _logger.debug_info("in for (line in fh)", tier=_logger.DEBUG_LOOP)
                token = line.split("#", 1)[0].strip()
                if not token:
                    _logger.debug_info("in if (not token)", tier=_logger.DEBUG_FUNCTION)
                    continue
                raw = re.split(r"[<>=!~\s]", token, 1)[0].strip()
                if raw:
                    _logger.debug_info("in if (raw)", tier=_logger.DEBUG_FUNCTION)
                    names.add(normalize_name(raw))
    except OSError:
        _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_FUNCTION)
        pass
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return sorted(names)


def is_core_package(name: str) -> bool:
    _logger.debug_info("enter args=%s", ascii({"name": name}), tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return normalize_name(name) in set(core_packages())


def is_installed(name: str) -> Tuple[bool, Optional[str]]:
    _logger.debug_info("enter args=%s", ascii({"name": name}), tier=_logger.DEBUG_FUNCTION)
    version = installed_version(name)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return (version is not None, version)


def _compare_versions(a: Optional[str], b: str) -> Optional[bool]:
    """True when ``a`` is older than ``b``; None when not comparable."""
    _logger.debug_info("enter args=%s", ascii({"a": a, "b": b}), tier=_logger.DEBUG_LOOP)
    if not a or not b:
        _logger.debug_info("in if (not a or not b)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None

    def parts(value: str):
        _logger.debug_info("_compare_versions.parts: enter args=%s", ascii({"value": value}), tier=_logger.DEBUG_LOOP)
        nums = re.findall(r"\d+", value)
        _logger.debug_info("_compare_versions.parts: exit", tier=_logger.DEBUG_LOOP)
        return [int(n) for n in nums] or [0]

    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return parts(a) < parts(b)
    except (TypeError, ValueError):
        _logger.debug_info("in except (TypeError, ValueError)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return a != b
