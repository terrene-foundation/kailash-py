"""Real SQLite workflow timings and deterministic benchmark-statistics checks.

The 10s bound detects stalled local operations. Machine-dependent durations are
reported, not substituted for evidence of PostgreSQL TDD speedup guarantees.
"""

import asyncio
import statistics
import time
import tracemalloc
from contextlib import asynccontextmanager
from typing import Dict, List

import pytest
import pytest_asyncio

from dataflow import DataFlow
from dataflow.nodes.transaction_nodes import (
    TransactionRollbackToSavepointNode,
    TransactionSavepointNode,
)
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class PerformanceValidator:
    """Utility class for validating TDD performance targets."""

    def __init__(self):
        self.measurements: List[float] = []
        self.target_ms = 100.0
        self.warning_threshold_ms = 80.0

    def record_measurement(self, duration_ms: float):
        """Record a performance measurement."""
        self.measurements.append(duration_ms)

    def get_statistics(self) -> Dict[str, float]:
        """Get performance statistics."""
        if not self.measurements:
            return {}

        return {
            "count": len(self.measurements),
            "mean": statistics.mean(self.measurements),
            "median": statistics.median(self.measurements),
            "min": min(self.measurements),
            "max": max(self.measurements),
            "std_dev": (
                statistics.stdev(self.measurements)
                if len(self.measurements) > 1
                else 0.0
            ),
            "target_achieved_pct": (
                sum(1 for m in self.measurements if m <= self.target_ms)
                / len(self.measurements)
            )
            * 100,
        }

    def validate_target_achieved(self, min_success_rate: float = 95.0) -> bool:
        """Validate that the target is achieved for the minimum success rate."""
        stats = self.get_statistics()
        return stats.get("target_achieved_pct", 0.0) >= min_success_rate


@pytest.fixture
def performance_validator():
    """Provide a performance validator for tests."""
    return PerformanceValidator()


@asynccontextmanager
async def _database(path):
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True)
    try:

        class PerfTestUser:
            id: str
            name: str
            email: str
            active: bool = True

        model_name = "PerfTestUser"
        db.model(PerfTestUser)
        assert await db.initialize()
        async with AsyncLocalRuntime() as runtime:
            yield db, runtime, model_name
    finally:
        await db.close_async()


@pytest_asyncio.fixture
async def tdd_transaction_dataflow(tmp_path):
    async with _database(tmp_path / "benchmark.db") as state:
        yield state


async def _run(state, operation, parameters, scope=None):
    db, runtime, model_name = state
    workflow = WorkflowBuilder()
    workflow.add_node(
        node_type=db.get_node(f"{model_name}{operation}Node"),
        node_id="operation",
        config=parameters,
    )
    built = workflow.build()
    node = built.get_node("operation")
    assert node.dataflow_instance is db
    node.set_workflow_context("dataflow_instance", db)
    if scope is not None:
        node.set_workflow_context("active_transaction", scope)
    results, run_id = await runtime.execute_workflow_async(built, inputs={})
    assert run_id
    assert results["operation"].get("error") is None
    return results["operation"]


async def _create(state, key, scope=None):
    return await _run(
        state,
        "Create",
        {
            "id": key,
            "name": key,
            "email": f"{key}@example.test",
            "active": True,
        },
        scope,
    )


async def _rows(state, scope=None):
    result = await _run(state, "List", {"filter": {"active": True}}, scope)
    return result["records"]


def _record(validator, start):
    elapsed = (time.perf_counter() - start) * 1000
    validator.record_measurement(elapsed)
    assert 0 < elapsed < 10000, f"Database operation exceeded 10s: {elapsed}ms"
    return elapsed


async def _adapter(state):
    db, _, model_name = state
    return await db._get_or_create_async_sql_node("sqlite")._get_adapter()


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_tdd_transaction_performance_single(
    tdd_transaction_dataflow, performance_validator
):
    state = tdd_transaction_dataflow
    start = time.perf_counter()
    adapter = await _adapter(state)
    async with adapter.transaction() as scope:
        await _create(state, "committed", scope)
        assert {r["id"] for r in await _rows(state, scope)} == {"committed"}
    assert {r["id"] for r in await _rows(state)} == {"committed"}
    _record(performance_validator, start)


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_tdd_savepoint_isolation_performance(
    tdd_transaction_dataflow, performance_validator
):
    state = tdd_transaction_dataflow
    start = time.perf_counter()
    adapter = await _adapter(state)
    async with adapter.transaction() as outer:
        await _create(state, "outer", outer)
        save = TransactionSavepointNode(name="inner")
        rollback = TransactionRollbackToSavepointNode(savepoint="inner")
        save.set_workflow_context("active_transaction", outer)
        rollback.set_workflow_context("active_transaction", outer)
        assert (await save.async_run())["status"] == "created"
        rollback.set_workflow_context(
            "savepoints", save.get_workflow_context("savepoints")
        )
        await _create(state, "inner", outer)
        assert {r["id"] for r in await _rows(state, outer)} == {"outer", "inner"}
        assert (await rollback.async_run())["status"] == "rolled_back_to_savepoint"
        assert {r["id"] for r in await _rows(state, outer)} == {"outer"}
    assert {r["id"] for r in await _rows(state)} == {"outer"}
    _record(performance_validator, start)


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_tdd_parallel_performance(performance_validator, tmp_path):
    async with _database(tmp_path / "one.db") as one:
        async with _database(tmp_path / "two.db") as two:
            start = time.perf_counter()

            async def exercise(state, key):
                await _create(state, key)
                return await _rows(state)

            first, second = await asyncio.gather(
                exercise(one, "first"), exercise(two, "second")
            )
            assert {r["id"] for r in first} == {"first"}
            assert {r["id"] for r in second} == {"second"}
            _record(performance_validator, start)


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_tdd_seeded_data_performance(
    tdd_transaction_dataflow, performance_validator
):
    state = tdd_transaction_dataflow
    for i in range(3):
        await _create(state, f"seed-{i}")
    start = time.perf_counter()
    assert {r["id"] for r in await _rows(state)} == {"seed-0", "seed-1", "seed-2"}
    _record(performance_validator, start)


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_tdd_connection_reuse_performance(
    tdd_transaction_dataflow, performance_validator
):
    state = tdd_transaction_dataflow
    adapter = await _adapter(state)
    start = time.perf_counter()
    async with adapter.transaction() as scope:
        connection = scope.connection
        for i in range(5):
            await _create(state, f"reuse-{i}", scope)
            assert scope.connection is connection
            assert len(await _rows(state, scope)) == i + 1
    assert len(await _rows(state)) == 5
    _record(performance_validator, start)


@pytest.mark.asyncio
async def test_tdd_fixture_setup_performance(performance_validator, tmp_path):
    start = time.perf_counter()
    async with _database(tmp_path / "setup.db") as state:
        assert await _rows(state) == []
    _record(performance_validator, start)
    assert performance_validator.get_statistics()["count"] == 1


def test_memory_usage_performance(record_property):
    already_tracing = tracemalloc.is_tracing()
    if not already_tracing:
        tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        data = list(range(1000))
        processed = [x * 2 for x in data]
        after, peak = tracemalloc.get_traced_memory()
        assert processed[-1] == 1998
        delta_mb = (after - before) / (1024 * 1024)
        assert 0 < delta_mb < 0.5
        assert peak > before
        record_property("memory_delta_bytes", after - before)
        record_property("memory_peak_bytes", peak)
    finally:
        if not already_tracing:
            tracemalloc.stop()


def test_tdd_performance_batch_validation(performance_validator):
    # Exact samples test the 100ms boundary without asserting scheduler latency.
    for duration in [10.0] * 9 + [100.0]:
        performance_validator.record_measurement(duration)
    stats = performance_validator.get_statistics()
    assert stats["count"] == 10
    assert stats["mean"] == 19.0
    assert stats["max"] == 100.0
    assert stats["target_achieved_pct"] == 100.0
    assert performance_validator.validate_target_achieved()
    performance_validator.record_measurement(101.0)
    assert not performance_validator.validate_target_achieved()


@pytest.mark.asyncio
async def test_performance_comparison_with_traditional(
    tdd_transaction_dataflow, performance_validator, tmp_path, record_property
):
    # Measure two real paths; do not invent a fixed cross-machine speed ratio.
    start = time.perf_counter()
    async with _database(tmp_path / "fresh-schema.db") as fresh:
        await _create(fresh, "fresh")
        assert len(await _rows(fresh)) == 1
    recreation_ms = _record(performance_validator, start)
    state = tdd_transaction_dataflow
    adapter = await _adapter(state)
    start = time.perf_counter()
    with pytest.raises(ValueError, match="rollback benchmark"):
        async with adapter.transaction() as scope:
            await _create(state, "discard", scope)
            raise ValueError("rollback benchmark")
    assert await _rows(state) == []
    rollback_ms = _record(performance_validator, start)
    record_property("schema_recreation_ms", recreation_ms)
    record_property("transaction_rollback_ms", rollback_ms)


def test_performance_validator_final_report(performance_validator):
    assert performance_validator.get_statistics() == {}
    assert not performance_validator.validate_target_achieved()
    for duration in [10.0] * 9 + [110.0]:
        performance_validator.record_measurement(duration)
    stats = performance_validator.get_statistics()
    assert stats["count"] == 10
    assert stats["target_achieved_pct"] == 90.0
    assert stats["mean"] == 20.0
    assert stats["min"] == 10.0
    assert stats["max"] == 110.0
    assert stats["median"] == 10.0
    assert stats["std_dev"] > 0
    assert performance_validator.validate_target_achieved(90.0)
    assert not performance_validator.validate_target_achieved(95.0)
