"""Package-name index (pypi-search-cache owns the download + cache)."""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
import zlib
from typing import Any, Dict, List, Optional

from .cache import _cache_get, _cache_put, _remember_search_state
from .constants import (
    CACHE_INDEX_KEY,
    CACHE_SEARCH_PREFIX,
    HYDRATE_TIMEOUT,
    INDEX_MAX_AGE_SECONDS,
    NAME_TTL_SECONDS,
    SEARCH_CACHE_TTL,
)
from .helpers import _NAME_RE, _tool, internet_enabled, normalize_name
from .metadata import _enrich_batch
from core.debug_log import get_logger

_logger = get_logger(__name__)

_names_mem: Dict[str, Any] = {"list": None, "at": 0.0}
_index_stale_used = False


def _stale_lmdb_names() -> Optional[List[str]]:
    """Recover the package list from the engine's LMDB even when it is stale.

    ``CacheManager().load()`` returns None once the ``all_packages`` value is
    older than the engine's 23 h TTL *without* re-downloading. Reading the blob
    directly lets us keep searching offline from the last downloaded index. The
    ``~43 MB`` Simple-index download then only happens on an explicit "Refresh
    index" (or a genuinely missing cache) — switching sections or reopening the
    category can never trigger it, which is what the PyPI rate-limit protection
    is for.
    """
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    global _index_stale_used
    _index_stale_used = False
    tool = _tool()
    if not tool:
        _logger.debug_info("in if (not tool)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    env = None
    names: Optional[List[str]] = None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        env = tool.init_lmdb_env()
        with env.begin() as txn:
            _logger.debug_info("in with (env.begin() as txn)", tier=_logger.DEBUG_LOOP)
            value = txn.get(b"all_packages")
        if value:
            _logger.debug_info("in if (value)", tier=_logger.DEBUG_LOOP)
            entry = json.loads(value.decode("utf-8"))
            compressed = base64.b64decode(entry["data"])
            raw = json.loads(zlib.decompress(compressed).decode("utf-8"))
            if isinstance(raw, list):
                _logger.debug_info("in if (isinstance(raw, list))", tier=_logger.DEBUG_LOOP)
                names = sorted({name for name in raw if name and _NAME_RE.match(name)})
                _index_stale_used = True
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        names = None
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
    return names or None


def _load_names() -> Optional[List[str]]:
    """Package name list from the engine's LMDB cache (no network).

    Fresh copies come from ``CacheManager().load()``; a stale (> 23 h) copy is
    recovered from the raw LMDB blob so the index is never re-fetched merely by
    reopening the category. The in-memory copy is cached for the engine TTL.
    """
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    tool = _tool()
    if not tool:
        _logger.debug_info("in if (not tool)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    if _names_mem["list"] is not None and time.time() - _names_mem["at"] < NAME_TTL_SECONDS:
        _logger.debug_info("in if (_names_mem[\"list\"] is not None and time.time() - _names_mem[\"at\"] < NAME_TTL_SECONDS)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return _names_mem["list"]
    names = None
    fresh = False
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        raw = tool.CacheManager().load()
        if raw:
            _logger.debug_info("in if (raw)", tier=_logger.DEBUG_LOOP)
            names = sorted({name for name in raw if name and _NAME_RE.match(name)})
            fresh = True
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        names = None
    if not names:
        _logger.debug_info("in if (not names)", tier=_logger.DEBUG_LOOP)
        names = _stale_lmdb_names()
    if names:
        _logger.debug_info("in if (names)", tier=_logger.DEBUG_LOOP)
        _names_mem["list"] = names
        _names_mem["at"] = time.time()
        if fresh and _cache_get(CACHE_INDEX_KEY) is None:
            # First touch of a freshly-cached engine index: tune the "last
            # fetch" stamp so the category shows index metadata immediately.
            _logger.debug_info("in if (fresh and _cache_get(CACHE_INDEX_KEY) is None)", tier=_logger.DEBUG_LOOP)
            _record_index_fetch(len(names))
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return names


def _record_index_fetch(total: int) -> None:
    """Stamp the "last fetch" of the package-name index in the snapshot cache."""
    _logger.debug_info("enter args=%s", ascii({"total": total}), tier=_logger.DEBUG_LOOP)
    _cache_put(CACHE_INDEX_KEY, {
        "fetched_at": time.time(),
        "fetched_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": int(total or 0),
    })
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)


def index_info() -> Dict[str, Any]:
    """Freshness metadata for the last name-index fetch."""
    _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
    entry = _cache_get(CACHE_INDEX_KEY)
    fetched_at = float(entry.get("fetched_at") or 0) if isinstance(entry, dict) else 0.0
    fresh = bool(fetched_at) and time.time() - fetched_at < INDEX_MAX_AGE_SECONDS
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return {
        "fetched_at_iso": (entry or {}).get("fetched_at_iso") or "",
        "total": int((entry or {}).get("total") or 0),
        "fresh": fresh,
        "stale_recovered": bool(_index_stale_used),
    }


def _hydrate_cache() -> Optional[List[str]]:
    """Force-download the name index in a child process (never kills the app).

    ``pypi-search-caching`` calls ``sys.exit()`` when its first-time download
    fails, so the potentially lethal refresh must not run in-process.
    """
    _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
    code = "from pypi_search_caching import get_packages; get_packages(True)"
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
        proc.communicate(timeout=HYDRATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        _logger.debug_info("in except (subprocess.TimeoutExpired)", tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            proc.kill()
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            pass
        proc.communicate()
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    if proc.returncode != 0:
        _logger.debug_info("in if (proc.returncode != 0)", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return None
    _names_mem["list"] = None
    _names_mem["at"] = 0.0
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return _load_names()


def refresh_pypi_index(force: bool = True) -> Dict[str, Any]:
    """Refresh the package-name cache (via the pypi-search-cache engine).

    This is the *only* explicit way the big Simple-index download happens;
    browsing/reopening the category never triggers it on its own.
    """
    _logger.debug_info("enter args=%s", ascii({"force": force}), tier=_logger.DEBUG_FUNCTION)
    if not internet_enabled():
        _logger.debug_info("in if (not internet_enabled())", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "internet_disabled",
        }
    if not _tool():
        _logger.debug_info("in if (not _tool())", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "pypi_search_cache_unavailable",
        }
    names = _hydrate_cache()
    if names is None:
        _logger.debug_info("in if (names is None)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": False,
            "reason": "pypi_unavailable",
        }
    _record_index_fetch(len(names))
    index_entry = _cache_get(CACHE_INDEX_KEY)
    fetched_at = float(index_entry.get("fetched_at") or 0) if isinstance(index_entry, dict) else 0.0
    fresh = bool(fetched_at) and time.time() - fetched_at < INDEX_MAX_AGE_SECONDS
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return {
        "ok": True,
        "total": len(names),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fresh": fresh,
    }


def pypi_search(query: str, page: int = 1, per_page: int = 12,
                force: bool = False) -> Dict[str, Any]:
    """Search package names using the pypi-search-cache engine + its cache.

    Matching mirrors the tool exactly (anchored regex search over its cached
    names); results are sorted prefix-first, then paginated and enriched. A
    successful response is snapshotted (query/page/last-fetch aware) so the
    same page returns instantly and offline without re-fetching anything —
    pass ``force=True`` (e.g. after an install) to recompute.
    """
    _logger.debug_info("enter args=%s", ascii({"query": query, "page": page, "per_page": per_page, "force": force}), tier=_logger.DEBUG_FUNCTION)
    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        page = max(1, int(page))
        per_page = max(1, min(50, int(per_page)))
    except (TypeError, ValueError):
        _logger.debug_info("in except (TypeError, ValueError)", tier=_logger.DEBUG_FUNCTION)
        page, per_page = 1, 12

    q = (query or "").strip()
    if not q:
        _logger.debug_info("in if (not q)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "query": "",
            "page": page,
            "per_page": per_page,
            "total": 0,
            "pages": 0,
            "items": [],
        }

    key = CACHE_SEARCH_PREFIX + normalize_name(q) + "|" + str(page) + "|" + str(per_page)
    if not force:
        _logger.debug_info("in if (not force)", tier=_logger.DEBUG_FUNCTION)
        cached = _cache_get(key, SEARCH_CACHE_TTL)
        if isinstance(cached, dict) and cached.get("ok"):
            _logger.debug_info("in if (isinstance(cached, dict) and cached.get(\"ok\"))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return cached

    names = _load_names()
    if names is None:
        _logger.debug_info("in if (names is None)", tier=_logger.DEBUG_FUNCTION)
        if not internet_enabled():
            _logger.debug_info("in if (not internet_enabled())", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": "internet_disabled",
            }
        if not _tool():
            _logger.debug_info("in if (not _tool())", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": "pypi_search_cache_unavailable",
            }
        names = _hydrate_cache()
        if names is None:
            _logger.debug_info("in if (names is None)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": "pypi_unavailable",
            }
        _names_mem["list"] = names
        _names_mem["at"] = time.time()
        _record_index_fetch(len(names))

    try:
        _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
        regex = re.compile("^.*" + re.escape(q) + ".*$", re.IGNORECASE)
    except re.error:
        _logger.debug_info("in except (re.error)", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "query": q,
            "page": page,
            "per_page": per_page,
            "total": 0,
            "pages": 0,
            "items": [],
        }

    matched = [name for name in names if regex.search(name)]
    qn = normalize_name(q)
    matched.sort(key=lambda name: (0 if name.startswith(qn) else 1, name))

    total = len(matched)
    pages = max(1, -(-total // per_page)) if total else 0
    page = min(page, pages) if pages else 1
    start = (page - 1) * per_page
    slice_names = matched[start:start + per_page]

    response = {
        "ok": True,
        "query": q,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "items": _enrich_batch(slice_names),
    }
    _cache_put(key, response, SEARCH_CACHE_TTL)
    _remember_search_state(q, page)
    _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
    return response
