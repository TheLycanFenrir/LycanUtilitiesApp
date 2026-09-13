import { useCallback } from "react";
import { sanitizePath } from "../utils/paths/pathSanitizer.js";

const URL_SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i;

function isPathLike(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  if (URL_SCHEME.test(value)) return false;
  return value.includes("/") || value.includes("\\") || /  +/.test(value);
}

function sanitizeArg(value) {
  if (Array.isArray(value)) return value.map(sanitizeArg);
  return isPathLike(value) ? sanitizePath(value) : value;
}

function getBridge() {
  if (typeof window === "undefined") return null;
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

export function usePyWebView() {
  const call = useCallback(async (method, ...args) => {
    const bridge = getBridge();
    if (!bridge) {
      console.warn(
        "[usePyWebView] window.pywebview.api is not initialized yet; cannot call " + method + ".",
      );
      return undefined;
    }
    if (typeof bridge[method] !== "function") {
      console.warn("[usePyWebView] api." + method + " is not exposed by the bridge.");
      return undefined;
    }
    const sanitized = args.map(sanitizeArg);
    try {
      return await bridge[method](...sanitized);
    } catch (error) {
      console.error("[usePyWebView] api." + method + " threw:", error);
      return undefined;
    }
  }, []);

  return {
    call,
    api: getBridge(),
    isAvailable: Boolean(getBridge()),
  };
}