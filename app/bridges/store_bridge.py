"""Lycan Utilities Store: catalog fetch, download simulation, learn-more."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from core.debug_log import get_logger
from core.scanner import (
    UTILITIES_DIR as _UTILITIES_DIR,
    ICON_TARGET_DIR as _FRONTEND_ICON_DIR,
)
from app.settings import get_store_fetchres_path, get_store_icons_dir, load_app_settings

from .envelope import ResponseStatus

_logger = get_logger(__name__)

# The Lycan Utilities Store catalog is NOT hardcoded: it is sourced from the
# persisted fetch-result file (userdata/lycan_utilities_store/lycan_utilities_store_fetchres.json)
# which the online loader rebuilds from each utility folder's manifest,
# utility_description.json and synced icon. On offline reads the same file
# becomes the source of truth so the UI always has a real fetch artifact.
_STORE_FREE_MARKET = True


if TYPE_CHECKING:
    class BaseApiHost:
        _utilities: dict[str, dict]
else:
    BaseApiHost = object


class StoreBridgeMixin(BaseApiHost):
    """Lycan Utilities Store surface of the Api bridge."""

    def _store_installed_ids(self) -> set[str]:
        """Ids that are locally installed (valid utilities in utilities/)."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return set(self._utilities)

    @staticmethod
    def _store_load_json(path: str) -> Any | None:
        """Best-effort JSON read for store data (manifest/description/fetchres)."""
        _logger.debug_info("enter args=%s", ascii({"path": path}), tier=_logger.DEBUG_LOOP)
        if not path:
            _logger.debug_info("in if (not path)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            with open(path, "r", encoding="utf-8") as fh:
                _logger.debug_info("in with (open(path, \"r\", encoding=\"utf-8\") as fh)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return json.load(fh)
        except (OSError, ValueError) as e:
            _logger.debug_info("in except (OSError, ValueError)", tier=_logger.DEBUG_LOOP)
            _logger.error(f"Failed to read JSON from '{path}': {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None

    @staticmethod
    def _store_load_manifest(module_dir: str) -> dict:
        """Read a utility manifest.json for the store catalog (broken ones ignored)."""
        _logger.debug_info("enter args=%s", ascii({"module_dir": module_dir}), tier=_logger.DEBUG_LOOP)
        data = StoreBridgeMixin._store_load_json(os.path.join(module_dir, "manifest.json"))
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _store_load_description(folder: str) -> dict:
        """Read utilities/<folder>/utility_description.json for the store listing."""
        _logger.debug_info("enter args=%s", ascii({"folder": folder}), tier=_logger.DEBUG_LOOP)
        if not _UTILITIES_DIR or not folder:
            _logger.debug_info("in if (not _UTILITIES_DIR or not folder)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {}
        path = os.path.join(_UTILITIES_DIR, folder, "utility_description.json")
        data = StoreBridgeMixin._store_load_json(path)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return data if isinstance(data, dict) else {}

    def _store_sync_icons(self, items: list[dict]) -> None:
        """Mirror each utility's icon into the store's userdata icons folder.

        Icons are sourced from the scanner-synced frontend mirror
        (frontend/public/assets/.cache/icons) and copied into
        userdata/lycan_utilities_store/icons/<id><ext> so the store keeps its
        own persisted icon store (no heroicon names anywhere).
        """
        _logger.debug_info("enter args=%s", ascii({"items": items}), tier=_logger.DEBUG_LOOP)
        icons_dir = get_store_icons_dir()
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            os.makedirs(icons_dir, exist_ok=True)
        except OSError as e:
            _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_LOOP)
            _logger.warning(f"Failed to load store icon '{icons_dir}': {e}")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return

        for item in items:
            _logger.debug_info("in for (item in items)", tier=_logger.DEBUG_LOOP)
            if not isinstance(item, dict):
                _logger.debug_info("in if (not isinstance(item, dict))", tier=_logger.DEBUG_LOOP)
                continue

            item_id = item.get("id")
            icon = item.get("icon") or ""

            if not item_id or icon.startswith("assets/"):
                _logger.debug_info("in if (not item_id or icon.startswith(\"assets/\"))", tier=_logger.DEBUG_LOOP)
                continue

            src = os.path.join(_FRONTEND_ICON_DIR, os.path.basename(icon))
            if not os.path.isfile(src):
                _logger.debug_info("in if (not os.path.isfile(src))", tier=_logger.DEBUG_LOOP)
                continue

            ext = os.path.splitext(src)[1] or ".png"
            target = os.path.join(icons_dir, f"{item_id}{ext}")

            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                if not os.path.exists(target):
                    _logger.debug_info("in if (not os.path.exists(target))", tier=_logger.DEBUG_LOOP)
                    shutil.copy2(src, target)
            except OSError as e:
                _logger.debug_info("in except (OSError)", tier=_logger.DEBUG_LOOP)
                _logger.error(f"Failed to copy icon for item ID '{item_id}': {e}")
                continue

    def _store_fetch_items(self) -> list[dict]:
        """Build the store catalog from the real utilities directory.

        Each entry merges the utility's manifest.json with its
        ``utility_description.json`` (when present) and the scanner-synced
        icon path. This is the data that gets persisted as the fetch result.
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        items: list[dict] = []
        if not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR):
            _logger.debug_info("in if (not _UTILITIES_DIR or not os.path.isdir(_UTILITIES_DIR))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return items

        installed = self._store_installed_ids()

        for name in sorted(os.listdir(_UTILITIES_DIR)):
            # Ignore hidden folders, cache, or internal files
            _logger.debug_info("in for (name in sorted(os.listdir(_UTILITIES_DIR)))", tier=_logger.DEBUG_LOOP)
            if name.startswith((".", "_", "__")):
                _logger.debug_info("in if (name.startswith((\".\", \"_\", \"__\")))", tier=_logger.DEBUG_LOOP)
                continue

            module_dir = os.path.join(_UTILITIES_DIR, name)
            if not os.path.isdir(module_dir):
                _logger.debug_info("in if (not os.path.isdir(module_dir))", tier=_logger.DEBUG_LOOP)
                continue

            manifest = self._store_load_manifest(module_dir)
            description = self._store_load_description(name)

            # Get primary ID from manifest or folder name
            mid = str(manifest.get("id") or name)
            descriptor = self._utilities.get(mid) or {}

            items.append({
                "id": mid,
                "title": description.get("title") or manifest.get("title") or mid,
                "description": description.get("description") or manifest.get("description") or "",
                "icon": descriptor.get("icon_rel") or "",
                "version": str(manifest.get("version") or "1.0.0"),
                "credits": description.get("credits") or "Lycan Utilities",
                "size_estimate": description.get("size_estimate") or "Unknown",
                "installed": mid in installed,
            })

        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return items

    def _store_write_fetchres(self, payload: dict) -> None:
        """Persist the fetched catalog to userdata/lycan_utilities_store/."""
        _logger.debug_info("enter args=%s", ascii({"payload": payload}), tier=_logger.DEBUG_LOOP)
        target_path = str(get_store_fetchres_path())
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(get_store_fetchres_path(), "w", encoding="utf-8") as fh:
                _logger.debug_info("in with (open(get_store_fetchres_path(), \"w\", encoding=\"utf-8\") as fh)", tier=_logger.DEBUG_LOOP)
                json.dump(payload, fh, indent=2)
        except (OSError, TypeError) as e:
            _logger.debug_info("in except (OSError, TypeError)", tier=_logger.DEBUG_LOOP)
            _logger.warning(f"Failed to save fetchres store to '{target_path}': {e}")
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            # Persistence is best-effort; a failing disk never blocks the store UI.

    def _store_read_fetchres(self) -> dict:
        """Load the last fetched catalog snapshot from disk (may be {}})."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        target_path = str(get_store_fetchres_path())
        if not os.path.isfile(target_path):
            _logger.debug_info("in if (not os.path.isfile(target_path))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {}

        data = self._store_load_json(target_path)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return data if isinstance(data, dict) else {}

    def get_utilities_store(self) -> dict:
        """Return the Lycan Utilities Store catalog.

        * Online fetch (``general.allow_internet``): the catalog is rebuilt
          from utilities/ folders plus their utility_description.json files,
          icons are mirrored into userdata/lycan_utilities_store/icons/, and
          the result is persisted to ``lycan_utilities_store_fetchres.json``.
        * Offline: the last persisted fetch-result is used and filtered to
          locally installed utilities (no download).
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        general = load_app_settings().get("general") or {}
        internet = bool(general.get("allow_internet", False))
        installed = self._store_installed_ids()

        if internet:
            _logger.debug_info("in if (internet)", tier=_logger.DEBUG_FUNCTION)
            items = self._store_fetch_items()
            self._store_sync_icons(items)
            previous = self._store_read_fetchres()
            payload = {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "internet": True,
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "items": items,
                "actions": previous.get("actions") or [],
            }
            self._store_write_fetchres(payload)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return payload

        payload = self._store_read_fetchres()
        raw_items = payload.get("items") or []
        items = [entry for entry in raw_items if isinstance(entry, dict) and entry.get("id") in installed]
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "internet": False,
            "fetched_at": payload.get("fetched_at") or "",
            "items": items,
            "actions": payload.get("actions") or []
        }

    def store_download(self, item_id: str) -> dict:
        """Simulate downloading/updating a store utility.

        This is a demo store; the action is recorded in the persisted fetch
        result and reported back. Downloads require internet access.
        """
        _logger.debug_info("enter args=%s", ascii({"item_id": item_id}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(item_id, str) or not item_id:
            _logger.debug_info("in if (not isinstance(item_id, str) or not item_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.error("Missing or invalid item_id")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_id",
                "detail": "A store item id is required.",
            }

        general = (load_app_settings().get("general") or {})

        if not general.get("allow_internet", False):
            _logger.debug_info("in if (not general.get(\"allow_internet\", False))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("Internet disabled")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "internet_disabled",
                "detail": "Internet access is disabled in Settings > General.",
            }

        items = self._store_fetch_items()
        entry = next(
            (e for e in items if isinstance(e, dict) and e.get("id") == item_id),
            None
        )

        if not entry:
            _logger.debug_info("in if (not entry)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("Catalog not found")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "not_found",
                "detail": "That item is not in the store catalog.",
            }

        existing = self._store_read_fetchres()
        installed = self._store_installed_ids()
        is_update = item_id in installed

        actions = list(existing.get("actions") or [])
        actions.append({
            "item_id": item_id,
            "action": "update" if is_update else "download",
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        })

        if len(actions) > 50:
            _logger.debug_info("in if (len(actions) > 50)", tier=_logger.DEBUG_FUNCTION)
            actions = actions[-50:]

        existing["actions"] = actions
        self._store_write_fetchres(dict(existing))

        is_free = bool(globals().get("_STORE_FREE_MARKET", True))

        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "item_id": item_id,
            "action": "update" if is_update else "download",
            "free": is_free,
            "version": str(entry.get("version") or "Unknown Version"),
        }

    def store_learn_more(self, item_id: str) -> dict:
        """Return the full details card for a store item from real catalog data."""
        _logger.debug_info("enter args=%s", ascii({"item_id": item_id}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(item_id, str) or not item_id:
            _logger.debug_info("in if (not isinstance(item_id, str) or not item_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.error("Missing or invalid item_id")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_id",
                "detail": "A store item id is required.",
            }

        # Get list of items by safely
        items = self._store_fetch_items() or []

        # Search entries from item_id
        entry = next((e for e in items if isinstance(e, dict) and e.get("id") == item_id), None)

        if not entry:
            _logger.debug_info("in if (not entry)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("Learn more information is not found")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "not_found",
                "detail": "That item is not in the store catalog.",
            }

        is_free = bool(globals().get("_STORE_FREE_MARKET", False))

        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "title": entry.get("title") or "Untitled",
            "description": entry.get("description") or "No description provided.",
            "version": entry.get("version") or "Unknown Version",
            "free": is_free,
            "credits": entry.get("credits") or "No Credit Provided",
            "size_estimate": entry.get("size_estimate") or "Unknown Size",
        }
