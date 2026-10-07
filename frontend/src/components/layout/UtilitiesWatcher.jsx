import { useEffect, useRef } from "react";
import { usePyWebView } from "../../hooks/usePyWebView.js";
import { useToast } from "../../contexts/ToastContext.jsx";

const POLL_MS = 4000;

/**
 * Watches utilities/ for external changes.
 *
 * - New utility folder or a `.py` edit  -> undismissable "restart" toast
 *   (sticky: it stays until the app is restarted; "Restart Now" relaunches).
 * - json / lua / asset updates          -> hard refresh (backend already
 *   rescanned, so reloading picks up the new data).
 */
export default function UtilitiesWatcher() {
  const { call } = usePyWebView();
  const { showToast } = useToast();
  const pendingRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      let res;
      try {
        res = await call("utilities_changes");
      } catch {
        return;
      }
      if (cancelled || !res || !res.action) return;
      if (res.action === "restart") {
        if (pendingRef.current === "restart") return;
        pendingRef.current = "restart";
        showToast(
          "The utilities folder changed (new utility or .py update). Restart the app to apply it.",
          "warn",
          4600,
          { kind: "restart-app", label: "Restart Now" },
          true,
        );
      } else if (res.action === "refresh") {
        window.location.reload();
      }
    };
    tick();
    const handle = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [call, showToast]);

  return null;
}