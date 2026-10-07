import { createElement } from "react";
import { buildElementProps, CONTAINER_DATA_ATTR } from "./elementProps.js";
import { renderUiChildren } from "./nodeRegistry.js";
import { isNodeVisible } from "../../utils/form/visibility.js";

/**
 * Container renderer for `section` nodes.
 *
 * A section with no declared areas (header/actions/footer) renders as a root
 * div with its children, mirroring the classic container layout. When a section
 * declares any of those areas the layout becomes explicit:
 *
 *   <div class="lyc-section ...">
 *     <div class="lyc-section-header">  (area: header)
 *     <div class="lyc-section-body">    (children)
 *     <div class="lyc-section-actions"> (area: actions)
 *     <div class="lyc-section-footer">  (area: footer)
 *
 * Areas accept a single node object or a list; they go through the shared
 * resolver like regular children.
 */
function wrapIfPresent(nodes) {
  if (nodes == null) return null;
  return Array.isArray(nodes) ? nodes : [nodes];
}

export default function SectionGenerator({ node, ctx }) {
  if (!node || typeof node !== "object") return null;
  if (!isNodeVisible(node, ctx?.snapshot)) return null;

  const props = buildElementProps(node);
  const rootId =
    typeof node.idName === "string"
      ? node.idName
      : typeof node.field_id === "string"
        ? node.field_id
        : undefined;
  props[CONTAINER_DATA_ATTR.section] = rootId || true;

  const header = wrapIfPresent(node.header);
  const actions = wrapIfPresent(node.actions);
  const footer = wrapIfPresent(node.footer);
  const hasAreas = header != null || actions != null || footer != null;

  if (!hasAreas) {
    const kids = renderUiChildren(node.children, ctx);
    return createElement("div", props, ...(kids || []));
  }

  const bodyKids = renderUiChildren(node.children, ctx);
  const areas = [];
  if (header != null) {
    const headerKids = renderUiChildren(header, ctx);
    areas.push(createElement("div", { className: "lyc-section-header", key: "header" }, headerKids));
  }
  areas.push(
    createElement("div", { className: "lyc-section-body", key: "body" }, ...(bodyKids || [])),
  );
  if (actions != null) {
    const actionKids = renderUiChildren(actions, ctx);
    areas.push(createElement("div", { className: "lyc-section-actions", key: "actions" }, actionKids));
  }
  if (footer != null) {
    const footerKids = renderUiChildren(footer, ctx);
    areas.push(createElement("div", { className: "lyc-section-footer", key: "footer" }, footerKids));
  }
  return createElement("div", props, ...areas);
}