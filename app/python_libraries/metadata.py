"""Per-package metadata (via pypi-search-cache's LMDB cache)."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .audit import _audit_environment
from .constants import META_WORKERS
from .helpers import _tool, internet_enabled, normalize_name
from .installed import _compare_versions, is_core_package, is_installed
from core.debug_log import get_logger

_logger = get_logger(__name__)

_meta_lock = threading.Lock()


def _meta_cached(norm: str) -> Optional[Dict[str, Any]]:
    """Structured info from the engine's LMDB metadata cache (no network)."""
    _logger.debug_info("enter args=%s", ascii({"norm": norm}), tier=_logger.DEBUG_LOOP)
    tool = _tool()
    if not tool:
        _logger.debug_info("in if (not tool)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    env = None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        env = tool.init_lmdb_env()
        entry = tool.retrieve_package_data(env, norm)
        if entry and entry.get("json"):
            _logger.debug_info("in if (entry and entry.get(\"json\"))", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                data = json.loads(entry["json"])
            except (TypeError, ValueError):
                _logger.debug_info("in except (TypeError, ValueError)", tier=_logger.DEBUG_LOOP)
                data = None
            info = (data or {}).get("info") or {}
            ts = (entry.get("headers") or {}).get("timestamp") or 0
            if time.time() - float(ts) < float(tool.LMDB_CACHE_MAX_AGE_SECONDS):
                _logger.debug_info("in if (time.time() - float(ts) < float(tool.LMDB_CACHE_MAX_AGE_SECONDS))", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return {
                    "name": str(info.get("name") or norm),
                    "version": str(info.get("version") or ""),
                    "summary": str(info.get("summary") or ""),
                    "author": str(info.get("author") or ""),
                    "home_page": str(info.get("home_page") or ""),
                }
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        pass
    finally:
        _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
        if env is not None:
            _logger.debug_info("in if (env is not None)", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                env.close()
            except Exception:
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
                pass
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return None


def _pypi_meta(name: str) -> Dict[str, Any]:
    """Card metadata for ``name`` (engine cache first, network refresh later).

    Returns a fixed subset: ``{name, version, summary, author, home_page}``.
    """
    _logger.debug_info("enter args=%s", ascii({"name": name}), tier=_logger.DEBUG_LOOP)
    norm = normalize_name(name)
    info = _meta_cached(norm)
    if info:
        _logger.debug_info("in if (info)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return info
    if not internet_enabled():
        _logger.debug_info("in if (not internet_enabled())", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "name": norm,
            "version": "",
            "summary": "",
            "author": "",
            "home_page": "",
            "stale": True,
        }
    tool = _tool()
    if tool:
        _logger.debug_info("in if (tool)", tier=_logger.DEBUG_LOOP)
        with _meta_lock:
            _logger.debug_info("in with (_meta_lock)", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                tool.fetch_project_details(norm, include_desc=False,
                                           verbose=False, test_mode=True)
            except Exception:
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
                pass
        info = _meta_cached(norm)
        if info:
            _logger.debug_info("in if (info)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return info
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return {
        "name": norm,
        "version": "",
        "summary": "",
        "author": "",
        "home_page": "",
        "error": True,
    }


def latest_version(name: str) -> str:
    """Latest known version from the engine's metadata cache (cache-first)."""
    _logger.debug_info("enter args=%s", ascii({"name": name}), tier=_logger.DEBUG_FUNCTION)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return str(_pypi_meta(name).get("version") or "")


def _enrich_batch(names: List[str]) -> List[Dict[str, Any]]:
    """Attach metadata to a page of names (parallel; metadata is cached)."""
    _logger.debug_info("enter args=%s", ascii({"names": names}), tier=_logger.DEBUG_LOOP)
    if not names:
        _logger.debug_info("in if (not names)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return []
    metas: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=META_WORKERS) as pool:
        _logger.debug_info("in with (ThreadPoolExecutor(max_workers=META_WORKERS) as pool)", tier=_logger.DEBUG_LOOP)
        futures = [pool.submit(_pypi_meta, name) for name in names]
        for name, future in zip(names, futures):
            _logger.debug_info("in for (name, future in zip(names, futures))", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                metas[name] = future.result()
            except Exception:
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
                metas[name] = {"name": normalize_name(name), "version": "",
                               "summary": "", "error": True}
    items: List[Dict[str, Any]] = []
    audit_map = (_audit_environment().get("by_name") or {})
    for name in names:
        _logger.debug_info("in for (name in names)", tier=_logger.DEBUG_LOOP)
        meta = metas.get(name) or {"name": name, "version": "", "summary": ""}
        norm = normalize_name(name)
        installed, installed_ver = is_installed(norm)
        latest = str(meta.get("version") or "")
        outdated = _compare_versions(installed_ver, latest) is True if installed else False
        vuln = audit_map.get(norm)
        items.append({
            "name": str(meta.get("name") or norm),
            "version": latest,
            "summary": str(meta.get("summary") or ""),
            "author": str(meta.get("author") or ""),
            "home_page": str(meta.get("home_page") or ""),
            "installed": installed,
            "installed_version": installed_ver or "",
            "outdated": bool(outdated),
            "core": is_core_package(norm),
            "vulnerable": bool(vuln and vuln.get("count")),
            "vuln_count": int((vuln or {}).get("count") or 0),
            "vuln_ids": [str(v.get("id") or "") for v in (vuln or {}).get("vulns") or []][:8],
        })
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return items
