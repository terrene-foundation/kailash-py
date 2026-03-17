# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for IdempotentExecutor — execution-level exactly-once wrapper.

Tests cover:
- Pass-through execution when no idempotency_key is provided
- First execution with key: claims key, executes, stores result
- Second execution with same key: returns cached result without re-executing
- Exactly-once guarantee: same key called N times, runtime.execute_count == 1
- Different keys execute independently
- Failed execution releases claim, allowing retry
- TTL enforcement: expired cached result triggers re-execution
- Constructor validation: store and ttl_seconds
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock runtime — counts executions
# ---------------------------------------------------------------------------
class MockRuntime:
    """Mock runtime that counts executions and returns predictable results."""

    def __init__(self, results=None):
        self.execute_count = 0
        self._results = results or {"output": "test"}

    def execute(self, workflow, parameters=None):
        self.execute_count += 1
        return self._results, f"run-{self.execute_count}"


class FailingRuntime:
    """Runtime that raises on the first N calls, then succeeds."""

    def __init__(self, fail_count=1, results=None):
        self.execute_count = 0
        self._fail_count = fail_count
        self._results = results or {"output": "recovered"}

    def execute(self, workflow, parameters=None):
        self.execute_count += 1
        if self.execute_count <= self._fail_count:
            raise RuntimeError(f"Execution failed (attempt {self.execute_count})")
        return self._results, f"run-{self.execute_count}"


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
async def idempotency_store(conn_manager):
    """Provide an initialized DBIdempotencyStore backend."""
    from kailash.infrastructure.idempotency_store import DBIdempotencyStore

    store = DBIdempotencyStore(conn_manager)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def executor(idempotency_store):
    """Provide an IdempotentExecutor with the real store."""
    from kailash.infrastructure.idempotency import IdempotentExecutor

    return IdempotentExecutor(idempotency_store, ttl_seconds=3600)


@pytest.fixture
def mock_runtime():
    """Provide a MockRuntime."""
    return MockRuntime()


@pytest.fixture
def mock_workflow():
    """Provide a placeholder workflow object (not executed by MockRuntime)."""
    return "mock-workflow-definition"


# ---------------------------------------------------------------------------
# Pass-through (no idempotency key)
# ---------------------------------------------------------------------------
class TestExecuteWithoutKey:
    async def test_execute_without_key_passes_through(
        self, executor, mock_runtime, mock_workflow
    ):
        """No idempotency_key provided -> executes directly without dedup."""
        results, run_id = await executor.execute(
            mock_runtime, mock_workflow, parameters={"input": "value"}
        )
        assert results == {"output": "test"}
        assert run_id == "run-1"
        assert mock_runtime.execute_count == 1

    async def test_execute_without_key_calls_runtime_every_time(
        self, executor, mock_runtime, mock_workflow
    ):
        """Without idempotency_key, every call reaches the runtime."""
        for i in range(3):
            results, run_id = await executor.execute(
                mock_runtime, mock_workflow, parameters={}
            )
        assert mock_runtime.execute_count == 3


# ---------------------------------------------------------------------------
# First execution with key
# ---------------------------------------------------------------------------
class TestFirstExecuteWithKey:
    async def test_first_execute_with_key_runs_workflow(
        self, executor, mock_runtime, mock_workflow
    ):
        """First call with an idempotency_key should execute the workflow."""
        results, run_id = await executor.execute(
            mock_runtime,
            mock_workflow,
            parameters={"x": 1},
            idempotency_key="req-001",
        )
        assert results == {"output": "test"}
        assert run_id == "run-1"
        assert mock_runtime.execute_count == 1

    async def test_first_execute_stores_result(
        self, executor, idempotency_store, mock_runtime, mock_workflow
    ):
        """After first execution, the result should be stored in the store."""
        await executor.execute(
            mock_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-stored",
        )
        cached = await idempotency_store.get("req-stored")
        assert cached is not None
        assert cached["status_code"] == 200
        stored_data = json.loads(cached["response_data"])
        assert stored_data["results"] == {"output": "test"}
        assert stored_data["run_id"] == "run-1"


# ---------------------------------------------------------------------------
# Second execution with same key returns cached
# ---------------------------------------------------------------------------
class TestSecondExecuteReturnsCached:
    async def test_second_execute_with_same_key_returns_cached(
        self, executor, mock_runtime, mock_workflow
    ):
        """Second call with same key should return cached result, no re-execution."""
        result1, run_id1 = await executor.execute(
            mock_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-dedup",
        )
        result2, run_id2 = await executor.execute(
            mock_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-dedup",
        )

        assert result1 == result2
        assert run_id1 == run_id2
        assert mock_runtime.execute_count == 1

    async def test_cached_result_preserves_exact_data(self, executor, mock_workflow):
        """Cached result must preserve the exact results dict and run_id."""
        custom_results = {"items": [1, 2, 3], "count": 3, "nested": {"key": "val"}}
        runtime = MockRuntime(results=custom_results)

        results1, run_id1 = await executor.execute(
            runtime, mock_workflow, idempotency_key="req-exact"
        )
        results2, run_id2 = await executor.execute(
            runtime, mock_workflow, idempotency_key="req-exact"
        )

        assert results2 == custom_results
        assert run_id2 == run_id1
        assert runtime.execute_count == 1


# ---------------------------------------------------------------------------
# Exactly-once: N calls, execute_count == 1
# ---------------------------------------------------------------------------
class TestExactlyOnceGuarantee:
    async def test_execute_count_is_exactly_one(
        self, executor, mock_runtime, mock_workflow
    ):
        """With same key called 5 times, runtime.execute_count must be 1."""
        for i in range(5):
            results, run_id = await executor.execute(
                mock_runtime,
                mock_workflow,
                parameters={"iteration": i},
                idempotency_key="req-once",
            )

        assert mock_runtime.execute_count == 1
        # All calls return the same result
        assert results == {"output": "test"}
        assert run_id == "run-1"


# ---------------------------------------------------------------------------
# Different keys execute independently
# ---------------------------------------------------------------------------
class TestDifferentKeysIndependent:
    async def test_different_keys_execute_independently(
        self, executor, mock_runtime, mock_workflow
    ):
        """Different idempotency keys must each trigger their own execution."""
        results_a, run_id_a = await executor.execute(
            mock_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="key-alpha",
        )
        results_b, run_id_b = await executor.execute(
            mock_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="key-beta",
        )
        results_c, run_id_c = await executor.execute(
            mock_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="key-gamma",
        )

        assert mock_runtime.execute_count == 3
        assert run_id_a == "run-1"
        assert run_id_b == "run-2"
        assert run_id_c == "run-3"


# ---------------------------------------------------------------------------
# Failed execution releases claim
# ---------------------------------------------------------------------------
class TestFailedExecutionReleasesClaim:
    async def test_failed_execution_releases_claim(
        self, executor, idempotency_store, mock_workflow
    ):
        """On error, claim is released so the key can be retried."""
        failing_runtime = FailingRuntime(fail_count=1)

        # First call fails
        with pytest.raises(RuntimeError, match="Execution failed"):
            await executor.execute(
                failing_runtime,
                mock_workflow,
                parameters={},
                idempotency_key="req-fail",
            )

        # Claim should be released — key should not be in the store
        cached = await idempotency_store.get("req-fail")
        assert cached is None

    async def test_retry_after_failure_succeeds(self, executor, mock_workflow):
        """After a failed execution releases the claim, a retry should succeed."""
        failing_runtime = FailingRuntime(fail_count=1)

        # First call fails
        with pytest.raises(RuntimeError, match="Execution failed"):
            await executor.execute(
                failing_runtime,
                mock_workflow,
                parameters={},
                idempotency_key="req-retry",
            )

        # Second call succeeds (fail_count=1 means first call fails, second succeeds)
        results, run_id = await executor.execute(
            failing_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-retry",
        )

        assert results == {"output": "recovered"}
        assert run_id == "run-2"
        assert failing_runtime.execute_count == 2

    async def test_retry_after_failure_caches_successful_result(
        self, executor, idempotency_store, mock_workflow
    ):
        """Successful retry after failure should cache the result for future calls."""
        failing_runtime = FailingRuntime(fail_count=1)

        # First call fails
        with pytest.raises(RuntimeError):
            await executor.execute(
                failing_runtime,
                mock_workflow,
                parameters={},
                idempotency_key="req-retry-cache",
            )

        # Second call succeeds
        results, run_id = await executor.execute(
            failing_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-retry-cache",
        )

        # Third call should return cached result, no re-execution
        results2, run_id2 = await executor.execute(
            failing_runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-retry-cache",
        )

        assert results2 == results
        assert run_id2 == run_id
        assert failing_runtime.execute_count == 2  # Only 2 executions total


# ---------------------------------------------------------------------------
# TTL enforcement
# ---------------------------------------------------------------------------
class TestTTLEnforcement:
    async def test_ttl_respected_expired_result_re_executes(
        self, idempotency_store, conn_manager, mock_workflow
    ):
        """Expired cached result should trigger re-execution."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        executor = IdempotentExecutor(idempotency_store, ttl_seconds=3600)
        runtime = MockRuntime()

        # First execution
        await executor.execute(
            runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-ttl",
        )
        assert runtime.execute_count == 1

        # Manually expire the entry by setting expires_at to the past
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        await conn_manager.execute(
            "UPDATE kailash_idempotency SET expires_at = ? WHERE idempotency_key = ?",
            past,
            "req-ttl",
        )

        # Second execution — should re-execute because the entry is expired
        results, run_id = await executor.execute(
            runtime,
            mock_workflow,
            parameters={},
            idempotency_key="req-ttl",
        )

        assert runtime.execute_count == 2
        assert results == {"output": "test"}


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------
class TestConstructorValidation:
    def test_requires_store(self):
        """IdempotentExecutor must require an idempotency_store argument."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        with pytest.raises(TypeError):
            IdempotentExecutor()  # type: ignore[call-arg]

    def test_custom_ttl(self, idempotency_store):
        """Custom ttl_seconds should be stored and used."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        executor = IdempotentExecutor(idempotency_store, ttl_seconds=7200)
        assert executor._ttl == 7200

    def test_default_ttl(self, idempotency_store):
        """Default ttl_seconds should be 3600 (1 hour)."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        executor = IdempotentExecutor(idempotency_store)
        assert executor._ttl == 3600


# ---------------------------------------------------------------------------
# Parameters forwarding
# ---------------------------------------------------------------------------
class TestParametersForwarding:
    async def test_parameters_forwarded_to_runtime(self, executor, mock_workflow):
        """Parameters dict should be forwarded to runtime.execute()."""

        class CapturingRuntime:
            def __init__(self):
                self.captured_params = None

            def execute(self, workflow, parameters=None):
                self.captured_params = parameters
                return {"ok": True}, "run-cap"

        runtime = CapturingRuntime()
        await executor.execute(
            runtime,
            mock_workflow,
            parameters={"input_a": 42, "input_b": "hello"},
            idempotency_key="req-params",
        )

        assert runtime.captured_params == {"input_a": 42, "input_b": "hello"}

    async def test_none_parameters_defaults_to_empty_dict(
        self, executor, mock_workflow
    ):
        """When parameters is None, runtime should receive an empty dict."""

        class CapturingRuntime:
            def __init__(self):
                self.captured_params = None

            def execute(self, workflow, parameters=None):
                self.captured_params = parameters
                return {"ok": True}, "run-cap"

        runtime = CapturingRuntime()
        await executor.execute(
            runtime, mock_workflow, idempotency_key="req-none-params"
        )

        assert runtime.captured_params == {}
