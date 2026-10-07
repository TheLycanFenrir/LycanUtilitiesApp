/**
 * Delegation for `form_component` / `form_field` nodes.
 *
 * Like the classic card system, fields are never re-implemented here: the node
 * references an existing store entry by `field_id` and the render is handed to
 * FormField. Presentation tweaks (className / label_name) are applied on a
 * render-time copy of the schema — the shared store schema is never mutated.
 */

import FormField from "./FormField.jsx";
import { isFieldVisible } from "../../utils/form/visibility.js";

export function renderFieldRef(node, ctx) {
  const fieldId = typeof node.field_id === "string" ? node.field_id : "";
  if (!fieldId) return null;
  const entry = ctx?.snapshot?.fields?.[fieldId];
  if (!isFieldVisible(entry, ctx?.snapshot)) return null;

  const schema = { ...entry.schema };
  const childClasses = typeof node.className === "string" ? node.className.trim() : "";
  if (childClasses) {
    schema.classes = [schema.classes, childClasses].filter(Boolean).join(" ");
  }
  if (typeof node.label_name === "string" && node.label_name.trim()) {
    schema.label_name = node.label_name.trim();
  }
  return (
    <FormField
      entry={{ ...entry, schema }}
      call={ctx?.call}
      onFieldBlur={ctx?.onFieldBlur}
    />
  );
}