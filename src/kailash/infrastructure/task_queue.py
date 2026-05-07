# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SQL-backed task queue using the ConnectionManager abstraction.

Provides a database-backed task queue that works across PostgreSQL, MySQL 8.0+,
and SQLite.  Uses ``FOR UPDATE SKIP LOCKED`` on PostgreSQL/MySQL for concurrent
dequeue without contention, and ``BEGIN IMMEDIATE`` on SQLite for single-writer
safety.

This module is the SQL alternative to the Redis-backed
:class:`~kailash.runtime.distributed.TaskQueue`.  It is suitable for Level 2
deployments where a SQL database is already available and Redis is not desired.

All SQL uses canonical ``?`` placeholders -- ConnectionManager translates to
the target dialect automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from kailash.runtime.dispatcher import Dispatcher, Task

logger = logging.getLogger(__name__)

__all__ = [
    "SQLTaskQueue",
    "SQLTaskMessage",
    "SQLTaskQueueDispatcher",
]

# Bounds on the queue's caller-controlled inputs. Defense-in-depth against
# poisoning by parties with INSERT privilege on the queue table (the
# multi-tenant queue isolation contract documented in
# `specs/scheduling.md` § "Multi-tenant queue isolation" assumes the
# operator gates writers; these bounds ensure even a permitted writer
# cannot DoS the worker pool by enqueueing unbounded payloads).
MAX_TASK_ID_LEN = 128  # uuid4 is 36 chars; W3 stable_hash is 32 chars
_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024  # 8 MiB — matches MAX_WORKFLOW_BLOB_BYTES


def _validate_task_id(tid: Any) -> None:
    """Validate a caller-supplied task_id.

    Per ``rules/security.md`` § "Input Validation", any caller-controlled
    string flowing into a primary-key column MUST be length- and charset-
    validated. Although the column is bound as a parameter (no SQLi),
    accepting unbounded keys lets a caller poison the dedup namespace
    (the W3 dispatcher computes ``task_id = stable_hash(schedule_id,
    fire_time)`` precisely so duplicate fires collapse — a caller who
    bypasses that and submits a chosen ``task_id`` could shadow a
    legitimate one).

    Accepts ``Any`` rather than ``str`` so the runtime type-confusion
    branch is reachable from external callers; static-typed callers see
    no widening because internal call sites still pass a ``str``.

    Raises
    ------
    ValueError
        If ``tid`` is not a non-empty string ≤ ``MAX_TASK_ID_LEN`` chars
        matching ``[a-zA-Z0-9_-]+``.
    """
    if not isinstance(tid, str):
        raise ValueError(f"task_id must be str, got {type(tid).__name__}")
    if len(tid) == 0 or len(tid) > MAX_TASK_ID_LEN:
        raise ValueError(f"task_id length {len(tid)} outside [1, {MAX_TASK_ID_LEN}]")
    if not _TASK_ID_RE.match(tid):
        raise ValueError(
            f"task_id must match {_TASK_ID_RE.pattern} "
            "(alphanumeric, underscore, hyphen)"
        )


@dataclass(frozen=True)
class SQLTaskMessage:
    """A task message stored in the SQL task queue.

    Frozen per EATP P10 — message instances flow across the queue boundary
    and MUST NOT be mutated after construction; the database row is the
    canonical state.

    Attributes:
        task_id: Unique identifier for the task.
        queue_name: Logical queue name for multi-queue support.
        payload: JSON-serializable task payload.
        status: Current status (pending, processing, completed, failed, dead_lettered).
        created_at: Unix timestamp when the task was created.
        updated_at: Unix timestamp of the last status change.
        attempts: Number of processing attempts so far.
        max_attempts: Maximum attempts before dead-lettering.
        visibility_timeout: Seconds before a processing task becomes re-eligible.
        worker_id: ID of the worker currently processing this task.
        error: Error message from the last failed attempt.
    """

    task_id: str = ""
    queue_name: str = "default"
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: float = 0.0
    updated_at: float = 0.0
    attempts: int = 0
    max_attempts: int = 3
    visibility_timeout: int = 300
    worker_id: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "task_id": self.task_id,
            "queue_name": self.queue_name,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "visibility_timeout": self.visibility_timeout,
            "worker_id": self.worker_id,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SQLTaskMessage:
        """Deserialize from a dictionary."""
        known_fields = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        # Ensure payload is deserialized from JSON string if needed
        if isinstance(filtered.get("payload"), str):
            filtered["payload"] = json.loads(filtered["payload"])
        return cls(**filtered)


class SQLTaskQueue:
    """SQL-backed task queue using ConnectionManager.

    Works with PostgreSQL, MySQL 8.0+, and SQLite.  Provides enqueue/dequeue
    semantics with visibility timeout, retry tracking, and dead-letter support.

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
    table_name:
        Name of the task queue table (default: ``kailash_task_queue``).
    default_visibility_timeout:
        Default seconds before a processing task becomes re-eligible
        for dequeue (default: 300).
    """

    def __init__(
        self,
        conn: Any,
        table_name: str = "kailash_task_queue",
        default_visibility_timeout: int = 300,
    ) -> None:
        from kailash.db.dialect import _validate_identifier

        _validate_identifier(table_name)
        self._conn = conn
        self._table = table_name
        self._default_visibility_timeout = default_visibility_timeout
        self._initialized = False

    async def initialize(self) -> None:
        """Create the task queue table if it does not exist.

        Safe to call multiple times (idempotent).

        Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, the
        dynamic table name is routed through ``dialect.quote_identifier()``
        for the DDL interpolation (validates + quotes). DML sites
        below reuse the validated ``self._table`` as-is since the
        identifier was already vetted by ``_validate_identifier`` in
        ``__init__`` (Rule 5 defense-in-depth).
        """
        if self._initialized:
            return

        _tc = self._conn.dialect.text_column(indexed=True)
        quoted_table = self._conn.dialect.quote_identifier(self._table)
        await self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {quoted_table} ("
            f"task_id {_tc} PRIMARY KEY, "
            f"queue_name {_tc} NOT NULL DEFAULT 'default', "
            "payload TEXT NOT NULL, "
            f"status {_tc} NOT NULL DEFAULT 'pending', "
            "created_at REAL NOT NULL, "
            "updated_at REAL NOT NULL, "
            "attempts INTEGER NOT NULL DEFAULT 0, "
            "max_attempts INTEGER NOT NULL DEFAULT 3, "
            "visibility_timeout INTEGER NOT NULL DEFAULT 300, "
            "worker_id TEXT NOT NULL DEFAULT '', "
            "error TEXT NOT NULL DEFAULT ''"
            ")"
        )

        # Index for efficient dequeue: pending tasks ordered by creation time
        await self._conn.create_index(
            f"idx_{self._table}_dequeue",
            self._table,
            "status, created_at",
        )

        # Index for stale processing detection
        await self._conn.create_index(
            f"idx_{self._table}_stale",
            self._table,
            "status, updated_at",
        )

        self._initialized = True
        logger.info("SQLTaskQueue table '%s' initialized", self._table)

    async def enqueue(
        self,
        payload: Dict[str, Any],
        queue_name: str = "default",
        task_id: Optional[str] = None,
        max_attempts: int = 3,
        visibility_timeout: Optional[int] = None,
    ) -> str:
        """Add a task to the queue.

        Parameters
        ----------
        payload:
            JSON-serializable task data.
        queue_name:
            Logical queue name for routing (default: ``"default"``).
        task_id:
            Explicit task ID, or auto-generated UUID if ``None``.
        max_attempts:
            Maximum delivery attempts before dead-lettering.
        visibility_timeout:
            Override default visibility timeout for this task.

        Returns
        -------
        str
            The task ID.
        """
        tid = task_id or str(uuid.uuid4())
        # Always validate, including the auto-generated UUID (defense-in-
        # depth: if uuid.uuid4 ever drifts to a different shape, the cap
        # still holds). Caller-supplied IDs are the actual attack surface
        # — see _validate_task_id docstring.
        _validate_task_id(tid)

        # Cap payload size before writing to the queue. A worker that
        # dequeues a multi-megabyte JSON blob will `json.loads` it into
        # memory; an unbounded payload OOMs the dequeueing worker. The
        # MAX_WORKFLOW_BLOB_BYTES cap on the producer (scheduler.py) is
        # the primary gate; this cap is the consumer-boundary defense
        # for callers that bypass the scheduler and enqueue directly.
        payload_json = json.dumps(payload)
        if len(payload_json.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"payload size {len(payload_json)} bytes exceeds "
                f"MAX_PAYLOAD_BYTES ({MAX_PAYLOAD_BYTES} bytes / "
                f"{MAX_PAYLOAD_BYTES // (1024 * 1024)} MiB). Reduce the "
                f"task payload (split work, externalize large inputs)."
            )

        now = time.time()
        vt = (
            visibility_timeout
            if visibility_timeout is not None
            else self._default_visibility_timeout
        )

        await self._conn.execute(
            f"INSERT INTO {self._table} "
            "(task_id, queue_name, payload, status, created_at, updated_at, "
            "attempts, max_attempts, visibility_timeout) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tid,
            queue_name,
            payload_json,
            "pending",
            now,
            now,
            0,
            max_attempts,
            vt,
        )

        logger.debug("Enqueued task %s to queue '%s'", tid, queue_name)
        return tid

    async def dequeue(
        self,
        queue_name: str = "default",
        worker_id: str = "",
    ) -> Optional[SQLTaskMessage]:
        """Dequeue the next pending task.

        Atomically claims the oldest pending task by updating its status to
        ``processing``.  Uses ``FOR UPDATE SKIP LOCKED`` on PostgreSQL/MySQL
        for concurrent safety.  On SQLite, the serialized write transaction
        provides equivalent safety.

        Parameters
        ----------
        queue_name:
            Queue to dequeue from.
        worker_id:
            Identifier of the worker claiming this task.

        Returns
        -------
        SQLTaskMessage or None
            The claimed task, or ``None`` if the queue is empty.
        """
        now = time.time()
        lock_clause = self._conn.dialect.for_update_skip_locked()

        # Atomic dequeue: SELECT + UPDATE within a single transaction
        async with self._conn.transaction() as tx:
            # Find the oldest pending task
            select_sql = (
                f"SELECT task_id FROM {self._table} "
                f"WHERE queue_name = ? AND status = 'pending' "
                f"ORDER BY created_at ASC LIMIT 1"
            )
            if lock_clause:
                select_sql += f" {lock_clause}"

            row = await tx.fetchone(select_sql, queue_name)
            if row is None:
                return None

            tid = row["task_id"]

            # Claim the task
            await tx.execute(
                f"UPDATE {self._table} SET status = 'processing', "
                "worker_id = ?, updated_at = ?, attempts = attempts + 1 "
                "WHERE task_id = ? AND status = 'pending'",
                worker_id,
                now,
                tid,
            )

            # Fetch the full task
            full = await tx.fetchone(
                f"SELECT * FROM {self._table} WHERE task_id = ?", tid
            )

        if full is None or full["status"] != "processing":
            return None  # Another worker claimed it

        return SQLTaskMessage.from_dict(dict(full))

    async def complete(self, task_id: str) -> None:
        """Mark a task as completed.

        Parameters
        ----------
        task_id:
            The task to mark as completed.
        """
        now = time.time()
        await self._conn.execute(
            f"UPDATE {self._table} SET status = 'completed', updated_at = ? "
            "WHERE task_id = ?",
            now,
            task_id,
        )
        logger.debug("Task %s completed", task_id)

    async def fail(self, task_id: str, error: str = "") -> None:
        """Mark a task as failed.

        If the task has exceeded its max_attempts, it is moved to
        ``dead_lettered`` status.  Otherwise, it returns to ``pending``
        for retry.

        Parameters
        ----------
        task_id:
            The task that failed.
        error:
            Error description.
        """
        now = time.time()

        async with self._conn.transaction() as tx:
            row = await tx.fetchone(
                f"SELECT attempts, max_attempts FROM {self._table} WHERE task_id = ?",
                task_id,
            )
            if row is None:
                logger.warning("Cannot fail task %s: not found", task_id)
                return

            if row["attempts"] >= row["max_attempts"]:
                new_status = "dead_lettered"
            else:
                new_status = "pending"

            await tx.execute(
                f"UPDATE {self._table} SET status = ?, error = ?, "
                "updated_at = ?, worker_id = '' WHERE task_id = ?",
                new_status,
                error,
                now,
                task_id,
            )

        logger.debug("Task %s -> %s (error: %s)", task_id, new_status, error[:80])

    async def requeue_stale(self, queue_name: str = "default") -> int:
        """Requeue tasks stuck in ``processing`` past their visibility timeout.

        Returns the number of requeued tasks.
        """
        now = time.time()

        # Find stale processing tasks
        rows = await self._conn.fetch(
            f"SELECT task_id, updated_at, visibility_timeout, attempts, max_attempts "
            f"FROM {self._table} "
            f"WHERE queue_name = ? AND status = 'processing'",
            queue_name,
        )

        requeued = 0
        for row in rows:
            elapsed = now - row["updated_at"]
            if elapsed > row["visibility_timeout"]:
                if row["attempts"] >= row["max_attempts"]:
                    new_status = "dead_lettered"
                else:
                    new_status = "pending"

                await self._conn.execute(
                    f"UPDATE {self._table} SET status = ?, worker_id = '', "
                    "updated_at = ? WHERE task_id = ? AND status = 'processing'",
                    new_status,
                    now,
                    row["task_id"],
                )
                requeued += 1

        if requeued:
            logger.info("Requeued %d stale tasks in queue '%s'", requeued, queue_name)
        return requeued

    async def get_stats(self, queue_name: str = "default") -> Dict[str, int]:
        """Get queue statistics by status.

        Returns
        -------
        dict
            Mapping of status to count, e.g.
            ``{"pending": 5, "processing": 2, "completed": 10, ...}``.
        """
        rows = await self._conn.fetch(
            f"SELECT status, COUNT(*) as cnt FROM {self._table} "
            f"WHERE queue_name = ? GROUP BY status",
            queue_name,
        )
        return {row["status"]: row["cnt"] for row in rows}

    async def purge_completed(
        self,
        queue_name: str = "default",
        older_than: Optional[float] = None,
    ) -> int:
        """Remove completed tasks, optionally older than a timestamp.

        Parameters
        ----------
        queue_name:
            Queue to purge.
        older_than:
            Unix timestamp cutoff.  Only tasks completed before this time
            are removed.  If ``None``, all completed tasks are removed.

        Returns
        -------
        int
            Number of tasks removed.
        """
        if older_than is not None:
            result = await self._conn.execute(
                f"DELETE FROM {self._table} "
                "WHERE queue_name = ? AND status = 'completed' AND updated_at < ?",
                queue_name,
                older_than,
            )
        else:
            result = await self._conn.execute(
                f"DELETE FROM {self._table} "
                "WHERE queue_name = ? AND status = 'completed'",
                queue_name,
            )

        # SQLite cursor returns rowcount, others may vary
        count = getattr(result, "rowcount", 0)
        if count:
            logger.info("Purged %d completed tasks from queue '%s'", count, queue_name)
        return count


# =====================================================================
# Dispatcher adapter — `kailash.runtime.dispatcher.Dispatcher` conformer
# =====================================================================


def _task_id_hash(task_id: str) -> str:
    """Return an 8-char hash of a task_id, safe for log fields.

    Per ``rules/observability.md`` Rule 8, schema-revealing identifiers
    in WARN/ERROR log lines MUST be hashed -- the raw ``task_id`` is
    a concatenation of schedule_id + planned_fire_time and reveals
    business-meaningful schedule names + cron timing.
    """
    import hashlib

    return hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8]


class SQLTaskQueueDispatcher(Dispatcher):
    """SQL-backed :class:`Dispatcher` adapter for ``WorkflowScheduler``.

    Adapts the lower-level :class:`SQLTaskQueue` to the
    :class:`~kailash.runtime.dispatcher.Dispatcher` ABC so a scheduler
    constructed with ``dispatch_via=SQLTaskQueueDispatcher(conn_mgr)``
    enqueues tasks to a SQL queue instead of executing in-process.

    Idempotency contract
    --------------------
    :meth:`enqueue` uses ``task.task_id`` as the queue's PRIMARY KEY.
    A duplicate enqueue with the SAME ``task_id`` is treated as a
    silent no-op -- the multi-instance-scheduler double-fire scenario
    becomes "already enqueued, skip" without raising to the caller.
    Non-PK failures (connectivity, serialization) propagate after a
    structured ERROR log line is emitted.

    Resume hint (informational)
    ---------------------------
    Workers polling this dispatcher SHOULD pass the ``task_id`` as
    the ``idempotency_key`` to ``runtime.execute(...)`` when paired
    with a checkpoint store. This gives resume-from-checkpoint
    semantics on crash recovery -- see ``specs/scheduling.md``
    § "Queue Dispatch".

    Multi-tenant deployment contract
    --------------------------------
    Multi-tenant deployments MUST provision a per-tenant queue table
    (e.g. ``table_name="kailash_task_queue_<tenant>"``). Cross-tenant
    queue sharing is BLOCKED by deployment convention: any party with
    ``INSERT INTO <queue_table>`` privilege can enqueue a workflow
    that the worker pool will execute under its own runtime. Because
    the worker is a single trust boundary, sharing one queue across
    tenants effectively grants every tenant the privilege of every
    other tenant. The defense is structural — each tenant gets its
    own table; no application-level multi-tenancy is performed inside
    the dispatcher.

    Operator runbook — purge cadence
    --------------------------------
    The queue table grows monotonically with every fire. Operators MUST
    schedule periodic :meth:`SQLTaskQueue.purge_completed` calls to
    drop rows in terminal status; otherwise the table fills disk over
    time. A soft cap is available via the ``soft_row_cap`` constructor
    arg: when set, the dispatcher emits a structured WARN log every
    time :meth:`enqueue` lands while the table holds more than
    ``soft_row_cap`` rows for the target queue. The WARN is operational
    signal — it does NOT refuse the enqueue (refusal would silently
    drop scheduled work; a noisy log is the correct trade-off). See
    ``specs/scheduling.md`` § "Queue dispatch — operator runbook".

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
    table_name:
        Name of the task queue table (default: ``kailash_task_queue``).
        Validated against ``[a-zA-Z_][a-zA-Z0-9_]*`` in the underlying
        :class:`SQLTaskQueue`. For multi-tenant deployments use one
        table per tenant (see "Multi-tenant deployment contract").
    soft_row_cap:
        Optional row-count threshold. When ``None`` (default), no cap
        warning fires. When set to an integer, every :meth:`enqueue`
        that lands while the queue table holds more than this many
        rows for the target queue emits a WARN log. Recommended range:
        100_000 - 1_000_000 depending on purge cadence.

    See Also
    --------
    :class:`~kailash.runtime.dispatcher.Dispatcher` -- the abstract contract.
    :func:`~kailash.runtime.dispatcher.compute_task_id` -- stable task_id helper.
    :class:`~kailash.runtime.scheduler.WorkflowScheduler` -- the producer.
    :meth:`SQLTaskQueue.purge_completed` -- the operator runbook step.
    """

    def __init__(
        self,
        conn: Any,
        table_name: str = "kailash_task_queue",
        *,
        soft_row_cap: Optional[int] = None,
    ) -> None:
        if soft_row_cap is not None and soft_row_cap <= 0:
            raise ValueError(
                f"soft_row_cap must be positive or None, got {soft_row_cap}"
            )
        self._queue = SQLTaskQueue(conn, table_name=table_name)
        self._initialized = False
        self._soft_row_cap = soft_row_cap
        # Suppress the WARN flood — fire at most once per minute per
        # queue_name. The cap is operational signal, not per-row alert.
        self._cap_warn_last: Dict[str, float] = {}

    async def initialize(self) -> None:
        """Create the underlying queue table if it does not exist.

        Safe to call multiple times (idempotent). Most callers will
        invoke this explicitly at startup so that the first
        :meth:`enqueue` does not pay the DDL cost.
        """
        if self._initialized:
            return
        await self._queue.initialize()
        self._initialized = True

    async def enqueue(self, task: Task) -> None:
        """Add a :class:`Task` to the queue.

        Idempotent on ``task.task_id`` -- duplicate enqueue is a silent
        no-op (DEBUG log; no exception). Non-duplicate failures log at
        ERROR with grep-able ``schedule_id`` + ``task_id_hash`` and
        propagate per the architecture plan §3 invariant 3.
        """
        if not self._initialized:
            await self.initialize()

        # workflow_blob is JSON-encoded UTF-8 bytes per
        # `kailash.runtime.dispatcher.Task` (NOT pickle, by deliberate
        # design — pickle on a queue payload is RCE per
        # `rules/security.md`). Decode UTF-8 and embed the JSON string
        # so the outer payload remains a pure JSON object.
        payload = {
            "schedule_id": task.schedule_id,
            "workflow_blob_json": task.workflow_blob.decode("utf-8"),
            "planned_fire_time": task.planned_fire_time,
            "kwargs": task.kwargs,
        }

        try:
            await self._queue.enqueue(
                payload=payload,
                queue_name=task.queue_name,
                task_id=task.task_id,
            )
        except Exception as exc:
            # Distinguish PK / unique-violation (silent skip) from genuine
            # failure (ERROR log + re-raise). asyncpg raises
            # UniqueViolationError; sqlite3 raises IntegrityError; aiomysql
            # surfaces a generic error with sqlstate '23000'.
            if _is_unique_violation(exc):
                logger.debug(
                    "task.enqueue.duplicate task_id_hash=%s schedule_id=%s",
                    _task_id_hash(task.task_id),
                    task.schedule_id,
                )
                return
            logger.error(
                "task.enqueue.failed task_id_hash=%s schedule_id=%s reason=%s",
                _task_id_hash(task.task_id),
                task.schedule_id,
                type(exc).__name__,
            )
            raise

        # Operator runbook signal: warn (rate-limited) when the queue
        # has grown past the soft cap. Refusing the enqueue would
        # silently drop scheduled work; the WARN is the operational
        # cue to call purge_completed or raise the cap. See class
        # docstring "Operator runbook — purge cadence".
        if self._soft_row_cap is not None:
            await self._maybe_warn_row_count(task.queue_name)

    async def _maybe_warn_row_count(self, queue_name: str) -> None:
        """Emit a rate-limited WARN if queue depth exceeds soft_row_cap.

        Cheap COUNT query; only runs when ``soft_row_cap`` is set. Fires
        at most once per minute per queue_name to bound log volume on
        a sustained over-cap deployment (the operator sees the same
        signal once per minute; not on every enqueue).
        """
        # soft_row_cap is None-checked at the call site; this method
        # is only invoked when it is set. Rebind to a local int so
        # static analyzers can narrow Optional[int] to int.
        cap = self._soft_row_cap
        if cap is None:
            return  # pragma: no cover (defensive — caller already checked)
        now = time.time()
        last = self._cap_warn_last.get(queue_name, 0.0)
        if now - last < 60.0:
            return
        try:
            row = await self._queue._conn.fetchone(
                f"SELECT COUNT(*) AS c FROM {self._queue._table} WHERE queue_name = ?",
                queue_name,
            )
        except Exception:
            # COUNT is operational signal; never let its failure
            # propagate to the caller's enqueue success path.
            logger.debug(
                "task.queue.row_count_check_failed queue_name=%s",
                queue_name,
            )
            return
        count = (row or {}).get("c", 0) if isinstance(row, dict) else 0
        if count > cap:
            logger.warning(
                "task.queue.over_cap queue_name=%s rows=%s soft_row_cap=%s "
                "remediation=call_purge_completed_or_raise_cap",
                queue_name,
                count,
                cap,
            )
            self._cap_warn_last[queue_name] = now

    def poll(self, queue_name: str = "default") -> AsyncIterator[Task]:
        """Yield tasks claimed from the queue, one at a time.

        The async iterator dequeues atomically (via
        :meth:`SQLTaskQueue.dequeue` which uses
        ``FOR UPDATE SKIP LOCKED`` on PostgreSQL/MySQL and
        ``BEGIN IMMEDIATE`` on SQLite). When the queue is empty the
        iterator stops (it does NOT block waiting for new work);
        callers wishing to long-poll should re-invoke ``poll()`` in a
        loop with a sleep.

        Returns
        -------
        AsyncIterator[Task]
            Tasks reconstructed from the stored payload.
        """
        return self._poll_iter(queue_name)

    async def _poll_iter(self, queue_name: str) -> AsyncIterator[Task]:
        if not self._initialized:
            await self.initialize()
        while True:
            msg = await self._queue.dequeue(
                queue_name=queue_name, worker_id="dispatcher"
            )
            if msg is None:
                return
            yield Task(
                task_id=msg.task_id,
                schedule_id=msg.payload.get("schedule_id", ""),
                workflow_blob=msg.payload.get("workflow_blob_json", "").encode("utf-8"),
                planned_fire_time=msg.payload.get("planned_fire_time", ""),
                queue_name=msg.queue_name,
                kwargs=msg.payload.get("kwargs") or {},
            )

    async def ack(self, task_id: str) -> None:
        """Mark a task as completed."""
        if not self._initialized:
            await self.initialize()
        await self._queue.complete(task_id)

    async def nack(self, task_id: str, *, reason: str) -> None:
        """Mark a task as failed.

        Logs a WARN line with grep-able ``task_id_hash`` per
        ``rules/observability.md`` Rule 8 (raw task_id contains
        schedule_id + fire-time and would reveal schedule timing
        to log aggregators).
        """
        if not self._initialized:
            await self.initialize()
        logger.warning(
            "task.nack task_id_hash=%s reason=%s",
            _task_id_hash(task_id),
            reason,
        )
        await self._queue.fail(task_id, error=reason)


def _is_unique_violation(exc: BaseException) -> bool:
    """Detect a primary-key / unique-constraint violation across dialects.

    PostgreSQL (asyncpg) raises ``asyncpg.exceptions.UniqueViolationError``
    (subclass of ``IntegrityConstraintViolationError``).
    SQLite raises ``sqlite3.IntegrityError`` whose ``args[0]`` contains
    the substring ``"UNIQUE"``.
    MySQL (aiomysql) raises with sqlstate ``'23000'`` and errno 1062;
    we match on the exception's ``args`` for the duplicate-entry signal.

    Per ``rules/zero-tolerance.md`` Rule 3 we MUST NOT swallow generic
    exceptions; this function is narrowly scoped to PK / unique
    constraint violations only and is the sole site that distinguishes
    "already enqueued" from "real failure" in the dispatcher.
    """
    name = type(exc).__name__
    if name in {"UniqueViolationError", "TransactionIntegrityConstraintViolationError"}:
        return True
    if name == "IntegrityError":
        msg = str(exc).upper()
        if "UNIQUE" in msg or "PRIMARY KEY" in msg or "DUPLICATE" in msg:
            return True
    # MySQL: aiomysql surfaces pymysql.err.IntegrityError; same heuristic.
    if "INTEGRITY" in name.upper():
        msg = str(exc).upper()
        if (
            "UNIQUE" in msg
            or "PRIMARY KEY" in msg
            or "DUPLICATE" in msg
            or "1062" in msg
        ):
            return True
    return False
