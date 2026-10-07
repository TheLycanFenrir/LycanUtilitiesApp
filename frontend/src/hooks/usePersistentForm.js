import { useCallback, useEffect, useRef } from "react";

const SAVE_DELAY = 350;

/**
 * Persist a tool's form fields on every change (debounced) and flush on
 * unmount / beforeunload / pagehide / visibility hidden, so the values are
 * retained even if the user leaves the tab or the app quits unexpectedly.
 *
 * `collect` must be a function returning the current form model; it is
 * reassigned on every render so the latest field values are always used.
 * `enabled` should flip to true only after saved settings were applied on
 * mount, preventing defaults from overwriting stored settings.
 *
 * Unmount safety: the shared form store may already be cleared by the time
 * the provider's cleanup runs (React unmounts a parent's effects before a
 * child inside the same subtree), so the latest collected snapshot is cached
 * and reused when the live store comes back empty. An empty payload is never
 * written back, otherwise leaving the form would wipe the stored settings
 * and reopening it would fallback to defaults.
 */
export function usePersistentForm({ toolId, call, collect, enabled }) {
  const collectRef = useRef(collect);
  const enabledRef = useRef(enabled);
  const timerRef = useRef(null);
  const lastKeyRef = useRef(null);
  const lastValueRef = useRef(null);

  // Sync the latest props into refs outside the render phase so the debounced
  // and unmount flushes always read the most current collect/enabled values.
  useEffect(() => {
    collectRef.current = collect;
    enabledRef.current = enabled;
  });

  const persist = useCallback((skipCollect = false) => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (!enabledRef.current) return;
    let data;
    if (skipCollect || !collectRef.current) {
      // During cleanup, use the cached value since form store may be cleared
      data = lastValueRef.current;
    } else {
      const fresh = collectRef.current();
      // Update the cached snapshot with the latest collected value
      if (fresh && typeof fresh === "object") {
        lastValueRef.current = fresh;
      }
      data = fresh;
    }
    if (!data || typeof data !== "object" || Object.keys(data).length === 0) return;
    call("save_settings", toolId, data);
  }, [call, toolId]);

  // Force immediate save without debounce, used before unmount
  const flush = useCallback(() => {
    if (!enabledRef.current || !collectRef.current) return;
    const fresh = collectRef.current();
    if (fresh && typeof fresh === "object") {
      lastValueRef.current = fresh;
    }
    if (lastValueRef.current && typeof lastValueRef.current === "object" && Object.keys(lastValueRef.current).length) {
      call("save_settings", toolId, lastValueRef.current);
    }
  }, [call, toolId]);

  useEffect(() => {
    if (!enabled) return;
    const snapshot = collect();
    if (snapshot && typeof snapshot === "object") lastValueRef.current = snapshot;
    const key = JSON.stringify(snapshot);
    if (key === lastKeyRef.current) return;
    lastKeyRef.current = key;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(persist, SAVE_DELAY);
  });

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") persist();
    };
    window.addEventListener("beforeunload", persist);
    window.addEventListener("pagehide", persist);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      window.removeEventListener("beforeunload", persist);
      window.removeEventListener("pagehide", persist);
      document.removeEventListener("visibilitychange", onVisibility);
      // Skip collect during cleanup since FormStateProvider clears the form store first
      persist(true);
    };
  }, [persist]);

  return { flush };
}