/**
 * Pure helper that maps arbitrary HTML parameters from a field schema onto the
 * control element rendered by FormField.
 *
 * The field-level schema validator in core/schema.py already accepts any key,
 * so this is the single place that decides what may reach the DOM: engine keys
 * the form already consumes are excluded, everything else (strings, numbers,
 * booleans, data-* / aria-*) is forwarded as a React DOM attribute.
 */

// Field schema keys consumed by the form engine. Never forwarded.
const RESERVED_KEYS = new Set([
  "field_id",
  "type",
  "label_name",
  "part",
  "description",
  "classes",
  "tooltip",
  "mode",
  "file_types",
  "default_input",
  "placeholder",
  "min",
  "max",
  "step",
  "force_clamp",
  "allow_decimal",
  "allow_negative",
  "pre_defined_dropdown",
  "max_length",
  "min_length",
  "real_time_validation",
  "enable_validation",
  "field_visibility",
  "show_if",
  "hide_if",
  "regex_validation",
  "regex_sanitization",
  "value",
  "id",
  "checked",
]);

// Author-friendly lowercase names -> the React DOM prop React actually reads.
// Plain names (e.g. `readonly`, `tabindex`) are valid HTML but invisible to
// React, so they must be rewritten to their camelCase React counterparts.
export const HTML_ATTR_MAP = {
  autocomplete: "autoComplete",
  autofocus: "autoFocus",
  autocapitalize: "autoCapitalize",
  autocorrect: "autoCorrect",
  spellcheck: "spellCheck",
  readonly: "readOnly",
  tabindex: "tabIndex",
  maxlength: "maxLength",
  minlength: "minLength",
  inputmode: "inputMode",
  enterkeyhint: "enterKeyHint",
  pattern: "pattern",
  size: "size",
  name: "name",
  list: "list",
  form: "form",
  dir: "dir",
  lang: "lang",
  title: "title",
  alt: "alt",
  role: "role",
  required: "required",
  disabled: "disabled",
  multiple: "multiple",
  accept: "accept",
};

/**
 * Build the DOM props to forward to a FormField control from its schema.
 *
 * Keys held by the engine are dropped; remaining primitive values are mapped
 * through HTML_ATTR_MAP (or passed through as-is), event handlers are never
 * forwarded from JSON, and data-* / aria-* keys always pass unchanged.
 */
export function buildFieldHtmlProps(schema) {
  const props = {};
  if (!schema || typeof schema !== "object") return props;
  for (const key of Object.keys(schema)) {
    if (RESERVED_KEYS.has(key)) continue;
    if (key.startsWith("on")) continue;
    const value = schema[key];
    if (
      typeof value !== "string" &&
      typeof value !== "number" &&
      typeof value !== "boolean"
    ) {
      continue;
    }
    if (key.startsWith("data-") || key.startsWith("aria-")) {
      props[key] = value;
      continue;
    }
    props[HTML_ATTR_MAP[key] || key] = value;
  }
  return props;
}