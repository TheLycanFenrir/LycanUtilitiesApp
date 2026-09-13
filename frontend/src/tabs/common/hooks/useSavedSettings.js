import { useEffect, useState } from "react";

export function useSavedSettings(toolId, call, applyModel) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const saved = await call("get_settings", toolId);
      if (!mounted) return;
      if (saved && typeof saved === "object" && Object.keys(saved).length) applyModel(saved);
      setLoaded(true);
    })();
    return () => {
      mounted = false;
    };
  }, [call, toolId, applyModel]);

  return { loaded };
}