import { createElement as h } from "react";

export function fieldRow(label, control, extra) {
  return h(
    "div",
    { className: "field" },
    h("label", null, label),
    control,
    extra,
  );
}