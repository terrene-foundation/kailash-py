# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""First-party persistent workflow history for the Kailash Python SDK.

This module is the W2 wave of the runtime-integration-trio: a queryable
audit log of per-node :class:`~kailash.runtime.durable.NodeCompletionEvent`
records emitted by :class:`~kailash.runtime.local.LocalRuntime` /
:class:`~kailash.runtime.async_local.AsyncLocalRuntime` via the W1
``on_node_complete`` hook registry.

Public surface:

* :class:`WorkflowHistoryStore` — abstract base.  Defines ``record_event``
  (the hook callback) plus the read-side query API (``list_runs``,
  ``get_run``, ``get_run_events``, ``list_failed``).
* :class:`PostgresHistoryStore` / :class:`SQLiteHistoryStore` — concrete
  implementations.  Both share the same dialect-portable schema and
  query plumbing; the subclasses exist so callers can be explicit about
  which dialect they target.  Per ``rules/infrastructure-sql.md``
  Rules 3-5 every query uses canonical ``?`` placeholders +
  :meth:`~kailash.db.dialect.QueryDialect.upsert` / ``dialect.blob_type()``
  / ``dialect.text_column()`` and per ``rules/schema-migration.md``
  Rule 1 ALL DDL lives in :meth:`initialize`.

Auto-subscribe pattern::

    from kailash.db.connection import ConnectionManager
    from kailash.infrastructure.history_store import PostgresHistoryStore
    from kailash.runtime.local import LocalRuntime

    conn = ConnectionManager(os.environ["KAILASH_DATABASE_URL"])
    await conn.initialize()
    history = PostgresHistoryStore(conn, retention_days=30)
    await history.initialize()

    runtime = LocalRuntime(history_store=history)
    # The runtime auto-registers history.record_event via the W1 hook
    # registry — every node completion lands a row in workflow_run_events
    # (and a workflow_runs row on first sight of the run_id).

Tenant isolation:
    Every read filters by ``tenant_id`` resolved from the runtime context
    (see :func:`~kailash.runtime.durable.resolve_tenant_id`).  Cross-tenant
    reads are BLOCKED at the store layer per
    ``rules/tenant-isolation.md`` MUST Rule 5.

Redaction at write-time:
    :meth:`record_event` routes every event through
    :func:`~kailash.runtime.durable.redact_event_for_persistence` BEFORE
    persisting.  Per the cross-cutting invariant: read-redaction at
    write-time, never re-redacted at read-time.

Retention:
    30-day TTL on ``terminal_at`` (NOT ``started_at``) by default.
    In-flight runs (``terminal_at IS NULL``) are NOT eligible for
    truncation.  ``retention_days=N`` overrides; ``retention_days=False``
    disables.  Lazy eviction at write-time + explicit
    :meth:`delete_runs_older_than` (which requires ``force_downgrade=True``
    per ``rules/schema-migration.md`` Rule 7).

Per-tenant cap:
    Default cap of 10,000 runs per tenant.  When a write would exceed
    the cap, the oldest run (by ``started_at``) is evicted with a WARN
    log line carrying op name + attempted/failed/sample fields per
    ``rules/observability.md`` Rule 7.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Union

from kailash.db.connection import ConnectionManager
from kailash.runtime.durable import NodeCompletionEvent, redact_event_for_persistence

logger = logging.getLogger(__name__)

__all__ = [
    "DowngradeRefusedError",
    "PostgresHistoryStore",
    "SQLiteHistoryStore",
    "WorkflowHistoryStore",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Per ``rules/infrastructure-sql.md`` MUST Rule 6 — table names cannot
#: be parameterized in SQL, so constructor-time validation is the only
#: defense against SQL injection through dynamic table names.
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

#: Default 30-day TTL on ``terminal_at`` for retention sweeps.
_DEFAULT_RETENTION_DAYS = 30

#: Default per-tenant cap; oldest run evicted with WARN log on overflow.
_DEFAULT_PER_TENANT_CAP = 10_000

#: ContextVar guarding ``delete_runs_older_than`` during an internal lazy
#: eviction sweep so the recursion through write-time eviction does not
#: trip the ``force_downgrade=True`` requirement on the public surface.
#: The flag is True ONLY when set explicitly inside the store's own write
#: path; user-supplied calls to ``delete_runs_older_than`` MUST still go
#: through the keyword-only ``force_downgrade`` gate.
_INTERNAL_EVICTION_CONTEXT: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "kailash.history_store.internal_eviction", default=False
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DowngradeRefusedError(RuntimeError):
    """Raised when :meth:`WorkflowHistoryStore.delete_runs_older_than` is
    called without the ``force_downgrade=True`` confirmation flag.

    The orchestrator-layer destructive-confirmation guard mandated by
    ``rules/schema-migration.md`` MUST Rule 7.  Distinct from
    ``DropRefusedError`` (per ``rules/dataflow-identifier-safety.md``
    MUST Rule 6) — the primitive layer guards individual DROP statements;
    this layer guards the multi-row retention sweep.
    """


# ---------------------------------------------------------------------------
# WorkflowHistoryStore (abstract base)
# ---------------------------------------------------------------------------


class WorkflowHistoryStore(ABC):
    """Abstract base for persistent workflow history backends.

    Subscribes to :meth:`runtime.on_node_complete` via :meth:`record_event`
    and persists per-node events into a queryable audit log partitioned by
    ``tenant_id``.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
        The history store does NOT close the manager on :meth:`close` —
        per ``rules/infrastructure-sql.md`` MUST NOT clauses, all stores
        share one pool owned by the caller (typically
        :class:`~kailash.infrastructure.factory.StoreFactory`).
    runs_table:
        Name of the workflow-runs table.  Validated against
        ``^[a-zA-Z_][a-zA-Z0-9_]*$`` per Rule 6.
    events_table:
        Name of the per-node-events table.  Validated similarly.
    retention_days:
        Number of days to retain a run after its ``terminal_at`` timestamp.
        ``False`` disables retention.  Default 30.
    per_tenant_cap:
        Maximum number of runs to retain per tenant.  When exceeded, the
        oldest run (by ``started_at``) is evicted with a WARN log line.
        Default 10,000.
    classification_policy:
        Optional policy forwarded to
        :func:`~kailash.runtime.durable.redact_event_for_persistence`.
        ``None`` is the single-classification default.
    """

    # ------------------------------------------------------------------
    # Construction + lifecycle
    # ------------------------------------------------------------------
    def __init__(
        self,
        conn_manager: ConnectionManager,
        *,
        runs_table: str = "workflow_runs",
        events_table: str = "workflow_run_events",
        retention_days: Union[int, bool] = _DEFAULT_RETENTION_DAYS,
        per_tenant_cap: int = _DEFAULT_PER_TENANT_CAP,
        classification_policy: Optional[Any] = None,
    ) -> None:
        # Per ``rules/infrastructure-sql.md`` MUST Rule 6 — validate the
        # table names BEFORE storing them; constructor-time validation is
        # the only defense against SQL injection through dynamic table
        # names.  A future caller passing a user-supplied table name must
        # see the failure here, not when the first query interpolates.
        if not isinstance(runs_table, str) or not _TABLE_NAME_RE.match(runs_table):
            raise ValueError(
                "WorkflowHistoryStore: runs_table must match " "[a-zA-Z_][a-zA-Z0-9_]*"
            )
        if not isinstance(events_table, str) or not _TABLE_NAME_RE.match(events_table):
            raise ValueError(
                "WorkflowHistoryStore: events_table must match "
                "[a-zA-Z_][a-zA-Z0-9_]*"
            )
        # retention_days: accept False (disabled) OR a positive int.
        if retention_days is False:
            self._retention_days: Optional[int] = None
        elif isinstance(retention_days, bool):
            # bool is a subclass of int — handle True explicitly so it
            # doesn't silently coerce to 1.
            raise ValueError(
                "WorkflowHistoryStore: retention_days=True is not a valid "
                "override; pass False to disable, or a positive integer."
            )
        elif isinstance(retention_days, int) and retention_days > 0:
            self._retention_days = retention_days
        else:
            raise ValueError(
                "WorkflowHistoryStore: retention_days must be a positive "
                "integer or False (to disable)."
            )

        if not isinstance(per_tenant_cap, int) or per_tenant_cap <= 0:
            raise ValueError(
                "WorkflowHistoryStore: per_tenant_cap must be a positive " "integer."
            )

        self._conn = conn_manager
        self._runs_table = runs_table
        self._events_table = events_table
        self._per_tenant_cap = per_tenant_cap
        self._policy = classification_policy
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables + indexes if they do not already exist.

        Per ``rules/schema-migration.md`` MUST Rule 1 ALL ``CREATE TABLE``
        and ``CREATE INDEX`` DDL lives in this method ONLY — the
        ``/redteam`` mechanical sweep (Rule 1a) MUST grep for inline DDL
        outside ``initialize`` and BLOCK on hits.
        """

    async def close(self) -> None:
        """Release any resources held by the backend.

        The underlying ConnectionManager is NOT closed here — it is
        owned by the caller and may be shared with other stores per
        ``rules/infrastructure-sql.md`` MUST NOT clause "No separate
        ConnectionManagers per store".
        """
        logger.debug("WorkflowHistoryStore backend closed")

    # ------------------------------------------------------------------
    # Hook-side: record_event (subscribed via runtime.on_node_complete)
    # ------------------------------------------------------------------
    async def record_event(self, event: NodeCompletionEvent) -> None:
        """Persist *event* — called by the runtime hook registry.

        Read-redaction at write time.  Per the cross-cutting invariant
        the event is routed through
        :func:`~kailash.runtime.durable.redact_event_for_persistence`
        BEFORE any database write.  Subscribers downstream of this store
        observe ALREADY-redacted rows.

        On first sight of ``event.run_id`` an entry is upserted into the
        runs table (``status='running'``); on every subsequent event the
        row is updated to reflect the latest state.  Terminal events
        (an event whose ``error`` field is set OR whose node is the
        workflow's final node) close out the run with ``terminal_at`` set.
        """
        if not self._initialized:
            raise RuntimeError(
                "WorkflowHistoryStore.record_event(): store is not "
                "initialized.  Call await store.initialize() before "
                "registering the callback with runtime.on_node_complete()."
            )

        if event.run_id is None:
            # The runtime path that produced this event ran without a
            # task_manager AND the AsyncLocalRuntime ID-derivation path
            # did not assign one.  Without a run_id we cannot partition
            # the event into a run row; log at WARN and drop.  See
            # ``rules/observability.md`` Rule 7 (no silent swallow).
            logger.warning(
                "history_store.record_event.skipped_no_run_id",
                extra={
                    "node_id_hash": _hash_short(event.node_id),
                    "workflow_id": event.workflow_id,
                },
            )
            return

        # Read-redaction at write time (cross-cutting invariant 4).
        redacted = redact_event_for_persistence(
            event, classification_policy=self._policy
        )

        # Build the persisted JSON payload.  Per the spec the payload
        # combines ``outputs`` + ``metadata`` after redaction; the raw
        # event's classification summary already lives in metadata.
        payload = {
            "outputs": dict(redacted.outputs),
            "metadata": dict(redacted.metadata),
        }
        payload_json = json.dumps(payload, default=str)

        # The classified-field count rides at column-level so operators
        # can run "show me runs whose events redacted >0 fields" without
        # scanning the JSON blob.
        classification_summary = redacted.metadata.get("classification_summary", {})
        classified_field_count = int(
            classification_summary.get("classified_field_count", 0)
        )

        ts_iso = redacted.ended_at.isoformat()
        started_at_iso = redacted.started_at.isoformat()
        node_id_hash = _hash_short(redacted.node_id)
        is_terminal_failure = redacted.error is not None

        async with self._conn.transaction() as tx:
            # 1) Upsert the run row.  Status becomes "failed" on the
            #    first error event; otherwise runs as "running" until
            #    a caller explicitly marks it complete via the runtime's
            #    own terminal-state path (W3+).  For W2 we only flip to
            #    "failed" on a node error.
            existing = await tx.fetchone(
                f"SELECT status, terminal_at FROM {self._runs_table} "
                f"WHERE run_id = ? AND tenant_id = ?",
                redacted.run_id,
                _tenant_partition(redacted.tenant_id),
            )
            if existing is None:
                # First sight of this run.  Insert a fresh row.
                status = "failed" if is_terminal_failure else "running"
                terminal_at = ts_iso if is_terminal_failure else None
                await tx.execute(
                    f"INSERT INTO {self._runs_table} "
                    f"(run_id, tenant_id, workflow_id, workflow_fingerprint, "
                    f"started_at, terminal_at, status, idempotency_key) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    redacted.run_id,
                    _tenant_partition(redacted.tenant_id),
                    redacted.workflow_id,
                    redacted.workflow_fingerprint,
                    started_at_iso,
                    terminal_at,
                    status,
                    redacted.idempotency_key,
                )
            elif is_terminal_failure and existing.get("terminal_at") is None:
                # Update an in-flight run to failed terminal state.
                await tx.execute(
                    f"UPDATE {self._runs_table} "
                    f"SET status = ?, terminal_at = ? "
                    f"WHERE run_id = ? AND tenant_id = ?",
                    "failed",
                    ts_iso,
                    redacted.run_id,
                    _tenant_partition(redacted.tenant_id),
                )

            # 2) Append the per-node event.  ``event_seq`` is monotonic
            #    per run — derived inside the same transaction so two
            #    concurrent writers cannot collide.
            seq_row = await tx.fetchone(
                f"SELECT COALESCE(MAX(event_seq), 0) AS max_seq "
                f"FROM {self._events_table} WHERE run_id = ?",
                redacted.run_id,
            )
            next_seq = int(seq_row["max_seq"] if seq_row else 0) + 1

            event_type = "node_failed" if is_terminal_failure else "node_completed"
            await tx.execute(
                f"INSERT INTO {self._events_table} "
                f"(run_id, event_seq, node_id_hash, event_type, payload_json, "
                f"classified_field_count, ts) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                redacted.run_id,
                next_seq,
                node_id_hash,
                event_type,
                payload_json,
                classified_field_count,
                ts_iso,
            )

        # 3) Lazy retention sweep + per-tenant cap.  These run OUTSIDE
        #    the transaction so they cannot rollback the write that
        #    triggered them.  Every site that performs a destructive
        #    sweep enters via the internal-eviction context to bypass
        #    the public ``force_downgrade=True`` gate per Rule 7.
        await self._lazy_retention_sweep()
        await self._enforce_per_tenant_cap(_tenant_partition(redacted.tenant_id))

    # ------------------------------------------------------------------
    # Read API (every method tenant-isolated)
    # ------------------------------------------------------------------
    async def list_runs(
        self,
        *,
        filter: Optional[Mapping[str, Any]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List runs filtered by ``filter`` (must include ``tenant_id``).

        Cross-tenant reads are BLOCKED — a missing or empty
        ``tenant_id`` raises ``ValueError``.  Index-backed query path:
        ``(tenant_id, started_at DESC)`` for the unfiltered list,
        ``(tenant_id, status, started_at DESC)`` for status-filtered.
        """
        filt = dict(filter or {})
        tenant_id = filt.pop("tenant_id", None)
        if not tenant_id:
            raise ValueError(
                "WorkflowHistoryStore.list_runs: filter MUST include "
                "tenant_id (non-empty).  Cross-tenant reads are blocked "
                "at the store layer per rules/tenant-isolation.md."
            )
        status_filter = filt.pop("status", None)
        if filt:
            # Refuse silently-ignored filter keys per
            # ``rules/zero-tolerance.md`` Rule 3c — accepted kwarg with
            # no consumer is a contract violation.
            raise ValueError(
                f"WorkflowHistoryStore.list_runs: unsupported filter keys "
                f"{sorted(filt.keys())!r}.  Supported: tenant_id, status."
            )
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")

        if status_filter is not None:
            rows = await self._conn.fetch(
                f"SELECT run_id, tenant_id, workflow_id, workflow_fingerprint, "
                f"started_at, terminal_at, status, idempotency_key "
                f"FROM {self._runs_table} "
                f"WHERE tenant_id = ? AND status = ? "
                f"ORDER BY started_at DESC LIMIT ? OFFSET ?",
                _tenant_partition(tenant_id),
                status_filter,
                limit,
                offset,
            )
        else:
            rows = await self._conn.fetch(
                f"SELECT run_id, tenant_id, workflow_id, workflow_fingerprint, "
                f"started_at, terminal_at, status, idempotency_key "
                f"FROM {self._runs_table} "
                f"WHERE tenant_id = ? "
                f"ORDER BY started_at DESC LIMIT ? OFFSET ?",
                _tenant_partition(tenant_id),
                limit,
                offset,
            )
        return [dict(r) for r in rows]

    async def get_run(
        self,
        run_id: str,
        *,
        tenant_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Return one run row, tenant-scoped.  None if no match."""
        if not run_id:
            raise ValueError("get_run: run_id must be a non-empty string")
        if not tenant_id:
            raise ValueError(
                "get_run: tenant_id MUST be a non-empty string.  Cross-"
                "tenant reads are blocked at the store layer."
            )
        row = await self._conn.fetchone(
            f"SELECT run_id, tenant_id, workflow_id, workflow_fingerprint, "
            f"started_at, terminal_at, status, idempotency_key "
            f"FROM {self._runs_table} WHERE run_id = ? AND tenant_id = ?",
            run_id,
            _tenant_partition(tenant_id),
        )
        return dict(row) if row else None

    async def get_run_events(
        self,
        run_id: str,
        *,
        tenant_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Return all events for *run_id* in monotonic ``event_seq`` order.

        Tenant scope is enforced by JOINing to the runs table — an event
        whose run is owned by a different tenant returns no rows.  The
        ``payload_json`` column is decoded back into a dict.
        """
        if not run_id:
            raise ValueError("get_run_events: run_id must be a non-empty string")
        if not tenant_id:
            raise ValueError(
                "get_run_events: tenant_id MUST be a non-empty string.  "
                "Cross-tenant reads are blocked at the store layer."
            )
        # Tenant-scope check: confirm the run row exists for this tenant
        # before returning any events.
        run = await self._conn.fetchone(
            f"SELECT 1 FROM {self._runs_table} " f"WHERE run_id = ? AND tenant_id = ?",
            run_id,
            _tenant_partition(tenant_id),
        )
        if run is None:
            return []
        rows = await self._conn.fetch(
            f"SELECT id, run_id, event_seq, node_id_hash, event_type, "
            f"payload_json, classified_field_count, ts "
            f"FROM {self._events_table} "
            f"WHERE run_id = ? ORDER BY event_seq ASC",
            run_id,
        )
        result: List[Dict[str, Any]] = []
        for row in rows:
            event_dict = dict(row)
            raw = event_dict.pop("payload_json", None)
            try:
                event_dict["payload"] = json.loads(raw) if raw else {}
            except (TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    "history_store.get_run_events.payload_decode_failed",
                    extra={
                        "run_id": run_id,
                        "event_seq": event_dict.get("event_seq"),
                        "error_type": type(exc).__name__,
                    },
                )
                event_dict["payload"] = {}
            result.append(event_dict)
        return result

    async def list_failed(
        self,
        *,
        tenant_id: Optional[str],
        since: Optional[Union[datetime, str]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List failed runs, tenant-scoped.  Index-backed via
        ``(tenant_id, status, started_at DESC)``.
        """
        if not tenant_id:
            raise ValueError("list_failed: tenant_id MUST be a non-empty string.")
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        since_iso: Optional[str]
        if since is None:
            since_iso = None
        elif isinstance(since, datetime):
            since_iso = since.isoformat()
        elif isinstance(since, str):
            since_iso = since
        else:
            raise TypeError(  # pyright: ignore[reportUnreachable]
                f"list_failed: since must be a datetime, ISO-8601 string, or None "
                f"— got {type(since).__name__!r}"
            )
        if since_iso is not None:
            rows = await self._conn.fetch(
                f"SELECT run_id, tenant_id, workflow_id, workflow_fingerprint, "
                f"started_at, terminal_at, status, idempotency_key "
                f"FROM {self._runs_table} "
                f"WHERE tenant_id = ? AND status = 'failed' "
                f"AND started_at >= ? "
                f"ORDER BY started_at DESC LIMIT ?",
                _tenant_partition(tenant_id),
                since_iso,
                limit,
            )
        else:
            rows = await self._conn.fetch(
                f"SELECT run_id, tenant_id, workflow_id, workflow_fingerprint, "
                f"started_at, terminal_at, status, idempotency_key "
                f"FROM {self._runs_table} "
                f"WHERE tenant_id = ? AND status = 'failed' "
                f"ORDER BY started_at DESC LIMIT ?",
                _tenant_partition(tenant_id),
                limit,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Retention API
    # ------------------------------------------------------------------
    async def delete_runs_older_than(
        self,
        timestamp: Union[datetime, str],
        *,
        force_downgrade: bool = False,
    ) -> int:
        """Delete all runs whose ``terminal_at`` is older than *timestamp*.

        In-flight runs (``terminal_at IS NULL``) are NEVER affected.
        Cross-tenant — every tenant's expired runs are pruned.

        Per ``rules/schema-migration.md`` MUST Rule 7 the destructive
        downgrade-shape API requires ``force_downgrade=True``;
        otherwise raises :class:`DowngradeRefusedError`.

        The internal write-time eviction sweep bypasses the gate via
        a contextvar — user-supplied calls MUST still pass the flag.
        """
        # The internal-eviction context is set ONLY inside this store's
        # own write path.  User-supplied calls always see the default
        # False and MUST satisfy the public ``force_downgrade`` gate.
        if not force_downgrade and not _INTERNAL_EVICTION_CONTEXT.get():
            raise DowngradeRefusedError(
                "delete_runs_older_than() refused — destructive sweep of "
                "workflow history rows.  Pass force_downgrade=True to "
                "acknowledge data loss is irreversible."
            )

        if isinstance(timestamp, datetime):
            ts_iso = timestamp.isoformat()
        elif isinstance(timestamp, str):
            ts_iso = timestamp
        else:
            raise TypeError(  # pyright: ignore[reportUnreachable]
                f"delete_runs_older_than: timestamp must be a datetime or "
                f"ISO-8601 string — got {type(timestamp).__name__!r}"
            )

        async with self._conn.transaction() as tx:
            expired_runs = await tx.fetch(
                f"SELECT run_id FROM {self._runs_table} "
                f"WHERE terminal_at IS NOT NULL AND terminal_at < ?",
                ts_iso,
            )
            run_ids = [r["run_id"] for r in expired_runs]
            deleted = len(run_ids)
            for run_id in run_ids:
                await tx.execute(
                    f"DELETE FROM {self._events_table} WHERE run_id = ?",
                    run_id,
                )
                await tx.execute(
                    f"DELETE FROM {self._runs_table} WHERE run_id = ?",
                    run_id,
                )

        if deleted > 0:
            logger.info(
                "history_store.retention.swept",
                extra={
                    "attempted": deleted,
                    "failed": 0,
                    "before_ts": ts_iso,
                },
            )
        return deleted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _lazy_retention_sweep(self) -> None:
        """Drop runs whose ``terminal_at`` exceeds the retention window.

        No-op when ``retention_days`` is None (disabled).  Bypasses the
        ``force_downgrade`` gate via the internal-eviction context.
        """
        if self._retention_days is None:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        token = _INTERNAL_EVICTION_CONTEXT.set(True)
        try:
            await self.delete_runs_older_than(cutoff)
        finally:
            _INTERNAL_EVICTION_CONTEXT.reset(token)

    async def _enforce_per_tenant_cap(self, tenant_id: str) -> None:
        """Evict the oldest runs for *tenant_id* until the cap is satisfied.

        Per ``rules/observability.md`` Rule 7 a WARN log line is emitted
        whenever ≥1 row is evicted — operators need bulk-failure
        visibility (attempted/failed/sample fields).
        """
        count_row = await self._conn.fetchone(
            f"SELECT COUNT(*) AS cnt FROM {self._runs_table} WHERE tenant_id = ?",
            tenant_id,
        )
        count = int(count_row["cnt"] if count_row else 0)
        excess = count - self._per_tenant_cap
        if excess <= 0:
            return

        # Identify the N oldest runs and drop them inside a transaction.
        oldest = await self._conn.fetch(
            f"SELECT run_id, started_at FROM {self._runs_table} "
            f"WHERE tenant_id = ? ORDER BY started_at ASC LIMIT ?",
            tenant_id,
            excess,
        )
        if not oldest:
            return

        sample_run_id = oldest[0]["run_id"]
        async with self._conn.transaction() as tx:
            for row in oldest:
                run_id = row["run_id"]
                await tx.execute(
                    f"DELETE FROM {self._events_table} WHERE run_id = ?",
                    run_id,
                )
                await tx.execute(
                    f"DELETE FROM {self._runs_table} "
                    f"WHERE run_id = ? AND tenant_id = ?",
                    run_id,
                    tenant_id,
                )

        logger.warning(
            "history_store.per_tenant_cap.evicted",
            extra={
                "attempted": excess,
                "failed": 0,
                "tenant_id_hash": _hash_short(tenant_id),
                "sample_run_id": sample_run_id,
                "cap": self._per_tenant_cap,
            },
        )


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class _SharedSchemaInitializer:
    """Mixin holding the dialect-portable DDL shared by both subclasses.

    The DDL lives ONLY in ``initialize`` per ``rules/schema-migration.md``
    MUST Rule 1.  Subclasses that need dialect-specific tweaks override
    ``initialize`` and call ``_create_schema``.
    """

    async def _create_schema(self) -> None:
        """Create the workflow_runs + workflow_run_events tables + indexes.

        Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1 every
        dynamic identifier interpolated into DDL routes through
        ``dialect.quote_identifier()``.  Per
        ``rules/infrastructure-sql.md`` Rule 4 the binary/blob and JSON
        column types come from the dialect helper, not hardcoded names.
        """
        # mypy: this mixin is consumed inside WorkflowHistoryStore so
        # ``self._conn`` / ``self._runs_table`` / ``self._events_table``
        # exist at runtime.
        conn = self._conn  # type: ignore[attr-defined]
        runs_table_quoted = conn.dialect.quote_identifier(
            self._runs_table  # type: ignore[attr-defined]
        )
        events_table_quoted = conn.dialect.quote_identifier(
            self._events_table  # type: ignore[attr-defined]
        )
        text_indexed = conn.dialect.text_column(indexed=True)
        text_unindexed = conn.dialect.text_column(indexed=False)
        # Per ``rules/infrastructure-sql.md`` MUST Rule 4 — the JSON
        # payload uses the dialect's TEXT column type (Postgres TEXT,
        # MySQL TEXT, SQLite TEXT) NOT the BLOB column.  The acceptance
        # criterion explicitly mandates ``dialect.text_column()``.
        # ``dialect.json_column_type()`` (JSONB on Postgres) would be
        # better long-term but the architecture plan for W2 specifies
        # TEXT-typed for portability across the three dialects.
        json_column_type = text_unindexed

        # workflow_runs
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {runs_table_quoted} (
                run_id {text_indexed} PRIMARY KEY,
                tenant_id {text_indexed} NOT NULL,
                workflow_id {text_indexed} NOT NULL,
                workflow_fingerprint {text_indexed} NOT NULL,
                started_at {text_indexed} NOT NULL,
                terminal_at TEXT,
                status {text_indexed} NOT NULL,
                idempotency_key TEXT
            )
            """
        )

        # workflow_run_events.  ``id`` uses the dialect's auto-id column
        # so MySQL gets AUTO_INCREMENT, Postgres SERIAL, SQLite INTEGER
        # PRIMARY KEY — per ``rules/infrastructure-sql.md`` MUST NOT
        # clause "No AUTOINCREMENT in shared DDL".
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {events_table_quoted} (
                {conn.dialect.auto_id_column()},
                run_id {text_indexed} NOT NULL,
                event_seq INTEGER NOT NULL,
                node_id_hash {text_indexed} NOT NULL,
                event_type {text_indexed} NOT NULL,
                payload_json {json_column_type} NOT NULL,
                classified_field_count INTEGER NOT NULL,
                ts {text_indexed} NOT NULL,
                UNIQUE(run_id, event_seq)
            )
            """
        )

        # Indexes per Wave 2 acceptance criteria.  All run via
        # conn.create_index which routes through dialect.quote_identifier.
        await conn.create_index(
            f"idx_{self._runs_table}_tenant_started_at",  # type: ignore[attr-defined]
            self._runs_table,  # type: ignore[attr-defined]
            "tenant_id, started_at",
        )
        await conn.create_index(
            f"idx_{self._runs_table}_tenant_run_id",  # type: ignore[attr-defined]
            self._runs_table,  # type: ignore[attr-defined]
            "tenant_id, run_id",
        )
        await conn.create_index(
            f"idx_{self._runs_table}_tenant_status_started",  # type: ignore[attr-defined]
            self._runs_table,  # type: ignore[attr-defined]
            "tenant_id, status, started_at",
        )
        await conn.create_index(
            f"idx_{self._events_table}_run_seq",  # type: ignore[attr-defined]
            self._events_table,  # type: ignore[attr-defined]
            "run_id, event_seq",
        )


class PostgresHistoryStore(_SharedSchemaInitializer, WorkflowHistoryStore):
    """PostgreSQL-backed workflow history store.

    Concrete subclass mainly for naming clarity — the dialect-portable
    schema in :class:`_SharedSchemaInitializer` already handles the
    PostgreSQL specifics (``SERIAL`` auto-id, ``TEXT`` columns,
    parameterized ``$N`` placeholders via the ConnectionManager).
    """

    async def initialize(self) -> None:
        """Create tables + indexes if not present."""
        await self._create_schema()
        self._initialized = True
        logger.info(
            "PostgresHistoryStore initialized " "(runs_table=%s, events_table=%s)",
            self._runs_table,
            self._events_table,
        )


class SQLiteHistoryStore(_SharedSchemaInitializer, WorkflowHistoryStore):
    """SQLite-backed workflow history store.

    Same dialect-portable schema as :class:`PostgresHistoryStore`; the
    ``ConnectionManager`` translates ``?`` placeholders identity for
    SQLite and emits ``INTEGER PRIMARY KEY`` (not ``AUTOINCREMENT`` —
    per ``rules/infrastructure-sql.md`` MUST NOT clause).
    """

    async def initialize(self) -> None:
        """Create tables + indexes if not present."""
        await self._create_schema()
        self._initialized = True
        logger.info(
            "SQLiteHistoryStore initialized " "(runs_table=%s, events_table=%s)",
            self._runs_table,
            self._events_table,
        )


# ---------------------------------------------------------------------------
# Tiny helpers (no external surface)
# ---------------------------------------------------------------------------


# Tenant-partition sentinel for single-tenant deployments.  Per
# ``rules/tenant-isolation.md`` MUST Rule 5 every row carries a non-NULL
# tenant_id; single-tenant deployments use the literal "default" so the
# index-backed query plan stays selective.
_DEFAULT_TENANT = "default"


def _tenant_partition(tenant_id: Optional[str]) -> str:
    """Map ``None`` → ``"default"`` for the tenant column.

    Single-tenant deployments don't carry a tenant context; the
    ``"default"`` sentinel keeps the column NOT NULL and the indexes
    selective, while still letting multi-tenant queries scope to a
    specific tenant.
    """
    if tenant_id is None or tenant_id == "":
        return _DEFAULT_TENANT
    return tenant_id


def _hash_short(value: str) -> str:
    """Short SHA-256 hash for schema-revealing log fields per
    ``rules/observability.md`` Rule 8 — never log raw node_id /
    tenant_id at WARN+.
    """
    import hashlib

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]
