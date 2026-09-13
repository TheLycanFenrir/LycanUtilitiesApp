"""Fast utility scanner, utilities_cache.json compiler and SHA-256 auto-validation.

Design
------
* ``scan_and_cache`` walks ``utilities/`` once, validates each utility's
  ``manifest.json`` / ``form_schema.json``, hashes every runtime file with
  SHA-256, syncs each utility's ``assets/icons`` into the frontend icon base,
  and persists a compiled ``utilities_cache.json`` in the utilities root.
* On application startup ``load_utilities`` prefers the cache: it recomputes the
  SHA-256 digests of the manifest/schema/runtime files and compares them with
  the stored hashes. Matching entries boot instantly (Fast Boot); a changed
  utility is re-parsed, re-cached, and recorded in ``util_lists_cache-lock.json``.
* The utilities root deliberately holds only utility folders plus the two JSON
  caches, so listing it is a cheap way for the dashboard to stay responsive.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys

from datetime import datetime
from typing import Any, Dict, List, Optional

CACHE_VERSION = 1

_MOD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Standalone runs (`python core/scanner.py`) must resolve the top-level
# `core` package; when imported by main.py the project root is already on the
# path and this insert is a harmless no-op.
if _MOD_ROOT not in sys.path:
    sys.path.insert(0, _MOD_ROOT)

from core.schema import validate_manifest, validate_form_schema


def _resolve(*parts: str) -> str:
    return os.path.join(_MOD_ROOT, *parts)


UTILITIES_DIR = os.environ.get("LYCAN_UTILITIES_DIR") or _resolve("utilities")
CACHE_PATH = _resolve("utilities", "utilities_cache.json")
LOCK_PATH = _resolve("utilities", "util_lists_cache-lock.json")
ICON_TARGET_DIR = _resolve("frontend", "public", "assets", "icons")


def sha256_file(path: str) -> Optional[str]:
    """SHA-256 hex digest of a file, or None when unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _sync_icons(module_dir: str, icon_file: Optional[str]) -> Optional[str]:
    """Copy a utility's ``assets/icons`` into the frontend icon base.

    Returns the cache ``icon_rel`` (web-relative path) or None when the utility
    ships no icons. Every PNG under ``assets/icons`` is mirrored, so a utility
    may expose any number of icon variants.
    """
    chosen: Optional[str] = None
    icons_dir = os.path.join(module_dir, "assets", "icons")
    if os.path.isdir(icons_dir):
        try:
            os.makedirs(ICON_TARGET_DIR, exist_ok=True)
        except OSError:
            icons_dir = None
    if icons_dir and os.path.isdir(icons_dir):
        for fname in sorted(os.listdir(icons_dir)):
            src = os.path.join(icons_dir, fname)
            if not os.path.isfile(src):
                continue
            target = os.path.join(ICON_TARGET_DIR, fname)
            try:
                if not os.path.exists(target) or sha256_file(src) != sha256_file(target):
                    shutil.copy2(src, target)
            except OSError:
                continue
            if chosen is None and fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                chosen = "assets/icons/" + fname
    if chosen is None and icon_file and str(icon_file).startswith("assets/icons/"):
        if os.path.isfile(os.path.join(module_dir, str(icon_file))):
            chosen = "assets/icons/" + os.path.basename(str(icon_file))
    return chosen


def _file_hashes(module_dir: str, names: List[str]) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for name in names:
        digest = sha256_file(os.path.join(module_dir, name))
        if digest:
            hashes[name] = digest
    return hashes


def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def scan_utility(module_dir: str) -> Optional[Dict[str, Any]]:
    """Parse and validate one utility directory; None when invalid or absent."""
    manifest_path = os.path.join(module_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return None
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        return None
    errors = validate_manifest(manifest)
    if errors:
        print(f"[utility-scanner] invalid {manifest_path}: {errors}")
        return None

    mid = str(manifest["id"])
    schema_name = manifest.get("schema") or "form_schema.json"
    runtime_name = str(manifest.get("runtime") or "") or None
    schema_path = os.path.join(module_dir, schema_name)
    form_schema = None
    errors = []
    if os.path.isfile(schema_path):
        form_schema = _read_json(schema_path)
        errors = validate_form_schema(form_schema)
        if errors:
            print(f"[utility-scanner] invalid schema for '{mid}': {errors}")
            form_schema = None

    names = [schema_name]
    handler_names: List[str] = []
    handlers = manifest.get("handlers") or {}
    for key in ("python", "lua"):
        value = handlers.get(key)
        if isinstance(value, str) and value:
            handler_names.append(value)
    for candidate in [runtime_name] + handler_names:
        if candidate and candidate not in names:
            names.append(candidate)
    hashes = _file_hashes(module_dir, names)

    icon_rel = _sync_icons(module_dir, manifest.get("icon_file"))
    return {
        "manifest": manifest,
        "form_schema": form_schema,
        "hashes": hashes,
        "schema_path": schema_name,
        "runtime_path": runtime_name,
        "icon_rel": icon_rel,
        "runtime_ok": bool(runtime_name and os.path.isfile(os.path.join(module_dir, runtime_name))),
    }


def compile_cache() -> Dict[str, Any]:
    """Full scan + cache compile. Returns the cache document."""
    utilities: Dict[str, Any] = {}
    if not os.path.isdir(UTILITIES_DIR):
        print(f"[utility-scanner] utilities directory missing: {UTILITIES_DIR}")
    else:
        for name in sorted(os.listdir(UTILITIES_DIR)):
            module_dir = os.path.join(UTILITIES_DIR, name)
            if not os.path.isdir(module_dir):
                continue
            entry = scan_utility(module_dir)
            if entry:
                mid = str(entry["manifest"]["id"])
                entry["dir"] = os.path.normpath(module_dir)
                utilities[mid] = entry
    return {
        "version": CACHE_VERSION,
        "compiled_at": datetime.now().isoformat(timespec="seconds"),
        "utilities": utilities,
    }


def _write_json(path: str, payload: Any) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except OSError:
        print(f"[utility-scanner] could not write {path}")


def _entry_changed(module_dir: str, cached: Dict[str, Any], computed: Dict[str, Any]) -> bool:
    for name, digest in computed.get("hashes", {}).items():
        if cached.get("hashes", {}).get(name) != digest:
            return True
    return False


def load_utilities(force_scan: bool = False) -> Dict[str, Any]:
    """Load utility listings, preferring the cache and validating SHA-256.

    Returns {"utilities": {id: entry}, "from_cache": bool, "recompiled": [ids]}.
    """
    cached: Dict[str, Any] = {}
    if not force_scan and os.path.isfile(CACHE_PATH):
        doc = _read_json(CACHE_PATH)
        if isinstance(doc, dict) and doc.get("version") == CACHE_VERSION:
            cached = doc.get("utilities") or {}

    recompiled: List[str] = []
    utilities: Dict[str, Any] = {}

    if os.path.isdir(UTILITIES_DIR):
        for name in sorted(os.listdir(UTILITIES_DIR)):
            module_dir = os.path.join(UTILITIES_DIR, name)
            if not os.path.isdir(module_dir):
                continue
            entry = scan_utility(module_dir)
            if not entry:
                continue
            mid = str(entry["manifest"]["id"])
            prior = cached.get(mid)
            if prior is not None and not _entry_changed(module_dir, prior, entry):
                # Fast Boot: nothing changed; reuse cached payloads.
                utilities[mid] = {
                    "manifest": prior.get("manifest") or entry["manifest"],
                    "form_schema": prior.get("form_schema"),
                    "hashes": prior.get("hashes") or entry["hashes"],
                    "schema_path": entry["schema_path"],
                    "runtime_path": entry["runtime_path"],
                    "icon_rel": prior.get("icon_rel") or entry["icon_rel"],
                    "runtime_ok": entry["runtime_ok"],
                    "dir": os.path.normpath(module_dir),
                }
                continue
            recompiled.append(mid)
            entry["dir"] = os.path.normpath(module_dir)
            utilities[mid] = entry
    else:
        print(f"[utility-scanner] utilities directory missing: {UTILITIES_DIR}")

    from_cache = not force_scan and not recompiled
    if recompiled or force_scan:
        doc = compile_cache()
        _write_json(CACHE_PATH, doc)
        _write_json(LOCK_PATH, {
            "updated_at": doc["compiled_at"],
            "recompiled": recompiled,
            "reason": "sha256_mismatch" if recompiled else "manual_scan",
        })
    return {"utilities": utilities, "from_cache": from_cache, "recompiled": recompiled}


def descriptor(entry: Dict[str, Any]) -> Dict[str, Any]:
    """React-facing utility descriptor (dashboard card + schema payload)."""
    manifest = entry.get("manifest") or {}
    return {
        "id": manifest.get("id"),
        "title": manifest.get("title") or manifest.get("id"),
        "description": manifest.get("description") or "",
        "icon": manifest.get("icon") or "🧰",
        "icon_file": entry.get("icon_rel") or manifest.get("icon_file"),
        "badge": manifest.get("badge") or "",
        "tags": manifest.get("tags") or [],
        "version": manifest.get("version") or "",
        "form_schema": entry.get("form_schema"),
        "has_runtime": bool(entry.get("runtime_ok")),
        "runtime_file": entry.get("runtime_path"),
        "coming_soon": not entry.get("runtime_ok"),
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(load_utilities(force_scan=True), default=str))