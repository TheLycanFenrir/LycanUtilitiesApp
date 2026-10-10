"""Standard status envelope for every public Api method.

Contract for EVERY public method (enforced by ``_api_response``):

  {
    "ok":     True | False,
    "reason": "SUCCESS" | "WARNING" | "FAILED" | "INFO",
    "detail": str | None,      # optional human/machine explanation
    ...payload kwargs...       # e.g. settings, tools, paths, job_id
  }

Machine-readable sub-codes ("not_queued", "internet_disabled", ...) travel
in the optional "code" kwarg so "reason" always stays a status token.
"""

from __future__ import annotations

import functools
from enum import Enum
from typing import Any

from core.debug_log import get_logger

# Console/file logger for bridge diagnostics (core/debug_log.py).
_logger = get_logger(__name__)


class ResponseStatus(str, Enum):
    """Canonical status tokens for the standard response envelope.

    Subclasses ``str`` so members compare and hash equal to their plain-string
    values (legacy ``reason`` strings from other modules match the tokens);
    ``_api_envelope`` always serializes them via ``.value`` so the JSON payload
    crossing to the frontend stays a plain string.
    """

    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"
    INFO = "INFO"


_STATUS_REASONS = frozenset(status.value for status in ResponseStatus)


def _api_envelope(result: Any) -> dict:
    """Normalize a raw return value into the standard status envelope.

    * non-dict returns and dicts without ``ok`` are treated as successes;
    * a legacy free-text ``reason`` is preserved as ``code`` (and as ``detail``
      when no detail was supplied) before ``reason`` is rewritten to a token;
    * failures always carry a ``detail``.
    """
    _logger.debug_info("enter args=%s", ascii({"result": result}), tier=_logger.DEBUG_LOOP)
    if not isinstance(result, dict):
        _logger.debug_info("in if (not isinstance(result, dict))", tier=_logger.DEBUG_LOOP)
        _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS.value,
            "detail": None,
            "data": result,
        }
    out = dict(result)
    ok = bool(out.get("ok", True))
    reason = out.get("reason")
    if reason not in _STATUS_REASONS:
        _logger.debug_info("in if (reason not in _STATUS_REASONS)", tier=_logger.DEBUG_LOOP)
        if reason is not None:
            _logger.debug_info("in if (reason is not None)", tier=_logger.DEBUG_LOOP)
            if not out.get("code"):
                _logger.debug_info("in if (not out.get(\"code\"))", tier=_logger.DEBUG_LOOP)
                out["code"] = str(reason)
            if not out.get("detail"):
                _logger.debug_info("in if (not out.get(\"detail\"))", tier=_logger.DEBUG_LOOP)
                out["detail"] = str(reason)
        reason = ResponseStatus.SUCCESS if ok else ResponseStatus.FAILED
    out["ok"] = ok
    out["reason"] = ResponseStatus(reason).value
    if out.get("detail") is None and not ok:
        _logger.debug_info("in if (out.get(\"detail\") is None and not ok)", tier=_logger.DEBUG_LOOP)
        out["detail"] = str(out.get("code") or "Request failed.")
    out.setdefault("detail", None)
    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return out


def _api_response(func):
    """Decorator applied to every public ``Api`` method (see loop in app.bridge).

    Guarantees the standardized status envelope for every return value and
    converts any unexpected exception into
    ``{"ok": False, "reason": "FAILED", "detail": str(exc)}`` while logging it
    through the bridge logger. Underscored (internal) methods are never
    wrapped and keep their raw return types.
    """

    _logger.debug_info("enter args=%s", ascii({"func": func}), tier=_logger.DEBUG_LOOP)
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        _logger.debug_info("_api_response.wrapper: enter args=%s", ascii({"args": args, "kwargs": kwargs}), tier=_logger.DEBUG_LOOP)
        try:
            _logger.debug_info("_api_response.wrapper: in try", tier=_logger.DEBUG_LOOP)
            _logger.debug_info("_api_response.wrapper: exit", tier=_logger.DEBUG_LOOP)
            return _api_envelope(func(self, *args, **kwargs))
        except Exception as exc:
            _logger.debug_info("_api_response.wrapper: in except (Exception)", tier=_logger.DEBUG_LOOP)
            _logger.exception("bridge.%s raised an unexpected exception", func.__name__)
            _logger.debug_info("_api_response.wrapper: exit", tier=_logger.DEBUG_LOOP)
            return _api_envelope({
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(exc),
            })

    _logger.debug_info("exit", tier=_logger.DEBUG_LOOP)
    return wrapper
