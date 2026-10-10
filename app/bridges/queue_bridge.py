"""Lycan Worker queue: pending jobs, persistence, worker loop, snapshot."""

from __future__ import annotations

import time
import traceback
import uuid
from collections import deque
from threading import Thread
from typing import Any, Callable, Optional, TYPE_CHECKING

from app.settings import record_used, load_worker_queue, save_worker_queue

from .common import _FINISHED_JOB_GRACE, _Job, _tool_title, _tool_icon_file
from .envelope import ResponseStatus
from core.debug_log import get_logger

_logger = get_logger(__name__)

if TYPE_CHECKING:
    class BaseApiHost:
        _runner_for: Callable[[str], Optional[Callable[..., None]]]
        _lock: Any
        _utilities: dict[str, dict]
        _jobs: dict[str, _Job]
        _recent_jobs: dict[str, str]
        _queue: deque[str]
        _queue_current: Optional[str]
        _queue_process: bool
        _queue_worker_alive: bool
        _queue_history: deque[dict]
        _done: Callable[..., bool]
else:
    BaseApiHost = object


class QueueBridgeMixin(BaseApiHost):
    """Lycan Worker queue surface of the Api bridge."""

    def enqueue_job(self, tool: str, params: dict) -> dict:
        """Queue a job configuration for the Lycan Worker without starting it."""
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "params": params}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(tool, str) or not tool.strip():
            _logger.debug_info("in if (not isinstance(tool, str) or not tool.strip())", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_tool",
                "detail": "A valid tool id is required.",
            }
        if not isinstance(params, dict):
            _logger.debug_info("in if (not isinstance(params, dict))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_params",
                "detail": "Job parameters must be a dictionary.",
            }
        tool = tool.strip()
        if self._runner_for(tool) is None:
            _logger.debug_info("in if (self._runner_for(tool) is None)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "unsupported_tool",
                "detail": f"Tool '{tool}' has no backend handler.",
                "tool": tool,
            }
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            job = _Job(uuid.uuid4().hex, tool, params)
            job.queued = True
            job.label = f"{_tool_title(tool, self._utilities)} \u00b7 {job.id[:6]}"
            self._jobs[job.id] = job
            self._queue.append(job.id)
        record_used(tool)
        self._persist_queue()
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "job_id": job.id,
            "tool": tool,
        }

    def update_queued_job(self, job_id: str, params: dict) -> dict:
        """Replace the parameters of a pending (not yet started) job."""
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id, "params": params}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(job_id, str) or not job_id:
            _logger.debug_info("in if (not isinstance(job_id, str) or not job_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_job_id",
                "detail": "A valid job id is required.",
            }
        if not isinstance(params, dict):
            _logger.debug_info("in if (not isinstance(params, dict))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_params",
                "detail": "Job parameters must be a dictionary.",
            }
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            job = self._jobs.get(job_id)
            if job is None or not job.queued or job_id not in self._queue:
                _logger.debug_info("in if (job is None or not job.queued or job_id not in self._queue)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "not_queued",
                    "detail": "The job is not pending in the queue.",
                }
            job.params = dict(params)
        self._persist_queue()
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
        }

    def get_queued_job(self, job_id: str) -> dict:
        """Return the stored configuration of a pending job (for editing)."""
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(job_id, str) or not job_id:
            _logger.debug_info("in if (not isinstance(job_id, str) or not job_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_job_id",
                "detail": "A valid job id is required.",
            }
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            job = self._jobs.get(job_id)
            if job is None or not job.queued:
                _logger.debug_info("in if (job is None or not job.queued)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "not_found",
                    "detail": "No pending job with that id.",
                }
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "job_id": job.id,
                "tool": job.tool,
                "params": dict(job.params),
            }

    def rename_job(self, job_id: str, name: str) -> dict:
        """Rename a pending job via user input.

        An empty name becomes "Unnamed". If the resulting name collides with
        another pending job, a numeric suffix "(0)", "(1)", ... is appended.
        """
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id, "name": name}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(job_id, str) or not job_id:
            _logger.debug_info("in if (not isinstance(job_id, str) or not job_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_job_id",
                "detail": "A valid job id is required.",
            }
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            job = self._jobs.get(job_id)
            if job is None or not job.queued or job_id not in self._queue:
                _logger.debug_info("in if (job is None or not job.queued or job_id not in self._queue)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "not_queued",
                    "detail": "The job is not pending in the queue.",
                }
            base = str(name or "").strip() or "Unnamed"
            taken = {
                self._jobs[jid].label
                for jid in self._queue
                if jid != job_id and self._jobs.get(jid) is not None
            }
            label = base
            suffix = 0
            while label in taken:
                _logger.debug_info("in while (label in taken)", tier=_logger.DEBUG_LOOP)
                label = f"{base} ({suffix})"
                suffix += 1
            job.label = label
        self._persist_queue()
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "label": label,
        }

    def reorder_job(self, job_id: str, to_index: int) -> dict:
        """Move a pending job to another position in the queue."""
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id, "to_index": to_index}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(job_id, str) or not job_id:
            _logger.debug_info("in if (not isinstance(job_id, str) or not job_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_job_id",
                "detail": "A valid job id is required.",
            }
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            if job_id not in self._queue:
                _logger.debug_info("in if (job_id not in self._queue)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "not_queued",
                    "detail": "The job is not pending in the queue.",
                }
            items = list(self._queue)
            idx = items.index(job_id)
            items.pop(idx)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
                to_index = int(to_index)
            except (ValueError, TypeError):
                _logger.debug_info("in except (ValueError, TypeError)", tier=_logger.DEBUG_FUNCTION)
                to_index = idx
            to_index = max(0, min(len(items), to_index))
            items.insert(to_index, job_id)
            self._queue = deque(items)
        self._persist_queue()
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "index": to_index,
        }

    def dequeue_job(self, job_id: str) -> dict:
        """Remove a pending (not yet started) job from the queue."""
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(job_id, str) or not job_id:
            _logger.debug_info("in if (not isinstance(job_id, str) or not job_id)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_job_id",
                "detail": "A valid job id is required.",
            }
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            job = self._jobs.get(job_id)
            if job is None or not job.queued or job_id not in self._queue:
                _logger.debug_info("in if (job is None or not job.queued or job_id not in self._queue)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "not_queued",
                    "detail": "The job is not pending in the queue.",
                }
            self._queue = deque(jid for jid in self._queue if jid != job_id)
            self._jobs.pop(job_id, None)
        self._persist_queue()
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
        }

    def clear_queue(self) -> dict:
        """Remove every pending job and reset the worker history."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            removed = len(self._queue)
            for jid in list(self._queue):
                _logger.debug_info("in for (jid in list(self._queue))", tier=_logger.DEBUG_LOOP)
                self._jobs.pop(jid, None)
            self._queue.clear()
            self._queue_history.clear()
        self._persist_queue()
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "removed": removed,
        }

    def start_queue(self) -> dict:
        """Begin processing the queued jobs sequentially on a worker thread."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            if not self._queue:
                _logger.debug_info("in if (not self._queue)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "empty",
                    "detail": "The queue is empty.",
                }
            self._queue_process = True
            if not self._queue_worker_alive:
                _logger.debug_info("in if (not self._queue_worker_alive)", tier=_logger.DEBUG_FUNCTION)
                self._queue_worker_alive = True
                Thread(target=self._queue_worker, daemon=True).start()
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
        }

    def stop_queue(self) -> dict:
        """Stop launching new jobs from the queue; the current job finishes."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            self._queue_process = False
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
        }

    def _persist_queue(self) -> None:
        """Snapshot every unfinished job (pending + current) to disk.

        On a crash or force-close the persisted entries are restored as
        incomplete, user-runnable jobs on the next launch.
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        entries = []
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
            for jid in list(self._queue):
                _logger.debug_info("in for (jid in list(self._queue))", tier=_logger.DEBUG_LOOP)
                job = self._jobs.get(jid)
                if job is not None:
                    _logger.debug_info("in if (job is not None)", tier=_logger.DEBUG_LOOP)
                    entries.append({"job_id": job.id, "tool": job.tool,
                                    "params": dict(job.params)})
            cid = self._queue_current
            if cid is not None:
                _logger.debug_info("in if (cid is not None)", tier=_logger.DEBUG_LOOP)
                job = self._jobs.get(cid)
                if job is not None:
                    _logger.debug_info("in if (job is not None)", tier=_logger.DEBUG_LOOP)
                    entries.append({"job_id": job.id, "tool": job.tool,
                                    "params": dict(job.params)})
        save_worker_queue(entries)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _restore_queue(self) -> None:
        """Re-queue jobs persisted by a previous (possibly crashed) session."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        restored = []
        for entry in load_worker_queue():
            _logger.debug_info("in for (entry in load_worker_queue())", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                job_id = str(entry["job_id"])
                tool = str(entry["tool"])
                params = dict(entry.get("params") or {})
            except (KeyError, TypeError, ValueError):
                _logger.debug_info("in except (KeyError, TypeError, ValueError)", tier=_logger.DEBUG_LOOP)
                continue
            if not job_id or self._runner_for(tool) is None:
                _logger.debug_info("in if (not job_id or self._runner_for(tool) is None)", tier=_logger.DEBUG_LOOP)
                continue
            if job_id in self._jobs:
                _logger.debug_info("in if (job_id in self._jobs)", tier=_logger.DEBUG_LOOP)
                continue
            job = _Job(job_id, tool, params)
            job.queued = True
            job.restored = True
            job.label = f"{_tool_title(tool, self._utilities)} \u00b7 {job_id[:6]}"
            self._jobs[job.id] = job
            self._queue.append(job.id)
            restored.append(job_id)
        if restored:
            _logger.debug_info("in if (restored)", tier=_logger.DEBUG_LOOP)
            print(f"Lycan Worker: restored {len(restored)} incomplete job(s) from a previous session.")
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _queue_state(self) -> str:
        """Derive the worker status: empty | idle | running | success | failed | aborted."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        if self._queue_current is not None:
            _logger.debug_info("in if (self._queue_current is not None)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return "running"
        if self._queue:
            _logger.debug_info("in if (self._queue)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return "idle"
        if self._queue_history:
            _logger.debug_info("in if (self._queue_history)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return self._queue_history[0]["outcome"]
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return "empty"

    def _prune_finished_jobs(self, grace: float = _FINISHED_JOB_GRACE) -> None:
        """Drop finished jobs whose replay grace period has lapsed.

        Caller must hold self._lock. Finished jobs are intentionally kept a
        while so a tool tab attaching after completion can still replay their
        log/progress events; this sweep bounds the growth of self._jobs.
        """
        _logger.debug_info("enter args=%s", ascii({"grace": grace}), tier=_logger.DEBUG_LOOP)
        now = time.monotonic()
        for jid, job in list(self._jobs.items()):
            _logger.debug_info("in for (jid, job in list(self._jobs.items()))", tier=_logger.DEBUG_LOOP)
            if job.finished and job.finished_at and now - job.finished_at > grace:
                _logger.debug_info("in if (job.finished and job.finished_at and now - job.finished_at > grace)", tier=_logger.DEBUG_LOOP)
                del self._jobs[jid]
                if self._recent_jobs.get(job.tool) == jid:
                    _logger.debug_info("in if (self._recent_jobs.get(job.tool) == jid)", tier=_logger.DEBUG_LOOP)
                    self._recent_jobs.pop(job.tool, None)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def get_queue(self) -> dict:
        """Snapshot of the Lycan Worker queue for the header dropdown."""
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
            self._prune_finished_jobs()
            current = None
            cid = self._queue_current
            if cid is not None:
                _logger.debug_info("in if (cid is not None)", tier=_logger.DEBUG_LOOP)
                job = self._jobs.get(cid)
                if job is not None:
                    _logger.debug_info("in if (job is not None)", tier=_logger.DEBUG_LOOP)
                    current = {
                        "job_id": job.id,
                        "tool": job.tool,
                        "tool_title": _tool_title(job.tool, self._utilities),
                        "label": job.label or "",
                        "progress": int(round(job.progress_pct)),
                        "status_text": job.status_text or "",
                        "paused": job.pause_event.is_set(),
                    }
            pending = []
            for jid in self._queue:
                _logger.debug_info("in for (jid in self._queue)", tier=_logger.DEBUG_LOOP)
                job = self._jobs.get(jid)
                if job is not None:
                    _logger.debug_info("in if (job is not None)", tier=_logger.DEBUG_LOOP)
                    pending.append({
                        "job_id": job.id,
                        "tool": job.tool,
                        "tool_title": _tool_title(job.tool, self._utilities),
                        "icon_file": _tool_icon_file(job.tool, self._utilities),
                        "label": job.label or "",
                        "restored": job.restored,
                    })
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "state": self._queue_state(),
                "processing": self._queue_process,
                "current": current,
                "pending": pending,
                "history": list(self._queue_history),
                "total": (1 if current else 0) + len(pending),
            }

    def _queue_worker(self) -> None:
        """Worker loop: run queued jobs one at a time until stopped or drained.

        ``_queue_worker_alive`` is ALWAYS cleared on the way out. An unexpected
        exception here can therefore never wedge the queue (otherwise Start
        Queue would permanently refuse to spawn a fresh worker while the UI
        stays stuck showing a "running" job).
        """
        _logger.debug_info("enter", tier=_logger.DEBUG_LOOP)
        while True:
            _logger.debug_info("in while (True)", tier=_logger.DEBUG_LOOP)
            try:
                _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
                with self._lock:
                    _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
                    if not self._queue_process or not self._queue:
                        _logger.debug_info("in if (not self._queue_process or not self._queue)", tier=_logger.DEBUG_LOOP)
                        self._queue_worker_alive = False
                        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                        return
                    job_id = self._queue.popleft()
                    job = self._jobs.get(job_id)
                    if job is None:
                        _logger.debug_info("in if (job is None)", tier=_logger.DEBUG_LOOP)
                        continue
                    job.queued = False
                    self._queue_current = job_id
                    self._recent_jobs[job.tool] = job_id
                self._persist_queue()
                runner = self._runner_for(job.tool)
                if runner is None:
                    _logger.debug_info("in if (runner is None)", tier=_logger.DEBUG_LOOP)
                    with self._lock:
                        _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
                        self._queue_current = None
                        self._queue_history.appendleft({
                            "job_id": job.id, "tool": job.tool,
                            "tool_title": _tool_title(job.tool, self._utilities),
                            "label": job.label or "", "outcome": "failed",
                        })
                        self._jobs.pop(job.id, None)
                    self._persist_queue()
                    continue
                thread = Thread(target=runner, args=(job, job.params), daemon=True)
                thread.start()
                thread.join()
                if not job.finished:
                    # The run method exited without recording a result (unexpected
                    # exception); mark the job failed so the worker can proceed.
                    _logger.debug_info("in if (not job.finished)", tier=_logger.DEBUG_LOOP)
                    self._done(job, False, "Job ended unexpectedly.", "runner exited")
                outcome = {"ok": "success", "error": "failed", "cancelled": "aborted"}.get(
                    job.outcome or "cancelled", "failed")
                with self._lock:
                    _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
                    self._queue_current = None
                    self._queue_history.appendleft({
                        "job_id": job.id, "tool": job.tool,
                        "tool_title": _tool_title(job.tool, self._utilities),
                        "label": job.label or "", "outcome": outcome,
                    })
                # Keep the finished job in self._jobs so a tab attaching after
                # completion can still replay its log/progress; get_queue()
                # prunes finished jobs after a grace period.
                self._persist_queue()
            except Exception as exc:
                # Never leave the queue wedged: restore a stoppable, restartable
                # state and mark the interrupted job (if any) as failed.
                _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
                traceback.print_exc()
                with self._lock:
                    _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
                    current_id = self._queue_current
                    self._queue_process = False
                    self._queue_current = None
                    self._queue_worker_alive = False
                    cur = self._jobs.get(current_id) if current_id is not None else None
                    interrupted = cur is not None and not cur.finished
                if interrupted:
                    _logger.debug_info("in if (interrupted)", tier=_logger.DEBUG_LOOP)
                    self._done(cur, False, "Queue worker stopped unexpectedly.",
                               str(exc) or "queue worker error")
                self._persist_queue()
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return
