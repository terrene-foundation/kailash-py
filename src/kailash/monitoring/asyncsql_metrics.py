"""
Prometheus metrics integration for AsyncSQL lock contention monitoring.

This module provides easy-to-use Prometheus metrics for monitoring AsyncSQL
per-pool locking performance and contention patterns.
"""

import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

try:
    import prometheus_client

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class AsyncSQLMetrics:
    """Prometheus metrics collector for AsyncSQL lock contention monitoring."""

    def __init__(
        self,
        enabled: bool = True,
        registry: Optional[prometheus_client.CollectorRegistry] = None,
    ):
        """
        Initialize AsyncSQL metrics collector.

        Args:
            enabled: Whether to collect metrics (disabled if prometheus_client not available)
            registry: Custom Prometheus registry (uses default if None)
        """
        self.enabled = enabled and PROMETHEUS_AVAILABLE
        self.registry = registry or prometheus_client.REGISTRY

        if not self.enabled:
            return

        # Lock acquisition counter
        self.lock_acquisition_counter = prometheus_client.Counter(
            "asyncsql_lock_acquisitions_total",
            "Total number of AsyncSQL lock acquisitions",
            ["pool_key", "status"],  # status: success, timeout, error
            registry=self.registry,
        )

        # Lock wait time histogram
        self.lock_wait_time_histogram = prometheus_client.Histogram(
            "asyncsql_lock_wait_seconds",
            "Time spent waiting for AsyncSQL locks",
            ["pool_key"],
            buckets=(
                0.001,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.5,
                5.0,
                float("inf"),
            ),
            registry=self.registry,
        )

        # Active locks gauge
        self.active_locks_gauge = prometheus_client.Gauge(
            "asyncsql_active_locks",
            "Number of currently active AsyncSQL locks",
            ["pool_key"],
            registry=self.registry,
        )

        # Pool operations counter
        self.pool_operations_counter = prometheus_client.Counter(
            "asyncsql_pool_operations_total",
            "Total number of AsyncSQL pool operations",
            ["pool_key", "operation"],  # operation: create, cleanup, acquire, release
            registry=self.registry,
        )

        # Lock contention summary
        self.lock_contention_summary = prometheus_client.Summary(
            "asyncsql_lock_contention_seconds",
            "Summary of AsyncSQL lock contention patterns",
            ["pool_key"],
            registry=self.registry,
        )

    def record_lock_acquisition(
        self, pool_key: str, status: str, wait_time: float = 0.0
    ):
        """
        Record a lock acquisition event.

        Args:
            pool_key: The pool key for the lock
            status: 'success', 'timeout', or 'error'
            wait_time: Time spent waiting for the lock in seconds
        """
        if not self.enabled:
            return

        self.lock_acquisition_counter.labels(pool_key=pool_key, status=status).inc()

        if wait_time > 0:
            self.lock_wait_time_histogram.labels(pool_key=pool_key).observe(wait_time)
            self.lock_contention_summary.labels(pool_key=pool_key).observe(wait_time)

    def set_active_locks(self, pool_key: str, count: int):
        """
        Update the count of active locks for a pool.

        Args:
            pool_key: The pool key
            count: Number of active locks
        """
        if not self.enabled:
            return

        self.active_locks_gauge.labels(pool_key=pool_key).set(count)

    def record_pool_operation(self, pool_key: str, operation: str):
        """
        Record a pool operation event.

        Args:
            pool_key: The pool key
            operation: 'create', 'cleanup', 'acquire', 'release'
        """
        if not self.enabled:
            return

        self.pool_operations_counter.labels(
            pool_key=pool_key, operation=operation
        ).inc()

    @asynccontextmanager
    async def timed_lock_acquisition(self, pool_key: str):
        """
        Context manager to time lock acquisition and automatically record metrics.

        Usage:
            async with metrics.timed_lock_acquisition('my_pool_key'):
                # Lock acquisition logic here
                async with some_lock:
                    # Work while holding lock
                    pass
        """
        start_time = time.time()
        status = "error"

        try:
            yield
            status = "success"
        except Exception as e:
            if "timeout" in str(e).lower():
                status = "timeout"
            else:
                status = "error"
            raise
        finally:
            wait_time = time.time() - start_time
            self.record_lock_acquisition(pool_key, status, wait_time)


# Global metrics instance (can be overridden)
_global_metrics: Optional[AsyncSQLMetrics] = None


def get_global_metrics() -> Optional[AsyncSQLMetrics]:
    """Get the global AsyncSQL metrics instance."""
    global _global_metrics
    if _global_metrics is None and PROMETHEUS_AVAILABLE:
        _global_metrics = AsyncSQLMetrics()
    return _global_metrics


def set_global_metrics(metrics: Optional[AsyncSQLMetrics]):
    """Set the global AsyncSQL metrics instance."""
    global _global_metrics
    _global_metrics = metrics


def enable_metrics(
    registry: Optional[prometheus_client.CollectorRegistry] = None,
) -> AsyncSQLMetrics:
    """
    Enable global AsyncSQL metrics collection.

    Args:
        registry: Custom Prometheus registry (uses default if None)

    Returns:
        The configured metrics instance
    """
    metrics = AsyncSQLMetrics(enabled=True, registry=registry)
    set_global_metrics(metrics)
    return metrics


def disable_metrics():
    """Disable global AsyncSQL metrics collection."""
    set_global_metrics(None)


# Convenience functions for manual metric recording
def record_lock_acquisition(pool_key: str, status: str, wait_time: float = 0.0):
    """Record a lock acquisition event using global metrics."""
    metrics = get_global_metrics()
    if metrics:
        metrics.record_lock_acquisition(pool_key, status, wait_time)


def record_pool_operation(pool_key: str, operation: str):
    """Record a pool operation event using global metrics."""
    metrics = get_global_metrics()
    if metrics:
        metrics.record_pool_operation(pool_key, operation)


def set_active_locks(pool_key: str, count: int):
    """Update active locks count using global metrics."""
    metrics = get_global_metrics()
    if metrics:
        metrics.set_active_locks(pool_key, count)


# Integration example for AsyncSQLDatabaseNode
def integrate_with_async_sql():
    """
    Example of how to integrate metrics with AsyncSQLDatabaseNode.

    This would typically be called during AsyncSQL initialization or
    through a configuration setting.
    """
    if not PROMETHEUS_AVAILABLE:
        return None

    # Enable metrics
    metrics = enable_metrics()

    # Example: monkey-patch AsyncSQL methods to include metrics
    # (This is just an example - actual integration would be cleaner)
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    # Store original methods
    original_get_pool_creation_lock = AsyncSQLDatabaseNode._get_pool_creation_lock
    original_acquire_lock = AsyncSQLDatabaseNode._acquire_pool_lock_with_timeout

    @classmethod
    def instrumented_get_pool_creation_lock(cls, pool_key: str):
        """Instrumented version that records pool operations."""
        record_pool_operation(pool_key, "acquire")
        return original_get_pool_creation_lock(pool_key)

    @classmethod
    async def instrumented_acquire_lock(cls, pool_key: str, timeout: float = 5.0):
        """Instrumented version that records lock acquisitions."""
        async with metrics.timed_lock_acquisition(pool_key):
            async with original_acquire_lock(pool_key, timeout):
                yield

    # Apply instrumentation
    AsyncSQLDatabaseNode._get_pool_creation_lock = instrumented_get_pool_creation_lock
    AsyncSQLDatabaseNode._acquire_pool_lock_with_timeout = instrumented_acquire_lock

    return metrics


if __name__ == "__main__":
    # Example usage
    print("AsyncSQL Metrics Module")
    print(f"Prometheus available: {PROMETHEUS_AVAILABLE}")

    if PROMETHEUS_AVAILABLE:
        # Enable metrics
        metrics = enable_metrics()

        # Simulate some metrics
        metrics.record_lock_acquisition("test_pool_1", "success", 0.005)
        metrics.record_lock_acquisition("test_pool_1", "success", 0.003)
        metrics.record_lock_acquisition("test_pool_2", "timeout", 5.0)
        metrics.set_active_locks("test_pool_1", 2)
        metrics.record_pool_operation("test_pool_1", "create")

        print("Metrics recorded successfully")
        print("Access metrics at: http://localhost:8000/metrics")
        print("(Start prometheus_client HTTP server to view metrics)")

        # Start metrics server (for testing)
        # prometheus_client.start_http_server(8000)
    else:
        print(
            "Install prometheus_client to enable metrics: pip install prometheus_client"
        )
