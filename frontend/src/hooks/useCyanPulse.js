import { useEffect } from "react";
import { registerCyanPulse, unregisterCyanPulse } from "../utils/color/cyanPulse.js";

export default function useCyanPulse(ref, kind) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    registerCyanPulse(el, kind);
    return () => unregisterCyanPulse(el);
  }, [ref, kind]);
}