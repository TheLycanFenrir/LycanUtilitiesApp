/**
 * Shared render context threaded through the generator tree.
 *
 * ctx = { snapshot, call, onFieldBlur, moduleId, ui }
 *
 *   snapshot    live form-store snapshot (reads only; mutations go through
 *               the store APIs, never through this object)
 *   call        pywebview bridge call(method, ...args) — may be undefined
 *               when the native bridge is not mounted (e.g. SSR)
 *   onFieldBlur blur hook the field layer reports to (persistence flush)
 *   moduleId    active tool id (identity for backend-routed UI actions)
 *   ui          { call, moduleId } adapter handed to the action layer
 */
export function makeUiContext({ snapshot, call, onFieldBlur, moduleId }) {
  return {
    snapshot,
    call,
    onFieldBlur,
    moduleId,
    ui: { call, moduleId },
  };
}