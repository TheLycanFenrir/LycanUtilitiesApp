"""Timeouts, TTLs and cache keys shared by the Python Libraries modules."""

from __future__ import annotations

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
