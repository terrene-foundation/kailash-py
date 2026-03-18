# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SQL-backed worker registry with heartbeat and dead worker reaping.

Provides a database-backed registry for tracking worker processes that consume
tasks from the :class:`~kailash.infrastructure.task_queue.SQLTaskQueue`.  Each
worker periodically sends heartbeat updates; workers whose heartbeats go stale
beyond a configurable threshold are reaped, and any tasks they held are
requeued for other workers to pick up.

This module mirrors the Redis-based heartbeat pattern from
:class:`~kailash.runtime.distributed.Worker` but uses the SQL
:class:`~kailash.db.connection.ConnectionManager` so no Redis dependency is
required for Level 2 deployments.

All SQL uses canonical ``?`` placeholders -- ConnectionManager translates to
the target dialect automatically.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

__all__ = [
    "SQLWorkerRegistry",
]


class SQLWorkerRegistry:
    """SQL-backed worker registry with heartbeat tracking and dead-worker reaping.

    Works with PostgreSQL, MySQL 8.0+, and SQLite through the shared
    :class:`~kailash.db.connection.ConnectionManager`.

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
    task_queue:
        The :class:`~kailash.infrastructure.task_queue.SQLTaskQueue` instance
        used to requeue tasks when dead workers are reaped.
    table_name:
        Name of the worker registry table (default:
        ``kailash_worker_registry``).
    """

    def __init__(
        self,
        conn: Any,
        task_queue: Any,
        table_name: str = "kailash_worker_registry",
    ) -> None:
        if not _TABLE_NAME_RE.match(table_name):
            raise ValueError(
                f"Invalid table name '{table_name}': "
                f"must match [a-zA-Z_][a-zA-Z0-9_]*"
            )
        self._conn = conn
        self._task_queue = task_queue
        self._table = table_name
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create the worker registry table if it does not exist.

        Safe to call multiple times (idempotent).
        """
        if self._initialized:
            return

        _tc = self._conn.dialect.text_column(indexed=True)
        await self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self._table} ("
            f"worker_id {_tc} PRIMARY KEY, "
            f"queue_name {_tc} NOT NULL, "
            f"status {_tc} NOT NULL DEFAULT 'active', "
            "last_beat_at REAL NOT NULL, "
            "started_at REAL NOT NULL, "
            "current_task TEXT, "
            "metadata_json TEXT DEFAULT '{}'"
            ")"
        )

        # Index for efficient dead-worker scans: active workers by last beat
        await self._conn.create_index(
            f"idx_{self._table}_status_beat",
            self._table,
            "status, last_beat_at",
        )

        self._initialized = True
        logger.info("SQLWorkerRegistry table '%s' initialized", self._table)

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    async def register(self, worker_id: str, queue_name: str) -> None:
        """Register a new worker in the registry.

        Parameters
        ----------
        worker_id:
            Unique identifier for the worker.
        queue_name:
            Logical queue name the worker is consuming from.
        """
        now = time.time()
        await self._conn.execute(
            f"INSERT INTO {self._table} "
            "(worker_id, queue_name, status, last_beat_at, started_at, "
            "current_task, metadata_json) "
            "VALUES (?, ?, 'active', ?, ?, NULL, '{}')",
            worker_id,
            queue_name,
            now,
            now,
        )
        logger.info("Registered worker '%s' on queue '%s'", worker_id, queue_name)

    async def heartbeat(self, worker_id: str) -> None:
        """Update the heartbeat timestamp for a worker.

        Parameters
        ----------
        worker_id:
            The worker sending the heartbeat.
        """
        now = time.time()
        await self._conn.execute(
            f"UPDATE {self._table} SET last_beat_at = ? WHERE worker_id = ?",
            now,
            worker_id,
        )
        logger.debug("Heartbeat from worker '%s'", worker_id)

    async def set_current_task(self, worker_id: str, task_id: str) -> None:
        """Record the task currently being processed by a worker.

        Parameters
        ----------
        worker_id:
            The worker processing the task.
        task_id:
            The task being processed.
        """
        await self._conn.execute(
            f"UPDATE {self._table} SET current_task = ? WHERE worker_id = ?",
            task_id,
            worker_id,
        )
        logger.debug("Worker '%s' now processing task '%s'", worker_id, task_id)

    async def clear_current_task(self, worker_id: str) -> None:
        """Clear the current task assignment for a worker.

        Parameters
        ----------
        worker_id:
            The worker that finished its task.
        """
        await self._conn.execute(
            f"UPDATE {self._table} SET current_task = NULL WHERE worker_id = ?",
            worker_id,
        )
        logger.debug("Worker '%s' cleared current task", worker_id)

    async def deregister(self, worker_id: str) -> None:
        """Mark a worker as inactive.

        Parameters
        ----------
        worker_id:
            The worker to deregister.
        """
        await self._conn.execute(
            f"UPDATE {self._table} SET status = 'inactive' WHERE worker_id = ?",
            worker_id,
        )
        logger.info("Deregistered worker '%s'", worker_id)

    # ------------------------------------------------------------------
    # Reaping
    # ------------------------------------------------------------------

    async def reap_dead_workers(
        self,
        staleness_seconds: float,
        queue_name: str,
    ) -> int:
        """Find and reap workers whose heartbeat has gone stale.

        For each stale worker:
        1. Requeue any tasks they held (``status='processing'`` with matching
           ``worker_id``) back to ``pending``.
        2. Mark the worker as ``inactive``.

        Parameters
        ----------
        staleness_seconds:
            Workers with ``last_beat_at`` older than
            ``now - staleness_seconds`` are considered dead.
        queue_name:
            Only reap workers in the specified queue.

        Returns
        -------
        int
            Number of workers reaped.
        """
        now = time.time()
        cutoff = now - staleness_seconds

        # Find stale active workers in the target queue
        stale_rows = await self._conn.fetch(
            f"SELECT worker_id FROM {self._table} "
            f"WHERE status = 'active' AND queue_name = ? AND last_beat_at < ?",
            queue_name,
            cutoff,
        )

        if not stale_rows:
            return 0

        reaped = 0
        task_table = self._task_queue._table

        for row in stale_rows:
            dead_worker_id = row["worker_id"]

            async with self._conn.transaction() as tx:
                # Requeue any tasks held by this dead worker
                await tx.execute(
                    f"UPDATE {task_table} SET status = 'pending', "
                    "worker_id = '', updated_at = ? "
                    "WHERE worker_id = ? AND status = 'processing'",
                    now,
                    dead_worker_id,
                )

                # Mark the worker inactive
                await tx.execute(
                    f"UPDATE {self._table} SET status = 'inactive', "
                    "current_task = NULL WHERE worker_id = ?",
                    dead_worker_id,
                )

            reaped += 1
            logger.warning(
                "Reaped dead worker '%s' (last beat %.1fs ago)",
                dead_worker_id,
                now - cutoff,
            )

        if reaped:
            logger.info("Reaped %d dead worker(s) in queue '%s'", reaped, queue_name)
        return reaped

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_active_workers(self, queue_name: str) -> List[Dict[str, Any]]:
        """Return all active workers for a given queue.

        Parameters
        ----------
        queue_name:
            Queue to query.

        Returns
        -------
        list[dict]
            List of worker rows as dictionaries.
        """
        rows = await self._conn.fetch(
            f"SELECT worker_id, queue_name, status, last_beat_at, "
            f"started_at, current_task, metadata_json "
            f"FROM {self._table} "
            f"WHERE status = 'active' AND queue_name = ? "
            f"ORDER BY started_at ASC",
            queue_name,
        )
        return rows
