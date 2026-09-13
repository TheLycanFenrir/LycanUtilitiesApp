"""Update checking against the GitHub releases feed.

The live GitHub API is attempted first.  While the release repository is still
being wired up (or the machine is offline) the check falls back to a bundled
test release, so the in-app update experience can be exercised without a
published release.  Swap ``_TEST_RELEASE`` for the real feed once one exists.
"""

from __future__ import annotations

import json
import urllib.request

from app.info import VERSION
from utils.settings import load_app_settings

_REPO_SLUG = "TheLycanFenrir/LycanUtilitiesApp"
_RELEASES_URL = f"https://github.com/{_REPO_SLUG}/releases/latest"
_RELEASE_API_URL = f"https://api.github.com/repos/{_REPO_SLUG}/releases/latest"
_CONNECTIVITY_URL = "https://api.github.com"

# Bundled test data: reported as the latest release so the update popup and
# changelog rendering can be verified before a real release is published.
_TEST_RELEASE = {
    "latest": "1.4.0",
    "url": _RELEASES_URL,
    "changelog": [
        {"title": "Update checker", "body": "Check for new releases from the app menu, complete with a scrollable changelog preview."},
        {"title": "Refresh commands", "body": "Added Refresh and Hard Refresh to the app menu for quick reloads."},
        {"title": "Network controls", "body": "New options to allow internet access and opt into automatic update checks."},
        {"title": "Dashboard polish", "body": "Last Used sorting updates live and your selected sort is remembered."},
        {"title": "Fixes & stability", "body": "Assorted under-the-hood fixes for a smoother experience."},
    ],
}


def _version_tuple(value):
    """Turn a dotted version string into a comparable tuple of ints."""
    parts = []
    for chunk in str(value or "").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _internet_available(timeout=5.0):
    """Best-effort connectivity probe with a short timeout."""
    try:
        urllib.request.urlopen(_CONNECTIVITY_URL, timeout=timeout).close()
        return True
    except Exception:
        return False


def _fetch_release():
    """Fetch and normalise the latest GitHub release for the frontend."""
    request = urllib.request.Request(
        _RELEASE_API_URL,
        headers={
            "User-Agent": "LycanUtilities",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        data = json.loads(response.read().decode("utf-8"))
    tag = str(data.get("tag_name") or data.get("name") or "").lstrip("vV")
    body = str(data.get("body") or "").strip()
    changelog = [
        {"title": line.lstrip("#-* ").strip(), "body": ""}
        for line in body.splitlines()
        if line.strip()
    ]
    return {
        "latest": tag,
        "url": str(data.get("html_url") or _RELEASES_URL),
        "changelog": changelog,
    }


def check_for_updates():
    """Report whether a newer release is available.

    Returns ``reason`` = ``internet_disabled`` when the user has blocked
    internet access in settings, or ``no_internet`` when the connectivity
    probe fails.  Otherwise ``update_available`` compares the running version
    against the latest release (falling back to the bundled test release).
    """
    general = (load_app_settings() or {}).get("general", {}) or {}
    if not general.get("allow_internet", False):
        return {"ok": False, "reason": "internet_disabled"}
    if not _internet_available():
        return {"ok": False, "reason": "no_internet"}
    try:
        release = _fetch_release()
    except Exception:
        release = dict(_TEST_RELEASE)
    latest = release.get("latest") or _TEST_RELEASE["latest"]
    return {
        "ok": True,
        "current": VERSION,
        "latest": latest,
        "url": release.get("url") or _RELEASES_URL,
        "changelog": release.get("changelog") or _TEST_RELEASE["changelog"],
        "update_available": _version_tuple(latest) > _version_tuple(VERSION),
    }
