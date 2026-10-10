import { useEffect, useState } from "react";

export function useSavedSettings(toolId, call, applyModel) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const saved = await call("get_settings", toolId);
      if (!mounted) return;
      const doc = saved && saved.ok !== false ? saved.settings : null;
      if (doc && typeof doc === "object" && Object.keys(doc).length) applyModel(doc);
      setLoaded(true);
    })();
    return () => {
      mounted = false;
    };
  }, [call, toolId, applyModel]);

  return { loaded };
}