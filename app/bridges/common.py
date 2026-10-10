"""Shared job model and module-level helpers used across bridge mixins."""

from __future__ import annotations

from collections import deque
from threading import Event, Lock
from typing import Optional
from core.debug_log import get_logger

_logger = get_logger(__name__)

# Events retained per job for replay. Consumers poll with a cursor, so even a
# late-attaching surface (Worker popup, tool tab) sees recent output.
EVENT_BUFFER_MAX = 2000

# How long a finished job stays in Api._jobs so a tool tab attaching after
# completion can still replay its log/progress. get_queue() prunes past this.
_FINISHED_JOB_GRACE = 120.0


class _Job:
    """One running or queued background task."""

    __slots__ = (
        "id", "tool", "params", "abort_event", "pause_event", "events",
        "event_seq", "ev_lock", "last_progress", "progress_pct", "status_text",
        "finished", "finished_at", "queued", "outcome", "label", "restored",
        "pending_confirm",
    )

    def __init__(self, job_id: str, tool: str, params: Optional[dict] = None) -> None:
        _logger.debug_info("enter args=%s", ascii({"job_id": job_id, "tool": tool, "params": params}), tier=_logger.DEBUG_LOOP)
        self.id = job_id
        self.tool = tool
        self.params: dict = dict(params or {})
        self.abort_event = Event()
        self.pause_event = Event()
        # Replayable event buffer: (sequence, payload) pairs. Consumers poll
        # with a cursor and only receive events newer than it, so multiple
        # surfaces (Worker popup, attached tool tab) can watch one job without
        # draining each other's events.
        self.events: deque = deque(maxlen=EVENT_BUFFER_MAX)
        self.event_seq = 0
        self.ev_lock = Lock()
        self.last_progress = 0.0
        self.progress_pct = 0.0
        self.status_text = ""
        self.finished = False
        # Monotonic timestamp set by _done(); used to prune finished jobs.
        self.finished_at = 0.0
        # Token of the confirmation currently awaiting an answer (if any).
        # poll() only replays a confirm while it is still pending, so a surface
        # attaching after the prompt was answered never sees a stale confirm.
        self.pending_confirm: Optional[str] = None
        # Queue bookkeeping: True until the worker dequeues the job.
        self.queued = False
        # Final result: "ok" | "error" | "cancelled" (set by _done).
        self.outcome: Optional[str] = None
        self.label = ""
        # True when the job was restored from the on-disk queue after a restart.
        self.restored = False
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)


def _tool_title(tool: str, utilities: Optional[dict] = None) -> str:
    """Extract utility title from manifest or fallback to tool ID"""
    _logger.debug_info("enter args=%s", ascii({"tool": tool, "utilities": utilities}), tier=_logger.DEBUG_LOOP)
    title = None
    if utilities:
        _logger.debug_info("in if (utilities)", tier=_logger.DEBUG_LOOP)
        util = utilities.get(tool)
        if isinstance(util, dict):
            _logger.debug_info("in if (isinstance(util, dict))", tier=_logger.DEBUG_LOOP)
            manifest = util.get("manifest") or {}
            title = manifest.get("title")
            if title:
                _logger.debug_info("in if (title)", tier=_logger.DEBUG_LOOP)
                _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
                return str(title)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return tool


def _tool_icon_file(tool: str, utilities: Optional[dict] = None) -> str:
    """Extract utility relative icon path or fallback to empty string."""
    _logger.debug_info("enter args=%s", ascii({"tool": tool, "utilities": utilities}), tier=_logger.DEBUG_LOOP)
    if utilities:
        _logger.debug_info("in if (utilities)", tier=_logger.DEBUG_LOOP)
        util = utilities.get(tool)
        if isinstance(util, dict):
            _logger.debug_info("in if (isinstance(util, dict))", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
            return str(util.get("icon_rel") or "")
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return ""
