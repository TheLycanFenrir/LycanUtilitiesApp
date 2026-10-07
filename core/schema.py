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

# UI tree node vocabulary: HTML-like containers rendered by ElementGenerator,
# references to existing form fields (delegated to FormField), nested container
# roots (section / popup), and declarative action hooks.
HTML_ELEMENT_TYPES = {
    "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "button", "label", "section", "header", "footer", "main", "aside", "nav",
    "ul", "ol", "li", "small", "strong", "em", "b", "i", "u", "code", "pre",
    "hr", "br", "img", "a",
}
FORM_REF_TYPES = {"form_component", "form_field"}
CONTAINER_ROOT_TYPES = {"section", "popup"}
UI_NODE_TYPES = HTML_ELEMENT_TYPES | FORM_REF_TYPES | CONTAINER_ROOT_TYPES

# Properties every UI-tree node may carry. HTML attributes that collide with
# the discriminator live under alternate names (e.g. `typeAttribute` -> type).
_UI_STRING_KEYS = (
    "idName", "className", "innerText", "title", "typeAttribute",
    "href", "target", "rel", "placeholder", "role", "alt", "src",
    "ariaLabel", "aria-label", "field_id", "label_name",
)
_UI_BOOL_KEYS = ("disabled", "field_visibility")
_UI_RESERVED_KEYS = (
    "type", "children", "styleCSS", "show_if", "hide_if",
    "actionId", "actionParams", "header", "actions", "footer",
    *_UI_STRING_KEYS, *_UI_BOOL_KEYS,
)
# Action ids may be used by Lua backends too, so allow a broad, safe charset.
ACTION_ID_RE = re.compile(r"^[a-zA-Z0-9_.:-]+$")


def _validate_container_node(node: Any, errors: List[str], tag: str, refs: List[str]) -> None:
    """Validate one UI container (section/popup) or tree child node."""
    if not isinstance(node, dict):
        errors.append(f"{tag}: expected an object")
        return
    ctype = node.get("type")
    if ctype not in UI_NODE_TYPES:
        errors.append(f"{tag}: unsupported UI element type '{ctype}'")
        return

    for key in node:
        if key in _UI_RESERVED_KEYS:
            continue
        if key.startswith("data-") or key.startswith("aria-"):
            continue
        errors.append(f"{tag}: unsupported property '{key}'")

    for key in _UI_STRING_KEYS:
        if key in node and not isinstance(node[key], str):
            errors.append(f"{tag}: '{key}' must be a string")
            continue
        if key == "typeAttribute" and key in node:
            if node[key] not in {"button", "submit", "reset"}:
                errors.append(f"{tag}: 'typeAttribute' must be button, submit or reset")
        if key in ("idName", "field_id") and key in node:
            value = node[key]
            if not isinstance(value, str) or not FIELD_ID_RE.match(value):
                errors.append(f"{tag}: '{key}' must be a lowercase identifier")

    if "actionId" in node:
        value = node["actionId"]
        if not isinstance(value, str) or not ACTION_ID_RE.match(value):
            errors.append(f"{tag}: 'actionId' must be an identifier string")
    if "actionParams" in node and not isinstance(node["actionParams"], dict):
        errors.append(f"{tag}: 'actionParams' must be an object")

    for key in _UI_BOOL_KEYS:
        if key in node and not isinstance(node[key], bool):
            errors.append(f"{tag}: '{key}' must be a boolean")

    if "styleCSS" in node:
        style = node["styleCSS"]
        if not isinstance(style, dict) or not all(
            isinstance(k, str) and isinstance(v, (str, int, float)) for k, v in style.items()
        ):
            errors.append(f"{tag}: 'styleCSS' must be an object of string/number values")

    if ctype in FORM_REF_TYPES:
        fid = node.get("field_id")
        if not isinstance(fid, str) or not FIELD_ID_RE.match(fid):
            errors.append(f"{tag}: invalid or missing 'field_id'")
        else:
            refs.append(fid)
        return

    children = node.get("children")
    if children is not None:
        if not isinstance(children, list):
            errors.append(f"{tag}: 'children' must be a list")
            return
        for index, child in enumerate(children):
            _validate_container_node(child, errors, f"{tag}.children[{index}]", refs)

    # Logical section areas (header / actions / footer) are single nodes or
    # lists of nodes, validated the same way as children.
    if ctype in CONTAINER_ROOT_TYPES:
        for area in ("header", "actions", "footer"):
            value = node.get(area)
            if value is None:
                continue
            nodes = value if isinstance(value, list) else [value]
            for index, child in enumerate(nodes):
                _validate_container_node(child, errors, f"{tag}.{area}[{index}]", refs)


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

    if isinstance(raw, dict) and "description" in raw and not isinstance(raw["description"], str):
        errors.append("form_schema 'description' must be a string")

    seen: set[str] = set()
    node_refs: List[str] = []
    for idx, field in enumerate(fields):
        tag = f"field[{idx}]"
        if not isinstance(field, dict):
            errors.append(f"{tag}: expected an object")
            continue
        ftype = field.get("type")
        if ftype in CONTAINER_ROOT_TYPES:
            # Container roots (section / popup) are layout nodes, not
            # data fields: they may use `idName` for identity and never join
            # the field registry.
            _validate_container_node(field, errors, tag, node_refs)
            continue
        fid = field.get("field_id")
        if not isinstance(fid, str) or not FIELD_ID_RE.match(fid):
            errors.append(f"{tag}: invalid or missing 'field_id'")
            continue
        if fid in seen:
            errors.append(f"{tag}: duplicate field_id '{fid}'")
        seen.add(fid)

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

        for key in ("part", "description"):
            if key in field and not isinstance(field[key], str):
                errors.append(f"{tag} '{fid}': '{key}' must be a string")

        if "regex_validation" in field:
            try:
                re.compile(str(field["regex_validation"]))
            except re.error as exc:
                errors.append(f"{tag} '{fid}': bad regex_validation: {exc}")

    for ref in node_refs:
        if ref not in seen:
            errors.append(f"UI tree references undefined field_id '{ref}'")
    return errors