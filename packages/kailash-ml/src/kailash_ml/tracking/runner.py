# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``km.track()`` async-context entry point.

Implements ``specs/ml-tracking.md`` §2.1-§2.4 — the three mandatory
clauses for the Phase 6 tracker entry point:

- §2.1 construction via ``async with km.track(...) as run:``
- §2.2 auto-set status: RUNNING / COMPLETED / FAILED / KILLED
- §2.4 16 mandatory auto-capture fields on run start

This module is async-first and does NOT depend on the 1.x
``kailash_ml.engines.experiment_tracker.ExperimentTracker`` — the
older engine is preserved for back-compat; new callers use
``km.track()`` which gives a drastically smaller surface.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import platform
import signal
import socket
import subprocess
import sys
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Optional

from kailash_ml._device_report import DeviceReport
from kailash_ml._result import TrainingResult
from kailash_ml.tracking.sqlite_backend import SQLiteTrackerBackend

__all__ = [
    "ExperimentRun",
    "RunStatus",
    "track",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants and run-status vocabulary
# ---------------------------------------------------------------------------


#: Runtime statuses recorded per ``specs/ml-tracking.md`` §2.2.
class RunStatus:
    """String constants for the four run statuses per spec §2.2.

    Kept as module-level constants (not an Enum) so the on-disk
    representation in the SQLite backend matches the public vocabulary
    exactly without any ``.value`` unwrapping.
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    KILLED = "KILLED"


_DEFAULT_TRACKER_DIR = Path.home() / ".kailash_ml"
_DEFAULT_TRACKER_DB = _DEFAULT_TRACKER_DIR / "ml.db"


# ---------------------------------------------------------------------------
# Contextvars — parent-run propagation + tenant-id override
# ---------------------------------------------------------------------------

#: The currently-active ``ExperimentRun``, scoped via :mod:`contextvars`
#: so nested ``async with km.track(...)`` calls pick up the correct
#: parent_run_id without callers threading it manually.
_current_run: contextvars.ContextVar[Optional["ExperimentRun"]] = (
    contextvars.ContextVar("kailash_ml_current_run", default=None)
)


def _resolve_tenant_id(explicit: Optional[str]) -> Optional[str]:
    """Return the effective tenant_id for a new run.

    Priority: explicit kwarg > ``KAILASH_TENANT_ID`` env var > ``None``.
    """
    if explicit is not None and explicit != "":
        return explicit
    from_env = os.environ.get("KAILASH_TENANT_ID")
    if from_env:
        return from_env
    return None


# ---------------------------------------------------------------------------
# Auto-capture helpers (spec §2.4 — 16 mandatory fields)
# ---------------------------------------------------------------------------


def _capture_git_state(
    cwd: Optional[Path] = None,
) -> tuple[Optional[str], Optional[str], Optional[bool]]:
    """Return ``(sha, branch, dirty)`` or ``(None, None, None)`` if no git.

    Each probe is wrapped separately so a partial git state (detached
    HEAD with no branch) still returns the SHA. Subprocess failures are
    logged at DEBUG — git absence is normal in CI / Docker.
    """

    def _run(args: list[str]) -> Optional[str]:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                cwd=str(cwd) if cwd else None,
                check=False,
                text=True,
                timeout=5.0,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            logger.debug(
                "tracking.git.probe_failed", extra={"args": args, "error": str(exc)}
            )
            return None
        if proc.returncode != 0:
            return None
        out = proc.stdout.strip()
        return out or None

    sha = _run(["git", "rev-parse", "HEAD"])
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    porcelain = _run(["git", "status", "--porcelain"])
    dirty: Optional[bool]
    if sha is None:
        dirty = None
    else:
        # porcelain may be None when the subprocess fails even though
        # rev-parse succeeded — treat that as unknown (None) rather
        # than falsely-clean False.
        dirty = bool(porcelain) if porcelain is not None else None
    return sha, branch, dirty


def _now_utc() -> datetime:
    """Wall-clock UTC timestamp — isolated for test patching."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ExperimentRun — the async context manager yielded by km.track()
# ---------------------------------------------------------------------------


class ExperimentRun:
    """A single experiment run.

    Created by :func:`track` (and therefore ``km.track()``). Callers
    MUST NOT construct directly — the async-context entry point is the
    only path that guarantees status transitions and SIGINT
    installation.

    Exposed fields:

    - :attr:`run_id` — UUIDv4 string, stable for the run's lifetime.
    - :attr:`experiment` — the experiment name passed to ``track()``.
    - :attr:`parent_run_id` — when nested inside another run, else
      ``None``.
    - :attr:`tenant_id` — resolved per ``_resolve_tenant_id``.

    Logging primitives: :meth:`log_param`, :meth:`log_params`,
    :meth:`attach_training_result`.
    """

    def __init__(
        self,
        *,
        experiment: str,
        backend: SQLiteTrackerBackend,
        params: Mapping[str, Any],
        tenant_id: Optional[str],
        parent_run_id: Optional[str],
    ) -> None:
        self.experiment = experiment
        self.run_id = str(uuid.uuid4())
        self.parent_run_id = parent_run_id
        self.tenant_id = tenant_id
        self._backend = backend
        # Accumulated params — the constructor kwargs form the initial
        # set and callers can add more via log_param / log_params.
        self._params: dict[str, Any] = {str(k): v for k, v in params.items()}
        # Device fields populated when ``attach_training_result`` is
        # called OR at ``__aexit__`` if a TrainingResult was injected
        # through the context-local helper.
        self._device_family: Optional[str] = None
        self._device_backend: Optional[str] = None
        self._device_fallback_reason: Optional[str] = None
        self._device_array_api: Optional[bool] = None
        # Wall-clock fields populated at __aenter__ / __aexit__.
        self._wall_clock_start: Optional[datetime] = None
        self._wall_clock_end: Optional[datetime] = None
        # Signal-handling state
        self._prev_sigint_handler: Any = None
        self._prev_sigterm_handler: Any = None
        self._killed = False
        # Contextvar token for parent-run propagation
        self._ctx_token: Any = None

    # ------------------------------------------------------------------
    # Logging primitives
    # ------------------------------------------------------------------

    async def log_param(self, key: str, value: Any) -> None:
        """Record a single param. Persisted immediately."""
        self._params[str(key)] = value
        await self._backend.set_params(self.run_id, self._params)

    async def log_params(self, params: Mapping[str, Any]) -> None:
        """Record multiple params. Persisted immediately."""
        for k, v in params.items():
            self._params[str(k)] = v
        await self._backend.set_params(self.run_id, self._params)

    def attach_training_result(self, result: TrainingResult) -> None:
        """Populate device fields from a ``TrainingResult``.

        Called by the Trainable fit path (directly or through the
        MLEngine auto-logger) so the DB row records the actual
        resolved device rather than leaving it ``None``.

        Per ``specs/ml-tracking.md`` §2.4, device fields are sourced
        from ``TrainingResult.device`` (a :class:`DeviceReport`) when
        present; older results that predate the DeviceReport field
        leave the fields ``None``.
        """
        device: Optional[DeviceReport] = result.device
        if device is not None:
            self._device_family = device.family
            self._device_backend = device.backend
            self._device_fallback_reason = device.fallback_reason
            self._device_array_api = bool(device.array_api)
        elif result.device_used:
            # Older Trainables without a full DeviceReport still set
            # TrainingResult.device_used — treat that string as the
            # backend so the tracker row is not empty.
            self._device_backend = result.device_used
            self._device_family = result.family

    # ------------------------------------------------------------------
    # Lifecycle: async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ExperimentRun":
        self._wall_clock_start = _now_utc()
        sha, branch, dirty = _capture_git_state()
        # Inherit parent-run id via contextvar if not explicitly set
        if self.parent_run_id is None:
            parent = _current_run.get()
            if parent is not None:
                self.parent_run_id = parent.run_id

        row = {
            "run_id": self.run_id,
            "experiment": self.experiment,
            "parent_run_id": self.parent_run_id,
            "status": RunStatus.RUNNING,
            "host": socket.gethostname(),
            "python_version": sys.version.split()[0],
            "git_sha": sha,
            "git_branch": branch,
            "git_dirty": dirty,
            "wall_clock_start": self._wall_clock_start.isoformat(),
            "wall_clock_end": None,
            "duration_seconds": None,
            "tenant_id": self.tenant_id,
            "device_family": self._device_family,
            "device_backend": self._device_backend,
            "device_fallback_reason": self._device_fallback_reason,
            "device_array_api": self._device_array_api,
            "params": self._params,
            "error_type": None,
            "error_message": None,
        }
        await self._backend.insert_run(row)

        # Bind contextvar so nested km.track() calls link properly.
        self._ctx_token = _current_run.set(self)

        # Install SIGINT / SIGTERM handlers for the KILLED status
        # transition. Signal handlers can only be installed on the
        # main thread in CPython — guard so worker-thread use does not
        # raise ``ValueError: signal only works in main thread``.
        if threading_is_main():
            try:
                self._prev_sigint_handler = signal.signal(
                    signal.SIGINT, self._on_kill_signal
                )
            except (ValueError, OSError) as exc:
                # Rare — e.g. running inside a subinterpreter where
                # signal installation is not permitted. Log and
                # continue; the block still records FAILED via the
                # exception path if the interrupt surfaces as
                # KeyboardInterrupt.
                logger.debug(
                    "tracking.signal.install_failed_sigint", extra={"error": str(exc)}
                )
                self._prev_sigint_handler = None
            # SIGTERM is POSIX-only — guard for Windows where some
            # SIG_* constants are not present.
            sigterm = getattr(signal, "SIGTERM", None)
            if sigterm is not None:
                try:
                    self._prev_sigterm_handler = signal.signal(
                        sigterm, self._on_kill_signal
                    )
                except (ValueError, OSError) as exc:
                    logger.debug(
                        "tracking.signal.install_failed_sigterm",
                        extra={"error": str(exc)},
                    )
                    self._prev_sigterm_handler = None
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        # Restore signal handlers first so finalisation never runs
        # with our handler still installed.
        if threading_is_main():
            if self._prev_sigint_handler is not None:
                try:
                    signal.signal(signal.SIGINT, self._prev_sigint_handler)
                except (ValueError, OSError):
                    pass
            sigterm = getattr(signal, "SIGTERM", None)
            if sigterm is not None and self._prev_sigterm_handler is not None:
                try:
                    signal.signal(sigterm, self._prev_sigterm_handler)
                except (ValueError, OSError):
                    pass
        # Release contextvar binding
        if self._ctx_token is not None:
            _current_run.reset(self._ctx_token)
            self._ctx_token = None

        self._wall_clock_end = _now_utc()
        assert self._wall_clock_start is not None  # set in __aenter__
        duration = max(
            0.0, (self._wall_clock_end - self._wall_clock_start).total_seconds()
        )

        if exc_type is None:
            status = RunStatus.COMPLETED
            err_type: Optional[str] = None
            err_msg: Optional[str] = None
        elif self._killed or exc_type is KeyboardInterrupt:
            status = RunStatus.KILLED
            err_type = exc_type.__name__ if exc_type else "KeyboardInterrupt"
            err_msg = (
                _short_traceback(exc_val) if exc_val is not None else "interrupted"
            )
        else:
            status = RunStatus.FAILED
            err_type = exc_type.__name__
            err_msg = _short_traceback(exc_val)

        await self._backend.update_run(
            self.run_id,
            {
                "status": status,
                "wall_clock_end": self._wall_clock_end.isoformat(),
                "duration_seconds": duration,
                "device_family": self._device_family,
                "device_backend": self._device_backend,
                "device_fallback_reason": self._device_fallback_reason,
                "device_array_api": self._device_array_api,
                "params": self._params,
                "error_type": err_type,
                "error_message": err_msg,
            },
        )
        # Do NOT suppress exceptions (spec §2.2) — return None / falsy.
        return None

    def _on_kill_signal(self, signum: int, frame: Any) -> None:
        """Signal handler — mark the run KILLED and re-raise KeyboardInterrupt.

        Installed for SIGINT / SIGTERM on ``__aenter__``. We flip the
        ``_killed`` flag so ``__aexit__`` records ``KILLED`` status
        regardless of how the exception surfaces, then raise
        ``KeyboardInterrupt`` so the ``async with`` block unwinds
        cleanly.
        """
        self._killed = True
        # Chain to previous SIGINT handler when one existed — some
        # runtimes (pytest-timeout, asyncio) rely on default SIGINT
        # semantics.
        raise KeyboardInterrupt()


# ---------------------------------------------------------------------------
# Public factory — ``km.track(...)``
# ---------------------------------------------------------------------------


@asynccontextmanager
async def track(
    experiment: str,
    *,
    backend: Optional[SQLiteTrackerBackend] = None,
    tenant_id: Optional[str] = None,
    store: Optional[str] = None,
    **params: Any,
) -> AsyncIterator[ExperimentRun]:
    """Async-context experiment tracker.

    Example::

        import kailash_ml as km
        async with km.track("cart-abandonment-v3", lr=0.01) as run:
            # train ...
            await run.log_param("batch_size", 64)

    Per ``specs/ml-tracking.md`` §2.2 the context manager auto-sets
    status on exit:

    - ``COMPLETED`` on clean exit
    - ``FAILED`` on exception (exception re-raised)
    - ``KILLED`` on SIGINT / SIGTERM

    And per §2.4 auto-captures the 16 mandatory fields on run start.

    Args:
        experiment: Experiment name (user-chosen grouping key).
        backend: An explicit :class:`SQLiteTrackerBackend` instance. If
            omitted, a backend is created on the default store path
            (``~/.kailash_ml/ml.db``) OR the ``store`` URI if provided.
        tenant_id: Optional tenant id. If omitted, falls back to the
            ``KAILASH_TENANT_ID`` env var; if still absent, runs as
            single-tenant.
        store: Override the default SQLite path. Accepts either a raw
            path (``"/tmp/ml.db"``), ``":memory:"``, or a
            ``sqlite:///...`` URI. Ignored when ``backend`` is given.
        **params: Arbitrary serialisable params logged at run start.
    """
    owns_backend = False
    if backend is None:
        backend = SQLiteTrackerBackend(_resolve_store_path(store))
        owns_backend = True
    resolved_tenant = _resolve_tenant_id(tenant_id)
    parent = _current_run.get()
    parent_run_id = parent.run_id if parent is not None else None
    run = ExperimentRun(
        experiment=experiment,
        backend=backend,
        params=params,
        tenant_id=resolved_tenant,
        parent_run_id=parent_run_id,
    )
    try:
        async with run as entered:
            yield entered
    finally:
        if owns_backend:
            await backend.close()


def _resolve_store_path(store: Optional[str]) -> str:
    """Convert optional ``store`` URI or path into a SQLite-ready path."""
    if store is None or store == "":
        return str(_DEFAULT_TRACKER_DB)
    if store == ":memory:":
        return ":memory:"
    if store.startswith("sqlite:///"):
        return store[len("sqlite:///") :] or ":memory:"
    if store.startswith("sqlite+memory"):
        return ":memory:"
    return store


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def threading_is_main() -> bool:
    """Return True iff the current thread is the main thread.

    Signal installation is main-thread-only in CPython; call this
    before ``signal.signal(...)``.
    """
    import threading

    return threading.current_thread() is threading.main_thread()


def _short_traceback(exc: Optional[BaseException]) -> str:
    """Return a compact ``type: msg\\n...`` string for error storage."""
    if exc is None:
        return ""
    lines = traceback.format_exception_only(type(exc), exc)
    return "".join(lines).strip()
