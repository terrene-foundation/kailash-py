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
import hashlib
import io
import json
import logging
import math
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import traceback
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Optional, Union

from kailash_ml._device_report import DeviceReport
from kailash_ml._result import TrainingResult
from kailash_ml.errors import (
    MetricValueError,
    ModelSignatureRequiredError,
    ParamValueError,
    TrackingError,
)
from kailash_ml.tracking.storage import AbstractTrackerStore, SqliteTrackerStore

__all__ = [
    "ArtifactHandle",
    "ExperimentRun",
    "ModelVersionInfo",
    "RunStatus",
    "track",
]


# ---------------------------------------------------------------------------
# W12 — value objects returned by logging primitives
# ---------------------------------------------------------------------------

#: Regex for param / metric / tag keys per spec §4.1 + §4.7.
_KEY_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.\-]*$")
#: Tag keys are stricter: lowercase + digits + underscore (spec §4.7 / W12 invariant 8).
_TAG_KEY_REGEX = re.compile(r"^[a-z_][a-z_0-9]*$")


@dataclass(frozen=True)
class ArtifactHandle:
    """Handle returned by :meth:`ExperimentRun.log_artifact` / ``log_figure``.

    Content-addressed per spec §4.3 — two calls with identical bytes
    return handles with the same ``sha256`` and the same ``storage_uri``.
    """

    name: str
    sha256: str
    storage_uri: str
    size_bytes: int
    content_type: Optional[str]


@dataclass(frozen=True)
class ModelVersionInfo:
    """Return value of :meth:`ExperimentRun.log_model` (spec §4.5).

    W12 emits a run-scoped snapshot; the cross-run :class:`ModelRegistry`
    lineage lives in W16 and is NOT populated by ``log_model``.
    """

    name: str
    format: str
    artifact_sha: str
    run_id: str


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
# Contextvars — parent-run + tenant + actor (spec §10.1 + §10.2 + §8.1)
# ---------------------------------------------------------------------------

#: The currently-active ``ExperimentRun``, scoped via :mod:`contextvars`
#: so nested ``async with km.track(...)`` calls pick up the correct
#: parent_run_id without callers threading it manually.
_current_run: contextvars.ContextVar[Optional["ExperimentRun"]] = (
    contextvars.ContextVar("kailash_ml_current_run", default=None)
)

#: Tenant id for the active ``km.track(...)`` scope per
#: ``specs/ml-tracking.md`` §10.2. Consumers read through the public
#: accessor :func:`kailash_ml.tracking.get_current_tenant_id`; direct
#: access to this symbol from outside the ``tracking`` package is
#: BLOCKED per §10.1.
_current_tenant_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "kailash_ml_current_tenant_id", default=None
)

#: Actor id for the active ``km.track(...)`` scope per spec §8.1.
#: Session-level property (NOT a per-call kwarg on mutation primitives —
#: HIGH-4 round-1 finding). Public accessor:
#: :func:`kailash_ml.tracking.get_current_actor_id`.
_current_actor_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "kailash_ml_current_actor_id", default=None
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

    Priority: explicit kwarg > ambient contextvar > ``KAILASH_TENANT_ID``
    env var > ``None``. The contextvar layer lets nested
    ``km.track(...)`` calls inherit the outer tenant without callers
    re-passing it (spec §10.2 + §7.2 resolution order).
    """
    if explicit is not None and explicit != "":
        return explicit
    ambient = _current_tenant_id.get()
    if ambient is not None and ambient != "":
        return ambient
    from_env = os.environ.get("KAILASH_TENANT_ID")
    if from_env:
        return from_env
    return None


def _resolve_actor_id(explicit: Optional[str]) -> Optional[str]:
    """Return the effective actor_id for a new run (spec §8.1).

    Priority: explicit kwarg > ambient contextvar > ``KAILASH_ACTOR_ID``
    env var > ``None``. Per HIGH-4 round-1 finding, ``actor_id`` is a
    session-level property plumbed via contextvar — MUST NOT surface as
    a per-call kwarg on mutation primitives (the only exception is the
    MCP boundary, where no contextvar crosses the process boundary).
    """
    if explicit is not None and explicit != "":
        return explicit
    ambient = _current_actor_id.get()
    if ambient is not None and ambient != "":
        return ambient
    from_env = os.environ.get("KAILASH_ACTOR_ID")
    if from_env:
        return from_env
    return None


# ---------------------------------------------------------------------------
# W12 — rank-0 guard + finite-check + key validation helpers
# ---------------------------------------------------------------------------


def _is_rank_zero() -> bool:
    """Return True unless the process is a non-zero rank in a DDP/FSDP job.

    Per ``specs/ml-tracking.md`` §4 + Decision 4, every logging primitive
    MUST be a no-op on non-rank-0 workers so the tracker backend is
    written exactly once per run even in multi-GPU training. When torch
    is not importable OR ``torch.distributed`` is not initialised, the
    process is single-process by definition — always rank 0.
    """
    try:
        import torch.distributed as dist  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — absence / import errors are expected
        return True
    try:
        if not dist.is_available() or not dist.is_initialized():
            return True
        return int(dist.get_rank()) == 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("tracking.ddp.rank_probe_failed", extra={"error": str(exc)})
        return True


def _validate_key(kind: str, key: str) -> None:
    """Validate a param / metric / tag key per spec §4.1."""
    if not isinstance(key, str) or not _KEY_REGEX.match(key):
        raise TrackingError(
            reason=f"{kind} key {key!r} must match {_KEY_REGEX.pattern}"
        )


def _validate_tag_key(key: str) -> None:
    """Validate a tag key per W12 invariant 8 (lowercase + _ + digits)."""
    if not isinstance(key, str) or not _TAG_KEY_REGEX.match(key):
        raise TrackingError(
            reason=f"tag key {key!r} must match {_TAG_KEY_REGEX.pattern}"
        )


def _validate_metric_value(key: str, value: Any) -> float:
    """Coerce + finite-check a metric value per spec §4.2."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricValueError(
            reason=f"metric {key!r} must be numeric, got {type(value).__name__}"
        )
    v = float(value)
    if not math.isfinite(v):
        raise MetricValueError(reason=f"metric {key!r} value={v} is not finite")
    return v


def _validate_param_value(key: str, value: Any) -> Any:
    """Finite-check a numeric param value per spec §4.1.

    Non-numeric params pass through unchanged; numeric params must be
    finite — NaN / ±Inf are rejected so downstream `params->>'key' = ?`
    comparison queries stay correct.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        v = float(value)
        if not math.isfinite(v):
            raise ParamValueError(reason=f"param {key!r} value={v} is not finite")
    return value


def _hash_and_materialise_artifact(
    artifact_root: Optional[str],
    payload: Union[bytes, str, Path],
) -> tuple[bytes, str, int, str]:
    """Return ``(bytes, sha256, size, storage_uri)`` for an artifact payload.

    ``artifact_root`` is the directory the backend dedicates to
    content-addressed blobs (``AbstractTrackerStore.artifact_root``).
    A backend returning ``None`` — e.g. a future S3-backed store
    without a local mirror — raises :class:`TrackingError` here per
    spec §4.3.

    When ``payload`` is bytes, the bytes are hashed + written to a
    content-addressed path under the root. When ``payload`` is a path,
    the file contents are read + hashed. The returned ``storage_uri``
    is the absolute path the bytes were persisted to; callers record
    it verbatim in ``experiment_artifacts``.
    """
    if artifact_root is None:
        raise TrackingError(
            "backend.artifact_root is None — this backend does not "
            "support local artifact materialisation; supply a write-"
            "through artifact store (W17)"
        )
    if isinstance(payload, (str, Path)):
        path = Path(payload)
        if not path.is_file():
            raise FileNotFoundError(f"log_artifact path {path!s} does not exist")
        blob = path.read_bytes()
    elif isinstance(payload, bytes):
        blob = payload
    else:
        raise TypeError(
            f"log_artifact payload must be bytes / str / Path, "
            f"got {type(payload).__name__}"
        )
    sha = hashlib.sha256(blob).hexdigest()
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    bucket = root / sha[:2]
    bucket.mkdir(parents=True, exist_ok=True)
    target = bucket / sha
    if not target.exists():
        # Write bytes atomically via a temp file + rename so concurrent
        # workers writing the same content can't race on a half-written
        # blob. ``NamedTemporaryFile`` in the same parent guarantees
        # ``os.replace`` is atomic on POSIX.
        tmp = target.with_suffix(".partial")
        tmp.write_bytes(blob)
        os.replace(tmp, target)
    return blob, sha, len(blob), str(target)


def _iso_utc() -> str:
    return _now_utc().isoformat()


def _coerce_tag_value(value: Any) -> str:
    """Coerce a tag value to ``str`` per spec §4.7.

    Non-string tag values are coerced via ``str()`` with a DEBUG log line.
    """
    if isinstance(value, str):
        return value
    coerced = str(value)
    logger.debug(
        "tracking.tag.value_coerced",
        extra={"value_type": type(value).__name__},
    )
    return coerced


def _serialise_figure(figure: Any) -> tuple[bytes, str]:
    """Serialise a plotly / matplotlib figure per spec §4.4.

    Returns ``(bytes, content_type)``. Plotly figures take the JSON
    path; matplotlib figures take the PNG path. Anything else raises
    :class:`TrackingError` — the surface is intentionally narrow so a
    future DL-diagnostics integration can trust the sink shape.
    """
    # Plotly figure first — the attribute check is duck-typed so we do
    # NOT require plotly to be importable at call time.
    if hasattr(figure, "to_json") and callable(figure.to_json):
        try:
            payload = figure.to_json()
        except Exception as exc:  # noqa: BLE001
            raise TrackingError(
                reason=f"log_figure: figure.to_json() failed: {exc}"
            ) from exc
        if isinstance(payload, str):
            return payload.encode("utf-8"), "application/vnd.plotly.v1+json"
        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload), "application/vnd.plotly.v1+json"
        raise TrackingError(
            reason=(
                f"log_figure: figure.to_json() returned "
                f"{type(payload).__name__}, expected str/bytes"
            )
        )
    # Matplotlib — `savefig(buf, format="png")` writes to an in-memory buffer.
    if hasattr(figure, "savefig") and callable(figure.savefig):
        buf = io.BytesIO()
        try:
            figure.savefig(buf, format="png")
        except Exception as exc:  # noqa: BLE001
            raise TrackingError(
                reason=f"log_figure: matplotlib savefig failed: {exc}"
            ) from exc
        return buf.getvalue(), "image/png"
    raise TrackingError(
        reason=(
            f"log_figure: unsupported figure type {type(figure).__name__}; "
            f"expected plotly.graph_objs.Figure or matplotlib.figure.Figure"
        )
    )


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
        backend: AbstractTrackerStore,
        params: Mapping[str, Any],
        tenant_id: Optional[str],
        parent_run_id: Optional[str],
        actor_id: Optional[str] = None,
    ) -> None:
        self.experiment = experiment
        self.run_id = str(uuid.uuid4())
        self.parent_run_id = parent_run_id
        self.tenant_id = tenant_id
        #: Actor identity established at :func:`track` entry (spec §8.1).
        #: Read-only after construction; mutation primitives route through
        #: the ambient contextvar, not this field.
        self.actor_id = actor_id
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
        # Contextvar tokens — one per ambient scope (run / tenant / actor).
        # Set at ``__aenter__`` via ``ContextVar.set(...)`` and released
        # at ``__aexit__`` via ``reset(token)``. Leaked tokens across
        # the async boundary are BLOCKED per spec §10.1.
        self._ctx_token: Any = None
        self._tenant_ctx_token: Any = None
        self._actor_ctx_token: Any = None

    # ------------------------------------------------------------------
    # Logging primitives — W12 (spec ml-tracking.md §4)
    # ------------------------------------------------------------------
    #
    # Every primitive honours two shared invariants:
    #
    # 1. **Rank-0 guard.** When the process is a non-zero rank in a
    #    DDP/FSDP job, every primitive is a no-op. Logging runs exactly
    #    once per global-step in multi-GPU training (Decision 4).
    # 2. **Key regex.** Param / metric keys follow §4.1
    #    ``^[a-zA-Z_][a-zA-Z0-9_.\-]*$``; tag keys follow the stricter
    #    §4.7 / invariant 8 regex ``^[a-z_][a-z_0-9]*$``. Both raise
    #    :class:`TrackingError` on mismatch.

    async def log_param(self, key: str, value: Any) -> None:
        """Record a single param. Persisted immediately (spec §4.1).

        Numeric values MUST be finite — ``NaN`` / ``±Inf`` raise
        :class:`ParamValueError` per §4.1 MUST-finite-check.
        """
        if not _is_rank_zero():
            return
        _validate_key("param", str(key))
        checked = _validate_param_value(str(key), value)
        self._params[str(key)] = checked
        await self._backend.set_params(self.run_id, self._params)

    async def log_params(self, params: Mapping[str, Any]) -> None:
        """Record multiple params. Persisted immediately (spec §4.1)."""
        if not _is_rank_zero():
            return
        updates: dict[str, Any] = {}
        for k, v in params.items():
            _validate_key("param", str(k))
            updates[str(k)] = _validate_param_value(str(k), v)
        for k, v in updates.items():
            self._params[k] = v
        await self._backend.set_params(self.run_id, self._params)

    async def log_metric(
        self,
        key: str,
        value: float,
        *,
        step: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Append one metric row (spec §4.2 — the round-1 CRIT gap).

        Metrics are append-only (one row per call) so ``log_metric("loss",
        v, step=k)`` produces the training curve directly. ``value`` MUST
        be finite — ``NaN`` / ``±Inf`` raise :class:`MetricValueError`.
        """
        if not _is_rank_zero():
            return
        _validate_key("metric", str(key))
        v = _validate_metric_value(str(key), value)
        ts = (timestamp or _now_utc()).isoformat()
        await self._backend.append_metric(self.run_id, str(key), v, step, ts)

    async def log_metrics(
        self,
        metrics: Mapping[str, float],
        *,
        step: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Append many metric rows atomically (spec §4.2)."""
        if not _is_rank_zero():
            return
        ts = (timestamp or _now_utc()).isoformat()
        rows: list[tuple[str, float, Optional[int], str]] = []
        for k, v in metrics.items():
            _validate_key("metric", str(k))
            rows.append((str(k), _validate_metric_value(str(k), v), step, ts))
        await self._backend.append_metrics_batch(self.run_id, rows)

    async def log_artifact(
        self,
        path_or_bytes: Union[str, Path, bytes],
        name: str,
        *,
        content_type: Optional[str] = None,
        data_subject_ids: Optional[list[str]] = None,
    ) -> ArtifactHandle:
        """Persist an artifact content-addressed by SHA-256 (spec §4.3).

        A second call with identical bytes returns an
        :class:`ArtifactHandle` with the same ``sha256`` and
        ``storage_uri`` — dedupe is structural (PK on
        ``(run_id, name, sha256)``). ``data_subject_ids`` is accepted
        for forward-compat with the W15 tenant/GDPR wave and is
        currently unused.

        Full encryption policy (``ArtifactEncryptionError``) + size
        cap (``ArtifactSizeExceededError``) land in W17 alongside the
        artifact-store backend work; this W12 path writes plaintext
        locally.
        """
        del data_subject_ids  # accepted for forward-compat (W15)
        if not _is_rank_zero():
            # Return a deterministic sentinel handle so callers on
            # non-rank-0 workers do not crash when they unpack the
            # return value. storage_uri="" signals "not persisted".
            return ArtifactHandle(
                name=name,
                sha256="",
                storage_uri="",
                size_bytes=0,
                content_type=content_type,
            )
        _, sha, size, uri = _hash_and_materialise_artifact(
            self._backend.artifact_root, path_or_bytes
        )
        await self._backend.insert_artifact(
            self.run_id,
            name,
            sha,
            content_type,
            size,
            uri,
            _iso_utc(),
        )
        return ArtifactHandle(
            name=name,
            sha256=sha,
            storage_uri=uri,
            size_bytes=size,
            content_type=content_type,
        )

    async def log_figure(
        self,
        figure: Any,
        name: str,
        *,
        step: Optional[int] = None,
    ) -> ArtifactHandle:
        """Serialise a plotly / matplotlib figure as an artifact (spec §4.4).

        Plotly figures serialise via ``figure.to_json()`` with MIME
        ``application/vnd.plotly.v1+json``. Matplotlib figures serialise
        via ``fig.savefig(buf, format="png")`` with MIME ``image/png``.
        The resulting bytes flow through :meth:`log_artifact` so the
        SHA-256 dedupe still applies. ``step`` is recorded via a
        sibling metric ``{name}.step`` for DL-diagnostics timeline
        reconstruction.
        """
        if not _is_rank_zero():
            return ArtifactHandle(
                name=name,
                sha256="",
                storage_uri="",
                size_bytes=0,
                content_type=None,
            )
        payload_bytes, content_type = _serialise_figure(figure)
        handle = await self.log_artifact(payload_bytes, name, content_type=content_type)
        if step is not None:
            # Sibling metric so downstream DL-diagnostics can reconstruct
            # the figure→step timeline without opening the artifact.
            try:
                await self.log_metric(f"{name}.step", float(step), step=int(step))
            except TrackingError:
                # key regex may reject e.g. "confusion matrix.step";
                # fall through silently — the figure artifact itself
                # still carries the step in its filename via the caller.
                pass
        return handle

    async def log_model(
        self,
        model: Any,
        name: str,
        *,
        format: str = "onnx",
        aliases: Optional[list[str]] = None,
        signature: Optional[Any] = None,
        lineage: Optional[Mapping[str, Any]] = None,
        training_result: Optional[TrainingResult] = None,
    ) -> ModelVersionInfo:
        """Record a run-scoped model-version snapshot (spec §4.5).

        Signature is mandatory (``signature is None`` raises
        :class:`ModelSignatureRequiredError`). Lineage OR an ambient
        run is mandatory — since :class:`ExperimentRun` is the run, the
        latter always holds and ``lineage=None`` is permitted.

        For W12 the serialisation path is minimal — the model is
        serialised via ``pickle`` for the ``pickle`` format, and via
        ``str(model).encode()`` otherwise. Full ONNX / PyTorch /
        Lightning / sklearn export lands in W17 (artifact-store /
        onnx) alongside the cross-run :class:`ModelRegistry`.
        """
        del aliases  # recorded in W18 (aliases + lineage queries)
        if signature is None:
            raise ModelSignatureRequiredError(
                reason=(
                    f"log_model({name!r}) requires a non-None signature "
                    f"(spec ml-tracking.md §4.5)"
                )
            )
        # self._run is always populated (log_model is an instance
        # method) — the spec's LineageRequiredError branch fires only
        # for module-level callers in W16+.
        if not _is_rank_zero():
            return ModelVersionInfo(
                name=name, format=format, artifact_sha="", run_id=self.run_id
            )
        # Serialise the model bytes. For W12 we accept bytes / str
        # payloads directly; richer exporters land in W17.
        if isinstance(model, (bytes, bytearray)):
            blob = bytes(model)
        else:
            try:
                import pickle  # noqa: PLC0415

                blob = pickle.dumps(model)
            except Exception as exc:
                raise TrackingError(
                    reason=(
                        f"log_model({name!r}) could not serialise model "
                        f"of type {type(model).__name__}: {exc}"
                    )
                ) from exc
        handle = await self.log_artifact(
            blob, f"model:{name}", content_type=f"application/x-{format}"
        )
        signature_json = (
            json.dumps(signature, default=str) if signature is not None else None
        )
        lineage_json = json.dumps(dict(lineage), default=str) if lineage else None
        if training_result is not None:
            # Side-effect: keep the run's device envelope in sync with
            # the model's training provenance.
            self.attach_training_result(training_result)
        await self._backend.insert_model_version(
            self.run_id,
            name,
            format,
            handle.sha256,
            signature_json,
            lineage_json,
            _iso_utc(),
        )
        return ModelVersionInfo(
            name=name,
            format=format,
            artifact_sha=handle.sha256,
            run_id=self.run_id,
        )

    async def attach_training_result_async(self, result: TrainingResult) -> None:
        """Async variant of :meth:`attach_training_result` that ALSO
        flattens ``result.metrics`` + ``result.hyperparameters`` into
        the metric / param tables (W12 invariant 6, spec §4.6).

        The sync :meth:`attach_training_result` is preserved for
        back-compat with W8 callers that populate device fields only;
        callers that want the full flattening MUST switch to this
        method.
        """
        if not _is_rank_zero():
            return
        # 1. Device envelope (mirrors the sync variant below).
        self.attach_training_result(result)
        # 2. Flatten metrics — spec §4.6 MUST "persist result.metrics
        #    + result.hyperparameters into appropriate tables". Numeric
        #    metrics get `log_metric`; non-numeric metrics are skipped
        #    with a DEBUG — the metrics table is numeric-only.
        metrics = getattr(result, "metrics", None) or {}
        numeric_rows: list[tuple[str, float, Optional[int], str]] = []
        ts = _iso_utc()
        for k, v in dict(metrics).items():
            if not _KEY_REGEX.match(str(k)):
                logger.debug(
                    "tracking.attach.metric_key_skipped",
                    extra={
                        "run_id": self.run_id,
                        "field_hash": hashlib.sha256(str(k).encode()).hexdigest()[:8],
                    },
                )
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                logger.debug(
                    "tracking.attach.metric_non_numeric_skipped",
                    extra={"run_id": self.run_id},
                )
                continue
            fv = float(v)
            if not math.isfinite(fv):
                logger.debug(
                    "tracking.attach.metric_non_finite_skipped",
                    extra={"run_id": self.run_id},
                )
                continue
            numeric_rows.append((str(k), fv, None, ts))
        if numeric_rows:
            await self._backend.append_metrics_batch(self.run_id, numeric_rows)
        # 3. Flatten hyperparameters — log_params already handles
        #    finite-check + key validation.
        hps = getattr(result, "hyperparameters", None) or {}
        valid_hps: dict[str, Any] = {}
        for k, v in dict(hps).items():
            if not _KEY_REGEX.match(str(k)):
                logger.debug(
                    "tracking.attach.hp_key_skipped",
                    extra={"run_id": self.run_id},
                )
                continue
            try:
                valid_hps[str(k)] = _validate_param_value(str(k), v)
            except ParamValueError:
                logger.debug(
                    "tracking.attach.hp_non_finite_skipped",
                    extra={"run_id": self.run_id},
                )
                continue
        if valid_hps:
            for k, v in valid_hps.items():
                self._params[k] = v
            await self._backend.set_params(self.run_id, self._params)

    async def add_tag(self, key: str, value: Any) -> None:
        """Record a single tag (spec §4.7)."""
        if not _is_rank_zero():
            return
        _validate_tag_key(str(key))
        await self._backend.upsert_tag(self.run_id, str(key), _coerce_tag_value(value))

    async def add_tags(self, tags: Mapping[str, Any]) -> None:
        """Record many tags atomically (spec §4.7)."""
        if not _is_rank_zero():
            return
        validated: dict[str, str] = {}
        for k, v in tags.items():
            _validate_tag_key(str(k))
            validated[str(k)] = _coerce_tag_value(v)
        await self._backend.upsert_tags(self.run_id, validated)

    async def set_tags(self, **tags: Any) -> None:
        """Record many tags via kwargs (spec §4.7 canonical API).

        Equivalent to :meth:`add_tags` with ``**kwargs`` instead of a
        mapping — matches the MLflow/W&B tutorial idiom
        ``run.set_tags(env="prod", cost_center="research")``.
        """
        await self.add_tags(tags)

    def attach_training_result(self, result: TrainingResult) -> None:
        """Populate device fields from a ``TrainingResult`` (W8 sync path).

        Sync variant preserved for back-compat with Trainable.fit()
        call sites that predate W12's metric/param-flattening. W12
        callers that also want the flattening MUST use
        :meth:`attach_training_result_async` (spec §4.6 MUST-flatten).

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

        # Bind contextvars so nested km.track() calls inherit run +
        # tenant + actor identity. Per spec §10.1/§10.2 and §8.1 the
        # three are session-level properties; the tokens released at
        # ``__aexit__`` restore the outer scope's bindings.
        self._ctx_token = _current_run.set(self)
        self._tenant_ctx_token = _current_tenant_id.set(self.tenant_id)
        self._actor_ctx_token = _current_actor_id.set(self.actor_id)

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

        # Release contextvar bindings in reverse order so the outer
        # scope's values are restored cleanly. All three tokens MUST
        # reset — leaking a tenant or actor binding past ``__aexit__``
        # would let sibling work inherit the wrong identity.
        if self._actor_ctx_token is not None:
            _current_actor_id.reset(self._actor_ctx_token)
            self._actor_ctx_token = None
        if self._tenant_ctx_token is not None:
            _current_tenant_id.reset(self._tenant_ctx_token)
            self._tenant_ctx_token = None
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
    backend: Optional[AbstractTrackerStore] = None,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
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
        backend: An explicit :class:`AbstractTrackerStore` instance
            (e.g. :class:`SqliteTrackerStore` or
            :class:`PostgresTrackerStore`). If omitted, a SQLite backend
            is created on the default store path
            (``~/.kailash_ml/ml.db``) OR the ``store`` URI if provided.
        tenant_id: Optional tenant id. Resolution order: explicit
            kwarg > ambient ``_current_tenant_id`` contextvar > env var
            ``KAILASH_TENANT_ID`` > ``None`` (single-tenant). The
            resolved value is re-bound into the contextvar for the
            duration of the run so nested primitives read it via
            :func:`kailash_ml.tracking.get_current_tenant_id` without
            re-passing it (spec §10.2).
        actor_id: Optional actor identity for audit rows (spec §8.1).
            Session-level only — MUST NOT be passed per-call on
            ``log_*`` primitives (HIGH-4 round-1 finding). Resolution
            order mirrors ``tenant_id``: kwarg > ambient contextvar >
            ``KAILASH_ACTOR_ID`` env var > ``None``. Read via
            :func:`kailash_ml.tracking.get_current_actor_id`.
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
        backend = SqliteTrackerStore(_resolve_store_path(store))
        owns_backend = True
    resolved_tenant = _resolve_tenant_id(tenant_id)
    resolved_actor = _resolve_actor_id(actor_id)
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
        actor_id=resolved_actor,
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
