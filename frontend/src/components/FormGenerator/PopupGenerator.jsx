import { useEffect, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { subscribePopup, isUiPopupOpen, closeUiPopup } from "./popupStore.js";
import { buildElementProps } from "./elementProps.js";
import { renderUiChildren } from "./nodeRegistry.js";
import { isNodeVisible } from "../../utils/form/visibility.js";

/**
 * Portal renderer for JSON-declared `popup` nodes.
 *
 * A popup is an identity-driven overlay (id = `idName`) that is only mounted
 * while the popupStore marks it open. It is opened/closed declaratively — from
 * a button elsewhere via an ``actionId`` such as ``open_popup`` with
 * ``actionParams: { popupId: <idName> }``, or from the backend through
 * ``send_ui_action``/``invoke_ui_action``. Rendering reuses the modal overlay
 * styles, renders into `document.body` via a portal, closes on Escape and on
 * overlay backdrop click, and mounts nothing server-side.
 *
 * Hooks run unconditionally (the popup is closed when there is nothing to show)
 * so the component stays compatible with the Rules of Hooks.
 */
export default function PopupGenerator({ node, ctx }) {
  const valid =
    Boolean(node && typeof node === "object") && isNodeVisible(node, ctx?.snapshot);
  const id = valid && typeof node.idName === "string" ? node.idName : "";

  const open = useSyncExternalStore(
    subscribePopup,
    () => isUiPopupOpen(id),
    () => false,
  );

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") closeUiPopup(id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, id]);

  if (!valid || !id || !open) return null;

  const props = buildElementProps(node);
  const className = ["modal-overlay", props.className].filter(Boolean).join(" ");
  props.className = className;
  props["data-popup"] = id || true;
  props["aria-modal"] = true;
  props.onClick = (event) => {
    if (event.target === event.currentTarget) closeUiPopup(id);
    event.stopPropagation();
  };

  return createPortal(
    <div {...props} role="dialog" aria-label={id}>
      <div className="modal">{renderUiChildren(node.children, ctx)}</div>
    </div>,
    document.body,
  );
}