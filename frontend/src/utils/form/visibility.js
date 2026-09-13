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