/**
 * External open/close store for JSON-declared popups.
 *
 * Mirrors the project's external-store pattern (see formStore.js): React reads
 * the open set with useSyncExternalStore while the action layer mutates it, so
 * any declarative node or backend action can open/close a popup without the
 * generators reaching across each other.
 */

const listeners = new Set();
let openSet = new Set();

function emit() {
  const next = new Set(openSet);
  openSet = next;
  for (const fn of listeners) fn();
}

export function subscribePopup(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getPopupState() {
  return openSet;
}

export function isUiPopupOpen(id) {
  return typeof id === "string" && id.length > 0 && openSet.has(id);
}

export function openUiPopup(id) {
  if (typeof id !== "string" || !id) return false;
  if (openSet.has(id)) return true;
  openSet.add(id);
  emit();
  return true;
}

export function closeUiPopup(id) {
  if (typeof id !== "string" || !id) return false;
  if (!openSet.has(id)) return false;
  openSet.delete(id);
  emit();
  return true;
}

export function toggleUiPopup(id) {
  if (typeof id !== "string" || !id) return false;
  if (openSet.has(id)) {
    openSet.delete(id);
  } else {
    openSet.add(id);
  }
  emit();
  return true;
}

export function closeAllUiPopups() {
  if (openSet.size === 0) return false;
  openSet = new Set();
  emit();
  return true;
}