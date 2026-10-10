"""Settings > Python Libraries: interpreter info, pip search/install/uninstall."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.python_libraries import (
    python_environment as _py_environment,
    pypi_search as _pypi_search,
    pypi_install as _pypi_install,
    pypi_uninstall as _pypi_uninstall,
    refresh_pypi_index as _refresh_pypi_index,
    utility_dependencies as _utility_dependencies,
    pypi_progress as _pypi_progress,
    python_audit as _pypi_audit,
)

from .envelope import ResponseStatus
from core.debug_log import get_logger

_logger = get_logger(__name__)

if TYPE_CHECKING:
    class BaseApiHost:
        _utilities: dict[str, dict]
else:
    BaseApiHost = object


class PythonLibrariesBridgeMixin(BaseApiHost):
    """Python Libraries surface of the Api bridge."""

    def get_python_libraries(self, force: bool = False) -> dict:
        """Settings > Python Libraries: interpreter info and per-utility deps.

        The dependency status is cached (see ``utility_dependencies``) so
        reopening or switching away from the category reuses the last fetch;
        pass ``force=True`` right after an install/uninstall to recompute.
        """
        _logger.debug_info("enter args=%s", ascii({"force": force}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            env = _py_environment()
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            env = {
                "ok": False,
                "reason": str(exc),
            }
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            utilities = _utility_dependencies(self._utilities, force=bool(force))
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            utilities = [{"error": str(exc)}]
        env_ok = not (isinstance(env, dict) and env.get("ok") is False)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS if env_ok else ResponseStatus.WARNING,
            "detail": None if env_ok else str(env.get("reason") or "Python environment unavailable."),
            "environment": env,
            "utilities": utilities,
        }

    def get_pypi_progress(self) -> dict:
        """Live progress of the current pip install/uninstall, if any (``progress`` key)."""
        _logger.debug_info("enter", tier=_logger.DEBUG_FUNCTION)
        _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
        return {
            "ok": True,
            "reason": ResponseStatus.SUCCESS,
            "progress": _pypi_progress(),
        }

    def pypi_audit(self, force: bool = False) -> dict:
        """Settings > Python Libraries: re-run the vulnerability scan.

        Audits every installed package via pip-audit against the OSV/PyPI
        advisory database and returns ``{ok, state, total, affected,
        fetched_at}``. ``force=True`` bypasses the snapshot cache (the UI's
        "Scan now" button).
        """
        _logger.debug_info("enter args=%s", ascii({"force": force}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return _pypi_audit(force=bool(force))
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "state": "failed",
                "detail": str(exc),
            }

    def pypi_search(self, query: str, page: int = 1, per_page: int = 12,
                    force: bool = False) -> dict:
        """Search the cached PyPI Simple index; one enriched page of results.

        ``force=True`` bypasses the result snapshot cache (used after
        install/uninstall so installed/outdated badges refresh).
        """
        _logger.debug_info("enter args=%s", ascii({"query": query, "page": page, "per_page": per_page, "force": force}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return _pypi_search("" if query is None else str(query), page, per_page, force=bool(force))
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(exc),
            }

    def refresh_pypi_index(self, force: bool = True) -> dict:
        """Download/refresh the official PyPI Simple index cache used by search."""
        _logger.debug_info("enter args=%s", ascii({"force": force}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return _refresh_pypi_index(force=bool(force))
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(exc),
            }

    def pypi_install(self, package: str, scope: str = "local",
                     upgrade: bool = False, confirmed: bool = False,
                     batch_total: int = 1, batch_done: int = 0,
                     vuln_ack: bool = False) -> dict:
        """Install/upgrade a Python package via pip.

        * scope local (default): the app's own .venv (immediately importable).
        * scope global: the base/system interpreter (requires ``confirmed``).
        * batch_total/batch_done: overall progress across a bulk install.
        * vuln_ack: the candidate was pre-scanned with pip-audit and the user
          confirmed the two-step "Proceed anyway?" prompt.
        """
        _logger.debug_info("enter args=%s", ascii({"package": package, "scope": scope, "upgrade": upgrade, "confirmed": confirmed, "batch_total": batch_total, "batch_done": batch_done, "vuln_ack": vuln_ack}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return _pypi_install(str(package), scope=str(scope),
                                 upgrade=bool(upgrade), confirmed=bool(confirmed),
                                 batch_total=int(batch_total or 1),
                                 batch_done=int(batch_done or 0),
                                 vuln_ack=bool(vuln_ack))
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(exc),
            }

    def pypi_uninstall(self, package: str, scope: str = "local",
                       confirmed: bool = False, batch_total: int = 1,
                       batch_done: int = 0) -> dict:
        """Uninstall a Python package via pip (core app packages are protected)."""
        _logger.debug_info("enter args=%s", ascii({"package": package, "scope": scope, "confirmed": confirmed, "batch_total": batch_total, "batch_done": batch_done}), tier=_logger.DEBUG_FUNCTION)
        try:
            _logger.debug_info("in try", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return _pypi_uninstall(str(package), scope=str(scope),
                                   confirmed=bool(confirmed),
                                   batch_total=int(batch_total or 1),
                                   batch_done=int(batch_done or 0))
        except Exception as exc:
            _logger.debug_info("in except (Exception)", tier=_logger.DEBUG_FUNCTION)
            _logger.debug_info("exit", tier=_logger.DEBUG_FUNCTION)
            return {
                "ok": False,
                "reason": ResponseStatus.FAILED,
                "detail": str(exc),
            }
