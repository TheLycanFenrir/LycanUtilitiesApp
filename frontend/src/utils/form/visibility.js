/**
 * Conditional visibility expression evaluator for form fields.
 *
 * Expression grammar (JSON-friendly):
 *   { field, equals | not_equals }             exact (string-coerced) match
 *   { field, in | not_in: [..] }               list membership
 *   { all: [expr, ..] } / { any: [expr, ..] }  logical and / or
 *   { not: expr }                              negation
 * Any unknown/malformed node is treated as "visible".
 */
export function valueOf(snapshot, fieldId) {
  const entry = snapshot.fields[fieldId];
  return entry ? entry.value : undefined;
}

function coalesce(a, b) {
  const pa = String(a == null ? "" : a);
  const pb = String(b == null ? "" : b);
  return pa === pb;
}

export function evalVisibility(expr, snapshot) {
  if (expr == null) return true;
  if (Array.isArray(expr.all)) return expr.all.every((e) => evalVisibility(e, snapshot));
  if (Array.isArray(expr.any)) return expr.any.some((e) => evalVisibility(e, snapshot));
  if ("not" in expr) return !evalVisibility(expr.not, snapshot);
  if (typeof expr.field === "string") {
    const got = valueOf(snapshot, expr.field);
    if ("equals" in expr) return coalesce(got, expr.equals);
    if ("not_equals" in expr) return !coalesce(got, expr.not_equals);
    if (Array.isArray(expr.in)) return expr.in.some((v) => coalesce(got, v));
    if (Array.isArray(expr.not_in)) return !expr.not_in.some((v) => coalesce(got, v));
  }
  return true;
}

/**
 * Whether a live store entry (field) should be rendered right now.
 * Mirrors the classic filter used by FormGenerator: explicit hide via
 * `field_visibility`, plus satisfied `show_if` / unsatisfied `hide_if`.
 */
export function isFieldVisible(entry, snapshot) {
  if (!entry || !entry.schema) return false;
  if (entry.visible === false) return false;
  const schema = entry.schema;
  if (schema.show_if != null && !evalVisibility(schema.show_if, snapshot)) return false;
  if (schema.hide_if != null && evalVisibility(schema.hide_if, snapshot)) return false;
  return true;
}

/**
 * Visibility gate for arbitrary declarative UI nodes (container nodes and any
 * recursive child element). Accepts the same `field_visibility` / `show_if` /
 * `hide_if` keys the field system uses so UI trees stay consistent with it.
 */
export function isNodeVisible(node, snapshot) {
  if (!node || typeof node !== "object") return false;
  if (node.field_visibility === false) return false;
  if (node.show_if != null && !evalVisibility(node.show_if, snapshot)) return false;
  if (node.hide_if != null && evalVisibility(node.hide_if, snapshot)) return false;
  return true;
}