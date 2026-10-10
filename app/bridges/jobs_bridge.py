"""Job lifecycle: start/poll/abort/pause/resume, confirms, event emitters."""

from __future__ import annotations

import time
import uuid
from collections import deque
from threading import Event, Thread
from typing import Optional, TYPE_CHECKING, Any, Callable

import math

from app.settings import record_used

from .common import _Job, _tool_title
from .envelope import ResponseStatus
from core.debug_log import get_logger

_logger = get_logger(__name__)

if TYPE_CHECKING:
    class BaseApiHost:
        _lock: Any
        _jobs: dict[str, _Job]
        _utilities: dict[str, dict[str, Any]]
        _queue: deque[str]
        _queue_history: deque[dict[str, Any]]
        _recent_jobs: dict[str, str]
        _pending_confirms: dict[str, dict[str, Any]]
        _run_utility: Callable[[_Job, dict[str, Any]], None]
        _prune_finished_jobs: Callable[[], None]
        _persist_queue: Callable[[], None]
else:
    BaseApiHost = object

class JobsBridgeMixin(BaseApiHost):
    """Job surface of the Api bridge (buffers, polling, worker emitters)."""

    def _runner_for(self, tool: str) -> Optional[Callable[[_Job, dict[str, Any]], None]]:
        """Return the run-loop for a utility id, or None if unsupported."""
        _logger.debug_info("enter args=%s", ascii({"tool": tool}), tier=_logger.DEBUG_LOOP)
        if not isinstance(tool, str) or not tool:
            _logger.debug_info("in if (not isinstance(tool, str) or not tool)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None

        util = self._utilities.get(tool)

        if not isinstance(util, dict):
            _logger.debug_info("in if (not isinstance(util, dict))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None

        if not util.get("runtime_ok"):
            _logger.debug_info("in if (not util.get(\"runtime_ok\"))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None

        runner: Optional[Callable[[_Job, dict[str, Any]], None]] = util.get("runner")
        if runner is None:
            _logger.debug_info("in if (runner is None)", tier=_logger.DEBUG_LOOP)
            runner = self._run_utility

        if not callable(runner):
            _logger.debug_info("in if (not callable(runner))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return None

        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return runner

    def _spawn_run(
        self,
        job: _Job,
        runner: Optional[Callable[[_Job, dict[str, Any]], None]] = None,
    ) -> bool:
        """Start the job's worker thread; returns False if it could not start."""
        _logger.debug_info("enter args=%s", ascii({"job": job, "runner": runner}), tier=_logger.DEBUG_LOOP)
        if runner is None:
            _logger.debug_info("in if (runner is None)", tier=_logger.DEBUG_LOOP)
            runner = self._runner_for(job.tool)
        if runner is None:
            _logger.debug_info("in if (runner is None)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return False
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            thread = Thread(
                target=runner,
                args=(job, job.params),
                daemon=True
            )
            thread.start()
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_LOOP)
            self._done(
                job,
                False,
                "failed to spawn run thread",
                str(exc)
            )
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return False
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return True

    def start_job(self, tool: str, params: dict) -> dict:
        _logger.debug_info("enter args=%s", ascii({"tool": tool, "params": params}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(tool, str) or not tool.strip():
            _logger.debug_info("in if (not isinstance(tool, str) or not tool.strip())", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_tool",
                "detail": "A valid tool id is required."
            }

        if not isinstance(params, dict):
            _logger.debug_info("in if (not isinstance(params, dict))", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_params",
                "detail": "Job parameters must be a dictionary."
            }

        tool = tool.strip()
        runner = self._runner_for(tool)

        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            self._prune_finished_jobs()

            job = _Job(uuid.uuid4().hex, tool, params)
            self._jobs[job.id] = job
            self._recent_jobs[tool] = job.id

        # If the tool is not supported, return an error
        if runner is None:
            _logger.debug_info("in if (runner is None)", tier=_logger.DEBUG_FUNCTION)
            self._log(job, f"No backend handler for tool '{tool}'", "warn")
            self._done(job, False, "Not implemented.", "unsupported tool")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "unsupported_tool",
                "detail": f"Tool '{tool}' has no backend handler.",
                "job_id": job.id,
                "tool": tool,
            }

        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            record_used(tool)
        except Exception:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            self._log(job, f"Failed to record tool usage for '{tool}'", "warn")

        # Background processing; the worker records the outcome via _done().
        if not self._spawn_run(job, runner):
            _logger.debug_info("in if (not self._spawn_run(job, runner))", tier=_logger.DEBUG_FUNCTION)
            self._done(job, False, "Unable to start the worker.", "worker_start_failed")
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "worker_start_failed",
                "detail": "Unable to start the worker.",
                "job_id": job.id,
                "tool": tool,
            }

        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "job_id": job.id,
            "tool": tool,
        }

    def get_tool_job(self, tool: str) -> dict:
        """Return the most recent live/replayable job for a tool, if any.

        Exiting and re-entering a tool tab unmounts it, wiping its console
        state (progress percent, output log, job id). The backend still holds
        the job with its replayable event buffer for a grace window after it
        finishes; this method lets the remounted tab rediscover the job and
        re-attach via poll(job_id, 0), restoring the log and percent. An
        explicit focus is handled by the frontend's own attach path.
        """
        _logger.debug_info("enter args=%s", ascii({"tool": tool}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(tool, str) or not tool:
            _logger.debug_info("in if (not isinstance(tool, str) or not tool)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "job_id": None,
            }

        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            self._prune_finished_jobs()
            jid = self._recent_jobs.get(tool)
            job = self._jobs.get(jid) if jid else None

            if job is None or job.queued:
                _logger.debug_info("in if (job is None or job.queued)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": True,
                    "reason": ResponseStatus.SUCCESS,
                    "job_id": None
                }

            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "job_id": job.id,
                "tool": job.tool,
                "progress": int(
                    max(0, min(100, round(job.progress_pct)))
                ),
                "status_text": job.status_text or "",
                "finished": job.finished,
                "outcome": job.outcome,
            }

    def poll(self, job_id: str, cursor: int = 0) -> dict:
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id, "cursor": cursor}), tier=_logger.DEBUG_LOOP)
        if not isinstance(job_id, str) or not job_id:
            _logger.debug_info("in if (not isinstance(job_id, str) or not job_id)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_job_id",
                "detail": "A valid job id is required.",
                "done": True,
                "events": [],
                "cursor": 0
            }

        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
            job = self._jobs.get(job_id)

        if job is None:
            _logger.debug_info("in if (job is None)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "job_not_found",
                "detail": f"Job '{job_id}' is no longer available.",
                "done": True,
                "events": [],
                "cursor": 0
            }

        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            cur = max(0, int(cursor))
        except (TypeError, ValueError):
            _logger.debug_info("in except (TypeError, ValueError)", tier=_logger.DEBUG_LOOP)
            cur = 0

        events = []
        new_cursor = cur
        with job.ev_lock:
            # A confirm event is only meaningful while its prompt is pending;
            # surface it to one consumer, never replay an already-answered one.
            _logger.debug_info("in with (job.ev_lock)", tier=_logger.DEBUG_LOOP)
            pending = job.pending_confirm
            for seq, payload in job.events:
                _logger.debug_info("in for (seq, payload in job.events)", tier=_logger.DEBUG_LOOP)
                if seq > cur and not (payload.get("kind") == "confirm" and payload.get("token") != pending):
                    _logger.debug_info("in if (seq > cur and not (payload.get(\"kind\") == \"confirm\" and payload.get(\"token\") != pending))", tier=_logger.DEBUG_LOOP)
                    events.append(payload)
            if events:
                _logger.debug_info("in if (events)", tier=_logger.DEBUG_LOOP)
                new_cursor = job.events[-1][0]

        # Never pop the job here: a finished job stays available (until the
        # grace-period prune in get_queue()) so a tab attaching after completion
        # can still replay its log/progress events.
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS, "done": job.finished,
            "events": events,
            "cursor": new_cursor
        }

    def abort_job(self, job_id: str) -> dict:
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

            if job is None:
                _logger.debug_info("in if (job is None)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": False,
                    "reason": ResponseStatus.FAILED,
                    "code": "not_found",
                    "detail": "No such job.",
                }

            if job.finished:
                _logger.debug_info("in if (job.finished)", tier=_logger.DEBUG_FUNCTION)
                _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
                return {
                    "ok": True,
                    "reason": ResponseStatus.SUCCESS,
                    "code": "already_completed",
                    "detail": "The job has already finished.",
                }

            if job.queued:
                _logger.debug_info("in if (job.queued)", tier=_logger.DEBUG_FUNCTION)
                self._queue = deque(
                    jid for jid in self._queue if jid != job_id
                )
                self._jobs.pop(job_id, None)

                self._queue_history.appendleft({
                    "job_id": job.id,
                    "tool": job.tool,
                    "tool_title": _tool_title(
                        job.tool, self._utilities
                    ),
                    "label": job.label or "",
                    "outcome": "aborted",
                })

                removed = True
            else:
                _logger.debug_info("in else", tier=_logger.DEBUG_FUNCTION)
                job.abort_event.set()
                removed = False

        if removed:
            _logger.debug_info("in if (removed)", tier=_logger.DEBUG_FUNCTION)
            self._persist_queue()
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": True,
                "reason": ResponseStatus.SUCCESS,
                "code": "removed_from_queue",
                "detail": "Job removed from the worker queue.",
            }

        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "code": "cancel_requested",
            "detail": "Cancellation requested.",
        }

    # Backwards-compatible aliases for the "conversion" naming (internal only).
    def _abort_conversion(self, job_id: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id}), tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return self.abort_job(job_id)

    def pause_job(self, job_id: str) -> dict:
        """Cooperatively pause a running job at its next checkpoint."""
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
        if job is None or job.queued or job.finished:
            _logger.debug_info("in if (job is None or job.queued or job.finished)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "not_running",
                "detail": "The job is not running.",
            }

        job.pause_event.set()
        self._status(job, "Pause requested", "warn")

        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS
        }

    def _pause_conversion(self, job_id: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id}), tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return self.pause_job(job_id)

    def resume_job(self, job_id: str) -> dict:
        """Resume a paused job."""
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

        if job is None or job.queued or job.finished:
            _logger.debug_info("in if (job is None or job.queued or job.finished)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "not_running",
                "detail": "The job is not running.",
            }

        job.pause_event.clear()
        self._status(job, "Resume requested", "accent")

        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS
        }


    def _resume_conversion(self, job_id: str) -> dict:
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id}), tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return self.resume_job(job_id)

    def resolve_confirm(self, token: str, accepted: bool) -> dict:
        _logger.debug_info("enter args=%s", ascii({"token": token, "accepted": accepted}), tier=_logger.DEBUG_FUNCTION)
        if not isinstance(token, str) or not token:
            _logger.debug_info("in if (not isinstance(token, str) or not token)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_token",
                "detail": "Invalid confirmation token.",
            }

        if type(accepted) is not bool:
            _logger.debug_info("in if (type(accepted) is not bool)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "invalid_value",
                "detail": "Invalid confirmation must be a boolean.",
            }

        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_FUNCTION)
            entry = self._pending_confirms.pop(token, None)

            if entry is not None:
                _logger.debug_info("in if (entry is not None)", tier=_logger.DEBUG_FUNCTION)
                entry["value"] = accepted
                entry["event"].set()

        if entry is None:
            _logger.debug_info("in if (entry is None)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "code": "not_found",
                "detail": "No pending confirmation for that token.",
            }

        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "code": "resolved",
            "detail": "Confirmation resolved.",
        }

    # ------------------------------------------------------------------ #
    #  Emitters (safe from any thread)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _emit(job: _Job, payload: dict) -> None:
        _logger.debug_info("enter args=%s", ascii({"job": job, "payload": payload}), tier=_logger.DEBUG_LOOP)
        with job.ev_lock:
            _logger.debug_info("in with (job.ev_lock)", tier=_logger.DEBUG_LOOP)
            job.event_seq += 1

            event = dict(payload)
            event["seq"] = job.event_seq

            job.events.append((job.event_seq, event))
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _log(self, job: _Job, message: str, level: str = "info") -> None:
        _logger.debug_info("enter args=%s", ascii({"job": job, "message": message, "level": level}), tier=_logger.DEBUG_LOOP)
        self._emit(job, {"kind": "log", "level": level, "message": str(message)})
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _status(self, job: _Job, text: str, tone: str = "blue") -> None:
        _logger.debug_info("enter args=%s", ascii({"job": job, "text": text, "tone": tone}), tier=_logger.DEBUG_LOOP)
        job.status_text = str(text)
        self._emit(job, {"kind": "status", "text": str(text), "tone": tone})
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _progress(self, job: _Job, percent: float, status_text: Optional[str] = None) -> None:
        _logger.debug_info("enter args=%s", ascii({"job": job, "percent": percent, "status_text": status_text}), tier=_logger.DEBUG_LOOP)
        now = time.monotonic()

        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            value = float(percent)
        except (TypeError, ValueError, OverflowError):
            _logger.debug_info("in except (TypeError, ValueError, OverflowError)", tier=_logger.DEBUG_LOOP)
            self._log(job, "Invalid progress percentage.", "error")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return

        if not math.isfinite(value):
            _logger.debug_info("in if (not math.isfinite(value))", tier=_logger.DEBUG_LOOP)
            self._log(job, "Progress percentage must be finite.", "error")
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return

        value = max(0.0, min(100.0, value))
        job.progress_pct = value

        if status_text is not None:
            _logger.debug_info("in if (status_text is not None)", tier=_logger.DEBUG_LOOP)
            job.status_text = str(status_text)
            self._emit(
                job,
                {
                    "kind": "status",
                    "text": str(status_text),
                    "tone": "blue"
                }
            )

        if now - job.last_progress < 0.10:
            _logger.debug_info("in if (now - job.last_progress < 0.10)", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return

        job.last_progress = now

        self._emit(
            job,
            {
                "kind": "progress",
                "percent": int(round(value)),
            }
        )

    def _done(self, job: _Job, ok: bool, message: str, error: Optional[str] = None) -> bool:
        _logger.debug_info("enter args=%s", ascii({"job": job, "ok": ok, "message": message, "error": error}), tier=_logger.DEBUG_LOOP)
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
            if job.finished:
                _logger.debug_info("in if (job.finished)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return False

            if ok:
                _logger.debug_info("in if (ok)", tier=_logger.DEBUG_LOOP)
                outcome = "ok"
            elif job.abort_event.is_set():
                _logger.debug_info("in elif (job.abort_event.is_set())", tier=_logger.DEBUG_LOOP)
                outcome = "cancelled"
            else:
                _logger.debug_info("in else", tier=_logger.DEBUG_LOOP)
                outcome = "error"

            job.outcome = outcome
            # Keep the job around until the frontend polls and drains its events;
            # poll() removes it lazily once the queue is empty. Popping immediately
            # would drop every queued event (logs, progress and done) for fast jobs.
            job.finished = True
            job.finished_at = time.monotonic()

            payload = {
                "kind": "done",
                "ok": outcome == "ok",
                "message": str(message),
                "error": error,
                "outcome": outcome,
            }

            self._emit(job, payload)

        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return True

    @staticmethod
    def _wait_if_paused(job: _Job) -> None:
        """Block the worker while the job is paused (used at bridge checkpoints)."""
        _logger.debug_info("enter args=%s", ascii({"job": job}), tier=_logger.DEBUG_LOOP)
        while job.pause_event.is_set():
            _logger.debug_info("in while (job.pause_event.is_set())", tier=_logger.DEBUG_LOOP)
            if job.abort_event.is_set():
                _logger.debug_info("in if (job.abort_event.is_set())", tier=_logger.DEBUG_LOOP)
                raise RuntimeError("ABORTED_BY_USER")

            time.sleep(0.1)

        if job.abort_event.is_set():
            _logger.debug_info("in if (job.abort_event.is_set())", tier=_logger.DEBUG_LOOP)
            raise RuntimeError("ABORTED_BY_USER")
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)

    def _confirm(self, job: _Job, message: str, *, title: str = "Confirmation",
                 yes: str = "Yes", no: str = "No") -> bool:
        """Ask the frontend to show a blocking confirmation on behalf of a worker.

        Queue jobs show their prompts inside the Worker popup; direct tool jobs
        show them in the console. Either way the wait is bounded: an Abort raises
        immediately and an unanswered prompt times out as a safe "No", so the
        queue can never hang forever on a confirmation nobody can answer.
        """
        _logger.debug_info("enter args=%s", ascii({"job": job, "message": message, "title": title, "yes": yes, "no": no}), tier=_logger.DEBUG_LOOP)
        confirm_timeout = 120.0
        token = uuid.uuid4().hex
        entry: dict[str, Any] = {"event": Event(), "value": False}
        with self._lock:
            _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
            self._pending_confirms[token] = entry
        self._emit(job, {
            "kind": "confirm",
            "token": token,
            "title": title,
            "message": str(message),
            "yes": yes,
            "no": no,
        })
        job.pending_confirm = token
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_LOOP)
            deadline = time.monotonic() + confirm_timeout
            while not entry["event"].wait(0.2):
                _logger.debug_info("in while (not entry[\"event\"].wait(0.2))", tier=_logger.DEBUG_LOOP)
                if job.abort_event.is_set():
                    _logger.debug_info("in if (job.abort_event.is_set())", tier=_logger.DEBUG_LOOP)
                    raise RuntimeError("ABORTED_BY_USER")
                if time.monotonic() > deadline:
                    _logger.debug_info("in if (time.monotonic() > deadline)", tier=_logger.DEBUG_LOOP)
                    self._emit(job, {"kind": "log", "level": "warn",
                                     "message": "Confirmation timed out; treated as 'No'."})
                    break
            value = bool(entry["value"])
        finally:
            _logger.debug_info("in finally", tier=_logger.DEBUG_LOOP)
            with self._lock:
                _logger.debug_info("in with (self._lock)", tier=_logger.DEBUG_LOOP)
                self._pending_confirms.pop(token, None)
            job.pending_confirm = None
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return value
