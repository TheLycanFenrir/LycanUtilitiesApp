import { useCallback, useEffect, useRef, useState } from "react";
import { showToast } from "../utils/platform/toast.js";

export function useJobConsole({ call }) {
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState("Idle");
  const [tone, setTone] = useState("blue");
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [confirmBox, setConfirmBox] = useState(null);
  const [flash, setFlash] = useState(null);
  const [paused, setPaused] = useState(false);

  const pollerRef = useRef(null);
  const pollLockRef = useRef(false);
  const confirmSeenRef = useRef(new Set());
  const flashTimer = useRef(null);
  const cursorRef = useRef(0);

  const showFlash = useCallback((message, kind = "info") => {
    setFlash({ message, kind });
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(null), 5000);
  }, []);

  const clearFlash = useCallback(() => {
    if (flashTimer.current) clearTimeout(flashTimer.current);
    setFlash(null);
  }, []);

  useEffect(() => {
    return () => {
      if (pollerRef.current) clearInterval(pollerRef.current);
      if (flashTimer.current) clearTimeout(flashTimer.current);
    };
  }, []);

  const appendLog = useCallback((level, message) => {
    setLogs((prev) => {
      const next = prev.concat({ level, message });
      if (next.length > 900) next.splice(0, next.length - 900);
      return next;
    });
  }, []);

  const stopPoll = useCallback(() => {
    if (pollerRef.current) {
      clearInterval(pollerRef.current);
      pollerRef.current = null;
    }
  }, []);

  const drainEvents = useCallback(async (events) => {
    for (const ev of events) {
      switch (ev.kind) {
        case "log":
          appendLog(ev.level, ev.message);
          if (ev.level === "warn") showFlash(ev.message, "warn");
          else if (ev.level === "error") showFlash(ev.message, "error");
          break;
        case "status":
          setStatus(ev.text);
          setTone(ev.tone || "blue");
          if (ev.text === "Paused") setPaused(true);
          else if (ev.text === "Working...") setPaused(false);
          break;
        case "progress":
          setProgress(Math.max(0, Math.min(100, Math.round(ev.percent || 0))));
          break;
        case "confirm":
          // Non-blocking: never hold the poll lock while waiting for an answer
          // (an answered confirm can be replayed to a late-attaching surface,
          // and blocking would freeze the console). Show the prompt instead;
          // whichever surface answers first resolves it.
          if (!confirmSeenRef.current.has(ev.token)) {
            confirmSeenRef.current.add(ev.token);
            setConfirmBox({
              token: ev.token,
              title: ev.title || "Confirmation",
              message: ev.message || "",
              yes: ev.yes || "Yes",
              no: ev.no || "No",
            });
          }
          break;
        case "done":
          stopPoll();
          setBusy(false);
          setJobId(null);
          setPaused(false);
          setConfirmBox(null);
          if (ev.ok) {
            setStatus("Finished");
            setTone("green");
            setProgress(100);
            showFlash(ev.message || "Complete", "good");
          } else if (ev.error) {
            setStatus("Finished with errors");
            setTone("red");
            showFlash(ev.error || ev.message || "Job failed", "error");
            if (/ffmpeg/i.test((ev.message || "") + " " + (ev.error || ""))) {
              showToast(
                "FFmpeg was not detected. Set it up in Settings \u2192 FFmpeg to run this tool.",
                "error",
                9000,
                { label: "Open FFmpeg Settings", kind: "open-settings" },
              );
            }
          } else {
            setStatus("Cancelled");
            setTone("red");
            showFlash(ev.message || "Cancelled", "warn");
          }
          break;
        default:
          break;
      }
    }
  }, [appendLog, call, showFlash, stopPoll]);

  const pollJob = useCallback(async (jid) => {
    if (pollLockRef.current) return;
    pollLockRef.current = true;
    try {
      const data = await call("poll", jid, cursorRef.current);
      if (data && typeof data.cursor === "number") cursorRef.current = data.cursor;
      if (data && Array.isArray(data.events) && data.events.length) {
        await drainEvents(data.events);
      } else if (data && data.done) {
        // The job no longer exists (already finished or removed). Drop the
        // attached/tracked state so the console does not stay stuck on busy.
        stopPoll();
        setBusy(false);
        setJobId(null);
        setPaused(false);
        setStatus("Idle");
        setTone("blue");
        appendLog("warn", "Job is no longer active.");
      }
    } catch (err) {
      appendLog("warn", "Poll error: " + err);
    } finally {
      pollLockRef.current = false;
    }
  }, [appendLog, call, drainEvents, stopPoll]);

  const runJob = useCallback(async (toolId, params) => {
    if (busy) return false;
    setBusy(true);
    setJobId(null);
    setProgress(0);
    setStatus("Running");
    setTone("blue");
    setLogs([]);
    confirmSeenRef.current.clear();
    try {
      await call("save_settings", toolId, params);
    } catch {
      setBusy(false);
      return false;
    }
    const res = await call("start_job", toolId, params);
    if (!res || !res.job_id) {
      setBusy(false);
      setStatus("Idle");
      setTone("blue");
      showFlash("Job could not be started", "error");
      return false;
    }
    setJobId(res.job_id);
    cursorRef.current = 0;
    pollerRef.current = setInterval(() => pollJob(res.job_id), 200);
    return true;
  }, [busy, call, pollJob, showFlash]);

  const abort = useCallback(async () => {
    if (!busy || !jobId) return;
    setBusy(false);
    setStatus("Cancelled");
    setTone("red");
    setPaused(false);
    appendLog("warn", "Process aborted by user");
    showFlash("Process aborted by user", "warn");
    try {
      await call("abort_job", jobId);
    } catch (err) {
      appendLog("warn", "Abort error: " + err);
    }
  }, [appendLog, busy, call, jobId, showFlash]);

  const pause = useCallback(async () => {
    if (!busy || !jobId || paused) return;
    try {
      const res = await call("pause_job", jobId);
      if (res && res.ok) {
        setPaused(true);
        setStatus("Paused");
        setTone("warn");
        appendLog("warn", "Process paused by user");
        showFlash("Process paused. Click Resume to continue.", "warn");
      }
    } catch (err) {
      appendLog("warn", "Pause error: " + err);
    }
  }, [appendLog, busy, call, jobId, paused, showFlash]);

  const resume = useCallback(async () => {
    if (!busy || !jobId || !paused) return;
    try {
      const res = await call("resume_job", jobId);
      if (res && res.ok) {
        setPaused(false);
        setStatus("Resuming...");
        setTone("blue");
        appendLog("info", "Process resumed.");
      }
    } catch (err) {
      appendLog("warn", "Resume error: " + err);
    }
  }, [appendLog, busy, call, jobId, paused]);

  const attach = useCallback(async (jid, opts) => {
    if (!jid) return false;
    stopPoll();
    setBusy(true);
    setJobId(jid);
    cursorRef.current = 0;
    setProgress(0);
    setStatus("Running");
    setTone("blue");
    setPaused(!!(opts && opts.paused));
    setLogs([]);
    setConfirmBox(null);
    confirmSeenRef.current.clear();
    pollerRef.current = setInterval(() => pollJob(jid), 200);
    return true;
  }, [pollJob, stopPoll]);

  const copyLog = useCallback(() => {
    const text = logs.map((l) => l.message).join("\n");
    if (!text) {
      showFlash("No log output to copy yet.", "warn");
      return;
    }
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(
        () => showFlash("Log copied to clipboard.", "good"),
        () => showFlash("Could not copy the log.", "error"),
      );
    }
  }, [logs, showFlash]);

  const answerConfirm = useCallback(async (accepted) => {
    if (!confirmBox) return;
    const { token } = confirmBox;
    setConfirmBox(null);
    try {
      await call("resolve_confirm", token, accepted);
    } catch (err) {
      appendLog("warn", "Confirm error: " + err);
    }
  }, [appendLog, call, confirmBox]);

  return {
    busy,
    jobId,
    status,
    tone,
    progress,
    logs,
    confirmBox,
    flash,
    paused,
    showFlash,
    clearFlash,
    runJob,
    abort,
    pause,
    resume,
    attach,
    copyLog,
    answerConfirm,
  };
}