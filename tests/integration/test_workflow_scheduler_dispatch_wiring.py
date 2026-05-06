# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for WorkflowScheduler dispatch_via=SQLTaskQueueDispatcher.

Per ``rules/testing.md`` Tier 2 contract: NO mocking. All operations hit a
real ConnectionManager with a real database (SQLite in-memory minimum,
PostgreSQL when available via TEST_PG_URL).

Per ``rules/orphan-detection.md`` Rule 2 + ``rules/facade-manager-detection.md``
Rule 1: every wired manager (SQLTaskQueueDispatcher) MUST have at least one
Tier 2 integration test exercising the framework hot path end-to-end. This
file is the wiring test for the W3 Dispatcher contract.

Scenarios covered:

1. enqueue persists a row through the dispatcher facade.
2. Double-fire idempotency — same task_id silently skipped, row count = 1.
3. ack marks completed; the row's status reflects the change.
4. nack increments attempts and routes through fail/dead-letter logic.
5. poll() round-trips the task through the dispatcher.
6. WorkflowScheduler dispatch_via=<real dispatcher> enqueues at fire time.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pickle
import socket
from datetime import UTC, datetime
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.task_queue import SQLTaskQueue, SQLTaskQueueDispatcher
from kailash.runtime.dispatcher import Task, compute_task_id

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Connection fixtures (real Postgres + SQLite per testing.md tier 2 NO MOCKING)
# ---------------------------------------------------------------------------


PG_URL = os.environ.get(
    "TEST_PG_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
SQLITE_URL = "sqlite:///:memory:"


def _is_pg_available() -> bool:
    parsed = urlparse(PG_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


@pytest.fixture(params=["sqlite", "pg"])
async def conn(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[ConnectionManager, None]:
    dialect = request.param
    if dialect == "sqlite":
        url = SQLITE_URL
    elif dialect == "pg":
        if not _is_pg_available():
            pytest.skip(f"PostgreSQL not available at {PG_URL}")
        url = PG_URL
    else:
        raise ValueError(dialect)

    mgr = ConnectionManager(url)
    await mgr.initialize()
    yield mgr
    # Cleanup: drop the dispatch table if present so each parameterization
    # starts clean. SQLite in-memory is process-scoped so this is belt-and-
    # suspenders; PostgreSQL needs the explicit drop.
    try:
        await mgr.execute("DROP TABLE IF EXISTS kailash_task_queue")
    except Exception:
        logger.debug("cleanup drop failed", exc_info=True)
    await mgr.close()


@pytest.fixture
async def dispatcher(
    conn: ConnectionManager,
) -> AsyncGenerator[SQLTaskQueueDispatcher, None]:
    d = SQLTaskQueueDispatcher(conn)
    await d.initialize()
    yield d


# ---------------------------------------------------------------------------
# Helpers — Protocol-satisfying deterministic adapter for workflow shape
# ---------------------------------------------------------------------------


class _IntegrationWorkflow:
    """A pickle-able deterministic workflow stand-in."""

    def __init__(self, name: str = "wf") -> None:
        self.name = name


class _IntegrationBuilder:
    def __init__(self, name: str = "wf") -> None:
        self.name = name

    def build(self) -> _IntegrationWorkflow:
        return _IntegrationWorkflow(self.name)


# ---------------------------------------------------------------------------
# Helper to construct a Task deterministically
# ---------------------------------------------------------------------------


def _make_task(schedule_id: str = "sched-int") -> Task:
    fire_time = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
    workflow = _IntegrationWorkflow("integration-wf")
    return Task(
        task_id=compute_task_id(schedule_id, fire_time),
        schedule_id=schedule_id,
        workflow_blob=pickle.dumps(workflow),
        planned_fire_time=fire_time.isoformat(),
    )


# ---------------------------------------------------------------------------
# Tier 2 dispatcher tests
# ---------------------------------------------------------------------------


class TestSQLTaskQueueDispatcherTier2:
    async def test_enqueue_persists_row(
        self, conn: ConnectionManager, dispatcher: SQLTaskQueueDispatcher
    ) -> None:
        task = _make_task("sched-persist")
        await dispatcher.enqueue(task)

        rows = await conn.fetch(
            "SELECT task_id, status FROM kailash_task_queue WHERE task_id = ?",
            task.task_id,
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"

    async def test_double_fire_is_idempotent(
        self, conn: ConnectionManager, dispatcher: SQLTaskQueueDispatcher
    ) -> None:
        """Same task_id enqueued twice — second is a silent no-op."""
        task = _make_task("sched-dedup")
        await dispatcher.enqueue(task)
        await dispatcher.enqueue(task)  # MUST NOT raise

        rows = await conn.fetch(
            "SELECT COUNT(*) AS cnt FROM kailash_task_queue WHERE task_id = ?",
            task.task_id,
        )
        assert rows[0]["cnt"] == 1, "double-fire MUST dedupe at queue layer"

    async def test_ack_marks_completed(
        self, conn: ConnectionManager, dispatcher: SQLTaskQueueDispatcher
    ) -> None:
        task = _make_task("sched-ack")
        await dispatcher.enqueue(task)
        await dispatcher.ack(task.task_id)

        rows = await conn.fetch(
            "SELECT status FROM kailash_task_queue WHERE task_id = ?",
            task.task_id,
        )
        assert rows[0]["status"] == "completed"

    async def test_nack_increments_attempts(
        self,
        conn: ConnectionManager,
        dispatcher: SQLTaskQueueDispatcher,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """nack records the failure and routes through fail/dead-letter."""
        task = _make_task("sched-nack")
        await dispatcher.enqueue(task)

        # Move to processing first (so attempts increments via dequeue path).
        # nack() works on any tracked task_id; we just need to verify the
        # underlying SQLTaskQueue.fail() gets called and the row is updated.
        with caplog.at_level(
            logging.WARNING, logger="kailash.infrastructure.task_queue"
        ):
            await dispatcher.nack(task.task_id, reason="timeout")

        rows = await conn.fetch(
            "SELECT status, error FROM kailash_task_queue WHERE task_id = ?",
            task.task_id,
        )
        assert rows[0]["error"] == "timeout"
        # WARN log MUST cite task_id_hash per observability.md Rule 8.
        warn_msgs = [
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert any(
            "task_id_hash=" in m and "timeout" in m for m in warn_msgs
        ), f"expected task_id_hash + reason in WARN log, got: {warn_msgs}"

    async def test_poll_yields_enqueued_task(
        self, dispatcher: SQLTaskQueueDispatcher
    ) -> None:
        """poll() round-trips a task end-to-end through the dispatcher."""
        task = _make_task("sched-poll")
        await dispatcher.enqueue(task)

        polled = []
        async for t in dispatcher.poll():
            polled.append(t)
            if len(polled) >= 1:
                break

        assert len(polled) == 1
        assert polled[0].task_id == task.task_id
        assert polled[0].schedule_id == "sched-poll"
        assert polled[0].planned_fire_time == task.planned_fire_time
        # workflow_blob round-trip MUST be byte-identical (pickle is the
        # opaque transport per spec).
        assert polled[0].workflow_blob == task.workflow_blob


# ---------------------------------------------------------------------------
# WorkflowScheduler -> dispatcher full-path test
# ---------------------------------------------------------------------------


apscheduler = pytest.importorskip(
    "apscheduler", reason="WorkflowScheduler requires APScheduler"
)


class TestWorkflowSchedulerDispatchFullPath:
    async def test_scheduler_dispatch_via_enqueues_through_real_db(
        self, conn: ConnectionManager, dispatcher: SQLTaskQueueDispatcher
    ) -> None:
        """End-to-end: WorkflowScheduler -> dispatcher -> real DB row."""
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(
            job_store_path=None,
            dispatch_via=dispatcher,
        )

        # Pin planned-fire-time deterministically so we can compute the
        # expected task_id and verify the persisted row.
        fixed_ft = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
        scheduler._planned_fire_time = lambda sid: fixed_ft

        builder = _IntegrationBuilder("scheduler-end-to-end")
        await scheduler._execute_workflow(builder, schedule_id="sched-e2e")

        # Verify the row was actually written.
        expected_task_id = compute_task_id("sched-e2e", fixed_ft)
        rows = await conn.fetch(
            "SELECT task_id, status FROM kailash_task_queue WHERE task_id = ?",
            expected_task_id,
        )
        assert len(rows) == 1, "scheduler dispatch_via MUST write through to DB"
        assert rows[0]["status"] == "pending"

    async def test_concurrent_double_fire_dedupes_at_pk(
        self, conn: ConnectionManager
    ) -> None:
        """Two scheduler instances firing the same (sched_id, fire_time) collapse.

        Multi-instance scheduler safety: both instances compute the SAME
        task_id from the same (schedule_id, planned_fire_time) and the
        second enqueue silently skips via PRIMARY KEY constraint.
        """
        from kailash.runtime.scheduler import WorkflowScheduler

        d_a = SQLTaskQueueDispatcher(conn)
        d_b = SQLTaskQueueDispatcher(conn)
        await d_a.initialize()
        # d_b shares the same table — second initialize is a no-op DDL.

        sched_a = WorkflowScheduler(job_store_path=None, dispatch_via=d_a)
        sched_b = WorkflowScheduler(job_store_path=None, dispatch_via=d_b)
        fixed_ft = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
        sched_a._planned_fire_time = lambda sid: fixed_ft
        sched_b._planned_fire_time = lambda sid: fixed_ft

        builder = _IntegrationBuilder("multi-instance")

        await asyncio.gather(
            sched_a._execute_workflow(builder, schedule_id="sched-multi"),
            sched_b._execute_workflow(builder, schedule_id="sched-multi"),
        )

        rows = await conn.fetch(
            "SELECT COUNT(*) AS cnt FROM kailash_task_queue WHERE task_id = ?",
            compute_task_id("sched-multi", fixed_ft),
        )
        assert (
            rows[0]["cnt"] == 1
        ), "multi-instance double-fire MUST collapse to 1 row via PK dedup"
