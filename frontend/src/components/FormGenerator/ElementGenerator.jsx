import { createElement } from "react";
import { HTML_TAGS, buildElementProps } from "./elementProps.js";
import { renderUiChildren } from "./nodeRegistry.js";
import { dispatchUiAction } from "./uiActions.js";
import { isNodeVisible } from "../../utils/form/visibility.js";

/**
 * Generic renderer for JSON-driven HTML-like elements (div, p, span, h1,
 * button, ...). Any node that is not a container, a field reference or a
 * registered custom type ends up here.
 *
 * An element may carry an `actionId` (plus optional `actionParams`): it then
 * becomes an actionable node whose onClick dispatches through the shared action
 * layer (`dispatchUiAction`) — the local handler registry first, then the
 * backend `ui_action` bridge for runtime/Lua hooks.
 */
export default function ElementGenerator({ node, ctx }) {
  if (!node || typeof node !== "object") return null;
  if (!isNodeVisible(node, ctx?.snapshot)) return null;

  const tag = typeof node.type === "string" && HTML_TAGS.has(node.type) ? node.type : "div";
  const props = buildElementProps(node);
  if (tag === "button" && !("type" in props)) props.type = "button";

  if (typeof node.actionId === "string" && node.actionId) {
    props.onClick = (event) => {
      event.preventDefault();
      const params = { ...(node.actionParams || {}) };
      dispatchUiAction(node.actionId, params, ctx?.ui);
    };
  }

  const kids = [];
  if (typeof node.innerText === "string" && node.innerText !== "") kids.push(node.innerText);
  const childNodes = renderUiChildren(node.children, ctx);
  if (childNodes) kids.push(...childNodes);
  return createElement(tag, props, ...kids);
}