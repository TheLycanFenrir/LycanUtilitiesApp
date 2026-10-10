import { useCallback, useEffect, useState } from "react";

export function usePathHistory(call, sourceKey, outputKey) {
  const [sourceHistory, setSourceHistory] = useState([]);
  const [outputHistory, setOutputHistory] = useState([]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const [srcRes, outRes] = await Promise.all([
        call("get_history", "paths", sourceKey),
        call("get_history", "paths", outputKey),
      ]);
      if (!mounted) return;
      const src = srcRes && srcRes.ok !== false ? srcRes.data : null;
      const out = outRes && outRes.ok !== false ? outRes.data : null;
      if (Array.isArray(src)) setSourceHistory(src);
      if (Array.isArray(out)) setOutputHistory(out);
    })();
    return () => {
      mounted = false;
    };
  }, [call, sourceKey, outputKey]);

  const addHistory = useCallback((key, value) => {
    if (!value) return;
    call("add_history", "paths", key, value);
  }, [call]);

  return { sourceHistory, outputHistory, addHistory };
}