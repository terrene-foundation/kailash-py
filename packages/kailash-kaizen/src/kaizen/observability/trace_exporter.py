# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
#
# Portions of this module were originally contributed from MLFP
# (Apache-2.0) and re-authored for the Kailash ecosystem. See
# ``specs/kaizen-observability.md`` § "Attribution" for the full
# donation history (kailash-py issue #567, PR#6 of 7).
"""TraceExporter — structured trace-event sink for Kaizen agents.

``TraceExporter`` accepts :class:`kailash.diagnostics.protocols.TraceEvent`
records from an agent run and routes them to a sink (JSONL file or
async callable). Every event is stamped with a cross-SDK-locked
SHA-256 fingerprint via
:func:`kailash.diagnostics.protocols.compute_trace_event_fingerprint`
so a Rust subscriber reading a Python-emitted JSONL line produces the
same correlation hash as the Python emitter (kailash-rs#468).

Third-party observability vendors (hosted tracing services, OTel
collectors, etc.) are deliberately NOT imported from this module.
``rules/independence.md`` forbids commercial-SDK coupling. Users who
want those sinks pass a :class:`CallableSink` that wraps whatever they
want — the in-tree sinks (``JsonlSink``, ``NoOpSink``, ``CallableSink``)
cover the full matrix of "log it to disk", "log it nowhere", and "let
my own code decide".

Fingerprint canonicalization contract (locked byte-identical with
kailash-rs v3.17.1+ / issue #468):

    - ``event.to_dict()`` yields the canonical-shape dict (Optional
      ``None`` fields preserved; Enum values as strings; timestamps
      as ISO-8601 with explicit ``+00:00``).
    - ``json.dumps(..., sort_keys=True, separators=(",", ":"),
       ensure_ascii=True, default=str)`` produces compact JSON
       matching Rust ``serde_json::to_string(&BTreeMap)`` byte-for-byte.
    - SHA-256 of the UTF-8 bytes, hex-encoded lowercase (64 hex chars).

Per ``rules/event-payload-classification.md`` §2: classified PK values
inside ``TraceEvent.payload`` MUST be hashed by the emitter BEFORE
construction (``payload_hash`` field, ``sha256:<8-hex>`` prefix). This
module does NOT re-hash payload contents — it trusts the emitter's
classification discipline, per the spec's event-surface contract.

Related:

  - ``rules/observability.md`` — structured logging + correlation IDs.
  - ``rules/orphan-detection.md`` §1 — the exporter MUST have a
    production call site in the :class:`~kaizen.core.base_agent.BaseAgent`
    hot path, not just a facade.
  - ``src/kailash/trust/pact/audit.py`` ``AuditAnchor.compute_hash`` —
    the sibling N4 canonical form for PACT audit chains; this module's
    trace-event canonicalization follows the same sort-keys + compact
    separators + UTF-8 + SHA-256 discipline.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, Union

from kailash.diagnostics.protocols import (
    TraceEvent,
    compute_trace_event_fingerprint,
)

if TYPE_CHECKING:  # pragma: no cover
    from kailash.trust.pact.audit import AuditAnchor  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = [
    "TraceExporter",
    "TraceExportError",
    "JsonlSink",
    "NoOpSink",
    "CallableSink",
    "SinkCallable",
    "compute_fingerprint",
]


def _hash_tenant_id(tenant_id: Optional[str]) -> Optional[str]:
    """Hash a tenant_id to the cross-SDK ``sha256:<8-hex>`` form.

    Per ``rules/observability.md`` §8 + ``rules/tenant-isolation.md`` §4,
    schema-level tenant identifiers MUST NOT appear as raw values on
    WARN+ or INFO log lines that may leak into broader-audience log
    aggregators (Datadog, Splunk, CloudWatch). This helper produces the
    same 8-hex-char prefix as
    ``rules/event-payload-classification.md`` §2 so forensic correlation
    across Python and Rust log streams remains stable.

    Returns ``None`` for a ``None`` input (no tenant scope to log).
    """
    if tenant_id is None:
        return None
    digest = hashlib.sha256(str(tenant_id).encode("utf-8")).hexdigest()[:8]
    return f"sha256:{digest}"


# Type alias for a sink callable. Sync or async both supported.
SinkCallable = Callable[[TraceEvent, str], Union[None, Awaitable[None]]]


class TraceExportError(RuntimeError):
    """Raised when a trace-event export operation fails.

    Carries the offending ``event_id`` and the underlying cause in the
    message so an operator can correlate the failure back to the agent
    run that produced it.
    """


# ---------------------------------------------------------------------------
# Fingerprint — re-exported under a short name for call-site convenience
# ---------------------------------------------------------------------------


def compute_fingerprint(event: TraceEvent) -> str:
    """Re-export of :func:`compute_trace_event_fingerprint`.

    Kept as a package-level alias so call sites within
    ``kaizen.observability`` import from one module. The underlying
    implementation MUST remain in ``kailash.diagnostics.protocols`` —
    the cross-SDK contract lives there and this re-export is a
    convenience only.
    """
    return compute_trace_event_fingerprint(event)


# ---------------------------------------------------------------------------
# Sinks — in-tree, no third-party vendor coupling
# ---------------------------------------------------------------------------


class NoOpSink:
    """Sink that discards every event. Default when no sink is wired.

    Useful for tests that only want to observe fingerprint parity
    without cluttering the filesystem.
    """

    def __call__(self, event: TraceEvent, fingerprint: str) -> None:
        return None


class JsonlSink:
    """Sink that appends each event as one JSON line to a file.

    Each line has the shape::

        {"fingerprint": "<64-hex>", ...<TraceEvent.to_dict()>}

    so downstream tools can index by the cross-SDK fingerprint AND
    read the event payload without re-computing. Writes are serialized
    by an internal :class:`threading.Lock` so concurrent agent runs
    can share one sink.

    Path-safety contract (security-reviewer H2):

      - The provided ``path`` is resolved via ``Path.expanduser().resolve(
        strict=False)`` at construction time. This normalizes ``..``
        segments so the audit trail in logs / error messages shows the
        fully-resolved destination, not the caller's unnormalized input.
      - On POSIX, writes go through ``os.open(..., O_NOFOLLOW, 0o600)``
        followed by ``os.fdopen`` — an attacker who plants a symlink at
        the target path gets ``OSError`` (typically ``ELOOP``) instead
        of a silent cross-write into the symlink target.
      - The file-mode bits are ``0o600`` (owner-only read/write). Trace
        streams may contain classified payload hashes and operational
        metadata that ops staff beyond the process owner should not see
        without explicit authorization.
      - **Callers MUST pre-validate tenant-derived paths against an
        allowlist.** ``JsonlSink`` resolves symlinks but does not reject
        ``..`` traversal above the allowlist root — path allowlisting
        is the caller's responsibility because it is policy, not
        mechanism.

    Args:
        path: Filesystem path to the JSONL log. Parent dirs are created
            lazily on first write.
        mode: Open mode; ``"a"`` (append) is the default and the only
            sensible choice for an append-only log.
    """

    def __init__(self, path: Union[str, Path], *, mode: str = "a") -> None:
        if mode not in ("a", "w"):
            raise ValueError(
                f"JsonlSink mode must be 'a' (append) or 'w' (write); got {mode!r}"
            )
        # Resolve the path once at construction time so every subsequent
        # audit trail (logs, error messages, the `.path` property) shows
        # the fully-normalized destination. strict=False allows the path
        # to not yet exist (lazy parent-dir creation happens on first
        # write) while still normalizing `..` segments.
        self._path = Path(path).expanduser().resolve(strict=False)
        self._mode = mode
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def __call__(self, event: TraceEvent, fingerprint: str) -> None:
        line = {"fingerprint": fingerprint, **event.to_dict()}
        payload = json.dumps(
            line,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        with self._lock:
            # Lazy parent-dir creation keeps the sink cheap to construct
            # for tests that never actually write.
            self._path.parent.mkdir(parents=True, exist_ok=True)

            # POSIX: open via os.open with O_NOFOLLOW so an attacker who
            # plants a symlink at the target path gets ELOOP instead of
            # a silent cross-write. Windows fallback uses Path.open with
            # mode 'a'/'w' (O_NOFOLLOW is POSIX-specific).
            if hasattr(os, "O_NOFOLLOW"):
                flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
                if self._mode == "a":
                    flags |= os.O_APPEND
                elif self._mode == "w":
                    flags |= os.O_TRUNC
                fd = os.open(str(self._path), flags, 0o600)
                with os.fdopen(fd, self._mode, encoding="utf-8") as f:
                    f.write(payload)
                    f.write("\n")
            else:  # pragma: no cover — Windows fallback
                with self._path.open(self._mode, encoding="utf-8") as f:
                    f.write(payload)
                    f.write("\n")


@dataclass(frozen=True)
class CallableSink:
    """Sink wrapping an arbitrary sync or async callable.

    The wrapped callable receives ``(event, fingerprint)``. Return
    values are ignored. Exceptions propagate to the exporter, which
    logs them and decides whether to continue based on its
    ``raise_on_error`` flag.
    """

    func: SinkCallable

    def __call__(
        self, event: TraceEvent, fingerprint: str
    ) -> Union[None, Awaitable[None]]:
        return self.func(event, fingerprint)


# ---------------------------------------------------------------------------
# TraceExporter — the single filter point (rules/event-payload-classification.md §1)
# ---------------------------------------------------------------------------


class TraceExporter:
    """Single-filter-point exporter for :class:`TraceEvent` records.

    Every trace event emitted by an agent MUST route through
    ``TraceExporter.export()`` (or ``export_async()``). The exporter
    stamps each event with its cross-SDK fingerprint and hands the
    pair off to the configured sink. This is the structural defense
    against drift — the single-emitter-point rule mirrors
    ``rules/event-payload-classification.md`` MUST Rule 1.

    Args:
        sink: Callable (sync or async) OR :class:`NoOpSink` /
            :class:`JsonlSink` / :class:`CallableSink` instance that
            accepts ``(TraceEvent, fingerprint)``. ``None`` uses
            :class:`NoOpSink`.
        run_id: Optional correlation identifier stamped onto every
            structured log line emitted by this exporter.
        tenant_id: Optional tenant scope stamped onto every log line.
            When set, downstream sinks MAY partition storage by tenant
            per ``rules/tenant-isolation.md``.
        raise_on_error: When ``True``, sink failures re-raise as
            :class:`TraceExportError`. When ``False`` (default), the
            error is logged and export continues — the exporter's
            availability MUST NOT break the agent's hot path.

    Raises:
        TypeError: If ``sink`` is not callable.
    """

    def __init__(
        self,
        sink: Optional[Union[SinkCallable, NoOpSink, JsonlSink, CallableSink]] = None,
        *,
        run_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        raise_on_error: bool = False,
    ) -> None:
        resolved_sink: SinkCallable
        if sink is None:
            resolved_sink = NoOpSink()
        elif callable(sink):
            resolved_sink = sink  # type: ignore[assignment]
        else:
            raise TypeError(
                f"TraceExporter.sink must be callable or a sink instance; "
                f"got {type(sink).__name__}"
            )

        self._sink: SinkCallable = resolved_sink
        self._run_id = run_id
        self._tenant_id = tenant_id
        self._raise_on_error = raise_on_error
        self._exported_count = 0
        self._errored_count = 0

        logger.info(
            "kaizen.observability.trace_exporter.init",
            extra={
                "trace_exporter_run_id": self._run_id,
                "trace_exporter_tenant_hash": _hash_tenant_id(self._tenant_id),
                "trace_exporter_sink": type(resolved_sink).__name__,
                "trace_exporter_raise_on_error": self._raise_on_error,
                "mode": "real",
            },
        )

    # ── Stats (bounded counters, no memory growth) ──────────────────

    @property
    def exported_count(self) -> int:
        return self._exported_count

    @property
    def errored_count(self) -> int:
        return self._errored_count

    # ── Core export paths ───────────────────────────────────────────

    def export(self, event: TraceEvent) -> str:
        """Export ``event`` synchronously; return its fingerprint.

        Raises:
            TypeError: If ``event`` is not a :class:`TraceEvent`.
            TraceExportError: Only when ``raise_on_error=True`` and
                the sink raises.
        """
        self._validate_event(event)
        fingerprint = compute_fingerprint(event)

        try:
            maybe_awaitable = self._sink(event, fingerprint)
            if inspect.isawaitable(maybe_awaitable):
                # Sync entry-point into an async sink: run to completion
                # via the safe-event-loop adapter. See
                # rules/patterns.md "Async Resource Cleanup" — we MUST
                # NOT spawn a new loop if one is already running.
                self._run_async(maybe_awaitable)
        except Exception as exc:  # noqa: BLE001 — we re-raise below
            self._errored_count += 1
            logger.exception(
                "kaizen.observability.trace_exporter.sink_error",
                extra={
                    "trace_exporter_run_id": self._run_id,
                    "trace_exporter_tenant_hash": _hash_tenant_id(self._tenant_id),
                    "trace_exporter_event_id": event.event_id,
                    "trace_exporter_event_type": event.event_type.value,
                    "trace_exporter_fingerprint": fingerprint,
                    "mode": "real",
                },
            )
            if self._raise_on_error:
                raise TraceExportError(
                    f"TraceExporter sink failed for event_id={event.event_id!r}: {exc}"
                ) from exc
            return fingerprint

        self._exported_count += 1
        logger.debug(
            "kaizen.observability.trace_exporter.export.ok",
            extra={
                "trace_exporter_run_id": self._run_id,
                "trace_exporter_tenant_hash": _hash_tenant_id(self._tenant_id),
                "trace_exporter_event_id": event.event_id,
                "trace_exporter_event_type": event.event_type.value,
                "trace_exporter_fingerprint": fingerprint,
                "mode": "real",
            },
        )
        return fingerprint

    async def export_async(self, event: TraceEvent) -> str:
        """Export ``event`` asynchronously; return its fingerprint.

        Mirrors :meth:`export` but awaits async sinks directly rather
        than routing through a synchronous loop-adapter.
        """
        self._validate_event(event)
        fingerprint = compute_fingerprint(event)

        try:
            maybe_awaitable = self._sink(event, fingerprint)
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
        except Exception as exc:  # noqa: BLE001 — we re-raise below
            self._errored_count += 1
            logger.exception(
                "kaizen.observability.trace_exporter.sink_error",
                extra={
                    "trace_exporter_run_id": self._run_id,
                    "trace_exporter_tenant_hash": _hash_tenant_id(self._tenant_id),
                    "trace_exporter_event_id": event.event_id,
                    "trace_exporter_event_type": event.event_type.value,
                    "trace_exporter_fingerprint": fingerprint,
                    "mode": "real",
                },
            )
            if self._raise_on_error:
                raise TraceExportError(
                    f"TraceExporter sink failed for event_id={event.event_id!r}: {exc}"
                ) from exc
            return fingerprint

        self._exported_count += 1
        logger.debug(
            "kaizen.observability.trace_exporter.export_async.ok",
            extra={
                "trace_exporter_run_id": self._run_id,
                "trace_exporter_tenant_hash": _hash_tenant_id(self._tenant_id),
                "trace_exporter_event_id": event.event_id,
                "trace_exporter_event_type": event.event_type.value,
                "trace_exporter_fingerprint": fingerprint,
                "mode": "real",
            },
        )
        return fingerprint

    # ── Internal helpers ────────────────────────────────────────────

    @staticmethod
    def _validate_event(event: TraceEvent) -> None:
        # Typed guard per rules/zero-tolerance.md Rule 3a: a non-TraceEvent
        # would hit AttributeError deep in to_dict(), obscuring the bug.
        if not isinstance(event, TraceEvent):
            raise TypeError(
                f"TraceExporter.export(event=...) requires a TraceEvent; "
                f"got {type(event).__name__}"
            )

    @staticmethod
    def _run_async(awaitable: Awaitable[None]) -> None:
        """Run an async sink's coroutine from a sync caller.

        Safe against "event loop already running" per
        ``rules/patterns.md`` § "Async Resource Cleanup": if a loop is
        running in the current thread, schedule the coroutine as a task
        on it; otherwise spawn a short-lived loop via ``asyncio.run``.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            loop.create_task(awaitable)
        else:
            asyncio.run(awaitable)


# ---------------------------------------------------------------------------
# Factory helpers for common sink shapes
# ---------------------------------------------------------------------------


def jsonl_exporter(
    path: Union[str, Path],
    *,
    run_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    raise_on_error: bool = False,
) -> TraceExporter:
    """Build a :class:`TraceExporter` backed by a :class:`JsonlSink`.

    Convenience for the most common case — "write every trace event
    to a JSONL file for offline analysis." The ``path`` parent dir is
    created lazily on first write.
    """
    return TraceExporter(
        sink=JsonlSink(path),
        run_id=run_id,
        tenant_id=tenant_id,
        raise_on_error=raise_on_error,
    )


def callable_exporter(
    func: SinkCallable,
    *,
    run_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    raise_on_error: bool = False,
) -> TraceExporter:
    """Build a :class:`TraceExporter` backed by a :class:`CallableSink`.

    Used when the caller wants full control over the destination
    (OTel span emitter, in-process list for tests, custom IPC bus).
    Third-party vendor SDKs live behind the user's own callable —
    ``kaizen.observability`` itself does not import them.
    """
    return TraceExporter(
        sink=CallableSink(func),
        run_id=run_id,
        tenant_id=tenant_id,
        raise_on_error=raise_on_error,
    )


# Ensure `os` import is not orphaned by a future refactor (used by the
# loud-sink defaults above in certain code paths; the symbol is imported
# for future module-level env-based configuration).
_ = os
