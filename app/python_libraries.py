"""Python Libraries: PyPI discovery, pip install/uninstall and dependency status.

Design
------
* Search/discovery is delegated to the third-party ``pypi-search-caching``
  package (project name ``pypi-search-cache``): it owns the PyPI Simple-index
  download and both caches:
  * package **names** in an LMDB ``all_packages`` blob, 23 h TTL;
  * per-package **details** (raw ``/pypi/<name>/json``) in LMDB, 7 d TTL with
    ETag/Last-Modified validation.
  Matching uses the exact algorithm the tool ships (anchored regex over its
  cached name list); results are merely sorted prefix-first, paginated and
  enriched from the tool's own metadata cache. Because the tool calls
  ``sys.exit()`` when its first-time index download fails, index hydration
  always runs in a child process so the app can never be killed by it.
* Runtime hooks execute Python **in-process** using the app's own interpreter,
  so "install" targets a real pip-managed environment:
  * *local* (recommended, default) -> ``sys.executable -m pip install`` (the
    project ``.venv`` created by ``setup_env.py``). Runtime hooks import
    installed packages immediately, in-process.
  * *global* -> the base/system interpreter that created the venv
    (``sys._base_executable``). Global actions always require an explicit
    ``confirmed`` flag so they can never happen silently.
* Per-utility requirements come from ``manifest.json``
  (``python_requirements`` vs ``additional_requirements``, the latter being
  non-Python tools such as FFmpeg) with ``requirements.txt`` as the file-based
  record. Network access is gated by Settings > General > Allow Internet Access.
* Security: ``pip-audit`` scans installed packages against the OSV/PyPI
  advisory database (the Settings "auto scan", run at most once per TTL) and
  every install candidate is pre-scanned; a package with known vulnerabilities
  is blocked until the user works through the two-step "Proceed anyway?" /
  "Are you sure?" confirmation (``vuln_ack``).
"""

from __future__ import annotations

import base64
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zlib

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from app.settings import load_app_settings

PIP_TIMEOUT = 300
HYDRATE_TIMEOUT = 360  # first-time full index download
META_WORKERS = 4
NAME_TTL_SECONDS = 23 * 3600  # mirrors pypi-search-cache's names TTL
INDEX_MAX_AGE_SECONDS = 23 * 3600  # engine's Simple-index TTL
SEARCH_CACHE_TTL = 10 * 60    # seconds a search response snapshot stays valid
UTIL_CACHE_TTL = 5 * 60       # seconds a utility-dependencies snapshot stays valid
VULN_CACHE_TTL = 10 * 60      # seconds the auto vulnerability scan stays valid
VULN_REQ_CACHE_TTL = 15 * 60  # seconds a pre-install advisory check stays valid
AUDIT_TIMEOUT = 60            # seconds for one pip-audit run
CACHE_STATE_KEY = "section_state"
CACHE_INDEX_KEY = "index"
CACHE_SEARCH_PREFIX = "search|"
CACHE_UTILS_PREFIX = "utils|"
CACHE_VULN_KEY = "vulns|env|"   # environment-wide installed-package scan
CACHE_VULN_REQ_PREFIX = "vulns|req|"  # per-candidate pre-install checks

_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")

_search_tool: Any = None          # lazy import of pypi_search_caching
_names_mem: Dict[str, Any] = {"list": None, "at": 0.0}
_meta_lock = threading.Lock()
_index_stale_used = False

_cache_mem: Any = None
_cache_lock = threading.Lock()
_cache_path_set = False
_cache_path_held: Optional[str] = None

# Live pip operation progress, read by the frontend via get_pypi_progress().
_progress: Dict[str, Any] = {}
_progress_lock = threading.Lock()


# -------------------------------------------------------------------------- #
#  Persistent snapshot cache (survives section switches and app restarts)
# -------------------------------------------------------------------------- #
def _cache_path() -> str:
    """Path to the Settings > Python Libraries cache/snapshot file."""
    global _cache_path_set, _cache_path_held
    if not _cache_path_set:
        try:
            from app.settings import get_python_libraries_cache_path
            _cache_path_held = get_python_libraries_cache_path()
        except Exception:
            _cache_path_held = None
        _cache_path_set = True
    return _cache_path_held or ""


def _cache_memload() -> Dict[str, Any]:
    """Load the persistent cache document (thread-safe, lazy)."""
    global _cache_mem
    if _cache_mem is None:
        doc: Dict[str, Any] = {}
        path = _cache_path()
        if path:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    doc = json.load(fh)
            except Exception:
                doc = {}
        _cache_mem = doc if isinstance(doc, dict) else {}
    return _cache_mem


def _cache_save() -> None:
    path = _cache_path()
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_cache_mem, fh)
    except Exception:
        pass


def _cache_get(key: str, ttl: float = 0) -> Optional[Any]:
    """Return a cached value if still within ``ttl`` seconds, else None."""
    with _cache_lock:
        entry = _cache_memload().get(key)
    if not isinstance(entry, dict) or "data" not in entry:
        return None
    ts = entry.get("ts") or 0
    if ttl and time.time() - float(ts) > float(ttl):
        return None
    return entry["data"]


def _cache_put(key: str, data: Any, ttl: float = 0) -> None:
    with _cache_lock:
        _cache_memload()[key] = {"ts": time.time(), "ttl": ttl, "data": data}
        _cache_save()


def _cache_section_state() -> Dict[str, Any]:
    entry = _cache_get(CACHE_STATE_KEY)
    return entry if isinstance(entry, dict) else {}


def section_state() -> Dict[str, Any]:
    """Last-used query/page for the Python Libraries category (for restoring UI)."""
    state = _cache_section_state()
    return {
        "query": str(state.get("query") or ""),
        "page": int(state.get("page") or 1),
    }


def _remember_search_state(query: str, page: int) -> None:
    _cache_put(CACHE_STATE_KEY, {"query": query, "page": int(page or 1)})


# -------------------------------------------------------------------------- #
#  Helpers
# -------------------------------------------------------------------------- #
def normalize_name(name: str) -> str:
    """PEP 503-ish canonical form: lowercase, ``_``/``.`` become ``-``."""
    return re.sub(r"[-_.]+", "-", str(name or "").strip().lower())


def internet_enabled() -> bool:
    try:
        general = (load_app_settings().get("general") or {})
        return bool(general.get("allow_internet", False))
    except Exception:
        return False


def local_only_scope() -> bool:
    """The persisted scope preference (True = install only into the app env)."""
    try:
        python_libraries = (load_app_settings().get("python_libraries") or {})
        return bool(python_libraries.get("local_only", True))
    except Exception:
        return True


def _tool():
    """Lazily import the ``pypi-search-caching`` search engine. None when absent."""
    global _search_tool
    if _search_tool is None:
        try:
            import pypi_search_caching as mod
            _search_tool = mod
        except Exception:
            _search_tool = False
    return _search_tool or None


# -------------------------------------------------------------------------- #
#  Name index (pypi-search-cache owns the download + cache)
# -------------------------------------------------------------------------- #
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
    global _index_stale_used
    _index_stale_used = False
    tool = _tool()
    if not tool:
        return None
    env = None
    names: Optional[List[str]] = None
    try:
        env = tool.init_lmdb_env()
        with env.begin() as txn:
            value = txn.get(b"all_packages")
        if value:
            entry = json.loads(value.decode("utf-8"))
            compressed = base64.b64decode(entry["data"])
            raw = json.loads(zlib.decompress(compressed).decode("utf-8"))
            if isinstance(raw, list):
                names = sorted({name for name in raw if name and _NAME_RE.match(name)})
                _index_stale_used = True
    except Exception:
        names = None
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
    return names or None


def _load_names() -> Optional[List[str]]:
    """Package name list from the engine's LMDB cache (no network).

    Fresh copies come from ``CacheManager().load()``; a stale (> 23 h) copy is
    recovered from the raw LMDB blob so the index is never re-fetched merely by
    reopening the category. The in-memory copy is cached for the engine TTL.
    """
    tool = _tool()
    if not tool:
        return None
    if _names_mem["list"] is not None and time.time() - _names_mem["at"] < NAME_TTL_SECONDS:
        return _names_mem["list"]
    names = None
    fresh = False
    try:
        raw = tool.CacheManager().load()
        if raw:
            names = sorted({name for name in raw if name and _NAME_RE.match(name)})
            fresh = True
    except Exception:
        names = None
    if not names:
        names = _stale_lmdb_names()
    if names:
        _names_mem["list"] = names
        _names_mem["at"] = time.time()
        if fresh and _cache_get(CACHE_INDEX_KEY) is None:
            # First touch of a freshly-cached engine index: tune the "last
            # fetch" stamp so the category shows index metadata immediately.
            _record_index_fetch(len(names))
    return names


def _record_index_fetch(total: int) -> None:
    """Stamp the "last fetch" of the package-name index in the snapshot cache."""
    _cache_put(CACHE_INDEX_KEY, {
        "fetched_at": time.time(),
        "fetched_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": int(total or 0),
    })


def index_info() -> Dict[str, Any]:
    """Freshness metadata for the last name-index fetch."""
    entry = _cache_get(CACHE_INDEX_KEY)
    fetched_at = float(entry.get("fetched_at") or 0) if isinstance(entry, dict) else 0.0
    fresh = bool(fetched_at) and time.time() - fetched_at < INDEX_MAX_AGE_SECONDS
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
    code = "from pypi_search_caching import get_packages; get_packages(True)"
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return None
    try:
        proc.communicate(timeout=HYDRATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        proc.communicate()
        return None
    if proc.returncode != 0:
        return None
    _names_mem["list"] = None
    _names_mem["at"] = 0.0
    return _load_names()


def refresh_pypi_index(force: bool = True) -> Dict[str, Any]:
    """Refresh the package-name cache (via the pypi-search-cache engine).

    This is the *only* explicit way the big Simple-index download happens;
    browsing/reopening the category never triggers it on its own.
    """
    if not internet_enabled():
        return {"ok": False, "reason": "internet_disabled"}
    if not _tool():
        return {"ok": False, "reason": "pypi_search_cache_unavailable"}
    names = _hydrate_cache()
    if names is None:
        return {"ok": False, "reason": "pypi_unavailable"}
    _record_index_fetch(len(names))
    fresh = time.time() - (_cache_get(CACHE_INDEX_KEY) or {}).get("fetched_at", 0) < INDEX_MAX_AGE_SECONDS
    return {"ok": True, "total": len(names),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "fresh": fresh}


def pypi_search(query: str, page: int = 1, per_page: int = 12,
                force: bool = False) -> Dict[str, Any]:
    """Search package names using the pypi-search-cache engine + its cache.

    Matching mirrors the tool exactly (anchored regex search over its cached
    names); results are sorted prefix-first, then paginated and enriched. A
    successful response is snapshotted (query/page/last-fetch aware) so the
    same page returns instantly and offline without re-fetching anything —
    pass ``force=True`` (e.g. after an install) to recompute.
    """
    try:
        page = max(1, int(page))
        per_page = max(1, min(50, int(per_page)))
    except (TypeError, ValueError):
        page, per_page = 1, 12

    q = (query or "").strip()
    if not q:
        return {"ok": True, "query": "", "page": page, "per_page": per_page,
                "total": 0, "pages": 0, "items": []}

    key = CACHE_SEARCH_PREFIX + normalize_name(q) + "|" + str(page) + "|" + str(per_page)
    if not force:
        cached = _cache_get(key, SEARCH_CACHE_TTL)
        if isinstance(cached, dict) and cached.get("ok"):
            return cached

    names = _load_names()
    if names is None:
        if not internet_enabled():
            return {"ok": False, "reason": "internet_disabled"}
        if not _tool():
            return {"ok": False, "reason": "pypi_search_cache_unavailable"}
        names = _hydrate_cache()
        if names is None:
            return {"ok": False, "reason": "pypi_unavailable"}
        _names_mem["list"] = names
        _names_mem["at"] = time.time()
        _record_index_fetch(len(names))

    try:
        regex = re.compile("^.*" + re.escape(q) + ".*$", re.IGNORECASE)
    except re.error:
        return {"ok": True, "query": q, "page": page, "per_page": per_page,
                "total": 0, "pages": 0, "items": []}

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
    return response


# -------------------------------------------------------------------------- #
#  Per-package metadata (via pypi-search-cache's LMDB cache)
# -------------------------------------------------------------------------- #
def _meta_cached(norm: str) -> Optional[Dict[str, Any]]:
    """Structured info from the engine's LMDB metadata cache (no network)."""
    tool = _tool()
    if not tool:
        return None
    env = None
    try:
        env = tool.init_lmdb_env()
        entry = tool.retrieve_package_data(env, norm)
        if entry and entry.get("json"):
            try:
                data = json.loads(entry["json"])
            except (TypeError, ValueError):
                data = None
            info = (data or {}).get("info") or {}
            ts = (entry.get("headers") or {}).get("timestamp") or 0
            if time.time() - float(ts) < float(tool.LMDB_CACHE_MAX_AGE_SECONDS):
                return {
                    "name": str(info.get("name") or norm),
                    "version": str(info.get("version") or ""),
                    "summary": str(info.get("summary") or ""),
                    "author": str(info.get("author") or ""),
                    "home_page": str(info.get("home_page") or ""),
                }
    except Exception:
        pass
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
    return None


def _pypi_meta(name: str) -> Dict[str, Any]:
    """Card metadata for ``name`` (engine cache first, network refresh later).

    Returns a fixed subset: ``{name, version, summary, author, home_page}``.
    """
    norm = normalize_name(name)
    info = _meta_cached(norm)
    if info:
        return info
    if not internet_enabled():
        return {"name": norm, "version": "", "summary": "", "author": "",
                "home_page": "", "stale": True}
    tool = _tool()
    if tool:
        with _meta_lock:
            try:
                tool.fetch_project_details(norm, include_desc=False,
                                           verbose=False, test_mode=True)
            except Exception:
                pass
        info = _meta_cached(norm)
        if info:
            return info
    return {"name": norm, "version": "", "summary": "", "author": "",
            "home_page": "", "error": True}


def latest_version(name: str) -> str:
    """Latest known version from the engine's metadata cache (cache-first)."""
    return str(_pypi_meta(name).get("version") or "")


def _enrich_batch(names: List[str]) -> List[Dict[str, Any]]:
    """Attach metadata to a page of names (parallel; metadata is cached)."""
    if not names:
        return []
    metas: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=META_WORKERS) as pool:
        futures = [pool.submit(_pypi_meta, name) for name in names]
        for name, future in zip(names, futures):
            try:
                metas[name] = future.result()
            except Exception:
                metas[name] = {"name": normalize_name(name), "version": "",
                               "summary": "", "error": True}
    items: List[Dict[str, Any]] = []
    audit_map = (_audit_environment().get("by_name") or {})
    for name in names:
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
    return items


# -------------------------------------------------------------------------- #
#  Installed state (the running interpreter's environment)
# -------------------------------------------------------------------------- #
def installed_version(name: str) -> Optional[str]:
    """Version of ``name`` in the current environment, or None when missing."""
    norm = normalize_name(name)
    try:
        return importlib.metadata.version(norm)
    except importlib.metadata.PackageNotFoundError:
        return None


def installed_distributions() -> Dict[str, str]:
    """``{normalized-name: version}`` for every distribution in this env."""
    result: Dict[str, str] = {}
    try:
        for dist in importlib.metadata.distributions():
            try:
                name = normalize_name(dist.metadata["Name"])
            except Exception:
                continue
            try:
                result[name] = str(dist.version)
            except Exception:
                result[name] = ""
    except Exception:
        pass
    return result


def core_packages() -> List[str]:
    """Names that must never be uninstalled (app requirements + essentials)."""
    names = {"pip", "setuptools", "wheel"}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    req_path = os.path.join(root, "requirements.txt")
    try:
        with open(req_path, "r", encoding="utf-8") as fh:
            for line in fh:
                token = line.split("#", 1)[0].strip()
                if not token:
                    continue
                raw = re.split(r"[<>=!~\s]", token, 1)[0].strip()
                if raw:
                    names.add(normalize_name(raw))
    except OSError:
        pass
    return sorted(names)


def is_core_package(name: str) -> bool:
    return normalize_name(name) in set(core_packages())


def is_installed(name: str) -> Tuple[bool, Optional[str]]:
    version = installed_version(name)
    return (version is not None, version)


def _compare_versions(a: Optional[str], b: str) -> Optional[bool]:
    """True when ``a`` is older than ``b``; None when not comparable."""
    if not a or not b:
        return None

    def parts(value: str):
        nums = re.findall(r"\d+", value)
        return [int(n) for n in nums] or [0]

    try:
        return parts(a) < parts(b)
    except (TypeError, ValueError):
        return a != b


# -------------------------------------------------------------------------- #
#  Vulnerability scanning (pip-audit against the OSV/PyPI advisory database)
# -------------------------------------------------------------------------- #
# pip-audit runs as a subprocess (the tool needs network + its own dependency
# stack). Two query shapes are used:
#   * environment scan  -> ``pip-audit -l`` audits every *installed* package;
#   * pre-install check -> ``pip-audit -r <file> --no-deps`` audits a pinned
#     ``name==version`` candidate (exact pins are required by --no-deps).
# Exit codes: 0 = no advisories, 1 = advisories found, anything else = the
# run failed. Both scan results are snapshotted so "auto scan" happens at most
# every few minutes instead of on every render.

_audit_lock = threading.Lock()


def _parse_audit_report(report: Any) -> Dict[str, Any]:
    """Normalize a pip-audit JSON report into ``{total, affected, by_name}``."""
    if not isinstance(report, dict):
        return {"total": 0, "affected": [], "by_name": {}}
    deps = report.get("dependencies")
    if not isinstance(deps, list):
        deps = []
    affected: List[Dict[str, Any]] = []
    by_name: Dict[str, Dict[str, Any]] = {}
    total = 0
    for dep in deps:
        if not isinstance(dep, dict) or not dep.get("name"):
            continue
        name = str(dep.get("name"))
        version = str(dep.get("version") or "")
        vulns = dep.get("vulns")
        if not isinstance(vulns, list):
            vulns = []
        seen_ids: set = set()
        cleaned: List[Dict[str, Any]] = []
        for v in vulns:
            if not isinstance(v, dict):
                continue
            v_id = str(v.get("id") or "")
            if v_id in seen_ids:
                continue
            seen_ids.add(v_id)
            aliases = v.get("aliases")
            if not isinstance(aliases, list):
                aliases = []
            fix_versions = v.get("fix_versions")
            if not isinstance(fix_versions, list):
                fix_versions = []
            cleaned.append({
                "id": v_id,
                "aliases": [str(a) for a in aliases if isinstance(a, str)],
                "fix_versions": [str(f) for f in fix_versions if isinstance(f, str)],
                "summary": str(v.get("description") or v.get("details") or ""),
            })
        if not cleaned:
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
    return {"total": total, "affected": affected, "by_name": by_name}


def _empty_audit(state: str) -> Dict[str, Any]:
    return {"ok": state == "ok", "state": state, "total": 0,
            "affected": [], "by_name": {}, "fetched_at": ""}


def _audit_available(python: Optional[str] = None) -> bool:
    """True when ``pip-audit`` is importable in the given interpreter."""
    py = python or sys.executable
    try:
        proc = subprocess.run([py, "-c", "import pip_audit"],
                              capture_output=True, text=True, timeout=20)
        return proc.returncode == 0
    except Exception:
        return False


def _run_pip_audit(python: str, requirements: Optional[List[str]],
                   timeout: int = AUDIT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """Run pip-audit and parse its JSON report. None on failure/timeout."""
    cmd = [python, "-m", "pip_audit", "--format", "json",
           "--progress-spinner", "off", "--desc", "on", "--aliases", "on"]
    tmp_path: Optional[str] = None
    if requirements:
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="pip-audit-", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("\n".join(requirements) + "\n")
        except OSError:
            return None
        cmd += ["--no-deps", "-r", tmp_path]
    else:
        cmd += ["-l"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    if proc.returncode not in (0, 1):
        return None
    try:
        report = json.loads(proc.stdout)
    except (TypeError, ValueError):
        return None
    return _parse_audit_report(report)


def _audit_environment(python: Optional[str] = None,
                       force: bool = False) -> Dict[str, Any]:
    """Scan every installed package in ``python`` against the advisory DB.

    This is the Settings "auto scan": it runs at most once per TTL and its
    report feeds both the per-package badges in search results and the
    environment row. ``force=True`` (used by the "Scan now" button) bypasses
    the snapshot.
    """
    py = python or sys.executable
    key = CACHE_VULN_KEY + normalize_name(os.path.basename(py))
    if not internet_enabled():
        return _empty_audit("offline")
    if not force:
        cached = _cache_get(key, VULN_CACHE_TTL)
        if isinstance(cached, dict):
            return cached
    with _audit_lock:
        if not force:
            cached = _cache_get(key, VULN_CACHE_TTL)
            if isinstance(cached, dict):
                return cached
        if not _audit_available(py):
            result = _empty_audit("unavailable")
            _cache_put(key, result, VULN_CACHE_TTL)
            return result
        parsed = _run_pip_audit(py, None)
        if parsed is None:
            result = _empty_audit("failed")
            _cache_put(key, result, VULN_CACHE_TTL)
            return result
        parsed["ok"] = True
        parsed["state"] = "ok"
        parsed["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _cache_put(key, parsed, VULN_CACHE_TTL)
        return parsed


def _audit_requirement(name: str, version: str,
                       python: Optional[str] = None) -> Dict[str, Any]:
    """Advisory check for ``name==version`` performed before an install.

    ``pip-audit --no-deps`` requires exact pins; when no version is known the
    scan degrades to the environment snapshot (which may still flag the
    already-installed copy). Cached per ``name@version`` so the follow-up
    install attempt re-uses the result.
    """
    norm = normalize_name(name)
    ver = (version or "").strip()
    empty = _empty_audit("offline" if not internet_enabled() else "pending")
    if not internet_enabled() or not ver:
        env = _audit_environment(python=python)
        if env.get("total"):
            result = dict(env)
            result.pop("by_name", None)
            result["ok"] = True
            return result
        return empty
    key = CACHE_VULN_REQ_PREFIX + norm + "@" + ver
    cached = _cache_get(key, VULN_REQ_CACHE_TTL)
    if isinstance(cached, dict):
        return cached
    py = python or sys.executable
    with _audit_lock:
        cached = _cache_get(key, VULN_REQ_CACHE_TTL)
        if isinstance(cached, dict):
            return cached
        if not _audit_available(py):
            result = _empty_audit("unavailable")
            _cache_put(key, result, VULN_REQ_CACHE_TTL)
            return result
        parsed = _run_pip_audit(py, ["{}=={}".format(norm, ver)])
        if parsed is None:
            result = _empty_audit("failed")
            _cache_put(key, result, VULN_REQ_CACHE_TTL)
            return result
        parsed["ok"] = True
        parsed["state"] = "ok"
        parsed["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _cache_put(key, parsed, VULN_REQ_CACHE_TTL)
        return parsed


def _summarize_audit(affected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact affected-package shape (ids + fixes) for the confirm dialog."""
    out: List[Dict[str, Any]] = []
    for entry in affected or []:
        vulns = entry.get("vulns") if isinstance(entry.get("vulns"), list) else []
        out.append({
            "name": entry.get("name"),
            "version": entry.get("version"),
            "count": int(entry.get("count") or 0),
            "ids": [str(v.get("id") or "") for v in vulns],
            "fix_versions": sorted({str(f) for v in vulns
                                    for f in (v.get("fix_versions") or []) if f}),
        })
    return out


def python_audit(force: bool = False) -> Dict[str, Any]:
    """Re-run the environment vulnerability scan (Settings > "Scan now")."""
    audit = _audit_environment(force=bool(force))
    body = {
        "ok": audit.get("ok", False),
        "state": audit.get("state", ""),
        "total": int(audit.get("total") or 0),
        "affected": _summarize_audit(audit.get("affected") or []),
        "fetched_at": audit.get("fetched_at") or "",
    }
    return body


# -------------------------------------------------------------------------- #
#  Pip operations
# -------------------------------------------------------------------------- #
def _interpreter_for(scope: str) -> Tuple[str, bool]:
    """Resolve the target interpreter for a scope.

    Returns ``(python_executable, is_base)``. ``is_base`` is True when the
    target is a different, shared (global) interpreter.
    """
    if scope == "global":
        base = getattr(sys, "_base_executable", None) or sys.executable
        is_base = os.path.abspath(base) != os.path.abspath(sys.executable)
        return base, is_base
    return sys.executable, False


# -------------------------------------------------------------------------- #
#  Live operation progress (polled by the frontend)
# -------------------------------------------------------------------------- #
def _set_progress(**kw: Any) -> None:
    with _progress_lock:
        _progress.update(kw)


def _clear_progress() -> None:
    with _progress_lock:
        _progress.clear()


def pypi_progress() -> Optional[Dict[str, Any]]:
    """Snapshot of the currently-running pip operation, or None when idle."""
    with _progress_lock:
        return dict(_progress) if _progress else None


def _bar_percent(text: str) -> Optional[int]:
    """Extract a percentage from a pip progress-bar frame, if present."""
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*%", text)
    if m:
        return max(0, min(100, int(float(m.group(1)))))
    # "12.3/45.6 MB" style byte ratio (tqdm-style bar segments).
    m = re.search(r"\b([\d.]+)\s*([kKmMgGtT]?B)\s*/\s*([\d.]+)\s*([kKmMgGtT]?B)", text)
    if m:
        units = {"": 1, "b": 1, "k": 1024, "K": 1024, "m": 1024 ** 2, "M": 1024 ** 2,
                 "g": 1024 ** 3, "G": 1024 ** 3, "t": 1024 ** 4, "T": 1024 ** 4}
        done = float(m.group(1)) * units.get(m.group(2), 1024)
        total = float(m.group(3)) * units.get(m.group(4), 1024)
        if total > 0:
            return max(0, min(100, int(done / total * 100)))
    return None


class _PipState:
    """Parsed progress state for a single pip run."""

    def __init__(self) -> None:
        self.collected = 0
        self.installing_total = 0
        self.done_markers = 0
        self.downloading = ""
        self.install_done = False
        self.uninstall_done = False

    def on_line(self, text: str) -> None:
        stripped = text.lstrip()
        if stripped.startswith("Collecting "):
            self.collected += 1
            name = stripped[len("Collecting "):].split(" from ", 1)[0].strip()
            _set_progress(phase="resolving", pct=min(26, 3 + self.collected * 3),
                          status="Resolving dependencies… (collected {})".format(name))
        elif stripped.startswith("Downloading "):
            self.downloading = stripped[len("Downloading "):]
            _set_progress(phase="downloading", pct=30, status="Downloading " + self.downloading)
        elif stripped.startswith("Installing collected packages: "):
            items = [s.strip() for s in stripped[len("Installing collected packages: "):].split(",") if s.strip()]
            self.installing_total = len(items) or 1
            _set_progress(phase="installing", pct=72, total_packages=self.installing_total,
                          status="Installing collected packages ({})…".format(self.installing_total))
        elif stripped.startswith("Uninstalling "):
            _set_progress(phase="uninstalling", pct=50, total_packages=1,
                          status=stripped[:-1] if stripped.endswith(":") else stripped)
        elif stripped.startswith("Successfully installed"):
            self.install_done = True
            _set_progress(phase="done", pct=100,
                          done_packages=self.installing_total or 1,
                          total_packages=self.installing_total or 1,
                          status="Installed successfully")
        elif stripped.startswith("Successfully uninstalled"):
            self.uninstall_done = True
            _set_progress(phase="done", pct=100, done_packages=1, total_packages=1,
                          status="Uninstalled successfully")
        elif self.installing_total and _progress.get("phase") == "installing" \
                and (stripped.endswith("... done") or stripped.endswith(" - done")
                     or stripped.endswith("done")):
            self.done_markers += 1
            pct = min(98, 72 + int(self.done_markers / (self.installing_total * 3) * 26))
            done = min(self.installing_total, max(1, int(pct / 100 * self.installing_total)))
            _set_progress(pct=pct, done_packages=done)
        elif stripped.startswith("Requirement already satisfied"):
            _set_progress(status="Requirement already satisfied")
        elif _progress.get("phase") == "downloading":
            pct = _bar_percent(text)
            if pct is not None:
                _set_progress(pct=min(99, 31 + int(pct * 0.37)),
                              status="Downloading {} ({}%)".format(self.downloading, pct))


def _stream_pip(python: str, args: List[str], op: str, name: str,
                batch_total: int = 1, batch_done: int = 0,
                timeout: int = PIP_TIMEOUT) -> Dict[str, Any]:
    """Run pip while streaming + parsing progress into the shared state.

    Callers pass ``--progress-bar on`` right after the subcommand so pip emits
    readable ``\\r``-separated frames (``NN% | ...``) that we parse into an
    overall percentage, and its ``Collecting …`` / ``Installing collected
    packages: …`` lines supply the package counters shown in the UI.
    """
    _set_progress(active=True, op=op, name=name, phase="resolving", pct=0,
                  batch_total=max(1, int(batch_total or 1)),
                  batch_done=max(0, int(batch_done or 0)),
                  total_packages=0, done_packages=0, status="Starting…",
                  started=time.time())
    cmd = [python, "-m", "pip", "--disable-pip-version-check", *args]
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as exc:
        _set_progress(phase="failed", status="Could not start pip")
        return {"ok": False, "reason": str(exc), "code": None, "output": []}

    state = _PipState()
    lines: List[str] = []
    buf = b""
    deadline = time.time() + timeout
    timed_out = False
    try:
        while True:
            try:
                chunk = os.read(proc.stdout.fileno(), 8192)
            except OSError:
                chunk = b""
            if not chunk:
                break
            if time.time() > deadline:
                timed_out = True
                break
            buf += chunk
            while True:
                cr = buf.find(b"\r")
                nl = buf.find(b"\n")
                if cr == -1 and nl == -1:
                    break
                if cr == -1:
                    idx = nl
                elif nl == -1:
                    idx = cr
                else:
                    idx = min(cr, nl)
                seg = buf[:idx]
                buf = buf[idx + 1:]
                seg_text = seg.decode("utf-8", "replace").strip()
                if seg_text:
                    lines.append(seg_text)
                    state.on_line(seg_text)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass

    if timed_out:
        try:
            proc.kill()
        except Exception:
            pass
        state.on_line("Successfully uninstalled") if op == "uninstall" else None
        _set_progress(phase="failed", status="Operation timed out")
        return {"ok": False, "reason": "timeout", "code": None, "output": lines[-60:]}

    try:
        proc.wait(timeout=15)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        proc.wait()
    if not state.install_done and not state.uninstall_done and proc.returncode == 0:
        # Success without a matching "Successfully …" line (rare paths).
        _set_progress(phase="done", pct=100,
                      done_packages=state.installing_total or 1,
                      total_packages=state.installing_total or 1,
                      status="Finished")
    elif proc.returncode != 0:
        _set_progress(phase="failed",
                      status="Failed (pip exit code {})".format(proc.returncode))
    _set_progress(active=False, pct=100 if proc.returncode == 0 else max(0, _progress.get("pct", 0) or 0))
    return {"ok": proc.returncode == 0, "code": proc.returncode, "output": lines[-60:]}


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
    norm = normalize_name(name)
    if not _NAME_RE.match(norm):
        return {"ok": False, "reason": "invalid_name", "name": norm}
    if not internet_enabled():
        return {"ok": False, "reason": "internet_disabled"}
    if scope == "global" and not confirmed:
        # Never touch the shared/system interpreter without an explicit
        # user confirmation from the frontend.
        return {"ok": False, "reason": "confirmation_required"}
    python, is_base = _interpreter_for(scope)
    target_version = latest_version(norm) or (installed_version(norm) or "")
    audit = _audit_requirement(norm, target_version, python)
    if audit.get("total") and not vuln_ack:
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
    return result


def pypi_uninstall(name: str, scope: str = "local", confirmed: bool = False,
                   batch_total: int = 1, batch_done: int = 0) -> Dict[str, Any]:
    """Uninstall a package through pip. Core packages are never removable."""
    norm = normalize_name(name)
    if not _NAME_RE.match(norm):
        return {"ok": False, "reason": "invalid_name", "name": norm}
    if is_core_package(norm):
        return {"ok": False, "reason": "core_package", "name": norm}
    if not confirmed:
        return {"ok": False, "reason": "confirmation_required"}
    python, is_base = _interpreter_for(scope)
    result = _stream_pip(python, ["uninstall", "--progress-bar", "on", "-y", norm],
                         "uninstall", norm, batch_total=batch_total, batch_done=batch_done)
    result["name"] = norm
    result["scope"] = "global" if is_base else "local"
    result["environment"] = python
    return result


def pip_available() -> bool:
    try:
        proc = subprocess.run([sys.executable, "-m", "pip", "--version"],
                              capture_output=True, text=True, timeout=20)
        return proc.returncode == 0
    except Exception:
        return False


def python_environment() -> Dict[str, Any]:
    base = getattr(sys, "_base_executable", None) or sys.executable
    in_venv = os.path.abspath(base) != os.path.abspath(sys.executable)
    try:
        version = sys.version.split()[0]
    except Exception:
        version = str(sys.version_info[:3])
    tool = _tool()
    idx = _load_names()
    info = index_info()
    state = section_state()
    audit = _audit_environment()
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


# -------------------------------------------------------------------------- #
#  Per-utility dependency status
# -------------------------------------------------------------------------- #
def _external_status(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Report whether a non-Python (external) requirement is satisfiable."""
    name = str(entry.get("name") or "")
    required = bool(entry.get("required", True))
    lower = name.lower()
    if lower in ("ffmpeg", "ffprobe"):
        settings = (load_app_settings() or {})
        ffmpeg = settings.get("ffmpeg") or {}
        configured = bool(ffmpeg.get("path"))
        base_ok = bool(shutil.which("ffmpeg") or shutil.which("ffprobe"))
        return {
            "name": name,
            "type": str(entry.get("type") or "external"),
            "required": required,
            "satisfied": configured or base_ok,
            "note": "App FFmpeg setting or system PATH" if (configured or base_ok)
                    else "No FFmpeg installation found",
        }
    return {
        "name": name,
        "type": str(entry.get("type") or "external"),
        "required": required,
        "satisfied": None,
        "note": "Not checked",
    }


def parse_requirements_file(module_dir: str) -> List[str]:
    """Names declared in a utility's ``requirements.txt`` (may be empty)."""
    try:
        with open(os.path.join(module_dir, "requirements.txt"), "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    names: List[str] = []
    for line in lines:
        token = line.split("#", 1)[0].strip()
        if not token:
            continue
        raw = re.split(r"[<>=!~\s]", token, 1)[0].strip()
        if raw:
            names.append(normalize_name(raw))
    return names


def _compute_utility_dependencies(utilities: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Installed/missing/outdated status for every utility's requirements.

    ``utilities`` mirrors the bridge's ``self._utilities`` map: each value has
    ``manifest`` and ``dir`` keys.
    """
    installed = installed_distributions()
    result: List[Dict[str, Any]] = []
    for tool, entry in (utilities or {}).items():
        manifest = (entry or {}).get("manifest") or {}
        module_dir = (entry or {}).get("dir") or ""
        python_reqs = manifest.get("python_requirements")
        if not isinstance(python_reqs, list):
            python_reqs = parse_requirements_file(module_dir)
        additional = manifest.get("additional_requirements")
        if not isinstance(additional, list):
            additional = []

        requirements: List[Dict[str, Any]] = []
        for req in python_reqs:
            if not isinstance(req, str) or not req.strip():
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
    return result


def utility_dependencies(utilities: Dict[str, Dict[str, Any]],
                         force: bool = False) -> List[Dict[str, Any]]:
    """Cached wrapper around ``_compute_utility_dependencies``.

    The status snapshot is persisted so switching sections or reopening the
    category reuses the last fetch within the TTL instead of re-querying the
    PyPI metadata for every requirement (the rate-limit protection). Pass
    ``force=True`` right after an install/uninstall to recompute it.
    """
    sig = ",".join(sorted(((utilities or {}).keys())))
    key = CACHE_UTILS_PREFIX + sig
    if not force:
        cached = _cache_get(key, UTIL_CACHE_TTL)
        if isinstance(cached, list):
            return cached
    result = _compute_utility_dependencies(utilities)
    _cache_put(key, result, UTIL_CACHE_TTL)
    return result