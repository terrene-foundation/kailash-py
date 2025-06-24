"""Async testing utilities."""

import asyncio
import functools
import time
from contextlib import asynccontextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from kailash.runtime.async_local import AsyncLocalRuntime
    from kailash.workflow import Workflow

T = TypeVar("T")


class AsyncTestUtils:
    """Utilities for async testing."""

    @staticmethod
    async def wait_for_condition(
        condition: Callable[[], Union[bool, Coroutine[Any, Any, bool]]],
        timeout: float = 5.0,
        interval: float = 0.1,
        message: str = "Condition not met",
    ):
        """Wait for a condition to become true."""
        start = time.time()
        while time.time() - start < timeout:
            # Evaluate condition
            if asyncio.iscoroutinefunction(condition):
                result = await condition()
            else:
                result = condition()

            if result:
                return

            await asyncio.sleep(interval)

        raise TimeoutError(f"{message} after {timeout}s")

    @staticmethod
    async def assert_completes_within(
        coro: Coroutine, seconds: float, message: str = None
    ) -> T:
        """Assert that a coroutine completes within time limit."""
        try:
            return await asyncio.wait_for(coro, timeout=seconds)
        except asyncio.TimeoutError:
            msg = message or f"Coroutine did not complete within {seconds}s"
            raise AssertionError(msg)

    @staticmethod
    async def assert_raises_async(
        exception_type: Type[Exception],
        coro: Union[Coroutine, Callable],
        *args,
        **kwargs,
    ):
        """Assert that a coroutine raises specific exception."""
        try:
            if asyncio.iscoroutine(coro):
                await coro
            else:
                await coro(*args, **kwargs)

            raise AssertionError(
                f"Expected {exception_type.__name__} but no exception was raised"
            )
        except exception_type as e:
            return e  # Return exception for further assertions
        except Exception as e:
            raise AssertionError(
                f"Expected {exception_type.__name__} but got "
                f"{type(e).__name__}: {e}"
            )

    @staticmethod
    @asynccontextmanager
    async def assert_duration(min_seconds: float = None, max_seconds: float = None):
        """Context manager to assert execution duration."""
        start = asyncio.get_event_loop().time()
        yield
        duration = asyncio.get_event_loop().time() - start

        if min_seconds is not None and duration < min_seconds:
            raise AssertionError(
                f"Operation completed too quickly: {duration:.3f}s < {min_seconds}s"
            )

        if max_seconds is not None and duration > max_seconds:
            raise AssertionError(
                f"Operation took too long: {duration:.3f}s > {max_seconds}s"
            )

    @staticmethod
    async def run_concurrent(
        *coroutines: Coroutine, return_exceptions: bool = False
    ) -> List[Any]:
        """Run multiple coroutines concurrently."""
        return await asyncio.gather(*coroutines, return_exceptions=return_exceptions)

    @staticmethod
    async def run_sequential(*coroutines: Coroutine) -> List[Any]:
        """Run multiple coroutines sequentially."""
        results = []
        for coro in coroutines:
            result = await coro
            results.append(result)
        return results

    @staticmethod
    def async_retry(
        max_attempts: int = 3,
        delay: float = 0.1,
        backoff: float = 2.0,
        exceptions: tuple = (Exception,),
    ):
        """Decorator to retry async functions."""

        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay

                for attempt in range(max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff

                raise last_exception

            return wrapper

        return decorator


class AsyncAssertions:
    """Async-aware assertions for testing."""

    @staticmethod
    async def assert_eventually_equals(
        getter: Callable[[], Union[Any, Coroutine[Any, Any, Any]]],
        expected: Any,
        timeout: float = 5.0,
        interval: float = 0.1,
        message: str = None,
    ):
        """Assert that a value eventually equals expected."""

        async def condition():
            if asyncio.iscoroutinefunction(getter):
                value = await getter()
            else:
                value = getter()
            return value == expected

        await AsyncTestUtils.wait_for_condition(
            condition,
            timeout=timeout,
            interval=interval,
            message=message or f"Value did not equal {expected}",
        )

    @staticmethod
    async def assert_eventually_true(
        condition: Callable[[], Union[bool, Coroutine[Any, Any, bool]]],
        timeout: float = 5.0,
        message: str = None,
    ):
        """Assert that a condition eventually becomes true."""
        await AsyncTestUtils.wait_for_condition(
            condition,
            timeout=timeout,
            message=message or "Condition did not become true",
        )

    @staticmethod
    async def assert_converges(
        getter: Callable[[], Union[float, Coroutine[Any, Any, float]]],
        tolerance: float = 0.01,
        timeout: float = 10.0,
        samples: int = 5,
    ):
        """Assert that a value converges to a stable state."""
        values = []
        sample_interval = timeout / (samples + 1)

        for _ in range(samples):
            if asyncio.iscoroutinefunction(getter):
                value = await getter()
            else:
                value = getter()
            values.append(value)
            await asyncio.sleep(sample_interval)

        # Check if values converged
        if len(values) < 2:
            return

        max_diff = max(abs(values[i] - values[i - 1]) for i in range(1, len(values)))
        assert max_diff <= tolerance, (
            f"Values did not converge within tolerance {tolerance}\n"
            f"Values: {values}\n"
            f"Max difference: {max_diff}"
        )

    @staticmethod
    async def assert_workflow_succeeds(
        workflow: "Workflow",
        inputs: Dict[str, Any],
        runtime: "AsyncLocalRuntime",
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Assert workflow executes successfully."""
        from ..runtime.async_local import AsyncLocalRuntime

        result = await AsyncTestUtils.assert_completes_within(
            runtime.execute_workflow_async(workflow, inputs),
            timeout,
            f"Workflow did not complete within {timeout}s",
        )

        if hasattr(result, "errors") and result.errors:
            raise AssertionError(
                "Workflow failed with errors:\n"
                + "\n".join(f"  {node}: {error}" for node, error in result.errors)
            )

        return result

    @staticmethod
    async def assert_concurrent_safe(
        func: Callable, *args, concurrency: int = 10, **kwargs
    ):
        """Assert function is safe for concurrent execution."""
        # Run function multiple times concurrently
        tasks = []
        for _ in range(concurrency):
            if asyncio.iscoroutinefunction(func):
                tasks.append(func(*args, **kwargs))
            else:
                tasks.append(
                    asyncio.get_event_loop().run_in_executor(
                        None, func, *args, **kwargs
                    )
                )

        # All should complete without error
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert (
            not exceptions
        ), f"Concurrent execution failed with {len(exceptions)} errors:\n" + "\n".join(
            str(e) for e in exceptions
        )

    @staticmethod
    async def assert_performance(
        coro: Coroutine,
        max_time: float = None,
        min_throughput: float = None,
        operations: int = 1,
    ) -> Any:
        """Assert performance requirements are met."""
        start = asyncio.get_event_loop().time()
        result = await coro
        duration = asyncio.get_event_loop().time() - start

        if max_time is not None:
            assert (
                duration <= max_time
            ), f"Operation took {duration:.3f}s, exceeding max {max_time}s"

        if min_throughput is not None:
            throughput = operations / duration
            assert (
                throughput >= min_throughput
            ), f"Throughput {throughput:.1f} ops/s below minimum {min_throughput} ops/s"

        return result

    @staticmethod
    async def assert_memory_stable(
        func: Callable,
        *args,
        iterations: int = 100,
        growth_tolerance: float = 0.1,
        **kwargs,
    ):
        """Assert that repeated execution doesn't leak memory."""
        import gc
        import os

        import psutil

        process = psutil.Process(os.getpid())

        # Warm up and measure baseline
        for _ in range(10):
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)

        gc.collect()
        await asyncio.sleep(0.1)
        baseline_memory = process.memory_info().rss

        # Run iterations
        for _ in range(iterations):
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)

        gc.collect()
        await asyncio.sleep(0.1)
        final_memory = process.memory_info().rss

        # Check growth
        growth = (final_memory - baseline_memory) / baseline_memory
        assert growth <= growth_tolerance, (
            f"Memory grew by {growth:.1%}, exceeding tolerance of {growth_tolerance:.1%}\n"
            f"Baseline: {baseline_memory / 1024 / 1024:.1f}MB\n"
            f"Final: {final_memory / 1024 / 1024:.1f}MB"
        )
