import { useEffect, useRef } from "react";

// Re-attach a tool tab to the most recent job the backend still holds for that
// tool. Exiting and re-entering a tool tab unmounts it and wipes its console
// state (progress percent, output log, job id). The backend keeps the job plus
// its replayable event buffer for a grace window after it finishes, so on
// remount we rediscover it via get_tool_job() and attach() to replay the live
// progress and output log. Yields to an explicit focusJobId and to queue mode.
//
// StrictMode-safe: dev mode double-invokes mount effects (setup -> cleanup ->
// setup), so the probe is guarded with a monotonic token instead of a one-shot
// flag that would be tripped by the aborted first invocation. seenRef records
// job ids already consumed this mount, so a finished job is never re-attached
// (that would loop: attach -> replay done -> idle -> probe again).
export function useRecentJobAttach({ call, toolId, focusJobId, queueRunning, attach, busy, jobId }) {
  const probeTokenRef = useRef(0);
  const seenRef = useRef(new Set());

  useEffect(() => {
    if (jobId) seenRef.current.add(jobId);
  }, [jobId]);

  useEffect(() => {
    if (focusJobId) return; // the tab's own effect handles the explicit attach
    if (queueRunning && queueRunning.tool === toolId) return; // queue mode attaches
    if (busy || jobId) return; // already attached, or a fresh run in this mount
    const token = ++probeTokenRef.current;
    let cancelled = false;
    (async () => {
      try {
        const res = await call("get_tool_job", toolId);
        if (cancelled || probeTokenRef.current !== token) return;
        if (!res || !res.job_id) return;
        if (seenRef.current.has(res.job_id)) return;
        seenRef.current.add(res.job_id);
        attach(res.job_id);
      } catch {
        // Transient bridge error; a later dep change retries.
      }
    })();
    return () => { cancelled = true; };
  }, [call, toolId, focusJobId, queueRunning, attach, busy, jobId]);
}