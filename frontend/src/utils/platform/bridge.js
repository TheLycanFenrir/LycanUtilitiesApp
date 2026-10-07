import { showToast } from "./toast.js";

function hasBridge() {
  return Boolean(window.pywebview && window.pywebview.api);
}

export async function openExternalLink(call, url) {
  if (!url) return;
  if (hasBridge()) {
    const res = await call("open_external_link", url);
    if (res && res.ok) return;
    if (res && res.reason === "invalid_url") {
      showToast("Could not open the external link.", "error");
      return;
    }
  }
  if (!hasBridge() && typeof window.open === "function") {
    window.open(url, "_blank");
    return;
  }
  showToast("Could not open the external link.", "error");
}

export async function openDevTools(call) {
  if (hasBridge()) {
    const res = await call("open_devtools");
    if (res && res.ok) return;
  }
  showToast("Console Info is only available in the desktop build.", "warn");
}

export async function quitApp(call) {
  if (hasBridge()) {
    const res = await call("quit_app");
    if (res && res.ok) return;
  }
  if (window.pywebview && window.pywebview.window && typeof window.pywebview.window.destroy === "function") {
    try {
      window.pywebview.window.destroy();
      return;
    } catch {
      // window already destroyed; fall through to the desktop-only hint
    }
  }
  showToast("Quit App is only available in the desktop build.", "warn");
}

export function reloadApp() {
  if (typeof window !== "undefined" && window.location) {
    window.location.reload();
  }
}

export function hardRefreshApp() {
  if (typeof window === "undefined" || !window.location) return;
  // Equivalent of a hard reload (Ctrl + F5): bypass caches by navigating
  // to a cache-busted copy of the current URL.
  const base = window.location.href.split("?")[0];
  window.location.replace(base + (base.includes("?") ? "&" : "?") + "_cb=" + Date.now());
}

export async function restartApp(call) {
  if (hasBridge()) {
    const res = await call("restart_app");
    if (res && res.ok) return;
  }
  showToast("Restart App is only available in the desktop build.", "warn");
}

export async function openUtilitiesFolder(call) {
  if (hasBridge()) {
    const res = await call("open_utilities_folder");
    if (res && res.ok) return;
  }
  showToast("Open Utilities Folder is only available in the desktop build.", "warn");
}