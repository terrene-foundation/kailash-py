# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable ExecutionStore backend using ConnectionManager.

Tracks workflow execution metadata (run_id, status, parameters, results).
Provides both a database-backed :class:`DBExecutionStore` and an
in-memory :class:`InMemoryExecutionStore` for Level 0 usage.

All queries use canonical ``?`` placeholders;
:class:`~kailash.db.connection.ConnectionManager` translates to the target
database dialect automatically.

Table: ``kailash_executions``

Schema::

    run_id        TEXT PRIMARY KEY
    workflow_id   TEXT
    status        TEXT NOT NULL DEFAULT 'pending'
    parameters    TEXT          -- JSON
    result        TEXT          -- JSON
    error         TEXT
    started_at    TEXT
    completed_at  TEXT
    worker_id     TEXT
    metadata_json TEXT          -- JSON
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.db.connection import ConnectionManager

# Maximum entries in the in-memory execution store before LRU eviction.
_MAX_INMEMORY_ENTRIES = 10000

logger = logging.getLogger(__name__)

__all__ = [
    "DBExecutionStore",
    "InMemoryExecutionStore",
]


class DBExecutionStore:
    """Database-backed execution store for tracking workflow execution metadata.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`ConnectionManager` instance.
    """

    TABLE_NAME = "kailash_executions"

    def __init__(self, conn_manager: ConnectionManager) -> None:
        self._conn = conn_manager

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the executions table and indices if they do not exist."""
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                run_id {self._conn.dialect.text_column(indexed=True)} PRIMARY KEY,
                workflow_id {self._conn.dialect.text_column(indexed=True)},
                status {self._conn.dialect.text_column(indexed=True)} NOT NULL DEFAULT 'pending',
                parameters TEXT,
                result TEXT,
                error TEXT,
                started_at TEXT,
                completed_at TEXT,
                worker_id TEXT,
                metadata_json TEXT
            )
            """
        )
        await self._conn.create_index(
            "idx_executions_status",
            self.TABLE_NAME,
            "status",
        )
        await self._conn.create_index(
            "idx_executions_workflow",
            self.TABLE_NAME,
            "workflow_id",
        )
        await self._conn.create_index(
            "idx_executions_started",
            self.TABLE_NAME,
            "started_at",
        )
        logger.info("ExecutionStore table '%s' initialized", self.TABLE_NAME)

    async def close(self) -> None:
        """Release any resources held by the backend.

        The underlying ConnectionManager is NOT closed here -- it is
        owned by the caller and may be shared with other stores.
        """
        logger.debug("ExecutionStore backend closed")

    # ------------------------------------------------------------------
    # Record operations
    # ------------------------------------------------------------------
    async def record_start(
        self,
        run_id: str,
        workflow_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        """Record the start of a workflow execution.

        Parameters
        ----------
        run_id:
            Unique identifier for this execution run.
        workflow_id:
            Identifier of the workflow being executed.
        parameters:
            Optional parameters dict to store as JSON.
        worker_id:
            Optional identifier of the worker processing this execution.
        """
        now = datetime.now(timezone.utc).isoformat()
        params_json = json.dumps(parameters) if parameters is not None else None

        await self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} "
            f"(run_id, workflow_id, status, parameters, started_at, worker_id) "
            f"VALUES (?, ?, 'pending', ?, ?, ?)",
            run_id,
            workflow_id,
            params_json,
            now,
            worker_id,
        )
        logger.info(
            "Execution started: run_id=%s workflow_id=%s worker_id=%s",
            run_id,
            workflow_id,
            worker_id,
        )

    async def record_completion(
        self,
        run_id: str,
        results: Dict[str, Any],
    ) -> None:
        """Record the successful completion of a workflow execution.

        Parameters
        ----------
        run_id:
            The execution run identifier.
        results:
            Results dict to store as JSON.
        """
        now = datetime.now(timezone.utc).isoformat()
        result_json = json.dumps(results)

        await self._conn.execute(
            f"UPDATE {self.TABLE_NAME} "
            f"SET status = 'completed', result = ?, completed_at = ? "
            f"WHERE run_id = ?",
            result_json,
            now,
            run_id,
        )
        logger.info("Execution completed: run_id=%s", run_id)

    async def record_failure(
        self,
        run_id: str,
        error: str,
    ) -> None:
        """Record the failure of a workflow execution.

        Parameters
        ----------
        run_id:
            The execution run identifier.
        error:
            Error message or traceback string.
        """
        now = datetime.now(timezone.utc).isoformat()

        await self._conn.execute(
            f"UPDATE {self.TABLE_NAME} "
            f"SET status = 'failed', error = ?, completed_at = ? "
            f"WHERE run_id = ?",
            error,
            now,
            run_id,
        )
        logger.warning("Execution failed: run_id=%s error=%s", run_id, error[:200])

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------
    async def get_execution(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single execution record by run_id.

        Parameters
        ----------
        run_id:
            The execution run identifier.

        Returns
        -------
        dict or None
            Execution record as a dict, or None if not found.
        """
        row = await self._conn.fetchone(
            f"SELECT * FROM {self.TABLE_NAME} WHERE run_id = ?",
            run_id,
        )
        return dict(row) if row else None

    async def list_executions(
        self,
        status: Optional[str] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List execution records with optional filters.

        Parameters
        ----------
        status:
            Filter by execution status (pending, completed, failed).
        workflow_id:
            Filter by workflow identifier.
        limit:
            Maximum number of records to return (default 100).

        Returns
        -------
        list[dict]
            Matching execution records.
        """
        conditions: List[str] = []
        params: List[Any] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if workflow_id is not None:
            conditions.append("workflow_id = ?")
            params.append(workflow_id)

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        query = (
            f"SELECT * FROM {self.TABLE_NAME}{where_clause} "
            f"ORDER BY started_at DESC LIMIT ?"
        )
        params.append(limit)

        rows = await self._conn.fetch(query, *params)
        return [dict(row) for row in rows]


class InMemoryExecutionStore:
    """In-memory execution store backed by a dict (Level 0, no database).

    Provides the same async interface as :class:`DBExecutionStore` but
    stores all data in ``self._store``.  Suitable for testing and simple
    single-process usage where persistence is not required.
    """

    def __init__(self, max_entries: int = _MAX_INMEMORY_ENTRIES) -> None:
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_entries = max_entries

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """No-op for in-memory store."""
        logger.debug("InMemoryExecutionStore initialized")

    async def close(self) -> None:
        """No-op for in-memory store."""
        logger.debug("InMemoryExecutionStore closed")

    # ------------------------------------------------------------------
    # Record operations
    # ------------------------------------------------------------------
    async def record_start(
        self,
        run_id: str,
        workflow_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        """Record the start of a workflow execution in memory."""
        # Evict oldest entries when at capacity
        while len(self._store) >= self._max_entries:
            self._store.popitem(last=False)
        now = datetime.now(timezone.utc).isoformat()
        self._store[run_id] = {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "status": "pending",
            "parameters": parameters,
            "result": None,
            "error": None,
            "started_at": now,
            "completed_at": None,
            "worker_id": worker_id,
            "metadata_json": None,
        }

    async def record_completion(
        self,
        run_id: str,
        results: Dict[str, Any],
    ) -> None:
        """Record successful completion of a workflow execution in memory."""
        now = datetime.now(timezone.utc).isoformat()
        if run_id not in self._store:
            logger.warning("record_completion called for unknown run_id: %s", run_id)
            return
        self._store[run_id]["status"] = "completed"
        self._store[run_id]["result"] = results
        self._store[run_id]["completed_at"] = now

    async def record_failure(
        self,
        run_id: str,
        error: str,
    ) -> None:
        """Record failure of a workflow execution in memory."""
        now = datetime.now(timezone.utc).isoformat()
        if run_id not in self._store:
            logger.warning("record_failure called for unknown run_id: %s", run_id)
            return
        self._store[run_id]["status"] = "failed"
        self._store[run_id]["error"] = error
        self._store[run_id]["completed_at"] = now

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------
    async def get_execution(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single execution record by run_id from memory."""
        entry = self._store.get(run_id)
        if entry is None:
            return None
        return dict(entry)

    async def list_executions(
        self,
        status: Optional[str] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List execution records with optional filters from memory."""
        results = list(self._store.values())

        if status is not None:
            results = [r for r in results if r["status"] == status]
        if workflow_id is not None:
            results = [r for r in results if r["workflow_id"] == workflow_id]

        # Sort by started_at descending (most recent first)
        results.sort(key=lambda r: r.get("started_at") or "", reverse=True)

        return [dict(r) for r in results[:limit]]
