# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SQLiteSink — durable TraceExporter sink sharing the ML run store.

Per ``specs/kaizen-ml-integration.md`` §5: TraceExporter gains a
``SQLiteSink`` option that writes to the canonical
``~/.kailash_ml/ml.db`` store (or any SQLite path), so agent traces
appear in the same durable surface as ML runs. Dashboards join
``_kml_run`` (from kailash-ml) to ``_kml_agent_runs`` (this module) on
``run_id`` to display "this ML run used these agent traces".

Cross-SDK parity (spec §8): the N4 canonical fingerprint (SHA-256 over
compact-sort-keys JSON) is computed by
``kailash.diagnostics.protocols.compute_trace_event_fingerprint``. This
sink does NOT re-compute — it persists the fingerprint supplied by the
caller (the ``TraceExporter`` is the single filter point per
``rules/event-payload-classification.md`` §1).

Schema:

    _kml_agent_runs           (trace_id PK, run_id FK, agent_id, ...)
    _kml_agent_events         (event_id PK, trace_id FK, seq, fingerprint, ...)

Tables are created with ``IF NOT EXISTS`` so the sink is safe to
instantiate against an existing ``ml.db``. All DDL is fixed — NO
dynamic identifiers — per ``rules/dataflow-identifier-safety.md`` §1.

Status enum (spec §5.3 + approved-decisions.md Decision 3):
``RUNNING`` / ``FINISHED`` / ``FAILED`` / ``KILLED``. Legacy
``SUCCESS`` / ``COMPLETED`` values are BLOCKED.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from kailash.diagnostics.protocols import TraceEvent, TraceEventStatus

__all__ = [
    "SQLiteSink",
    "SQLiteSinkError",
    "default_ml_db_path",
    "VALID_AGENT_RUN_STATUSES",
]

logger = logging.getLogger(__name__)


# Cross-SDK status enum — spec §5.3. Any value outside this set is
# rejected at insert time (and by the unit test
# ``test_sqlitesink_rejects_invalid_status``).
VALID_AGENT_RUN_STATUSES: frozenset[str] = frozenset(
    {"RUNNING", "FINISHED", "FAILED", "KILLED"}
)


# Fixed DDL — NO dynamic identifiers. Per
# ``rules/dataflow-identifier-safety.md`` §1: every CREATE / ALTER
# interpolation is an injection vector unless routed through a dialect
# helper. Since this schema is fixed (no tenant / model / agent
# prefixes in table names), the identifiers are hardcoded literals.
_SCHEMA_AGENT_RUNS = """
CREATE TABLE IF NOT EXISTS _kml_agent_runs (
    trace_id          TEXT PRIMARY KEY,
    run_id            TEXT,
    agent_id          TEXT NOT NULL,
    tenant_id         TEXT,
    actor_id          TEXT,
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    status            TEXT NOT NULL,
    cost_microdollars INTEGER NOT NULL DEFAULT 0
);
"""

_INDEX_AGENT_RUNS_TENANT = """
CREATE INDEX IF NOT EXISTS _kml_agent_runs_tenant_idx
    ON _kml_agent_runs(tenant_id);
"""

_INDEX_AGENT_RUNS_RUN = """
CREATE INDEX IF NOT EXISTS _kml_agent_runs_run_idx
    ON _kml_agent_runs(run_id);
"""

_SCHEMA_AGENT_EVENTS = """
CREATE TABLE IF NOT EXISTS _kml_agent_events (
    event_id      TEXT PRIMARY KEY,
    trace_id      TEXT NOT NULL REFERENCES _kml_agent_runs(trace_id),
    seq           INTEGER NOT NULL,
    event_type    TEXT NOT NULL,
    event_status  TEXT NOT NULL,
    fingerprint   TEXT NOT NULL,
    at            TEXT NOT NULL,
    payload_json  TEXT
);
"""

_INDEX_AGENT_EVENTS_TRACE = """
CREATE INDEX IF NOT EXISTS _kml_agent_events_trace_idx
    ON _kml_agent_events(trace_id, seq);
"""


class SQLiteSinkError(RuntimeError):
    """Raised on SQLiteSink schema-init or insert failures."""


def default_ml_db_path() -> Path:
    """Return the canonical ``~/.kailash_ml/ml.db`` path.

    Matches ``kailash_ml.tracking.runner._DEFAULT_TRACKER_DB`` so the
    Kaizen agent-trace tables share a database file with the ML run
    tables — dashboards can ``JOIN _kml_run ON _kml_agent_runs.run_id``
    without a second connection.
    """
    return Path.home() / ".kailash_ml" / "ml.db"


class SQLiteSink:
    """Persistent trace-event sink backed by SQLite.

    Args:
        db_path: Filesystem path to the SQLite database file. Defaults
            to :func:`default_ml_db_path` (``~/.kailash_ml/ml.db``) —
            the same store kailash-ml's ``ExperimentTracker`` writes to,
            so ``_kml_run.run_id`` joins to ``_kml_agent_runs.run_id``.
        run_id: When supplied, every exported event's trace row records
            this as its ML run correlation id. When ``None``, the sink
            leaves ``run_id`` NULL — callers relying on join behavior
            MUST pass the ambient ``km.track()`` run_id at construction.
        agent_id: Default agent id for trace-row creation. Every event
            exported against a fresh ``trace_id`` creates a row with
            this agent_id; events with their own agent_id override.
        tenant_id: Optional tenant scope — persisted on every trace row
            per ``rules/tenant-isolation.md`` §5.

    Thread-safety: a single ``sqlite3.Connection`` is created in
    ``check_same_thread=False`` mode and guarded by an internal
    ``threading.Lock``. This is the sqlite3-recommended pattern for
    sinks that export from multiple worker threads.

    Per ``rules/patterns.md`` § Async Resource Cleanup: this class
    emits a ``ResourceWarning`` from ``__del__`` when callers forget
    to call :meth:`close`; the finalizer does NOT perform any cleanup
    that would touch the logging machinery (which would deadlock under
    GC).
    """

    _DEFAULT_AGENT_ID: str = "kaizen.agent"

    def __init__(
        self,
        *,
        db_path: Optional[Path] = None,
        run_id: Optional[str] = None,
        agent_id: str = _DEFAULT_AGENT_ID,
        tenant_id: Optional[str] = None,
    ) -> None:
        self._db_path: Path = db_path if db_path is not None else default_ml_db_path()
        self._run_id: Optional[str] = run_id
        self._agent_id: str = agent_id
        self._tenant_id: Optional[str] = tenant_id
        self._seq_by_trace: dict[str, int] = {}
        self._lock = threading.Lock()
        self._closed = False

        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                isolation_level=None,  # autocommit — we manage transactions explicitly
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as e:
            raise SQLiteSinkError(
                f"SQLiteSink failed to open {self._db_path}: {e}"
            ) from e

        self._init_schema()

        logger.info(
            "kaizen.ml.sqlite_sink.init",
            extra={
                "db_path": str(self._db_path),
                "run_id": self._run_id,
                "agent_id": self._agent_id,
                "tenant_id": self._tenant_id,
                "mode": "real",
            },
        )

    def _init_schema(self) -> None:
        try:
            with self._lock:
                self._conn.execute(_SCHEMA_AGENT_RUNS)
                self._conn.execute(_INDEX_AGENT_RUNS_TENANT)
                self._conn.execute(_INDEX_AGENT_RUNS_RUN)
                self._conn.execute(_SCHEMA_AGENT_EVENTS)
                self._conn.execute(_INDEX_AGENT_EVENTS_TRACE)
        except sqlite3.Error as e:
            raise SQLiteSinkError(
                f"SQLiteSink schema-init failed on {self._db_path}: {e}"
            ) from e

    # ── Public contract (TraceExporter sink callable shape) ────────

    def export(self, event: TraceEvent, fingerprint: str) -> None:
        """Persist ``event`` with its pre-computed ``fingerprint``.

        The fingerprint is computed ONCE at the ``TraceExporter`` layer
        (the single filter point per ``rules/event-payload-classification.md``
        §1). This sink persists what it is given — it does NOT re-hash,
        which both preserves cross-SDK parity and avoids the
        fingerprint drift that would occur if two layers both computed
        their own digest from the same canonical dict.
        """
        self._validate_status(event.status)
        self._ensure_trace_row(event)
        self._insert_event(event, fingerprint)

    async def export_async(self, event: TraceEvent, fingerprint: str) -> None:
        """Async counterpart of :meth:`export` — the backing ``sqlite3``
        driver is sync, so this simply delegates under the lock. The
        method exists so ``TraceExporter`` can route both sync and async
        agents through the same sink without a separate backend path.
        """
        self.export(event, fingerprint)

    def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        if self._closed:
            return
        with self._lock:
            if self._closed:
                return
            try:
                self._conn.close()
            except sqlite3.Error as e:
                logger.warning(
                    "kaizen.ml.sqlite_sink.close_failed",
                    extra={
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "mode": "real",
                    },
                )
            self._closed = True
        logger.info(
            "kaizen.ml.sqlite_sink.closed",
            extra={"db_path": str(self._db_path), "mode": "real"},
        )

    # ── Context-manager convenience ────────────────────────────────

    def __enter__(self) -> "SQLiteSink":
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.close()

    # ── Internals ──────────────────────────────────────────────────

    def _validate_status(self, status: Optional[TraceEventStatus]) -> None:
        # Per spec §5.3: event-level status is OK / ERROR / CANCELLED
        # (from TraceEventStatus). The run-level status (_kml_agent_runs)
        # uses RUNNING / FINISHED / FAILED / KILLED — different surface,
        # validated at trace-row creation time.
        #
        # This helper is the event-level gate; trace-row gating happens
        # in _ensure_trace_row.
        if status is None:
            return
        if not isinstance(status, TraceEventStatus):
            raise SQLiteSinkError(
                f"event.status must be TraceEventStatus, got {type(status).__name__}"
            )

    def _ensure_trace_row(self, event: TraceEvent) -> str:
        """Create the per-trace row on first event; return the trace_id.

        The trace_id is derived from ``event.trace_id`` when set, else
        from ``event.run_id`` — the ``TraceExporter`` supplies both
        when available. Per spec §5.4: when a ``km.track()`` run is
        ambient at sink construction, that run's ``run_id`` is stamped
        on the trace row so the dashboard can join ``_kml_run`` to
        ``_kml_agent_runs``.
        """
        trace_id = event.trace_id or event.run_id
        if not trace_id:
            trace_id = f"trace-{uuid.uuid4().hex}"

        with self._lock:
            if trace_id in self._seq_by_trace:
                return trace_id
            # Seq counter per trace — monotone within trace (spec §5.2).
            self._seq_by_trace[trace_id] = 0

            existing = self._conn.execute(
                "SELECT trace_id FROM _kml_agent_runs WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if existing is not None:
                return trace_id

            started_at = (
                event.timestamp.astimezone(timezone.utc).isoformat()
                if event.timestamp.tzinfo is not None
                else event.timestamp.replace(tzinfo=timezone.utc).isoformat()
            )
            try:
                self._conn.execute(
                    """
                    INSERT INTO _kml_agent_runs (
                        trace_id, run_id, agent_id, tenant_id, actor_id,
                        started_at, ended_at, status, cost_microdollars
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace_id,
                        self._run_id,
                        event.agent_id or self._agent_id,
                        event.tenant_id or self._tenant_id,
                        None,  # actor_id — supplied by PACT envelope on later work
                        started_at,
                        None,
                        "RUNNING",
                        int(event.cost_microdollars or 0),
                    ),
                )
            except sqlite3.Error as e:
                raise SQLiteSinkError(
                    f"SQLiteSink insert into _kml_agent_runs failed: {e}"
                ) from e

        logger.info(
            "kaizen.ml.sqlite_sink.trace_started",
            extra={
                "trace_id": trace_id,
                "run_id": self._run_id,
                "agent_id": event.agent_id or self._agent_id,
                "mode": "real",
            },
        )
        return trace_id

    def _insert_event(self, event: TraceEvent, fingerprint: str) -> None:
        trace_id = event.trace_id or event.run_id or ""
        event_id = event.event_id or f"event-{uuid.uuid4().hex}"

        status_str = event.status.value if event.status is not None else "ok"
        event_type_str = (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        )
        at_str = (
            event.timestamp.astimezone(timezone.utc).isoformat()
            if event.timestamp.tzinfo is not None
            else event.timestamp.replace(tzinfo=timezone.utc).isoformat()
        )

        payload_json: Optional[str]
        if event.payload is not None:
            try:
                payload_json = json.dumps(
                    event.payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    default=str,
                )
            except (TypeError, ValueError) as e:
                logger.warning(
                    "kaizen.ml.sqlite_sink.payload_unserializable",
                    extra={
                        "event_id": event_id,
                        "error_type": type(e).__name__,
                        "mode": "real",
                    },
                )
                payload_json = None
        else:
            payload_json = None

        with self._lock:
            seq = self._seq_by_trace.get(trace_id, 0) + 1
            self._seq_by_trace[trace_id] = seq
            try:
                self._conn.execute(
                    """
                    INSERT INTO _kml_agent_events (
                        event_id, trace_id, seq, event_type, event_status,
                        fingerprint, at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        trace_id,
                        seq,
                        event_type_str,
                        status_str,
                        fingerprint,
                        at_str,
                        payload_json,
                    ),
                )
                # Accumulate cost on the trace row (spec §5.2 — running
                # total; dashboard uses it as the rollup for display).
                if event.cost_microdollars:
                    self._conn.execute(
                        """
                        UPDATE _kml_agent_runs
                        SET cost_microdollars = cost_microdollars + ?
                        WHERE trace_id = ?
                        """,
                        (int(event.cost_microdollars), trace_id),
                    )
            except sqlite3.Error as e:
                raise SQLiteSinkError(
                    f"SQLiteSink insert into _kml_agent_events failed: {e}"
                ) from e

    def finalize_trace(
        self,
        trace_id: str,
        *,
        status: str = "FINISHED",
        ended_at: Optional[datetime] = None,
    ) -> None:
        """Mark a trace row terminal. Callers use this when the agent
        run completes to transition ``RUNNING → FINISHED/FAILED/KILLED``.

        Status MUST be a member of :data:`VALID_AGENT_RUN_STATUSES`.
        """
        if status not in VALID_AGENT_RUN_STATUSES:
            raise SQLiteSinkError(
                f"Invalid status {status!r}; must be one of "
                f"{sorted(VALID_AGENT_RUN_STATUSES)}"
            )
        ended = (
            ended_at.astimezone(timezone.utc).isoformat()
            if ended_at is not None and ended_at.tzinfo is not None
            else (ended_at or datetime.now(timezone.utc))
            .astimezone(timezone.utc)
            .isoformat()
        )
        with self._lock:
            try:
                self._conn.execute(
                    """
                    UPDATE _kml_agent_runs
                    SET status = ?, ended_at = ?
                    WHERE trace_id = ?
                    """,
                    (status, ended, trace_id),
                )
            except sqlite3.Error as e:
                raise SQLiteSinkError(f"SQLiteSink finalize_trace failed: {e}") from e

    # ── Finalizer — ResourceWarning only, no real cleanup ──────────

    def __del__(self, _warnings: Any = None) -> None:  # pragma: no cover
        if _warnings is None:
            import warnings as _warnings_module

            _warnings = _warnings_module
        if not getattr(self, "_closed", True):
            try:
                _warnings.warn(
                    "SQLiteSink not closed; call sink.close() to release "
                    "the sqlite3 connection",
                    ResourceWarning,
                    stacklevel=2,
                )
            except Exception:  # interpreter shutdown
                pass
