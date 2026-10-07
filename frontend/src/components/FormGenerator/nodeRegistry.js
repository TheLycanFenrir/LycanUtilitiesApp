/**
 * Shared resolver, registry and tree helpers for the generator architecture.
 *
 * Every generator renders children through `resolveUiNode`, so any JSON node
 * can appear anywhere in the tree regardless of which generator created it
 * (popups may hold sections, sections may hold elements, fields and further
 * sections, elements may hold fields, ...). Node handling:
 *
 *   section         -> SectionGenerator
 *   popup           -> PopupGenerator
 *   form_component / form_field -> FieldGenerator's field delegation
 *   registered type -> custom renderer (registerNodeType)
 *   anything else   -> ElementGenerator (HTML-like elements)
 *
 * The import cycle with the generator components is intentional and safe:
 * components are referenced only inside function bodies (at render time), so
 * module evaluation order never matters.
 */

import { Fragment, createElement } from "react";
import { renderFieldRef } from "./fieldRef.jsx";
import { isNodeVisible } from "../../utils/form/visibility.js";
import SectionGenerator from "./SectionGenerator.jsx";
import PopupGenerator from "./PopupGenerator.jsx";
import ElementGenerator from "./ElementGenerator.jsx";

const nodeRegistry = new Map();

/**
 * Register a renderer for a custom node type.
 *
 * A renderer is `(node, ctx) => ReactElement` where ctx carries `snapshot`,
 * `call`, `onFieldBlur`, `moduleId` and `ui`. Container / form-reference types
 * take precedence over registered types, which are resolved before the HTML
 * element fallback (same ordering as the classic UI-tree system).
 */
export function registerNodeType(type, renderer) {
  if (typeof type === "string" && type && typeof renderer === "function") {
    nodeRegistry.set(type, renderer);
  }
  return nodeRegistry;
}

export function getNodeRenderer(type) {
  return nodeRegistry.get(type);
}

const CONTAINER_TYPES = new Set(["section"]);
const POPUP_TYPE = "popup";
const FIELD_REF_TYPES = new Set(["form_component", "form_field"]);

export function isUiContainerType(type) {
  return type === POPUP_TYPE || CONTAINER_TYPES.has(type);
}

/** Classify a node type for planning/rendering without running any code. */
export function resolveNodeKind(type) {
  if (type === POPUP_TYPE) return "popup";
  if (CONTAINER_TYPES.has(type)) return "section";
  if (FIELD_REF_TYPES.has(type)) return "field";
  if (nodeRegistry.has(type)) return "custom";
  return "element";
}

export function resolveUiNode(node, ctx) {
  if (!node || typeof node !== "object") return null;
  if (!isNodeVisible(node, ctx?.snapshot)) return null;
  const type = typeof node.type === "string" ? node.type : "";
  if (type === POPUP_TYPE || CONTAINER_TYPES.has(type)) {
    // Visibility of the container itself is enforced by the generators; the
    // node-level gate below already covers permanent hide/show_if/hide_if.
    const generator = type === POPUP_TYPE ? PopupGenerator : SectionGenerator;
    return createElement(generator, { node, ctx });
  }
  if (FIELD_REF_TYPES.has(type)) {
    return renderFieldRef(node, ctx);
  }
  const custom = nodeRegistry.get(type);
  if (custom) return custom(node, ctx);
  return createElement(ElementGenerator, { node, ctx });
}

/**
 * Render a list of child nodes through the shared resolver. Hidden children
 * (field_visibility / show_if / hide_if) are skipped; each rendered child gets
 * a stable Fragment key from its identity or position.
 */
export function renderUiChildren(children, ctx) {
  if (!Array.isArray(children) || children.length === 0) return null;
  const out = [];
  children.forEach((child, index) => {
    const element = resolveUiNode(child, ctx);
    if (element == null) return;
    const identity =
      child && typeof child === "object"
        ? child.idName || child.field_id || child.actionId || `node-${index}`
        : `node-${index}`;
    out.push(createElement(Fragment, { key: identity }, element));
  });
  return out.length ? out : null;
}

/**
 * Collect every field_id referenced by `form_component` / `form_field` nodes
 * anywhere inside the given UI trees (recursively, including header/actions/
 * footer areas). Used by the layout planner to keep container-owned fields from
 * also rendering as regular panels.
 */
export function collectUiFieldIds(uiNodes, out = new Set()) {
  for (const node of uiNodes || []) collectUiFieldIdsIn(node, out);
  return out;
}

/** Backwards-compatible alias of collectSectionFieldIds (legacy branding). */
export function collectCardFieldIds(uiNodes, out = new Set()) {
  return collectSectionFieldIds(uiNodes, out);
}

export function collectSectionFieldIds(uiNodes, out = new Set()) {
  return collectUiFieldIds(uiNodes, out);
}

function collectUiFieldIdsIn(node, out) {
  if (!node || typeof node !== "object") return;
  const type = node.type;
  if (type === "form_component" || type === "form_field") {
    if (typeof node.field_id === "string" && node.field_id) out.add(node.field_id);
    return;
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) collectUiFieldIdsIn(child, out);
  }
  for (const area of ["header", "actions", "footer"]) {
    const value = node[area];
    if (value == null) continue;
    const nodes = Array.isArray(value) ? value : [value];
    for (const child of nodes) collectUiFieldIdsIn(child, out);
  }
}

// Convenience used by the layout planner.
export { isNodeVisible } from "../../utils/form/visibility.js";