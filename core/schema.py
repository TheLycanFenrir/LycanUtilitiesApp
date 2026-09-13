"""Lightweight JSON schema validators for module manifests and form schemas.

No external validation dependency: modules describe their own contract and the
scanner only needs a cheap, safe gate before a module is served to the UI.
"""

from __future__ import annotations

import re

from typing import Any, List

SUPPORTED_FIELD_TYPES = {"text", "number", "dropdown", "date", "color", "checkbox", "file"}
FIELD_ID_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

LIST_TYPES = {"dropdown", "file"}


def validate_manifest(manifest: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    mid = manifest.get("id")
    if not isinstance(mid, str) or not FIELD_ID_RE.match(mid):
        errors.append("manifest 'id' must be a non-empty lowercase identifier")
    if not isinstance(manifest.get("title"), str) or not manifest.get("title").strip():
        errors.append("manifest 'title' must be a non-empty string")
    for key in ("icon_file", "icon", "badge", "runtime", "schema"):
        value = manifest.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"manifest '{key}' must be a string when present")
    return errors


def validate_form_schema(raw: Any) -> List[str]:
    errors: List[str] = []
    if isinstance(raw, list):
        fields = raw
    elif isinstance(raw, dict) and isinstance(raw.get("fields"), list):
        fields = raw["fields"]
    else:
        return ["form_schema must be a field list or an object with a 'fields' list"]

    seen: set[str] = set()
    for idx, field in enumerate(fields):
        tag = f"field[{idx}]"
        if not isinstance(field, dict):
            errors.append(f"{tag}: expected an object")
            continue
        fid = field.get("field_id")
        if not isinstance(fid, str) or not FIELD_ID_RE.match(fid):
            errors.append(f"{tag}: invalid or missing 'field_id'")
            continue
        if fid in seen:
            errors.append(f"{tag}: duplicate field_id '{fid}'")
        seen.add(fid)

        ftype = field.get("type")
        if ftype not in SUPPORTED_FIELD_TYPES:
            errors.append(f"{tag} '{fid}': unsupported type '{ftype}'")
            continue

        if ftype == "number":
            for key in ("min", "max", "step"):
                value = field.get(key)
                if value is not None and not isinstance(value, (int, float)):
                    errors.append(f"{tag} '{fid}': '{key}' must be numeric")
            for key in ("force_clamp", "allow_decimal", "allow_negative"):
                if key in field and not isinstance(field[key], bool):
                    errors.append(f"{tag} '{fid}': '{key}' must be a boolean")

        if ftype == "dropdown":
            opts = field.get("pre_defined_dropdown")
            if opts is not None:
                if not isinstance(opts, list) or not all(
                    isinstance(o, (list, tuple)) and len(o) == 2 for o in opts
                ):
                    errors.append(f"{tag} '{fid}': 'pre_defined_dropdown' must be [val, label] pairs")

        if "default_input" in field and isinstance(field["default_input"], str):
            if isinstance(field.get("regex_sanitization"), dict):
                pat = field["regex_sanitization"].get("pattern")
                if pat is not None:
                    try:
                        re.compile(str(pat))
                    except re.error as exc:
                        errors.append(f"{tag} '{fid}': bad regex_sanitization.pattern: {exc}")

        for key in ("enable_validation", "real_time_validation", "field_visibility"):
            if key in field and not isinstance(field[key], bool):
                errors.append(f"{tag} '{fid}': '{key}' must be a boolean")

        if "regex_validation" in field:
            try:
                re.compile(str(field["regex_validation"]))
            except re.error as exc:
                errors.append(f"{tag} '{fid}': bad regex_validation: {exc}")
    return errors