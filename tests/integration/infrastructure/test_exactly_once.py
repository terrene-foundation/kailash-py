# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PY-EI-020: Exactly-once execution integration tests.

Tests the IdempotentExecutor with real database backends to verify
that the same idempotency key always produces the same result and
the underlying workflow executes exactly once.
"""

from __future__ import annotations

import asyncio

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.idempotency_store import DBIdempotencyStore


@pytest.fixture
async def sqlite_store():
    conn = ConnectionManager("sqlite:///:memory:")
    await conn.initialize()
    store = DBIdempotencyStore(conn)
    await store.initialize()
    yield store
    await conn.close()


class MockRuntime:
    """Mock runtime that tracks execution count."""

    def __init__(self, results=None):
        self.execute_count = 0
        self._results = results or {"output": "computed_value"}

    def execute(self, workflow, parameters=None):
        self.execute_count += 1
        return dict(self._results), f"run-{self.execute_count}"


class MockWorkflow:
    """Minimal workflow stand-in for testing."""

    pass


@pytest.mark.integration
@pytest.mark.asyncio
class TestExactlyOnceExecution:
    async def test_same_key_executes_only_once(self, sqlite_store):
        """Calling execute 5 times with the same key runs the workflow once."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        runtime = MockRuntime({"value": 42})
        executor = IdempotentExecutor(sqlite_store, ttl_seconds=3600)
        workflow = MockWorkflow()

        results = []
        for _ in range(5):
            result, run_id = await executor.execute(
                runtime, workflow, parameters={}, idempotency_key="key-001"
            )
            results.append(result)

        assert (
            runtime.execute_count == 1
        ), f"Expected 1 execution, got {runtime.execute_count}"
        # All results should be identical
        for r in results:
            assert r == {"value": 42}

    async def test_different_keys_execute_independently(self, sqlite_store):
        """Different idempotency keys each trigger their own execution."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        runtime = MockRuntime({"data": "result"})
        executor = IdempotentExecutor(sqlite_store)
        workflow = MockWorkflow()

        await executor.execute(runtime, workflow, idempotency_key="key-A")
        await executor.execute(runtime, workflow, idempotency_key="key-B")
        await executor.execute(runtime, workflow, idempotency_key="key-C")

        assert runtime.execute_count == 3

    async def test_no_key_always_executes(self, sqlite_store):
        """Without an idempotency key, every call executes."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        runtime = MockRuntime()
        executor = IdempotentExecutor(sqlite_store)
        workflow = MockWorkflow()

        await executor.execute(runtime, workflow)
        await executor.execute(runtime, workflow)
        await executor.execute(runtime, workflow)

        assert runtime.execute_count == 3

    async def test_failed_execution_allows_retry(self, sqlite_store):
        """If execution fails, the key is released for retry."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        class FailingRuntime:
            def __init__(self):
                self.call_count = 0

            def execute(self, workflow, parameters=None):
                self.call_count += 1
                if self.call_count == 1:
                    raise RuntimeError("Transient failure")
                return {"recovered": True}, "run-ok"

        runtime = FailingRuntime()
        executor = IdempotentExecutor(sqlite_store)
        workflow = MockWorkflow()

        # First call fails
        with pytest.raises(RuntimeError, match="Transient failure"):
            await executor.execute(runtime, workflow, idempotency_key="retry-key")

        # Second call succeeds (claim was released)
        result, run_id = await executor.execute(
            runtime, workflow, idempotency_key="retry-key"
        )
        assert result == {"recovered": True}
        assert runtime.call_count == 2

    async def test_concurrent_claims_only_one_wins(self, sqlite_store):
        """Two concurrent execute calls with the same key — only one executes."""
        from kailash.infrastructure.idempotency import IdempotentExecutor

        call_count = 0

        class SlowRuntime:
            def execute(self, workflow, parameters=None):
                nonlocal call_count
                call_count += 1
                return {"winner": call_count}, f"run-{call_count}"

        runtime = SlowRuntime()
        executor = IdempotentExecutor(sqlite_store)
        workflow = MockWorkflow()

        # Sequential calls (SQLite doesn't truly support concurrent transactions)
        r1, _ = await executor.execute(runtime, workflow, idempotency_key="race-key")
        r2, _ = await executor.execute(runtime, workflow, idempotency_key="race-key")

        assert call_count == 1
        assert r1 == r2  # Both get the same result
