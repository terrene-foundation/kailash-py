"""Unit tests for async testing utilities."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest

from kailash.nodes import PythonCodeNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.testing import AsyncAssertions, AsyncTestUtils
from kailash.workflow import Workflow


class TestAsyncTestUtils:
    """Test AsyncTestUtils functionality."""

    @pytest.mark.asyncio
    async def test_wait_for_condition(self):
        """Test waiting for condition."""
        counter = 0

        def condition():
            nonlocal counter
            counter += 1
            return counter >= 3

        # Should succeed
        await AsyncTestUtils.wait_for_condition(condition, timeout=1.0, interval=0.1)
        assert counter >= 3

    @pytest.mark.asyncio
    async def test_wait_for_condition_timeout(self):
        """Test condition timeout."""

        def never_true():
            return False

        with pytest.raises(TimeoutError, match="Condition not met"):
            await AsyncTestUtils.wait_for_condition(never_true, timeout=0.1)

    @pytest.mark.asyncio
    async def test_wait_for_async_condition(self):
        """Test waiting for async condition."""
        counter = 0

        async def async_condition():
            nonlocal counter
            counter += 1
            await asyncio.sleep(0.01)
            return counter >= 2

        await AsyncTestUtils.wait_for_condition(async_condition, timeout=1.0)
        assert counter >= 2

    @pytest.mark.asyncio
    async def test_assert_completes_within(self):
        """Test completion time assertion."""

        # Fast coroutine should pass
        async def fast_coro():
            await asyncio.sleep(0.01)
            return "done"

        result = await AsyncTestUtils.assert_completes_within(fast_coro(), 1.0)
        assert result == "done"

        # Slow coroutine should fail
        async def slow_coro():
            await asyncio.sleep(0.5)

        with pytest.raises(AssertionError, match="did not complete"):
            await AsyncTestUtils.assert_completes_within(slow_coro(), 0.1)

    @pytest.mark.asyncio
    async def test_assert_raises_async(self):
        """Test async exception assertion."""

        # Test with coroutine that raises
        async def failing_coro():
            await asyncio.sleep(0.01)
            raise ValueError("test error")

        exc = await AsyncTestUtils.assert_raises_async(ValueError, failing_coro())
        assert str(exc) == "test error"

        # Test with async function
        async def failing_func(msg):
            raise RuntimeError(msg)

        exc = await AsyncTestUtils.assert_raises_async(
            RuntimeError, failing_func, "function error"
        )
        assert str(exc) == "function error"

        # Test when no exception raised
        async def success_coro():
            return "success"

        with pytest.raises(AssertionError, match="no exception was raised"):
            await AsyncTestUtils.assert_raises_async(ValueError, success_coro())

        # Test wrong exception type
        with pytest.raises(AssertionError, match="Expected ValueError"):
            await AsyncTestUtils.assert_raises_async(ValueError, failing_func, "error")

    @pytest.mark.asyncio
    async def test_assert_duration(self):
        """Test duration assertion context manager."""
        # Within range should pass
        async with AsyncTestUtils.assert_duration(min_seconds=0.01, max_seconds=0.5):
            await asyncio.sleep(0.05)

        # Too fast should fail
        with pytest.raises(AssertionError, match="completed too quickly"):
            async with AsyncTestUtils.assert_duration(min_seconds=0.1):
                await asyncio.sleep(0.01)

        # Too slow should fail
        with pytest.raises(AssertionError, match="took too long"):
            async with AsyncTestUtils.assert_duration(max_seconds=0.01):
                await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_run_concurrent(self):
        """Test running coroutines concurrently."""
        results = []

        async def coro(n):
            await asyncio.sleep(0.01)
            results.append(n)
            return n * 2

        # Run concurrently
        values = await AsyncTestUtils.run_concurrent(coro(1), coro(2), coro(3))

        assert values == [2, 4, 6]
        assert set(results) == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_run_concurrent_with_exceptions(self):
        """Test concurrent execution with exceptions."""

        async def success():
            return "success"

        async def failure():
            raise ValueError("failed")

        # With return_exceptions=True
        results = await AsyncTestUtils.run_concurrent(
            success(), failure(), success(), return_exceptions=True
        )

        assert results[0] == "success"
        assert isinstance(results[1], ValueError)
        assert results[2] == "success"

    @pytest.mark.asyncio
    async def test_run_sequential(self):
        """Test running coroutines sequentially."""
        order = []

        async def coro(n):
            order.append(n)
            await asyncio.sleep(0.01)
            return n

        results = await AsyncTestUtils.run_sequential(coro(1), coro(2), coro(3))

        # Should be in order
        assert results == [1, 2, 3]
        assert order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_async_retry_decorator(self):
        """Test async retry decorator."""
        attempt_count = 0

        @AsyncTestUtils.async_retry(max_attempts=3, delay=0.01)
        async def flaky_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("flaky")
            return "success"

        result = await flaky_function()
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_exhausted(self):
        """Test retry exhaustion."""

        @AsyncTestUtils.async_retry(max_attempts=2, delay=0.01)
        async def always_fails():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            await always_fails()


class TestAsyncAssertions:
    """Test AsyncAssertions functionality."""

    @pytest.mark.asyncio
    async def test_assert_eventually_equals(self):
        """Test eventual equality assertion."""
        value = 0

        def getter():
            return value

        # Start async task to change value
        async def change_value():
            nonlocal value
            await asyncio.sleep(0.1)
            value = 42

        task = asyncio.create_task(change_value())

        # Should eventually equal 42
        await AsyncAssertions.assert_eventually_equals(getter, 42, timeout=1.0)

        await task

    @pytest.mark.asyncio
    async def test_assert_eventually_equals_async_getter(self):
        """Test eventual equality with async getter."""
        counter = 0

        async def async_getter():
            nonlocal counter
            counter += 1
            if counter >= 3:
                return "ready"
            return "not ready"

        await AsyncAssertions.assert_eventually_equals(
            async_getter, "ready", timeout=1.0
        )
        assert counter >= 3

    @pytest.mark.asyncio
    async def test_assert_eventually_true(self):
        """Test eventual truth assertion."""
        ready = False

        async def condition():
            return ready

        # Start task to set ready
        async def set_ready():
            nonlocal ready
            await asyncio.sleep(0.05)
            ready = True

        task = asyncio.create_task(set_ready())

        await AsyncAssertions.assert_eventually_true(condition)
        assert ready

        await task

    @pytest.mark.asyncio
    async def test_assert_converges(self):
        """Test convergence assertion."""
        value = 100.0

        def getter():
            nonlocal value
            # Converge towards 50
            value = value * 0.9 + 50 * 0.1
            return value

        # Should converge (tolerance adjusted for exponential decay rate)
        await AsyncAssertions.assert_converges(
            getter, tolerance=5.0, timeout=2.0, samples=20
        )

        # Should be close to 50 (allow more tolerance for slow convergence)
        assert abs(value - 50) < 20

    @pytest.mark.asyncio
    async def test_assert_converges_failure(self):
        """Test convergence assertion failure."""
        value = 0

        def oscillating_getter():
            nonlocal value
            # Oscillate, don't converge
            value = 100 if value == 0 else 0
            return value

        with pytest.raises(AssertionError, match="did not converge"):
            await AsyncAssertions.assert_converges(
                oscillating_getter, tolerance=10, timeout=0.5, samples=5
            )

    @pytest.mark.asyncio
    async def test_assert_workflow_succeeds(self):
        """Test workflow success assertion."""
        # Create simple workflow
        workflow = Workflow("test", "Test Workflow")
        workflow.add_node(
            "start", PythonCodeNode(name="start", code="result = {'value': 42}")
        )

        runtime = AsyncLocalRuntime()

        # Should succeed
        result = await AsyncAssertions.assert_workflow_succeeds(workflow, {}, runtime)

        # Result is a dict from AsyncLocalRuntime
        assert "start" in result["results"]
        start_result = result["results"]["start"]
        # PythonCodeNode wraps the result in {"result": ...}
        assert start_result == {"result": {"value": 42}}

    @pytest.mark.asyncio
    async def test_assert_workflow_succeeds_failure(self):
        """Test workflow success assertion with failure."""
        # Create failing workflow
        workflow = Workflow("failing", "Failing Workflow")
        workflow.add_node(
            "fail", PythonCodeNode(name="fail", code="raise ValueError('test')")
        )

        runtime = AsyncLocalRuntime()

        # Should raise WorkflowExecutionError
        from kailash.sdk_exceptions import WorkflowExecutionError

        with pytest.raises(WorkflowExecutionError, match="Async execution failed"):
            await AsyncAssertions.assert_workflow_succeeds(workflow, {}, runtime)

    @pytest.mark.asyncio
    async def test_assert_concurrent_safe(self):
        """Test concurrent safety assertion."""
        counter = 0
        lock = asyncio.Lock()

        async def safe_increment():
            nonlocal counter
            async with lock:
                temp = counter
                await asyncio.sleep(0.001)
                counter = temp + 1

        # Should pass - function is thread-safe
        await AsyncAssertions.assert_concurrent_safe(safe_increment, concurrency=10)

        assert counter == 10

    @pytest.mark.asyncio
    async def test_assert_concurrent_safe_failure(self):
        """Test concurrent safety assertion with unsafe function."""
        counter = 0

        async def unsafe_function():
            nonlocal counter
            counter += 1
            # Simulate race condition - fail on second call
            if counter == 2:
                raise RuntimeError("Race condition!")
            return "ok"

        # Should detect the error
        with pytest.raises(AssertionError, match="Concurrent execution failed"):
            await AsyncAssertions.assert_concurrent_safe(unsafe_function, concurrency=5)

    @pytest.mark.asyncio
    async def test_assert_performance(self):
        """Test performance assertion."""

        async def fast_operation():
            await asyncio.sleep(0.01)
            return "done"

        # Should pass
        result = await AsyncAssertions.assert_performance(
            fast_operation(), max_time=0.1
        )
        assert result == "done"

        # Test throughput
        operations = 10
        start = time.time()

        async def batch_operation():
            await asyncio.sleep(0.1)
            return operations

        result = await AsyncAssertions.assert_performance(
            batch_operation(), min_throughput=50, operations=operations  # 50 ops/sec
        )

        # Should fail on slow operation
        with pytest.raises(AssertionError, match="exceeding max"):
            await AsyncAssertions.assert_performance(asyncio.sleep(0.1), max_time=0.01)
