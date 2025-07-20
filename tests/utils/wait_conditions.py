"""Helper utilities for replacing fixed sleep calls with proper synchronization.

This module provides utilities to replace arbitrary sleep() calls in tests with
condition-based waiting, making tests faster and more reliable.
"""

import asyncio
import socket
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Union

import aiohttp
import requests


async def wait_for_condition(
    condition: Callable[[], Union[bool, Any]],
    timeout: float = 10.0,
    interval: float = 0.1,
    error_message: Optional[str] = None,
) -> Any:
    """Wait for a condition to become true.

    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        error_message: Custom error message if timeout occurs

    Returns:
        The return value of the condition function

    Raises:
        TimeoutError: If condition is not met within timeout

    Example:
        # Wait for a service to be ready
        await wait_for_condition(
            lambda: service.is_ready(),
            timeout=5,
            error_message="Service failed to start"
        )
    """
    start_time = time.time()
    last_exception = None

    while (time.time() - start_time) < timeout:
        try:
            result = condition()
            if result:
                return result
        except Exception as e:
            last_exception = e

        await asyncio.sleep(interval)

    # Timeout occurred
    if error_message:
        msg = error_message
    else:
        msg = f"Condition not met after {timeout} seconds"

    if last_exception:
        msg += f" (last error: {last_exception})"

    raise TimeoutError(msg)


def wait_for_condition_sync(
    condition: Callable[[], Union[bool, Any]],
    timeout: float = 10.0,
    interval: float = 0.1,
    error_message: Optional[str] = None,
) -> Any:
    """Synchronous version of wait_for_condition.

    Use this for non-async test functions.
    """
    start_time = time.time()
    last_exception = None

    while (time.time() - start_time) < timeout:
        try:
            result = condition()
            if result:
                return result
        except Exception as e:
            last_exception = e

        time.sleep(interval)

    # Timeout occurred
    if error_message:
        msg = error_message
    else:
        msg = f"Condition not met after {timeout} seconds"

    if last_exception:
        msg += f" (last error: {last_exception})"

    raise TimeoutError(msg)


async def wait_for_port(
    host: str = "localhost",
    port: int = 8080,
    timeout: float = 30.0,
    interval: float = 0.5,
) -> None:
    """Wait for a TCP port to be available.

    Args:
        host: Hostname to check
        port: Port number to check
        timeout: Maximum time to wait
        interval: Time between checks

    Example:
        # Wait for a service to start listening
        await wait_for_port("localhost", 5432, timeout=60)
    """

    async def check_port():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex((host, port))
            return result == 0
        finally:
            sock.close()

    await wait_for_condition(
        check_port,
        timeout=timeout,
        interval=interval,
        error_message=f"Port {host}:{port} not available",
    )


async def wait_for_http_health(
    url: str, timeout: float = 30.0, interval: float = 0.5, expected_status: int = 200
) -> None:
    """Wait for an HTTP health endpoint to return expected status.

    Args:
        url: Health check URL
        timeout: Maximum time to wait
        interval: Time between checks
        expected_status: Expected HTTP status code

    Example:
        # Wait for API to be healthy
        await wait_for_http_health("http://localhost:8080/health")
    """

    async def check_health():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=2) as response:
                    return response.status == expected_status
        except:
            return False

    await wait_for_condition(
        check_health,
        timeout=timeout,
        interval=interval,
        error_message=f"Health check failed for {url}",
    )


def wait_for_http_health_sync(
    url: str, timeout: float = 30.0, interval: float = 0.5, expected_status: int = 200
) -> None:
    """Synchronous version of wait_for_http_health."""

    def check_health():
        try:
            response = requests.get(url, timeout=2)
            return response.status_code == expected_status
        except:
            return False

    wait_for_condition_sync(
        check_health,
        timeout=timeout,
        interval=interval,
        error_message=f"Health check failed for {url}",
    )


async def wait_for_container_health(
    container, timeout: float = 30.0, interval: float = 0.5
) -> None:
    """Wait for a Docker container to be healthy.

    Args:
        container: Docker container object
        timeout: Maximum time to wait
        interval: Time between checks

    Example:
        # Wait for container to be healthy
        container = docker_client.containers.run("postgres:13", detach=True)
        await wait_for_container_health(container)
    """

    async def check_container():
        container.reload()
        status = container.attrs.get("State", {}).get("Health", {}).get("Status")
        return status == "healthy"

    await wait_for_condition(
        check_container,
        timeout=timeout,
        interval=interval,
        error_message=f"Container {container.name} failed health check",
    )


class EventWaiter:
    """Helper for event-based synchronization in tests.

    Example:
        waiter = EventWaiter()

        # Pass callback to async operation
        start_async_task(on_complete=waiter.set)

        # Wait for completion
        await waiter.wait(timeout=5)
    """

    def __init__(self):
        self.event = asyncio.Event()
        self.result = None
        self.error = None

    def set(self, result=None, error=None):
        """Signal that the event has occurred."""
        self.result = result
        self.error = error
        self.event.set()

    async def wait(self, timeout: float = 10.0):
        """Wait for the event to be set."""
        await asyncio.wait_for(self.event.wait(), timeout=timeout)

        if self.error:
            raise self.error

        return self.result

    def reset(self):
        """Reset the waiter for reuse."""
        self.event.clear()
        self.result = None
        self.error = None


class CacheTestHelper:
    """Helper for testing cache expiration without long waits.

    Example:
        cache_helper = CacheTestHelper(cache_node)

        # Set with short TTL
        await cache_helper.set_with_short_ttl("key", "value", ttl=0.1)

        # Wait for expiration
        await cache_helper.wait_for_expiration("key")
    """

    def __init__(self, cache_node):
        self.cache = cache_node

    async def set_with_short_ttl(self, key: str, value: Any, ttl: float = 0.1):
        """Set a cache value with a short TTL for testing."""
        await self.cache.set(key, value, ttl=ttl)

    async def wait_for_expiration(self, key: str, timeout: float = 1.0):
        """Wait for a cache key to expire."""
        await wait_for_condition(
            lambda: self.cache.get(key) is None,
            timeout=timeout,
            interval=0.05,
            error_message=f"Cache key '{key}' did not expire",
        )


def replace_sleep_with_condition(test_func):
    """Decorator to help identify tests that need sleep replacement.

    This decorator can be used to mark tests that have been updated
    to use proper synchronization instead of sleep calls.

    Example:
        @replace_sleep_with_condition
        async def test_service_startup():
            # Old way:
            # service.start()
            # time.sleep(3)

            # New way:
            service.start()
            await wait_for_http_health("http://localhost:8080/health")
    """
    test_func._uses_proper_sync = True
    return test_func


# Example usage patterns for common scenarios:


async def wait_for_workflow_completion(runtime, workflow_id, timeout=30):
    """Wait for a workflow to complete execution."""
    await wait_for_condition(
        lambda: runtime.get_status(workflow_id) in ["completed", "failed"],
        timeout=timeout,
        error_message=f"Workflow {workflow_id} did not complete",
    )


async def wait_for_database_ready(connection_params, timeout=60):
    """Wait for database to be ready for connections."""
    import asyncpg

    async def try_connect():
        try:
            conn = await asyncpg.connect(**connection_params)
            await conn.close()
            return True
        except:
            return False

    await wait_for_condition(
        try_connect,
        timeout=timeout,
        interval=1.0,
        error_message="Database connection failed",
    )


async def wait_for_queue_empty(queue, timeout=10):
    """Wait for a queue to be empty."""
    await wait_for_condition(
        lambda: queue.empty(),
        timeout=timeout,
        interval=0.1,
        error_message="Queue did not empty in time",
    )


async def wait_for_metric_threshold(
    metrics_collector,
    metric_name: str,
    threshold: float,
    comparison: str = ">=",
    timeout: float = 10,
):
    """Wait for a metric to reach a threshold.

    Args:
        metrics_collector: Object that provides get_metric() method
        metric_name: Name of the metric to check
        threshold: Threshold value
        comparison: Comparison operator (>=, >, <=, <, ==)
        timeout: Maximum time to wait
    """
    comparisons = {
        ">=": lambda a, b: a >= b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a == b,
    }

    compare_func = comparisons.get(comparison)
    if not compare_func:
        raise ValueError(f"Invalid comparison operator: {comparison}")

    await wait_for_condition(
        lambda: compare_func(metrics_collector.get_metric(metric_name), threshold),
        timeout=timeout,
        error_message=f"Metric {metric_name} did not reach {comparison} {threshold}",
    )
