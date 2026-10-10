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

Package facade: the public API is re-exported here so callers keep using
``from app.python_libraries import ...`` while the implementation lives in the
domain modules next to this file.
"""

from .audit import python_audit
from .cache import section_state
from .constants import (
    AUDIT_TIMEOUT,
    CACHE_INDEX_KEY,
    CACHE_SEARCH_PREFIX,
    CACHE_STATE_KEY,
    CACHE_UTILS_PREFIX,
    CACHE_VULN_KEY,
    CACHE_VULN_REQ_PREFIX,
    HYDRATE_TIMEOUT,
    INDEX_MAX_AGE_SECONDS,
    META_WORKERS,
    NAME_TTL_SECONDS,
    PIP_TIMEOUT,
    SEARCH_CACHE_TTL,
    UTIL_CACHE_TTL,
    VULN_CACHE_TTL,
    VULN_REQ_CACHE_TTL,
)
from .helpers import internet_enabled, local_only_scope, normalize_name
from .index import index_info, pypi_search, refresh_pypi_index
from .installed import (
    core_packages,
    installed_distributions,
    installed_version,
    is_core_package,
    is_installed,
)
from .metadata import latest_version
from .pipops import pip_available, pypi_install, pypi_uninstall, python_environment
from .progress import pypi_progress
from .requirements import parse_requirements_file, utility_dependencies

__all__ = [
    "AUDIT_TIMEOUT",
    "CACHE_INDEX_KEY",
    "CACHE_SEARCH_PREFIX",
    "CACHE_STATE_KEY",
    "CACHE_UTILS_PREFIX",
    "CACHE_VULN_KEY",
    "CACHE_VULN_REQ_PREFIX",
    "HYDRATE_TIMEOUT",
    "INDEX_MAX_AGE_SECONDS",
    "META_WORKERS",
    "NAME_TTL_SECONDS",
    "PIP_TIMEOUT",
    "SEARCH_CACHE_TTL",
    "UTIL_CACHE_TTL",
    "VULN_CACHE_TTL",
    "VULN_REQ_CACHE_TTL",
    "core_packages",
    "index_info",
    "installed_distributions",
    "installed_version",
    "internet_enabled",
    "is_core_package",
    "is_installed",
    "latest_version",
    "local_only_scope",
    "normalize_name",
    "parse_requirements_file",
    "pip_available",
    "pypi_install",
    "pypi_progress",
    "pypi_search",
    "pypi_uninstall",
    "python_audit",
    "python_environment",
    "refresh_pypi_index",
    "section_state",
    "utility_dependencies",
]
