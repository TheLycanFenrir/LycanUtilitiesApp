import { useEffect } from "react";
import { registerBluePulse, unregisterBluePulse } from "../utils/color/cyanPulse.js";

export default function useBluePulse(ref, kind) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    registerBluePulse(el, kind);
    return () => unregisterBluePulse(el);
  }, [ref, kind]);
}