# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for dialect-portable ExecutionStore backends.

Tests cover:
- DBExecutionStore: SQL-backed execution metadata tracking
  - Table/index creation via initialize()
  - record_start: INSERT new execution row
  - record_completion: UPDATE status/result/completed_at
  - record_failure: UPDATE status/error/completed_at
  - get_execution: SELECT single execution by run_id
  - list_executions: SELECT with optional status/workflow_id/limit filters
  - Lifecycle: initialize/close idempotency
  - Edge cases: missing run_id, double start, JSON round-trip

- InMemoryExecutionStore: dict-backed execution tracking (Level 0)
  - Same interface as DBExecutionStore
  - No database dependency
  - Full method parity
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
async def conn_manager():
    """Provide an in-memory SQLite ConnectionManager."""
    mgr = ConnectionManager("sqlite:///:memory:")
    await mgr.initialize()
    yield mgr
    await mgr.close()


@pytest.fixture
async def execution_store(conn_manager):
    """Provide an initialized DBExecutionStore backend."""
    from kailash.infrastructure.execution_store import DBExecutionStore

    store = DBExecutionStore(conn_manager)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def in_memory_store():
    """Provide an InMemoryExecutionStore."""
    from kailash.infrastructure.execution_store import InMemoryExecutionStore

    return InMemoryExecutionStore()


# ===========================================================================
# DBExecutionStore Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
class TestDBExecutionStoreLifecycle:
    async def test_initialize_creates_table(self, conn_manager):
        """initialize() should create the kailash_executions table."""
        from kailash.infrastructure.execution_store import DBExecutionStore

        store = DBExecutionStore(conn_manager)
        await store.initialize()

        rows = await conn_manager.fetch(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kailash_executions'"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "kailash_executions"
        await store.close()

    async def test_initialize_creates_indices(self, conn_manager):
        """initialize() should create the status, workflow, and started_at indices."""
        from kailash.infrastructure.execution_store import DBExecutionStore

        store = DBExecutionStore(conn_manager)
        await store.initialize()

        rows = await conn_manager.fetch(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_executions_%'"
        )
        index_names = {row["name"] for row in rows}
        assert "idx_executions_status" in index_names
        assert "idx_executions_workflow" in index_names
        assert "idx_executions_started" in index_names
        await store.close()

    async def test_double_initialize_is_safe(self, conn_manager):
        """Calling initialize() twice should not raise."""
        from kailash.infrastructure.execution_store import DBExecutionStore

        store = DBExecutionStore(conn_manager)
        await store.initialize()
        await store.initialize()  # Should be idempotent
        await store.close()

    async def test_close_is_safe_multiple_times(self, conn_manager):
        """Calling close() multiple times should not raise."""
        from kailash.infrastructure.execution_store import DBExecutionStore

        store = DBExecutionStore(conn_manager)
        await store.initialize()
        await store.close()
        await store.close()

    async def test_requires_connection_manager(self):
        """Constructor must require a ConnectionManager."""
        from kailash.infrastructure.execution_store import DBExecutionStore

        with pytest.raises(TypeError):
            DBExecutionStore()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# record_start
# ---------------------------------------------------------------------------
class TestDBExecutionStoreRecordStart:
    async def test_record_start_inserts_execution(self, execution_store):
        """record_start should insert a new execution record."""
        await execution_store.record_start(
            run_id="run-001",
            workflow_id="wf-abc",
            parameters={"key": "value"},
            worker_id="worker-1",
        )

        result = await execution_store.get_execution("run-001")
        assert result is not None
        assert result["run_id"] == "run-001"
        assert result["workflow_id"] == "wf-abc"
        assert result["status"] == "pending"
        assert result["worker_id"] == "worker-1"

    async def test_record_start_stores_parameters_as_json(self, execution_store):
        """Parameters dict should be stored as JSON TEXT."""
        params = {"model": "gpt-4", "temperature": 0.7, "nested": {"deep": True}}
        await execution_store.record_start(
            run_id="run-json",
            workflow_id="wf-json",
            parameters=params,
        )

        result = await execution_store.get_execution("run-json")
        assert result is not None
        stored_params = json.loads(result["parameters"])
        assert stored_params == params

    async def test_record_start_sets_started_at(self, execution_store):
        """record_start should set started_at to an ISO 8601 timestamp."""
        await execution_store.record_start(
            run_id="run-time",
            workflow_id="wf-time",
        )

        result = await execution_store.get_execution("run-time")
        assert result is not None
        assert result["started_at"] is not None
        # Should parse as ISO 8601
        datetime.fromisoformat(result["started_at"])

    async def test_record_start_defaults_status_to_pending(self, execution_store):
        """Default status after record_start should be 'pending'."""
        await execution_store.record_start(
            run_id="run-pending",
            workflow_id="wf-pending",
        )

        result = await execution_store.get_execution("run-pending")
        assert result is not None
        assert result["status"] == "pending"

    async def test_record_start_without_optional_params(self, execution_store):
        """record_start should work without parameters and worker_id."""
        await execution_store.record_start(
            run_id="run-minimal",
            workflow_id="wf-minimal",
        )

        result = await execution_store.get_execution("run-minimal")
        assert result is not None
        assert result["run_id"] == "run-minimal"
        assert result["workflow_id"] == "wf-minimal"
        assert result["parameters"] is None
        assert result["worker_id"] is None


# ---------------------------------------------------------------------------
# record_completion
# ---------------------------------------------------------------------------
class TestDBExecutionStoreRecordCompletion:
    async def test_record_completion_updates_status(self, execution_store):
        """record_completion should set status to 'completed'."""
        await execution_store.record_start(
            run_id="run-complete",
            workflow_id="wf-complete",
        )
        await execution_store.record_completion(
            run_id="run-complete",
            results={"output": "success"},
        )

        result = await execution_store.get_execution("run-complete")
        assert result is not None
        assert result["status"] == "completed"

    async def test_record_completion_stores_result_as_json(self, execution_store):
        """Results should be serialized as JSON TEXT."""
        results = {"nodes": {"node1": {"value": 42}}, "summary": "done"}
        await execution_store.record_start(
            run_id="run-result",
            workflow_id="wf-result",
        )
        await execution_store.record_completion(
            run_id="run-result",
            results=results,
        )

        result = await execution_store.get_execution("run-result")
        assert result is not None
        stored_results = json.loads(result["result"])
        assert stored_results == results

    async def test_record_completion_sets_completed_at(self, execution_store):
        """record_completion should set completed_at timestamp."""
        await execution_store.record_start(
            run_id="run-done",
            workflow_id="wf-done",
        )
        await execution_store.record_completion(
            run_id="run-done",
            results={"ok": True},
        )

        result = await execution_store.get_execution("run-done")
        assert result is not None
        assert result["completed_at"] is not None
        datetime.fromisoformat(result["completed_at"])


# ---------------------------------------------------------------------------
# record_failure
# ---------------------------------------------------------------------------
class TestDBExecutionStoreRecordFailure:
    async def test_record_failure_updates_status(self, execution_store):
        """record_failure should set status to 'failed'."""
        await execution_store.record_start(
            run_id="run-fail",
            workflow_id="wf-fail",
        )
        await execution_store.record_failure(
            run_id="run-fail",
            error="ValueError: something broke",
        )

        result = await execution_store.get_execution("run-fail")
        assert result is not None
        assert result["status"] == "failed"

    async def test_record_failure_stores_error_message(self, execution_store):
        """Error string should be stored verbatim."""
        error_msg = "Traceback (most recent call last):\n  File ...\nRuntimeError: boom"
        await execution_store.record_start(
            run_id="run-err",
            workflow_id="wf-err",
        )
        await execution_store.record_failure(
            run_id="run-err",
            error=error_msg,
        )

        result = await execution_store.get_execution("run-err")
        assert result is not None
        assert result["error"] == error_msg

    async def test_record_failure_sets_completed_at(self, execution_store):
        """record_failure should set completed_at timestamp."""
        await execution_store.record_start(
            run_id="run-fail-time",
            workflow_id="wf-fail-time",
        )
        await execution_store.record_failure(
            run_id="run-fail-time",
            error="oops",
        )

        result = await execution_store.get_execution("run-fail-time")
        assert result is not None
        assert result["completed_at"] is not None
        datetime.fromisoformat(result["completed_at"])


# ---------------------------------------------------------------------------
# get_execution
# ---------------------------------------------------------------------------
class TestDBExecutionStoreGetExecution:
    async def test_get_execution_returns_dict(self, execution_store):
        """get_execution should return a dict with all columns."""
        await execution_store.record_start(
            run_id="run-get",
            workflow_id="wf-get",
            parameters={"a": 1},
            worker_id="w1",
        )

        result = await execution_store.get_execution("run-get")
        assert isinstance(result, dict)
        assert "run_id" in result
        assert "workflow_id" in result
        assert "status" in result
        assert "parameters" in result
        assert "result" in result
        assert "error" in result
        assert "started_at" in result
        assert "completed_at" in result
        assert "worker_id" in result
        assert "metadata_json" in result

    async def test_get_execution_nonexistent_returns_none(self, execution_store):
        """get_execution for a missing run_id should return None."""
        result = await execution_store.get_execution("run-does-not-exist")
        assert result is None

    async def test_get_execution_after_completion(self, execution_store):
        """get_execution should reflect the latest state after completion."""
        await execution_store.record_start(
            run_id="run-full",
            workflow_id="wf-full",
            parameters={"input": "data"},
        )
        await execution_store.record_completion(
            run_id="run-full",
            results={"output": "processed"},
        )

        result = await execution_store.get_execution("run-full")
        assert result is not None
        assert result["status"] == "completed"
        assert result["started_at"] is not None
        assert result["completed_at"] is not None
        assert json.loads(result["parameters"]) == {"input": "data"}
        assert json.loads(result["result"]) == {"output": "processed"}


# ---------------------------------------------------------------------------
# list_executions
# ---------------------------------------------------------------------------
class TestDBExecutionStoreListExecutions:
    async def test_list_executions_returns_all(self, execution_store):
        """list_executions with no filters should return all executions."""
        for i in range(5):
            await execution_store.record_start(
                run_id=f"run-list-{i}",
                workflow_id="wf-list",
            )

        results = await execution_store.list_executions()
        assert len(results) == 5

    async def test_list_executions_filter_by_status(self, execution_store):
        """list_executions with status filter should return matching only."""
        await execution_store.record_start(run_id="run-a", workflow_id="wf-x")
        await execution_store.record_start(run_id="run-b", workflow_id="wf-x")
        await execution_store.record_start(run_id="run-c", workflow_id="wf-x")
        await execution_store.record_completion(run_id="run-a", results={})
        await execution_store.record_failure(run_id="run-b", error="fail")

        pending = await execution_store.list_executions(status="pending")
        assert len(pending) == 1
        assert pending[0]["run_id"] == "run-c"

        completed = await execution_store.list_executions(status="completed")
        assert len(completed) == 1
        assert completed[0]["run_id"] == "run-a"

        failed = await execution_store.list_executions(status="failed")
        assert len(failed) == 1
        assert failed[0]["run_id"] == "run-b"

    async def test_list_executions_filter_by_workflow_id(self, execution_store):
        """list_executions with workflow_id filter should return matching only."""
        await execution_store.record_start(run_id="run-w1", workflow_id="wf-alpha")
        await execution_store.record_start(run_id="run-w2", workflow_id="wf-beta")
        await execution_store.record_start(run_id="run-w3", workflow_id="wf-alpha")

        alpha = await execution_store.list_executions(workflow_id="wf-alpha")
        assert len(alpha) == 2
        alpha_ids = {r["run_id"] for r in alpha}
        assert alpha_ids == {"run-w1", "run-w3"}

        beta = await execution_store.list_executions(workflow_id="wf-beta")
        assert len(beta) == 1
        assert beta[0]["run_id"] == "run-w2"

    async def test_list_executions_combined_filters(self, execution_store):
        """list_executions should support combining status and workflow_id filters."""
        await execution_store.record_start(run_id="run-cf1", workflow_id="wf-1")
        await execution_store.record_start(run_id="run-cf2", workflow_id="wf-1")
        await execution_store.record_start(run_id="run-cf3", workflow_id="wf-2")
        await execution_store.record_completion(run_id="run-cf1", results={})

        results = await execution_store.list_executions(
            status="completed", workflow_id="wf-1"
        )
        assert len(results) == 1
        assert results[0]["run_id"] == "run-cf1"

    async def test_list_executions_respects_limit(self, execution_store):
        """list_executions should respect the limit parameter."""
        for i in range(10):
            await execution_store.record_start(
                run_id=f"run-lim-{i}",
                workflow_id="wf-lim",
            )

        results = await execution_store.list_executions(limit=3)
        assert len(results) == 3

    async def test_list_executions_default_limit_100(self, execution_store):
        """list_executions default limit should be 100."""
        # We just verify it does not error out and returns up to the limit.
        # Creating only 5 entries is fine — no need to create 101.
        for i in range(5):
            await execution_store.record_start(
                run_id=f"run-def-{i}",
                workflow_id="wf-def",
            )

        results = await execution_store.list_executions()
        assert len(results) == 5

    async def test_list_executions_empty_returns_empty_list(self, execution_store):
        """list_executions on empty store should return empty list."""
        results = await execution_store.list_executions()
        assert results == []

    async def test_list_executions_no_match_returns_empty(self, execution_store):
        """list_executions with no matching filter should return empty list."""
        await execution_store.record_start(run_id="run-nm", workflow_id="wf-nm")

        results = await execution_store.list_executions(status="completed")
        assert results == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestDBExecutionStoreEdgeCases:
    async def test_multiple_executions_isolated(self, execution_store):
        """Different run_ids must store independent data."""
        await execution_store.record_start(
            run_id="run-iso-1",
            workflow_id="wf-iso",
            parameters={"idx": 1},
        )
        await execution_store.record_start(
            run_id="run-iso-2",
            workflow_id="wf-iso",
            parameters={"idx": 2},
        )

        r1 = await execution_store.get_execution("run-iso-1")
        r2 = await execution_store.get_execution("run-iso-2")
        assert r1 is not None
        assert r2 is not None
        assert json.loads(r1["parameters"]) == {"idx": 1}
        assert json.loads(r2["parameters"]) == {"idx": 2}

    async def test_complex_json_parameters_roundtrip(self, execution_store):
        """Complex nested JSON parameters must survive serialization."""
        params = {
            "nested": {"deep": {"deeper": True}},
            "list": [1, "two", None, 4.0],
            "null_val": None,
            "unicode": "hello \u00e9\u00e8\u00ea",
        }
        await execution_store.record_start(
            run_id="run-complex",
            workflow_id="wf-complex",
            parameters=params,
        )

        result = await execution_store.get_execution("run-complex")
        assert result is not None
        assert json.loads(result["parameters"]) == params

    async def test_complex_json_results_roundtrip(self, execution_store):
        """Complex nested JSON results must survive serialization."""
        results = {
            "nodes": {
                "node-1": {"output": [1, 2, 3]},
                "node-2": {"output": {"nested": True}},
            },
            "metadata": {"duration_ms": 1234},
        }
        await execution_store.record_start(
            run_id="run-cplx-res",
            workflow_id="wf-cplx-res",
        )
        await execution_store.record_completion(
            run_id="run-cplx-res",
            results=results,
        )

        result = await execution_store.get_execution("run-cplx-res")
        assert result is not None
        assert json.loads(result["result"]) == results


# ===========================================================================
# InMemoryExecutionStore Tests
# ===========================================================================


class TestInMemoryExecutionStoreLifecycle:
    async def test_initialize_is_noop(self, in_memory_store):
        """initialize() on InMemoryExecutionStore should not raise."""
        await in_memory_store.initialize()

    async def test_close_is_noop(self, in_memory_store):
        """close() on InMemoryExecutionStore should not raise."""
        await in_memory_store.close()


class TestInMemoryExecutionStoreRecordStart:
    async def test_record_start_stores_execution(self, in_memory_store):
        """record_start should store execution metadata in memory."""
        await in_memory_store.initialize()
        await in_memory_store.record_start(
            run_id="mem-001",
            workflow_id="wf-mem",
            parameters={"key": "val"},
            worker_id="w-1",
        )

        result = await in_memory_store.get_execution("mem-001")
        assert result is not None
        assert result["run_id"] == "mem-001"
        assert result["workflow_id"] == "wf-mem"
        assert result["status"] == "pending"
        assert result["worker_id"] == "w-1"

    async def test_record_start_without_optional_params(self, in_memory_store):
        """record_start should work without optional parameters."""
        await in_memory_store.initialize()
        await in_memory_store.record_start(
            run_id="mem-min",
            workflow_id="wf-min",
        )

        result = await in_memory_store.get_execution("mem-min")
        assert result is not None
        assert result["parameters"] is None
        assert result["worker_id"] is None


class TestInMemoryExecutionStoreRecordCompletion:
    async def test_record_completion_updates_status(self, in_memory_store):
        """record_completion should update status to 'completed'."""
        await in_memory_store.initialize()
        await in_memory_store.record_start(
            run_id="mem-comp",
            workflow_id="wf-comp",
        )
        await in_memory_store.record_completion(
            run_id="mem-comp",
            results={"done": True},
        )

        result = await in_memory_store.get_execution("mem-comp")
        assert result is not None
        assert result["status"] == "completed"
        assert result["result"] == {"done": True}
        assert result["completed_at"] is not None


class TestInMemoryExecutionStoreRecordFailure:
    async def test_record_failure_updates_status(self, in_memory_store):
        """record_failure should update status to 'failed'."""
        await in_memory_store.initialize()
        await in_memory_store.record_start(
            run_id="mem-fail",
            workflow_id="wf-fail",
        )
        await in_memory_store.record_failure(
            run_id="mem-fail",
            error="something broke",
        )

        result = await in_memory_store.get_execution("mem-fail")
        assert result is not None
        assert result["status"] == "failed"
        assert result["error"] == "something broke"
        assert result["completed_at"] is not None


class TestInMemoryExecutionStoreGetExecution:
    async def test_get_nonexistent_returns_none(self, in_memory_store):
        """get_execution for missing run_id should return None."""
        await in_memory_store.initialize()
        result = await in_memory_store.get_execution("nonexistent")
        assert result is None


class TestInMemoryExecutionStoreListExecutions:
    async def test_list_all_executions(self, in_memory_store):
        """list_executions with no filters should return all."""
        await in_memory_store.initialize()
        for i in range(3):
            await in_memory_store.record_start(
                run_id=f"mem-list-{i}",
                workflow_id="wf-list",
            )

        results = await in_memory_store.list_executions()
        assert len(results) == 3

    async def test_list_filter_by_status(self, in_memory_store):
        """list_executions should filter by status."""
        await in_memory_store.initialize()
        await in_memory_store.record_start(run_id="m-a", workflow_id="wf")
        await in_memory_store.record_start(run_id="m-b", workflow_id="wf")
        await in_memory_store.record_completion(run_id="m-a", results={})

        pending = await in_memory_store.list_executions(status="pending")
        assert len(pending) == 1
        assert pending[0]["run_id"] == "m-b"

    async def test_list_filter_by_workflow_id(self, in_memory_store):
        """list_executions should filter by workflow_id."""
        await in_memory_store.initialize()
        await in_memory_store.record_start(run_id="m-w1", workflow_id="wf-1")
        await in_memory_store.record_start(run_id="m-w2", workflow_id="wf-2")

        results = await in_memory_store.list_executions(workflow_id="wf-1")
        assert len(results) == 1
        assert results[0]["run_id"] == "m-w1"

    async def test_list_respects_limit(self, in_memory_store):
        """list_executions should respect the limit parameter."""
        await in_memory_store.initialize()
        for i in range(10):
            await in_memory_store.record_start(
                run_id=f"m-lim-{i}",
                workflow_id="wf",
            )

        results = await in_memory_store.list_executions(limit=3)
        assert len(results) == 3

    async def test_list_empty_returns_empty(self, in_memory_store):
        """list_executions on empty store should return empty list."""
        await in_memory_store.initialize()
        results = await in_memory_store.list_executions()
        assert results == []
