import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "lycan.ui.zoom";
const ZOOM_MIN = 25;
const ZOOM_MAX = 500;
const ZOOM_BASE = 100;
const ZOOM_STEPS = [25, 33, 50, 67, 75, 80, 90, 100, 110, 125, 150, 175, 200, 250, 300, 400, 500];

const ZoomCtx = createContext(null);

function readStored() {
  try {
    const n = parseInt(window.localStorage.getItem(STORAGE_KEY), 10);
    if (!Number.isNaN(n)) return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, n));
  } catch (e) {
  }
  return ZOOM_BASE;
}

export function ZoomProvider({ children }) {
  const [zoom, setZoom] = useState(readStored);
  const [popup, setPopup] = useState(null);

  useEffect(() => {
    document.documentElement.style.setProperty("--app-scale", String(zoom / 100));
    try {
      window.localStorage.setItem(STORAGE_KEY, String(zoom));
    } catch (e) {
    }
  }, [zoom]);

  const applyZoom = useCallback((value) => {
    const next = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.round(Number(value) || ZOOM_BASE)));
    setZoom(next);
  }, []);

  const zoomIn = useCallback(() => {
    setZoom((prev) => {
      for (const level of ZOOM_STEPS) if (level > prev) return level;
      return ZOOM_MAX;
    });
  }, []);

  const zoomOut = useCallback(() => {
    setZoom((prev) => {
      let next = ZOOM_MIN;
      for (const level of ZOOM_STEPS) if (level < prev) next = level;
      return next;
    });
  }, []);

  const resetZoom = useCallback(() => setZoom(ZOOM_BASE), []);

  const openZoomPopup = useCallback((anchor) => {
    if (!anchor) return;
    const width = 260;
    let left = anchor.right - width;
    if (left < 8) left = 8;
    let top = anchor.bottom + 8;
    if (top + 160 > window.innerHeight - 8 && anchor.top - 8 > 8) top = anchor.top - 8;
    setPopup({ left: Math.round(left), top: Math.round(top) });
  }, []);

  const closeZoomPopup = useCallback(() => setPopup(null), []);

  const value = useMemo(
    () => ({ zoom, popup, applyZoom, zoomIn, zoomOut, resetZoom, openZoomPopup, closeZoomPopup }),
    [zoom, popup, applyZoom, zoomIn, zoomOut, resetZoom, openZoomPopup, closeZoomPopup],
  );
  return <ZoomCtx.Provider value={value}>{children}</ZoomCtx.Provider>;
}

export function useZoom() {
  const ctx = useContext(ZoomCtx);
  if (!ctx) throw new Error("useZoom must be used within ZoomProvider");
  return ctx;
}