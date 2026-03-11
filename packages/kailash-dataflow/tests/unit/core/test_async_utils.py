"""
Unit tests for async_utils module.

Tests cover:
- async_safe_run() in sync context (no running loop)
- async_safe_run() in async context (running loop)
- Exception propagation
- Timeout handling
- Nested calls
- Context detection
- Utility functions

See: TODO-159 - Async-Safe Wrapper Utility
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from dataflow.core.async_utils import (
    async_context,
    async_safe_run,
    cleanup_thread_pool,
    ensure_async,
    get_execution_context,
    is_event_loop_running,
    run_sync,
)


class TestIsEventLoopRunning:
    """Tests for is_event_loop_running() function."""

    def test_returns_false_in_sync_context(self):
        """Verify returns False when no event loop is running."""
        # In a sync test, there's no running event loop
        assert is_event_loop_running() is False

    @pytest.mark.asyncio
    async def test_returns_true_in_async_context(self):
        """Verify returns True when event loop is running."""
        # In an async test, the event loop is running
        assert is_event_loop_running() is True

    def test_handles_no_loop_gracefully(self):
        """Verify handles missing event loop without error."""
        # Should not raise, just return False
        result = is_event_loop_running()
        assert isinstance(result, bool)


class TestGetExecutionContext:
    """Tests for get_execution_context() function."""

    def test_sync_context_detected(self):
        """Verify sync context is detected correctly."""
        context = get_execution_context()
        assert context == "sync"

    @pytest.mark.asyncio
    async def test_async_context_detected(self):
        """Verify async context is detected when loop is running."""
        context = get_execution_context()
        # Should detect as 'async' or more specific framework
        assert context in ("async", "fastapi", "jupyter", "docker_async")

    def test_returns_string(self):
        """Verify always returns a string."""
        context = get_execution_context()
        assert isinstance(context, str)
        assert len(context) > 0


class TestAsyncSafeRunSyncContext:
    """Tests for async_safe_run() in synchronous context (no running loop)."""

    def test_executes_simple_coroutine(self):
        """Verify simple coroutine execution works."""

        async def simple_coro():
            return 42

        result = async_safe_run(simple_coro())
        assert result == 42

    def test_executes_async_with_await(self):
        """Verify coroutine with await works."""

        async def coro_with_await():
            await asyncio.sleep(0.01)
            return "completed"

        result = async_safe_run(coro_with_await())
        assert result == "completed"

    def test_preserves_return_value_types(self):
        """Verify various return types are preserved."""

        async def return_dict():
            return {"key": "value", "number": 123}

        async def return_list():
            return [1, 2, 3]

        async def return_none():
            return None

        assert async_safe_run(return_dict()) == {"key": "value", "number": 123}
        assert async_safe_run(return_list()) == [1, 2, 3]
        assert async_safe_run(return_none()) is None

    def test_propagates_exceptions(self):
        """Verify exceptions from coroutines are propagated."""

        async def raises_error():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            async_safe_run(raises_error())

    def test_propagates_custom_exceptions(self):
        """Verify custom exception types are preserved."""

        class CustomError(Exception):
            pass

        async def raises_custom():
            raise CustomError("custom error message")

        with pytest.raises(CustomError, match="custom error message"):
            async_safe_run(raises_custom())

    def test_timeout_parameter(self):
        """Verify timeout parameter works in sync context."""

        async def slow_coro():
            await asyncio.sleep(5)
            return "should not reach"

        with pytest.raises(asyncio.TimeoutError):
            async_safe_run(slow_coro(), timeout=0.1)

    def test_respects_timeout_success(self):
        """Verify fast operations complete within timeout."""

        async def fast_coro():
            await asyncio.sleep(0.01)
            return "fast"

        result = async_safe_run(fast_coro(), timeout=1.0)
        assert result == "fast"


class TestAsyncSafeRunAsyncContext:
    """Tests for async_safe_run() when called from async context."""

    @pytest.mark.asyncio
    async def test_executes_in_async_context(self):
        """Verify works when event loop is already running."""

        async def inner_coro():
            return "from async context"

        # This should use thread pool since loop is running
        result = async_safe_run(inner_coro())
        assert result == "from async context"

    @pytest.mark.asyncio
    async def test_preserves_return_values_in_async(self):
        """Verify return values preserved in async context."""

        async def return_complex():
            return {"nested": {"data": [1, 2, 3]}}

        result = async_safe_run(return_complex())
        assert result == {"nested": {"data": [1, 2, 3]}}

    @pytest.mark.asyncio
    async def test_propagates_exceptions_in_async(self):
        """Verify exceptions propagated in async context."""

        async def raises_in_async():
            raise RuntimeError("async context error")

        with pytest.raises(RuntimeError, match="async context error"):
            async_safe_run(raises_in_async())

    @pytest.mark.asyncio
    async def test_timeout_in_async_context(self):
        """Verify timeout works in async context."""

        async def slow_async():
            await asyncio.sleep(5)
            return "slow"

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            async_safe_run(slow_async(), timeout=0.1)


class TestAsyncSafeRunThreadSafety:
    """Tests for thread safety of async_safe_run()."""

    def test_concurrent_calls_from_sync(self):
        """Verify concurrent calls work correctly."""
        results = []
        errors = []

        async def worker(n):
            await asyncio.sleep(0.01)
            return n * 2

        def call_async_safe(n):
            try:
                result = async_safe_run(worker(n))
                results.append((n, result))
            except Exception as e:
                errors.append((n, e))

        # Run 10 concurrent calls
        threads = [
            threading.Thread(target=call_async_safe, args=(i,)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        for n, result in results:
            assert result == n * 2

    @pytest.mark.asyncio
    async def test_concurrent_calls_from_async(self):
        """Verify concurrent calls work in async context."""
        results = []
        errors = []

        async def worker(n):
            await asyncio.sleep(0.01)
            return n * 2

        def call_sync(n):
            try:
                result = async_safe_run(worker(n))
                results.append((n, result))
            except Exception as e:
                errors.append((n, e))

        # Use thread pool to call sync from async
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(call_sync, i) for i in range(10)]
            for f in futures:
                f.result(timeout=5)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10


class TestAsyncSafeRunNestedCalls:
    """Tests for nested async_safe_run() calls."""

    def test_shallow_nesting(self):
        """Verify shallow nesting works."""

        async def inner():
            return "inner"

        async def outer():
            # This would be unusual but should work
            return await inner()

        result = async_safe_run(outer())
        assert result == "inner"

    def test_prevents_deep_recursion(self):
        """Verify protection against infinite recursion."""
        call_count = [0]

        async def recursive():
            call_count[0] += 1
            if call_count[0] > 15:
                return "stopped"
            # This would create deep nesting
            return async_safe_run(recursive())

        # Should either work (with thread pool) or raise recursion limit
        # The implementation limits depth to 10
        with pytest.raises(RuntimeError, match="recursively too many times"):
            async_safe_run(recursive())


class TestEnsureAsync:
    """Tests for ensure_async() utility function."""

    @pytest.mark.asyncio
    async def test_awaits_coroutine(self):
        """Verify coroutines are awaited."""

        async def get_value():
            return 42

        result = await ensure_async(get_value())
        assert result == 42

    @pytest.mark.asyncio
    async def test_returns_regular_value(self):
        """Verify regular values pass through unchanged."""
        result = await ensure_async(42)
        assert result == 42

        result = await ensure_async("string")
        assert result == "string"

        result = await ensure_async([1, 2, 3])
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_handles_none(self):
        """Verify None is handled correctly."""
        result = await ensure_async(None)
        assert result is None


class TestRunSyncDecorator:
    """Tests for run_sync() decorator."""

    def test_creates_sync_wrapper(self):
        """Verify decorator creates working sync wrapper."""

        @run_sync
        async def async_function():
            await asyncio.sleep(0.01)
            return "result"

        # Should be callable synchronously
        result = async_function()
        assert result == "result"

    def test_preserves_function_name(self):
        """Verify function name is preserved."""

        @run_sync
        async def my_named_function():
            return 1

        assert my_named_function.__name__ == "my_named_function"

    def test_passes_arguments(self):
        """Verify arguments are passed correctly."""

        @run_sync
        async def add(a, b, c=0):
            return a + b + c

        assert add(1, 2) == 3
        assert add(1, 2, c=3) == 6

    def test_propagates_exceptions(self):
        """Verify exceptions are propagated from decorated function."""

        @run_sync
        async def raises():
            raise ValueError("decorator error")

        with pytest.raises(ValueError, match="decorator error"):
            raises()


class TestAsyncContextManager:
    """Tests for async_context() context manager."""

    def test_tracks_depth(self):
        """Verify context depth tracking."""
        # Note: Use cleanup to ensure clean state
        cleanup_thread_pool()
        with async_context() as depth1:
            assert depth1 >= 1  # May vary based on prior state
            prior_depth = depth1
            with async_context() as depth2:
                assert depth2 == prior_depth + 1

    def test_cleans_up_on_exit(self):
        """Verify depth is decremented on exit."""
        cleanup_thread_pool()
        with async_context() as depth1:
            inner_depth = depth1
        # After exit, depth should decrease
        with async_context() as depth2:
            # Both should be same depth (incremented from same base)
            assert depth2 == depth1


class TestCleanupThreadPool:
    """Tests for cleanup_thread_pool() function."""

    def test_cleanup_is_safe_to_call_multiple_times(self):
        """Verify cleanup can be called multiple times safely."""

        # First, trigger thread pool creation
        async def dummy():
            return 1

        async_safe_run(dummy())

        # Call cleanup multiple times
        cleanup_thread_pool()
        cleanup_thread_pool()
        cleanup_thread_pool()

        # Should still work after cleanup
        result = async_safe_run(dummy())
        assert result == 1


class TestRealWorldScenarios:
    """Tests simulating real-world usage scenarios."""

    def test_database_operation_simulation(self):
        """Simulate a database operation pattern."""

        async def db_query(query: str) -> dict:
            await asyncio.sleep(0.01)  # Simulate I/O
            return {"query": query, "rows": [1, 2, 3]}

        result = async_safe_run(db_query("SELECT * FROM users"))
        assert result["query"] == "SELECT * FROM users"
        assert result["rows"] == [1, 2, 3]

    def test_multiple_sequential_operations(self):
        """Simulate multiple sequential async operations."""

        async def operation(n: int) -> int:
            await asyncio.sleep(0.001)
            return n * 2

        results = []
        for i in range(5):
            result = async_safe_run(operation(i))
            results.append(result)

        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_mixed_sync_async_workflow(self):
        """Simulate mixed sync/async workflow in FastAPI-like context."""

        async def async_step(data: str) -> str:
            await asyncio.sleep(0.001)
            return f"async:{data}"

        def sync_step(data: str) -> str:
            # This simulates calling async from sync code within async context
            return async_safe_run(async_step(data))

        # Simulate FastAPI endpoint that calls sync library
        result = sync_step("input")
        assert result == "async:input"

    def test_exception_chain_preserved(self):
        """Verify exception chain is preserved for debugging."""

        async def inner_error():
            raise ValueError("inner cause")

        async def outer_wrapper():
            try:
                await inner_error()
            except ValueError:
                raise RuntimeError("outer error") from ValueError("inner cause")

        with pytest.raises(RuntimeError, match="outer error"):
            async_safe_run(outer_wrapper())


class TestPerformance:
    """Performance-related tests."""

    def test_sync_context_overhead_minimal(self):
        """Verify minimal overhead in sync context."""

        async def fast_op():
            return 1

        # Warm up
        async_safe_run(fast_op())

        # Measure
        start = time.perf_counter()
        for _ in range(100):
            async_safe_run(fast_op())
        elapsed = time.perf_counter() - start

        # Should complete 100 calls in under 1 second (10ms each max)
        assert elapsed < 1.0, f"Sync context too slow: {elapsed}s for 100 calls"

    @pytest.mark.asyncio
    async def test_async_context_reasonable_overhead(self):
        """Verify reasonable overhead in async context."""

        async def fast_op():
            return 1

        # Warm up
        async_safe_run(fast_op())

        # Measure - thread pool adds overhead
        start = time.perf_counter()
        for _ in range(20):
            async_safe_run(fast_op())
        elapsed = time.perf_counter() - start

        # Should complete 20 calls in under 5 seconds (250ms each max)
        # Thread pool adds overhead but should be reasonable
        assert elapsed < 5.0, f"Async context too slow: {elapsed}s for 20 calls"
