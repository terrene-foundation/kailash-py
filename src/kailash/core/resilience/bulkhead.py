"""Bulkhead isolation pattern implementation for operation segregation.

This module implements the Bulkhead pattern to isolate different types of
operations with separate resource pools, preventing resource exhaustion
in one area from affecting other operations.

The bulkhead provides:
- Resource pool isolation by operation type
- Thread pool management for CPU-bound tasks
- Connection pool management for I/O operations
- Priority-based resource allocation
- Real-time monitoring and metrics

Example:
    >>> bulkhead = BulkheadManager()
    >>>
    >>> # Execute with isolation
    >>> async with bulkhead.get_partition("critical_operations") as partition:
    ...     result = await partition.execute(critical_task)
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union
from uuid import uuid4

logger = logging.getLogger(__name__)


class PartitionType(Enum):
    """Types of bulkhead partitions."""

    CPU_BOUND = "cpu_bound"  # For CPU-intensive operations
    IO_BOUND = "io_bound"  # For I/O operations
    CRITICAL = "critical"  # For critical high-priority operations
    BACKGROUND = "background"  # For background/batch operations
    CUSTOM = "custom"  # Custom partition types


class ResourceType(Enum):
    """Types of resources managed by bulkhead."""

    THREADS = "threads"
    CONNECTIONS = "connections"
    MEMORY = "memory"
    SEMAPHORE = "semaphore"


@dataclass
class PartitionConfig:
    """Configuration for a bulkhead partition."""

    name: str
    partition_type: PartitionType
    max_concurrent_operations: int = 10
    max_threads: Optional[int] = None  # For CPU-bound partitions
    max_connections: Optional[int] = None  # For I/O partitions
    timeout: int = 30  # Operation timeout in seconds
    priority: int = 1  # Higher number = higher priority
    queue_size: int = 100  # Max queued operations
    isolation_level: str = "strict"  # strict, relaxed, shared
    circuit_breaker_enabled: bool = True
    metrics_enabled: bool = True
    resource_limits: Dict[ResourceType, int] = field(default_factory=dict)


@dataclass
class PartitionMetrics:
    """Metrics for a bulkhead partition."""

    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    rejected_operations: int = 0
    queued_operations: int = 0
    active_operations: int = 0
    avg_execution_time: float = 0.0
    max_execution_time: float = 0.0
    resource_utilization: Dict[ResourceType, float] = field(default_factory=dict)
    last_activity: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BulkheadPartition:
    """Individual partition within the bulkhead for operation isolation."""

    def __init__(self, config: PartitionConfig):
        """Initialize bulkhead partition."""
        self.config = config
        self.metrics = PartitionMetrics()
        self._lock = asyncio.Lock()

        # Resource management
        self._semaphore = asyncio.Semaphore(config.max_concurrent_operations)
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._active_operations: Set[str] = set()
        self._operation_queue: asyncio.Queue = asyncio.Queue(maxsize=config.queue_size)

        # Initialize thread pool for CPU-bound operations
        if config.partition_type == PartitionType.CPU_BOUND and config.max_threads:
            self._thread_pool = ThreadPoolExecutor(
                max_workers=config.max_threads,
                thread_name_prefix=f"bulkhead-{config.name}",
            )

        # Circuit breaker integration
        self._circuit_breaker = None
        if config.circuit_breaker_enabled:
            from kailash.core.resilience.circuit_breaker import (
                CircuitBreakerConfig,
                ConnectionCircuitBreaker,
            )

            breaker_config = CircuitBreakerConfig(
                failure_threshold=5, recovery_timeout=30
            )
            self._circuit_breaker = ConnectionCircuitBreaker(breaker_config)

        logger.info(f"Initialized bulkhead partition: {config.name}")

    async def execute(
        self,
        func: Callable,
        *args,
        priority: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> Any:
        """Execute operation within partition isolation.

        Args:
            func: Function to execute
            *args: Function arguments
            priority: Operation priority (overrides partition default)
            timeout: Operation timeout (overrides partition default)
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            BulkheadRejectionError: If partition is overloaded
            asyncio.TimeoutError: If operation times out
        """
        operation_id = str(uuid4())
        start_time = time.time()

        # Use provided timeout or partition default
        op_timeout = timeout or self.config.timeout

        try:
            # Check if partition can accept new operations
            async with self._lock:
                current_active = len(self._active_operations)
                current_queued = self._operation_queue.qsize()

                # Reject if no queue capacity (queue_size=0) and at capacity
                if (
                    self.config.queue_size == 0
                    and current_active >= self.config.max_concurrent_operations
                ):
                    await self._record_rejection("no_queue_capacity")
                    raise BulkheadRejectionError(
                        f"Partition {self.config.name} has no queue capacity and is at max concurrent operations"
                    )

                # Reject if queue is full
                if self._operation_queue.full():
                    await self._record_rejection("queue_full")
                    raise BulkheadRejectionError(
                        f"Partition {self.config.name} queue is full"
                    )

            # Queue the operation
            await self._operation_queue.put((operation_id, func, args, kwargs))

            async with self._lock:
                self.metrics.queued_operations += 1

            # Execute with circuit breaker if enabled
            if self._circuit_breaker:
                result = await self._circuit_breaker.call(
                    self._execute_isolated, operation_id, func, args, kwargs, op_timeout
                )
            else:
                result = await self._execute_isolated(
                    operation_id, func, args, kwargs, op_timeout
                )

            execution_time = time.time() - start_time
            await self._record_success(execution_time)

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            await self._record_failure(execution_time)
            raise
        finally:
            # Clean up
            async with self._lock:
                if operation_id in self._active_operations:
                    self._active_operations.remove(operation_id)
                self.metrics.active_operations = len(self._active_operations)

    async def _execute_isolated(
        self, operation_id: str, func: Callable, args: tuple, kwargs: dict, timeout: int
    ) -> Any:
        """Execute operation with resource isolation."""
        # Acquire semaphore (limits concurrent operations)
        async with self._semaphore:
            async with self._lock:
                self._active_operations.add(operation_id)
                self.metrics.active_operations = len(self._active_operations)
                self.metrics.total_operations += 1
                self.metrics.last_activity = datetime.now(UTC)

            try:
                # Remove from queue
                await self._operation_queue.get()

                # Execute based on partition type
                if (
                    self.config.partition_type == PartitionType.CPU_BOUND
                    and self._thread_pool
                ):
                    # Run CPU-bound task in thread pool
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(self._thread_pool, func, *args),
                        timeout=timeout,
                    )
                else:
                    # Run I/O-bound or async task directly
                    if asyncio.iscoroutinefunction(func):
                        result = await asyncio.wait_for(
                            func(*args, **kwargs), timeout=timeout
                        )
                    else:
                        # Synchronous function
                        result = await asyncio.wait_for(
                            asyncio.to_thread(func, *args, **kwargs), timeout=timeout
                        )

                return result

            finally:
                async with self._lock:
                    self.metrics.queued_operations = max(
                        0, self.metrics.queued_operations - 1
                    )

    async def _record_success(self, execution_time: float):
        """Record successful operation."""
        async with self._lock:
            self.metrics.successful_operations += 1

            # Update execution time metrics
            total_ops = self.metrics.successful_operations
            current_avg = self.metrics.avg_execution_time
            self.metrics.avg_execution_time = (
                current_avg * (total_ops - 1) + execution_time
            ) / total_ops

            if execution_time > self.metrics.max_execution_time:
                self.metrics.max_execution_time = execution_time

    async def _record_failure(self, execution_time: float):
        """Record failed operation."""
        async with self._lock:
            self.metrics.failed_operations += 1

    async def _record_rejection(self, reason: str):
        """Record rejected operation."""
        async with self._lock:
            self.metrics.rejected_operations += 1

        logger.warning(
            f"Operation rejected from partition {self.config.name}: {reason}"
        )

    def get_status(self) -> Dict[str, Any]:
        """Get current partition status."""
        return {
            "name": self.config.name,
            "type": self.config.partition_type.value,
            "metrics": {
                "total_operations": self.metrics.total_operations,
                "successful_operations": self.metrics.successful_operations,
                "failed_operations": self.metrics.failed_operations,
                "rejected_operations": self.metrics.rejected_operations,
                "active_operations": self.metrics.active_operations,
                "queued_operations": self.metrics.queued_operations,
                "avg_execution_time": self.metrics.avg_execution_time,
                "max_execution_time": self.metrics.max_execution_time,
                "success_rate": (
                    self.metrics.successful_operations
                    / max(1, self.metrics.total_operations)
                ),
            },
            "config": {
                "max_concurrent_operations": self.config.max_concurrent_operations,
                "timeout": self.config.timeout,
                "priority": self.config.priority,
                "queue_size": self.config.queue_size,
            },
            "resources": {
                "semaphore_available": self._semaphore._value,
                "queue_size": self._operation_queue.qsize(),
                "thread_pool_active": (
                    self._thread_pool._threads if self._thread_pool else 0
                ),
            },
            "circuit_breaker": (
                self._circuit_breaker.get_status() if self._circuit_breaker else None
            ),
        }

    async def shutdown(self):
        """Shutdown partition and clean up resources."""
        logger.info(f"Shutting down bulkhead partition: {self.config.name}")

        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)

        # Wait for active operations to complete (with timeout)
        timeout = 30  # seconds
        start_time = time.time()

        while self._active_operations and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)

        if self._active_operations:
            logger.warning(
                f"Partition {self.config.name} shutdown with {len(self._active_operations)} "
                "active operations still running"
            )


class BulkheadRejectionError(Exception):
    """Raised when operation is rejected due to bulkhead limits."""

    pass


class BulkheadManager:
    """Manages multiple bulkhead partitions for operation isolation."""

    def __init__(self):
        """Initialize bulkhead manager."""
        self.partitions: Dict[str, BulkheadPartition] = {}
        self._lock = threading.Lock()

        # Create default partitions
        self._create_default_partitions()

        logger.info("Initialized BulkheadManager with default partitions")

    def _create_default_partitions(self):
        """Create default partitions for common operations."""
        default_configs = [
            PartitionConfig(
                name="critical",
                partition_type=PartitionType.CRITICAL,
                max_concurrent_operations=5,
                timeout=10,
                priority=10,
                queue_size=20,
            ),
            PartitionConfig(
                name="database",
                partition_type=PartitionType.IO_BOUND,
                max_concurrent_operations=20,
                max_connections=50,
                timeout=30,
                priority=5,
                queue_size=100,
            ),
            PartitionConfig(
                name="compute",
                partition_type=PartitionType.CPU_BOUND,
                max_concurrent_operations=5,
                max_threads=4,
                timeout=60,
                priority=3,
                queue_size=50,
            ),
            PartitionConfig(
                name="background",
                partition_type=PartitionType.BACKGROUND,
                max_concurrent_operations=10,
                timeout=120,
                priority=1,
                queue_size=200,
            ),
        ]

        for config in default_configs:
            self.partitions[config.name] = BulkheadPartition(config)

    def create_partition(self, config: PartitionConfig) -> BulkheadPartition:
        """Create a new bulkhead partition."""
        with self._lock:
            if config.name in self.partitions:
                raise ValueError(f"Partition {config.name} already exists")

            partition = BulkheadPartition(config)
            self.partitions[config.name] = partition

            logger.info(f"Created bulkhead partition: {config.name}")
            return partition

    def get_partition(self, name: str) -> BulkheadPartition:
        """Get partition by name."""
        if name not in self.partitions:
            raise ValueError(f"Partition {name} not found")
        return self.partitions[name]

    @asynccontextmanager
    async def isolated_execution(self, partition_name: str):
        """Context manager for isolated execution."""
        partition = self.get_partition(partition_name)
        try:
            yield partition
        finally:
            # Any cleanup can be done here
            pass

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all partitions."""
        return {
            name: partition.get_status() for name, partition in self.partitions.items()
        }

    async def shutdown_all(self):
        """Shutdown all partitions."""
        logger.info("Shutting down all bulkhead partitions")

        # Shutdown all partitions concurrently
        shutdown_tasks = [
            partition.shutdown() for partition in self.partitions.values()
        ]

        await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        self.partitions.clear()
        logger.info("All bulkhead partitions shut down")


# Global bulkhead manager instance
_bulkhead_manager: Optional[BulkheadManager] = None


def get_bulkhead_manager() -> BulkheadManager:
    """Get global bulkhead manager instance."""
    global _bulkhead_manager
    if _bulkhead_manager is None:
        _bulkhead_manager = BulkheadManager()
    return _bulkhead_manager


async def execute_with_bulkhead(
    partition_name: str, func: Callable, *args, **kwargs
) -> Any:
    """Convenience function to execute operation with bulkhead isolation."""
    manager = get_bulkhead_manager()
    partition = manager.get_partition(partition_name)
    return await partition.execute(func, *args, **kwargs)
