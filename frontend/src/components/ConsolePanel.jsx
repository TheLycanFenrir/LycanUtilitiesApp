import { useCallback, useEffect, useRef, useState } from "react";

const PIN_THRESHOLD = 24;

export default function ConsolePanel({ status, tone, progress, logs, busy, jobId, copyLog, abort, pause, resume, paused }) {
  const logsRef = useRef(null);
  const [pinned, setPinned] = useState(true);

  useEffect(() => {
    const el = logsRef.current;
    if (!el || !pinned) return;
    el.scrollTop = el.scrollHeight;
  }, [logs, pinned]);

  const handleScroll = useCallback(() => {
    const el = logsRef.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD);
  }, []);

  const handleResumeScroll = useCallback(() => {
    const el = logsRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    setPinned(true);
  }, []);

  return (
    <aside className="console">
      <div className="console-head">
        <span className="console-title">Console</span>
        <span className="console-status">
          <span className={"status-dot " + tone} />
          <span className={status === "Idle" ? "status-dim" : ""}>{status}</span>
        </span>
      </div>
      <div className="progress-wrap">
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: progress + "%" }} />
        </div>
        <div className="progress-label">{progress}%</div>
      </div>
      <div className="log-bar">
        <span className="log-bar-title">Output Log</span>
        <button type="button" className="btn" onClick={copyLog}>Copy Log</button>
      </div>
      <div className="logs" ref={logsRef} onScroll={handleScroll}>
        {logs.map((log, i) => (
          <div key={i} className={"log-line " + log.level}>{log.message}</div>
        ))}
      </div>
      {!pinned && (
        <button type="button" className="log-follow" onClick={handleResumeScroll}>
          &#9660; Jump to bottom
        </button>
      )}
      <div className="console-actions">
        <button type="button" className="btn" onClick={copyLog}>Copy Log to Clipboard</button>
        {busy && jobId && (
          paused ? (
            <button type="button" className="btn accent" onClick={resume}>Resume</button>
          ) : (
            <button type="button" className="btn secondary" onClick={pause}>Pause</button>
          )
        )}
        <button type="button" className="btn danger" onClick={abort} disabled={!busy || !jobId}>
          Abort
        </button>
      </div>
    </aside>
  );
}