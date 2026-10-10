import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../common/SvgIcon.jsx";
import EmojiText from "../common/EmojiText.jsx";
import { svgBody } from "../../utils/icons/heroiconPaths.js";
import { toolIconFile } from "../../utils/paths/paths.js";
import wolfHead from "../../assets/icons/wolf-head.svg?raw";

const STATE_LABELS = {
  empty: "Worker",
  idle: "Pending",
  running: "Working",
  success: "Finished",
  failed: "Failed",
  aborted: "Aborted",
};

const STATE_TONES = {
  empty: "blue",
  idle: "blue",
  running: "blue",
  success: "green",
  failed: "red",
  aborted: "orange",
};

const OUTCOME_TONES = {
  success: "green",
  failed: "red",
  aborted: "orange",
};

function WolfIcon() {
  return (
    <svg viewBox="0 0 512 512" className="svg-icon wolf" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: svgBody(wolfHead) }} />
  );
}

export default function WorkerDropdown({ call, onFocusTool, onEditJob }) {
  const [open, setOpen] = useState(false);
  const [queue, setQueue] = useState(null);
  const [dragIdx, setDragIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [nameDraft, setNameDraft] = useState("");
  const skipRenameRef = useRef(false);
  const wrapRef = useRef(null);
  const popupRef = useRef(null);
  const pollRef = useRef(null);
  const [popupH, setPopupH] = useState(null);
  const [notice, setNotice] = useState(null);
  const [confirmBox, setConfirmBox] = useState(null);
  const [jobLogs, setJobLogs] = useState([]);
  const [logPinned, setLogPinned] = useState(true);
  const [logExpanded, setLogExpanded] = useState(false);
  const noticeTimer = useRef(null);
  const queueRef = useRef(null);
  const eventPollRef = useRef(null);
  const eventPollLockRef = useRef(false);
  const confirmSeenRef = useRef(new Set());
  const logsJobIdRef = useRef(null);
  const lastCursorRef = useRef(0);
  const logScrollRef = useRef(null);
  const H_MIN = 220;

  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);

  // Keep the running job's Output Log scrolled to the newest line while pinned.
  useEffect(() => {
    const el = logScrollRef.current;
    if (el && logPinned) el.scrollTop = el.scrollHeight;
  }, [jobLogs, logPinned]);

  useEffect(() => () => {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
  }, []);

  const showNotice = useCallback((msg) => {
    setNotice(msg || null);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    if (msg) noticeTimer.current = setTimeout(() => setNotice(null), 4000);
  }, []);

  const handleLogScroll = useCallback(() => {
    const el = logScrollRef.current;
    if (!el) return;
    setLogPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
  }, []);

  const copyJobLog = useCallback(async () => {
    const text = jobLogs.map((l) => l.message).join("\n");
    if (!text) return;
    if (navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
        showNotice("Log copied to clipboard.");
      } catch {
        showNotice("Could not copy the log.");
      }
    }
  }, [jobLogs, showNotice]);

  const startResize = (e) => {
    e.preventDefault();
    const startH = popupRef.current ? popupRef.current.offsetHeight : H_MIN;
    const startY = e.clientY;
    const onMove = (ev) => {
      setPopupH(Math.max(H_MIN, Math.min(startH + (ev.clientY - startY), window.innerHeight - 60)));
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const fetchQueue = useCallback(async () => {
    try {
      const data = await call("get_queue");
      if (data) setQueue(data);
    } catch {
      // Ignore transient poll errors; the next tick retries.
    }
  }, [call]);

  const refresh = useCallback(async () => {
    try {
      await fetchQueue();
    } catch {
      // best effort
    }
  }, [fetchQueue]);

  const answerConfirm = useCallback((accepted) => {
    if (!confirmBox) return;
    const token = confirmBox.token;
    setConfirmBox(null);
    call("resolve_confirm", token, accepted);
  }, [call, confirmBox]);

  // Drain the current queue job's event stream so backend confirmations are
  // answered here (get_queue alone cannot see them; an unanswered confirm used
  // to hang the job at 0% and wedge the whole queue).
  const pollCurrentJob = useCallback(async () => {
    if (eventPollLockRef.current) return;
    const jid = queueRef.current && queueRef.current.current && queueRef.current.current.job_id;
    if (!jid) return;
    if (jid !== logsJobIdRef.current) {
      logsJobIdRef.current = jid;
      setJobLogs([]);
      setLogPinned(true);
      lastCursorRef.current = 0;
    }
    eventPollLockRef.current = true;
    try {
      const data = await call("poll", jid, lastCursorRef.current);
      if (data && typeof data.cursor === "number") lastCursorRef.current = data.cursor;
      const events = data && Array.isArray(data.events) ? data.events : [];
      for (const ev of events) {
        if (ev.kind === "log") {
          setJobLogs((prev) => {
            const next = prev.concat({ level: ev.level || "info", message: ev.message || "" });
            if (next.length > 600) next.splice(0, next.length - 600);
            return next;
          });
        } else if (ev.kind === "confirm") {
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
        } else if (ev.kind === "done") {
          refresh();
        }
      }
    } catch {
      // Transient poll errors: the next tick retries.
    } finally {
      eventPollLockRef.current = false;
    }
  }, [call, refresh]);

  useEffect(() => {
    if (!open) return;
    const initTimer = setTimeout(() => fetchQueue(), 0);
    pollRef.current = setInterval(fetchQueue, 1000);
    eventPollRef.current = setInterval(pollCurrentJob, 300);
    // Close on a mousedown captured OUTSIDE the wrap. mousedown fires before
    // any React state update, so it can't be fooled by a click whose target
    // gets replaced mid-dispatch (the rename flow swaps the label for an
    // input). The toggle button keeps working because it is inside the wrap.
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(initTimer);
      if (pollRef.current) clearInterval(pollRef.current);
      if (eventPollRef.current) clearInterval(eventPollRef.current);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, fetchQueue, pollCurrentJob]);

  const actJob = async (method, jobId) => {
    let res;
    try {
      res = await call(method, jobId);
    } catch (e) {
      showNotice(e && e.message ? e.message : "Action failed");
    }
    refresh();
    if (typeof res === "object" && res) {
      const note = res.code || (res.ok ? "" : res.detail);
      if (note) showNotice(note);
    } else if (res === undefined) {
      showNotice(method + " is unavailable in the bridge");
    }
  };

  const moveJob = async (jobId, toIndex) => {
    try {
      await call("reorder_job", jobId, toIndex);
    } catch {
      // best effort
    }
    refresh();
  };

  const editJob = async (jobId) => {
    try {
      await onEditJob(jobId);
    } catch {
      // best effort
    }
    setOpen(false);
  };

  const startRename = (item) => {
    skipRenameRef.current = false;
    setRenamingId(item.job_id);
    setNameDraft(item.label || "");
  };

  const commitRename = async () => {
    if (skipRenameRef.current) {
      skipRenameRef.current = false;
      return;
    }
    const id = renamingId;
    setRenamingId(null);
    if (!id) return;
    try {
      const res = await call("rename_job", id, nameDraft);
      if (res && res.ok) {
        setQueue((q) =>
          q ? { ...q, pending: q.pending.map((it) => (it.job_id === id ? { ...it, label: res.label } : it)) } : q,
        );
      } else if (res && res.code === "not_queued") {
        refresh();
      }
    } catch {
      // best effort
    }
  };

  const handleRenameKey = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      commitRename();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      skipRenameRef.current = true;
      setRenamingId(null);
    }
  };

  const dragStart = (idx) => (e) => {
    e.dataTransfer.effectAllowed = "move";
    setDragIdx(idx);
  };

  const dragEnter = (idx) => () => setDragOverIdx(idx);

  const dragOver = (e) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
  };

  const dragDrop = (idx) => () => {
    if (dragIdx === null || dragIdx === idx) {
      setDragIdx(null);
      setDragOverIdx(null);
      return;
    }
    const from = dragIdx;
    setDragIdx(null);
    setDragOverIdx(null);
    const item = queue.pending[from];
    if (item) moveJob(item.job_id, idx);
  };

  const dragEnd = () => {
    setDragIdx(null);
    setDragOverIdx(null);
  };

  const queueAction = async (method) => {
    let res;
    try {
      res = await call(method);
    } catch (e) {
      showNotice(e && e.message ? e.message : "Action failed");
    }
    refresh();
    if (typeof res === "object" && res) {
      const note = res.code || (res.ok ? "" : res.detail);
      if (note) showNotice(note);
    } else if (res === undefined) {
      showNotice(method + " is unavailable in the bridge");
    }
  };

  const state = (queue && queue.state) || "empty";
  const hasPending = !!(queue && queue.pending.length);
  const showChip = queue && (state === "idle") && hasPending;
  const showDot = queue && state === "running";

  return (
    <div className="worker-wrap" ref={wrapRef}>
      <button
        type="button"
        className="worker-toggle"
        title="Lycan Worker queue"
        aria-label="Lycan Worker queue"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <WolfIcon />
        <span className="worker-toggle-label">Lycan Worker</span>
        <span className="worker-chevron"><Icon name="chevron-down" /></span>
        {showChip && <span className="worker-chip">{queue.pending.length}</span>}
        {showDot && <span className="worker-dot" />}
      </button>
      {open ? (
        <div className="worker-popup" ref={popupRef} style={popupH ? { height: popupH } : undefined}>
          <div className="worker-head">
            <span className="worker-title"><WolfIcon /> Lycan Worker</span>
            <span className="grow" />
            <div className="worker-status-row">
              <span className={"status-dot " + (STATE_TONES[state] || "blue")} />
              <span className="worker-status">
                {state === "running" && (queue.current ? queue.current.status_text || "Working..." : "Working...")}
                {state === "idle" && (hasPending ? (queue.pending.length + " job" + (queue.pending.length === 1 ? "" : "s") + " waiting") : "Queue stopped")}
                {state === "empty" && "No jobs queued"}
                {["success", "failed", "aborted"].includes(state) && "Last job " + STATE_LABELS[state].toLowerCase()}
              </span>
            </div>
            <div
              className="worker-resize-grip"
              title="Drag to resize the queue height"
              aria-label="Drag to resize the queue height"
              onMouseDown={startResize}
            >
              <Icon name="ellipsis" />
            </div>
          </div>
          {notice && <div className="worker-notice" role="status">{notice}</div>}
          {confirmBox && (
            <div className="worker-confirm" role="alertdialog" aria-modal="true">
              <div className="worker-confirm-title">{confirmBox.title}</div>
              <div className="worker-confirm-message">{confirmBox.message}</div>
              <div className="worker-confirm-actions">
                <button type="button" className="btn small" onClick={() => answerConfirm(false)}>{confirmBox.no}</button>
                <button type="button" className="btn small accent" onClick={() => answerConfirm(true)}>{confirmBox.yes}</button>
              </div>
            </div>
          )}
          {!queue ? (
            <div className="worker-empty">Loading...</div>
          ) : (
            <>
              <div className="worker-popup-body">

                {queue.current && (
                  <div className="worker-job">
                    <div className="worker-job-head">
                      <span className="worker-job-title">{queue.current.tool_title}</span>
                      <span className="grow" />
                      {queue.current.paused ? <span className="chip">Paused</span> : <span className="worker-job-progress">{queue.current.progress}%</span>}
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: (queue.current.progress || 0) + "%" }} />
                  </div>
                  <div className="worker-job-meta">
                    <span className="worker-job-status">{queue.current.status_text || "Working..."}</span>
                    <span className="worker-job-id"><EmojiText text={queue.current.label} /></span>
                  </div>
                  <div className="worker-job-actions">
                    {state === "running" && !queue.current.paused && (
                      <button
                        type="button"
                        className="btn small"
                        title="Pause the running job"
                        onClick={() => actJob("pause_job", queue.current.job_id)}
                      >
                        <Icon name="pause" /> Pause
                      </button>
                    )}
                    {state === "running" && (
                      <button
                        type="button"
                        className="btn small danger"
                        title="Abort the running job"
                        onClick={() => actJob("abort_job", queue.current.job_id)}
                      >
                        <Icon name="stop" /> Abort
                      </button>
                    )}
                    {queue.current.paused ? (
                      <button type="button" className="btn small accent" onClick={() => actJob("resume_job", queue.current.job_id)}>
                        <Icon name="play" /> Resume
                      </button>
                    ) : null}
                    {onFocusTool ? (
                      <button
                        type="button"
                        className="btn small"
                        title="Open this job in its tool tab"
                        onClick={() => onFocusTool(queue.current.tool, queue.current.job_id)}
                      >
                        <Icon name="bolt" /> Show Progress
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className={"btn small" + (logExpanded ? " accent" : "")}
                      aria-expanded={logExpanded}
                      title={logExpanded ? "Hide the output log" : "Show the output log"}
                      onClick={() => setLogExpanded((v) => !v)}
                    >
                      <Icon name={logExpanded ? "chevron-down" : "chevron-up"} /> Output log
                      <span className="worker-log-count">&nbsp;{jobLogs.length}</span>
                    </button>
                  </div>
                  {logExpanded && (
                    <div className="worker-log">
                      <div className="worker-log-lines" ref={logScrollRef} onScroll={handleLogScroll}>
                        {jobLogs.length === 0 ? (
                          <div className="worker-log-empty">No output yet. Waiting for the job to produce output...</div>
                        ) : (
                          jobLogs.map((log, idx) => (
                            <div key={idx} className={"log-line " + log.level}>{log.message}</div>
                          ))
                        )}
                      </div>
                      {jobLogs.length > 0 && (
                        <div className="worker-log-tools">
                          <button type="button" className="btn tiny" onClick={copyJobLog}>Copy</button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {hasPending && (
                <div className="worker-section">
                  <div className="worker-section-title">Queue ({queue.pending.length}) &middot; drag rows to reorder</div>
                  {queue.pending.map((item, idx) => {
                    const renaming = renamingId === item.job_id;
                    return (
                      <div
                        key={item.job_id}
                        className={
                          "worker-row" +
                          (dragIdx === idx ? " dragging" : "") +
                          (dragOverIdx === idx && dragIdx !== null && dragIdx !== idx ? " drag-target" : "")
                        }
                        draggable={!renaming}
                        onDragStart={dragStart(idx)}
                        onDragEnter={dragEnter(idx)}
                        onDragOver={dragOver}
                        onDrop={dragDrop(idx)}
                        onDragEnd={dragEnd}
                      >
                        {item.icon_file ? (
                          <img
                            className="worker-queue-icon"
                            src={toolIconFile(item.icon_file)}
                            alt=""
                            draggable={false}
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                          />
                        ) : (
                          <Icon name="queue-list" />
                        )}
                        <div className="worker-row-main">
                          {renaming ? (
                            <input
                              className="worker-rename-input"
                              value={nameDraft}
                              autoFocus
                              onChange={(e) => setNameDraft(e.target.value)}
                              onFocus={(e) => e.currentTarget.select()}
                              onBlur={() => commitRename()}
                              onKeyDown={handleRenameKey}
                              aria-label="Job name"
                            />
                          ) : (
                            <button
                              type="button"
                              className="worker-row-label"
                              title="Click to rename"
                              onClick={() => startRename(item)}
                            >
                              <EmojiText text={item.label} />
                            </button>
                          )}
                          {item.restored && (
                            <span className="chip warn" title="Incomplete from a previous session — re-run or edit it">Incomplete</span>
                          )}
                        </div>
                        <div className="worker-row-actions">
                          {onEditJob ? (
                            <button
                              type="button"
                              className="worker-remove worker-edit"
                              title="Edit job settings"
                              aria-label={"Edit " + item.label}
                              onClick={() => editJob(item.job_id)}
                            >
                              <Icon name="pencil" />
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="worker-remove"
                            title="Remove from queue"
                            aria-label={"Remove " + item.label + " from queue"}
                            onClick={() => actJob("dequeue_job", item.job_id)}
                          >
                            <Icon name="x" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {queue.history && queue.history.length > 0 && (
                <div className="worker-section">
                  <div className="worker-section-title">Recent</div>
                  {queue.history.map((item) => (
                    <div className="worker-row" key={item.job_id}>
                      <span className={"status-dot " + (OUTCOME_TONES[item.outcome] || "blue")} />
                      <span className="worker-row-label" title={item.label}><EmojiText text={item.label} /></span>
                      <span className="worker-row-outcome">{STATE_LABELS[item.outcome] || item.outcome}</span>
                    </div>
                  ))}
                </div>
              )}
              </div>

              <div className="worker-footer">
                {hasPending && state !== "running" ? (
                  <>
                    <button type="button" className="btn accent small" onClick={() => queueAction("start_queue")}>
                      <Icon name="play" /> Start Queue
                    </button>
                    <button type="button" className="btn small" onClick={() => queueAction("clear_queue")}>
                      <Icon name="x" /> Clear
                    </button>
                  </>
                ) : null}
                {state === "running" && (
                  <button type="button" className="btn small" title="Stop launching further queued jobs" onClick={() => queueAction("stop_queue")}>
                    <Icon name="stop" /> Stop Queue
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}