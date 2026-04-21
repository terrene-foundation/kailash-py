# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``km.track()`` async-context entry point.

Implements ``specs/ml-tracking.md`` §2.1-§2.4 + §3 — the mandatory
clauses for the 1.0.0 tracker entry point:

- §2.1 construction via ``async with km.track(...) as run:``
- §2.4 17 mandatory auto-capture fields on run start
- §3.2 status transitions: RUNNING → {FINISHED, FAILED, KILLED}
- §3.3 SIGINT/SIGTERM handling — idempotent across nested runs
- §3.4 nested runs via ambient contextvar OR explicit parent_run_id
- §3.5 4-member enum byte-identical with kailash-rs (Decision 3)

This module is async-first and does NOT depend on the 0.x
``kailash_ml.engines.experiment_tracker.ExperimentTracker`` — the
older engine is preserved for back-compat; new callers use
``km.track()`` which gives a drastically smaller surface.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
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


#: Runtime statuses recorded per ``specs/ml-tracking.md`` §3.2 + §3.5.
class RunStatus:
    """String constants for the four run statuses per spec §3.2.

    Kept as module-level constants (not an Enum) so the on-disk
    representation matches the public vocabulary exactly without any
    ``.value`` unwrapping. The 4-member set
    ``{RUNNING, FINISHED, FAILED, KILLED}`` is byte-identical with
    kailash-rs ``RunStatus`` per Decision 3 (§3.5). Legacy values
    ``COMPLETED`` / ``SUCCESS`` / ``SUCCEEDED`` / ``CANCELLED`` /
    ``DONE`` are BLOCKED — legacy 0.x rows are hard-coerced to
    ``FINISHED`` by the ``1_0_0_rename_status`` numbered migration.
    """

    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    KILLED = "KILLED"


#: The only valid on-disk status values — used by asserts + tests.
_ALLOWED_STATUSES = frozenset(
    {RunStatus.RUNNING, RunStatus.FINISHED, RunStatus.FAILED, RunStatus.KILLED}
)


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


# ---------------------------------------------------------------------------
# Process-wide signal-handler coordination (spec §3.3)
# ---------------------------------------------------------------------------
#
# Spec §3.3 requires SIGINT/SIGTERM handling to be idempotent across
# nested runs. Installing the handler in every ``__aenter__`` would
# overwrite an outer handler with an inner one — the inner ``__aexit__``
# then restores the outer's copy, the outer's later ``__aexit__``
# restores whatever the inner thought was installed before it, and
# any user-level handler that predated the outermost run is lost.
#
# The defense: install the handler EXACTLY ONCE (at the first run's
# enter), track every currently-RUNNING run in a process-wide list,
# and restore the pre-enter handler when the last run exits. On a
# signal, we iterate the whole list and mark every active run as
# KILLED with ``killed_reason="signal.SIGINT"`` / ``"signal.SIGTERM"``
# before re-raising ``KeyboardInterrupt`` so the ``async with`` blocks
# unwind via normal exception machinery.

_signal_lock = threading.Lock()
#: Runs currently inside an ``async with km.track(...)`` block — append
#: on ``__aenter__``, remove on ``__aexit__``. Process-wide; module-
#: level so a single signal handler can see every outstanding run
#: regardless of which coroutine scheduled it.
_active_runs: list["ExperimentRun"] = []
_prev_sigint_handler: Any = None
_prev_sigterm_handler: Any = None
_sigint_installed: bool = False
_sigterm_installed: bool = False


def _process_kill_signal(signum: int, frame: Any) -> None:
    """Module-level signal handler.

    Marks every currently-active ``ExperimentRun`` as killed, records
    the signal name on each, and raises ``KeyboardInterrupt`` so the
    enclosing ``async with km.track(...)`` block unwinds. The reason
    string shape (``"signal.SIGINT"`` / ``"signal.SIGTERM"``) is fixed
    per spec §3.3 so alerting pipelines can filter on it.
    """
    sigint = signal.SIGINT
    sigterm = getattr(signal, "SIGTERM", None)
    reason: str
    if signum == sigint:
        reason = "signal.SIGINT"
    elif sigterm is not None and signum == sigterm:
        reason = "signal.SIGTERM"
    else:
        reason = f"signal.{signum}"
    with _signal_lock:
        for run in _active_runs:
            run._killed = True
            if run._killed_reason is None:
                run._killed_reason = reason
    raise KeyboardInterrupt()


def _install_signal_handlers_if_needed() -> None:
    """Install SIGINT + SIGTERM handlers idempotently.

    Only runs on the main thread (CPython restricts ``signal.signal``).
    On every subsequent call, checks the module-level ``_sigint_installed``
    / ``_sigterm_installed`` flags so nested runs do NOT re-install over
    our own handler — this is the install-once invariant of §3.3.
    """
    if not _threading_is_main():
        return
    global _prev_sigint_handler, _prev_sigterm_handler
    global _sigint_installed, _sigterm_installed
    with _signal_lock:
        if not _sigint_installed:
            try:
                _prev_sigint_handler = signal.signal(
                    signal.SIGINT, _process_kill_signal
                )
                _sigint_installed = True
            except (ValueError, OSError) as exc:
                logger.debug(
                    "tracking.signal.install_failed_sigint",
                    extra={"error": str(exc)},
                )
                _prev_sigint_handler = None
        sigterm = getattr(signal, "SIGTERM", None)
        if sigterm is not None and not _sigterm_installed:
            try:
                _prev_sigterm_handler = signal.signal(sigterm, _process_kill_signal)
                _sigterm_installed = True
            except (ValueError, OSError) as exc:
                logger.debug(
                    "tracking.signal.install_failed_sigterm",
                    extra={"error": str(exc)},
                )
                _prev_sigterm_handler = None


def _restore_signal_handlers_if_last() -> None:
    """Restore the pre-first-run handlers when no runs remain active."""
    if not _threading_is_main():
        return
    global _prev_sigint_handler, _prev_sigterm_handler
    global _sigint_installed, _sigterm_installed
    with _signal_lock:
        if _active_runs:
            return  # another run still pending — keep handler installed
        if _sigint_installed:
            try:
                signal.signal(
                    signal.SIGINT,
                    (
                        _prev_sigint_handler
                        if _prev_sigint_handler is not None
                        else signal.SIG_DFL
                    ),
                )
            except (ValueError, OSError):
                pass
            _sigint_installed = False
            _prev_sigint_handler = None
        sigterm = getattr(signal, "SIGTERM", None)
        if sigterm is not None and _sigterm_installed:
            try:
                signal.signal(
                    sigterm,
                    (
                        _prev_sigterm_handler
                        if _prev_sigterm_handler is not None
                        else signal.SIG_DFL
                    ),
                )
            except (ValueError, OSError):
                pass
            _sigterm_installed = False
            _prev_sigterm_handler = None


def _threading_is_main() -> bool:
    return threading.current_thread() is threading.main_thread()


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


def _capture_versions() -> dict[str, Optional[str]]:
    """Return the four library/runtime versions per ``ml-tracking.md`` §2.4.

    - ``kailash_ml_version`` — always ``kailash_ml.__version__`` (package is
      imported by definition here).
    - ``torch_version`` — ``torch.__version__`` when torch importable, else None.
    - ``cuda_version`` — ``torch.version.cuda`` when torch importable AND CUDA
      is reported; None otherwise (includes MPS/CPU-only hosts).
    - ``lightning_version`` — ``lightning.__version__`` when lightning is
      importable, else None.

    Every probe is wrapped separately so a partial stack (torch without
    CUDA, lightning missing) still yields as many fields as possible.
    """
    # kailash_ml — always present at this point (we're inside its package).
    try:
        from kailash_ml import __version__ as kml_version  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — probe must not raise
        kml_version = None

    torch_version: Optional[str] = None
    cuda_version: Optional[str] = None
    try:
        import torch  # noqa: PLC0415

        torch_version = getattr(torch, "__version__", None)
        cuda_version = getattr(getattr(torch, "version", None), "cuda", None)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("tracking.torch.probe_failed", extra={"error": str(exc)})

    lightning_version: Optional[str] = None
    try:
        import lightning  # noqa: PLC0415

        lightning_version = getattr(lightning, "__version__", None)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("tracking.lightning.probe_failed", extra={"error": str(exc)})

    return {
        "kailash_ml_version": kml_version,
        "torch_version": torch_version,
        "cuda_version": cuda_version,
        "lightning_version": lightning_version,
    }


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
        # Top-level TrainingResult mirrors — populated by
        # attach_training_result when the caller wires a Trainable. The
        # field names mirror TrainingResult's own surface per
        # ``specs/ml-tracking.md`` §2.4 — ``device_used`` / ``accelerator``
        # / ``precision`` live here alongside the ``device.*`` DeviceReport
        # fields so both surfaces persist and a stale-read never conflates
        # them.
        self._device_used: Optional[str] = None
        self._accelerator: Optional[str] = None
        self._precision: Optional[str] = None
        # Library/runtime versions — captured eagerly at construction
        # because they are process-wide constants. Probed at
        # ``__aenter__`` because construction order vs import order is
        # not guaranteed; deferring until the context opens gives
        # torch/lightning their best chance of being importable.
        self._kailash_ml_version: Optional[str] = None
        self._lightning_version: Optional[str] = None
        self._torch_version: Optional[str] = None
        self._cuda_version: Optional[str] = None
        # Wall-clock fields populated at __aenter__ / __aexit__.
        self._wall_clock_start: Optional[datetime] = None
        self._wall_clock_end: Optional[datetime] = None
        # Signal-handling state — set from the module-level handler
        # when a SIGINT / SIGTERM fires during an active run. Per spec
        # §3.3 the reason string shape is fixed so alerting pipelines
        # can filter on it.
        self._killed = False
        self._killed_reason: Optional[str] = None
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
        # Top-level TrainingResult fields — always populate when
        # non-empty (spec §2.4 rows 11-13: ``device_used`` /
        # ``accelerator`` / ``precision`` come from TrainingResult's
        # own fields, not the DeviceReport envelope).
        if result.device_used:
            self._device_used = result.device_used
        if result.accelerator:
            self._accelerator = result.accelerator
        if result.precision:
            self._precision = result.precision

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

        # Library/runtime version probes (spec §2.4 rows 5-8).
        versions = _capture_versions()
        self._kailash_ml_version = versions["kailash_ml_version"]
        self._lightning_version = versions["lightning_version"]
        self._torch_version = versions["torch_version"]
        self._cuda_version = versions["cuda_version"]

        row = {
            "run_id": self.run_id,
            "experiment": self.experiment,
            "parent_run_id": self.parent_run_id,
            "status": RunStatus.RUNNING,
            "host": socket.gethostname(),
            "python_version": sys.version.split()[0],
            "kailash_ml_version": self._kailash_ml_version,
            "lightning_version": self._lightning_version,
            "torch_version": self._torch_version,
            "cuda_version": self._cuda_version,
            "git_sha": sha,
            "git_branch": branch,
            "git_dirty": dirty,
            "wall_clock_start": self._wall_clock_start.isoformat(),
            "wall_clock_end": None,
            "duration_seconds": None,
            "tenant_id": self.tenant_id,
            "device_used": self._device_used,
            "accelerator": self._accelerator,
            "precision": self._precision,
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

        # Register with the process-level active-run list and install
        # signal handlers exactly once per process. Nested runs see
        # the handler already installed and skip re-installation — this
        # is the idempotence invariant of spec §3.3 / W11 invariant 5.
        with _signal_lock:
            _active_runs.append(self)
        _install_signal_handlers_if_needed()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        # Pop self from the active-run list BEFORE restoring handlers
        # so the restore check "is the list empty" sees the right state.
        with _signal_lock:
            try:
                _active_runs.remove(self)
            except ValueError:
                # Defensive — should never happen because __aenter__
                # appends unconditionally, but a partially-initialised
                # run (insert_run failed before append) would miss it.
                pass
        _restore_signal_handlers_if_last()

        # Release contextvar binding
        if self._ctx_token is not None:
            _current_run.reset(self._ctx_token)
            self._ctx_token = None

        self._wall_clock_end = _now_utc()
        assert self._wall_clock_start is not None  # set in __aenter__
        duration = max(
            0.0, (self._wall_clock_end - self._wall_clock_start).total_seconds()
        )

        # Status transition per spec §3.2:
        #   no exception   → FINISHED
        #   CancelledError → KILLED (async equivalent of signal)
        #   _killed flag   → KILLED (SIGINT/SIGTERM fired while inside)
        #   KeyboardInterrupt → KILLED (signal propagated as KI)
        #   any other      → FAILED (exception re-raised)
        if exc_type is None:
            status = RunStatus.FINISHED
            err_type: Optional[str] = None
            err_msg: Optional[str] = None
        elif (
            self._killed
            or exc_type is KeyboardInterrupt
            or (exc_type is not None and issubclass(exc_type, asyncio.CancelledError))
        ):
            status = RunStatus.KILLED
            if exc_type is asyncio.CancelledError and self._killed_reason is None:
                self._killed_reason = "asyncio.CancelledError"
            elif self._killed_reason is None:
                # KeyboardInterrupt without a signal handler firing is
                # indistinguishable from SIGINT at this layer — record
                # the best-effort reason rather than leaving None.
                self._killed_reason = "signal.SIGINT"
            err_type = exc_type.__name__ if exc_type else "KeyboardInterrupt"
            err_msg = (
                _short_traceback(exc_val)
                if exc_val is not None
                else self._killed_reason
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
                "device_used": self._device_used,
                "accelerator": self._accelerator,
                "precision": self._precision,
                "device_family": self._device_family,
                "device_backend": self._device_backend,
                "device_fallback_reason": self._device_fallback_reason,
                "device_array_api": self._device_array_api,
                "params": self._params,
                "error_type": err_type,
                "error_message": err_msg,
            },
        )
        # Do NOT suppress exceptions (spec §3.2) — return None / falsy.
        return None


# ---------------------------------------------------------------------------
# Public factory — ``km.track(...)``
# ---------------------------------------------------------------------------


@asynccontextmanager
async def track(
    experiment: str,
    *,
    backend: Optional[SQLiteTrackerBackend] = None,
    tenant_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    store: Optional[str] = None,
    **params: Any,
) -> AsyncIterator[ExperimentRun]:
    """Async-context experiment tracker.

    Example::

        import kailash_ml as km
        async with km.track("cart-abandonment-v3", lr=0.01) as run:
            # train ...
            await run.log_param("batch_size", 64)

    Per ``specs/ml-tracking.md`` §3.2 the context manager auto-sets
    status on exit:

    - ``FINISHED`` on clean exit
    - ``FAILED`` on exception (exception re-raised)
    - ``KILLED`` on SIGINT / SIGTERM / :class:`asyncio.CancelledError`

    And per §2.4 auto-captures the 17 mandatory fields on run start.

    Args:
        experiment: Experiment name (user-chosen grouping key).
        backend: An explicit :class:`SQLiteTrackerBackend` instance. If
            omitted, a backend is created on the default store path
            (``~/.kailash_ml/ml.db``) OR the ``store`` URI if provided.
        tenant_id: Optional tenant id. If omitted, falls back to the
            ``KAILASH_TENANT_ID`` env var; if still absent, runs as
            single-tenant.
        parent_run_id: Explicit parent run id (spec §3.1 MUST honor).
            When omitted, the ambient run from
            :func:`kailash_ml.tracking.get_current_run` is used so
            nested ``async with km.track(...)`` calls link
            automatically (§3.4).
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
    # Explicit parent_run_id wins per spec §3.4; fall back to the
    # ambient contextvar so sibling specs' example
    # ``async with km.track("sweep") as parent: async with km.track("trial")``
    # picks up the outer run without plumbing.
    resolved_parent: Optional[str]
    if parent_run_id is not None and parent_run_id != "":
        resolved_parent = parent_run_id
    else:
        parent = _current_run.get()
        resolved_parent = parent.run_id if parent is not None else None
    run = ExperimentRun(
        experiment=experiment,
        backend=backend,
        params=params,
        tenant_id=resolved_tenant,
        parent_run_id=resolved_parent,
    )
    try:
        async with run as entered:
            yield entered
    finally:
        if owns_backend and backend is not None:
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


def _short_traceback(exc: Optional[BaseException]) -> str:
    """Return a compact ``type: msg\\n...`` string for error storage."""
    if exc is None:
        return ""
    lines = traceback.format_exception_only(type(exc), exc)
    return "".join(lines).strip()
