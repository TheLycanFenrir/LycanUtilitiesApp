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
 */
export function usePersistentForm({ toolId, call, collect, enabled }) {
  const collectRef = useRef(collect);
  const enabledRef = useRef(enabled);
  const timerRef = useRef(null);
  const lastKeyRef = useRef(null);

  collectRef.current = collect;
  enabledRef.current = enabled;

  const persist = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (!enabledRef.current || !collectRef.current) return;
    call("save_settings", toolId, collectRef.current());
  }, [call, toolId]);

  useEffect(() => {
    if (!enabled) return;
    const key = JSON.stringify(collect());
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
      persist();
    };
  }, [persist]);
}