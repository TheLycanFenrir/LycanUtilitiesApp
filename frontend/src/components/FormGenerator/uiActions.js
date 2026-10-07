/**
 * UI action layer bridging the generator tree and the Lua/Python backend.
 *
 * Declarative nodes never talk to the runtime directly: an element carrying an
 * `actionId` (plus `actionParams`) dispatches through the action layer, which
 * resolves a registered local handler OR forwards to the backend via the
 * pywebview bridge (`call("ui_action", moduleId, actionId, params)`). The
 * backend/runtime may also push actions back through
 * ``window.__lycanForm.invoke_ui_action`` (see InteropContext.send_ui_action),
 * which routes into the same registry so one handler can serve both directions.
 *
 * React generators         ->  UI definition / action layer  ->  bridge/call
 *                                                               |-> Lua Runtime
 * backend send_ui_action() -> window.__lycanForm.invoke_ui_action -> registry
 */

import { openUiPopup, closeUiPopup, toggleUiPopup } from "./popupStore.js";

const actionHandlers = new Map();

/** Register a local action handler: `(params, ui) => result | Promise`. */
export function registerUiAction(name, handler) {
  if (typeof name === "string" && name && typeof handler === "function") {
    actionHandlers.set(name, handler);
  }
  return actionHandlers;
}

/** Remove a previously registered handler (returns true when removed). */
export function unregisterUiAction(name, handler) {
  if (typeof name !== "string" || !name) return false;
  const current = actionHandlers.get(name);
  if (handler == null) {
    return actionHandlers.delete(name);
  }
  if (current === handler) {
    return actionHandlers.delete(name);
  }
  return false;
}

export function getUiActionHandler(name) {
  return typeof name === "string" ? actionHandlers.get(name) : undefined;
}

export function hasUiAction(name) {
  return typeof name === "string" && actionHandlers.has(name);
}

function errorResult(error) {
  console.error("[uiActions] action failed:", error);
  return { ok: false, reason: error && error.message ? String(error.message) : String(error) };
}

/**
 * Send an action to the backend action hook. Resolves to the bridge response
 * (an object) or a graceful failure result when no bridge is mounted.
 */
export async function sendUiAction(call, actionId, params, moduleId) {
  if (typeof call !== "function") {
    return { ok: false, reason: "no_bridge" };
  }
  try {
    return await call("ui_action", moduleId, actionId, params || {});
  } catch (error) {
    return errorResult(error);
  }
}

/**
 * Dispatch a UI action: a registered local handler wins; otherwise the action
 * is forwarded to the backend through the bridge. Returns a promise.
 */
export async function dispatchUiAction(actionId, params, ui) {
  const handler = getUiActionHandler(actionId);
  if (handler) {
    try {
      return await handler(params || {}, ui || {});
    } catch (error) {
      return errorResult(error);
    }
  }
  return sendUiAction(ui?.call, actionId, params, ui?.moduleId);
}

/**
 * Inbound endpoint for backend `send_ui_action`. Only local (registered)
 * handlers are invoked; unmapped actions are reported instead of exploding,
 * so a Lua/Python hook can never crash the UI with an unknown action id.
 */
export async function invokeUiAction(actionId, params, ui) {
  const handler = getUiActionHandler(actionId);
  if (!handler) {
    console.warn(`[uiActions] no local handler for backend action '${actionId}'.`);
    return { ok: false, reason: "no_local_handler" };
  }
  try {
    return await handler(params || {}, ui || {});
  } catch (error) {
    return errorResult(error);
  }
}

// Backend UI payloads always carry `popupId` explicitly (never guessed from
// component internals), so opening/closing is explicit in the JSON definition.
const popupIdParam = (params) => (params && typeof params.popupId === "string" ? params.popupId : "");

registerUiAction("open_popup", async (params) => {
  const id = popupIdParam(params);
  return id ? { ok: openUiPopup(id), popup: id } : { ok: false, reason: "missing_popup_id" };
});

registerUiAction("close_popup", async (params) => {
  const id = popupIdParam(params);
  return id ? { ok: closeUiPopup(id), popup: id } : { ok: false, reason: "missing_popup_id" };
});

registerUiAction("toggle_popup", async (params) => {
  const id = popupIdParam(params);
  return id ? { ok: toggleUiPopup(id), popup: id } : { ok: false, reason: "missing_popup_id" };
});