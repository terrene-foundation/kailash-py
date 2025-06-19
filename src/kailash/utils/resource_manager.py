"""Resource management utilities for the Kailash SDK.

This module provides context managers and utilities for efficient resource
management across the SDK, ensuring proper cleanup and preventing memory leaks.
"""

import asyncio
import logging
import threading
import weakref
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import Any, Callable, Dict, Generic, Optional, Set, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ResourcePool(Generic[T]):
    """Generic resource pool for connection pooling and resource reuse.

    This class provides a thread-safe pool for managing expensive resources
    like database connections, HTTP clients, etc.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = 10,
        timeout: float = 30.0,
        cleanup: Optional[Callable[[T], None]] = None,
    ):
        """Initialize the resource pool.

        Args:
            factory: Function to create new resources
            max_size: Maximum pool size
            timeout: Timeout for acquiring resources
            cleanup: Optional cleanup function for resources
        """
        self._factory = factory
        self._max_size = max_size
        self._timeout = timeout
        self._cleanup = cleanup

        self._pool: list[T] = []
        self._in_use: Set[T] = set()
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_size)
        self._created_count = 0

    @contextmanager
    def acquire(self):
        """Acquire a resource from the pool.

        Yields:
            Resource instance

        Raises:
            TimeoutError: If resource cannot be acquired within timeout
        """
        if not self._semaphore.acquire(timeout=self._timeout):
            raise TimeoutError(f"Failed to acquire resource within {self._timeout}s")

        resource = None
        try:
            with self._lock:
                # Try to get from pool
                if self._pool:
                    resource = self._pool.pop()
                else:
                    # Create new resource if under limit
                    if self._created_count < self._max_size:
                        resource = self._factory()
                        self._created_count += 1
                    else:
                        raise RuntimeError("Pool exhausted")

                self._in_use.add(resource)

            yield resource

        finally:
            if resource is not None:
                with self._lock:
                    self._in_use.discard(resource)
                    self._pool.append(resource)
            self._semaphore.release()

    def cleanup_all(self):
        """Clean up all resources in the pool."""
        with self._lock:
            # Clean up pooled resources
            for resource in self._pool:
                if self._cleanup:
                    try:
                        self._cleanup(resource)
                    except Exception as e:
                        logger.error(f"Error cleaning up resource: {e}")

            # Clean up in-use resources (best effort)
            for resource in self._in_use:
                if self._cleanup:
                    try:
                        self._cleanup(resource)
                    except Exception as e:
                        logger.error(f"Error cleaning up in-use resource: {e}")

            self._pool.clear()
            self._in_use.clear()
            self._created_count = 0


class AsyncResourcePool(Generic[T]):
    """Async version of ResourcePool for async resources."""

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = 10,
        timeout: float = 30.0,
        cleanup: Optional[Callable[[T], Any]] = None,
    ):
        """Initialize the async resource pool.

        Args:
            factory: Async function to create new resources
            max_size: Maximum pool size
            timeout: Timeout for acquiring resources
            cleanup: Optional async cleanup function
        """
        self._factory = factory
        self._max_size = max_size
        self._timeout = timeout
        self._cleanup = cleanup

        self._pool: list[T] = []
        self._in_use: Set[T] = set()
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_size)
        self._created_count = 0

    @asynccontextmanager
    async def acquire(self):
        """Acquire a resource from the pool asynchronously.

        Yields:
            Resource instance

        Raises:
            TimeoutError: If resource cannot be acquired within timeout
        """
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self._timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Failed to acquire resource within {self._timeout}s")

        resource = None
        try:
            async with self._lock:
                # Try to get from pool
                if self._pool:
                    resource = self._pool.pop()
                else:
                    # Create new resource if under limit
                    if self._created_count < self._max_size:
                        if asyncio.iscoroutinefunction(self._factory):
                            resource = await self._factory()
                        else:
                            resource = self._factory()
                        self._created_count += 1
                    else:
                        raise RuntimeError("Pool exhausted")

                self._in_use.add(resource)

            yield resource

        finally:
            if resource is not None:
                async with self._lock:
                    self._in_use.discard(resource)
                    self._pool.append(resource)
            self._semaphore.release()

    async def cleanup_all(self):
        """Clean up all resources in the pool asynchronously."""
        async with self._lock:
            # Clean up pooled resources
            for resource in self._pool:
                if self._cleanup:
                    try:
                        if asyncio.iscoroutinefunction(self._cleanup):
                            await self._cleanup(resource)
                        else:
                            self._cleanup(resource)
                    except Exception as e:
                        logger.error(f"Error cleaning up resource: {e}")

            # Clean up in-use resources (best effort)
            for resource in self._in_use:
                if self._cleanup:
                    try:
                        if asyncio.iscoroutinefunction(self._cleanup):
                            await self._cleanup(resource)
                        else:
                            self._cleanup(resource)
                    except Exception as e:
                        logger.error(f"Error cleaning up in-use resource: {e}")

            self._pool.clear()
            self._in_use.clear()
            self._created_count = 0


class ResourceTracker:
    """Track and manage resources across the SDK to prevent leaks."""

    def __init__(self):
        self._resources: Dict[str, weakref.WeakSet] = defaultdict(weakref.WeakSet)
        self._metrics: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = threading.Lock()

    def register(self, resource_type: str, resource: Any):
        """Register a resource for tracking.

        Args:
            resource_type: Type/category of resource
            resource: Resource instance to track
        """
        with self._lock:
            self._resources[resource_type].add(resource)

            # Update metrics
            if resource_type not in self._metrics:
                self._metrics[resource_type] = {
                    "created": 0,
                    "active": 0,
                    "peak": 0,
                    "last_created": None,
                }

            self._metrics[resource_type]["created"] += 1
            self._metrics[resource_type]["active"] = len(self._resources[resource_type])
            self._metrics[resource_type]["peak"] = max(
                self._metrics[resource_type]["peak"],
                self._metrics[resource_type]["active"],
            )
            self._metrics[resource_type]["last_created"] = datetime.now(UTC)

    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get current resource metrics.

        Returns:
            Dictionary of metrics by resource type
        """
        with self._lock:
            # Update active counts
            for resource_type in self._metrics:
                self._metrics[resource_type]["active"] = len(
                    self._resources[resource_type]
                )

            return dict(self._metrics)

    def get_active_resources(
        self, resource_type: Optional[str] = None
    ) -> Dict[str, int]:
        """Get count of active resources.

        Args:
            resource_type: Optional filter by type

        Returns:
            Dictionary of resource type to active count
        """
        with self._lock:
            if resource_type:
                return {resource_type: len(self._resources.get(resource_type, set()))}
            else:
                return {
                    rtype: len(resources)
                    for rtype, resources in self._resources.items()
                }


# Global resource tracker instance
_resource_tracker = ResourceTracker()


def get_resource_tracker() -> ResourceTracker:
    """Get the global resource tracker instance."""
    return _resource_tracker


@contextmanager
def managed_resource(
    resource_type: str, resource: Any, cleanup: Optional[Callable] = None
):
    """Context manager for tracking and cleaning up resources.

    Args:
        resource_type: Type/category of resource
        resource: Resource instance
        cleanup: Optional cleanup function

    Yields:
        The resource instance
    """
    _resource_tracker.register(resource_type, resource)

    try:
        yield resource
    finally:
        if cleanup:
            try:
                cleanup(resource)
            except Exception as e:
                logger.error(f"Error cleaning up {resource_type}: {e}")


@asynccontextmanager
async def async_managed_resource(
    resource_type: str, resource: Any, cleanup: Optional[Callable] = None
):
    """Async context manager for tracking and cleaning up resources.

    Args:
        resource_type: Type/category of resource
        resource: Resource instance
        cleanup: Optional async cleanup function

    Yields:
        The resource instance
    """
    _resource_tracker.register(resource_type, resource)

    try:
        yield resource
    finally:
        if cleanup:
            try:
                if asyncio.iscoroutinefunction(cleanup):
                    await cleanup(resource)
                else:
                    cleanup(resource)
            except Exception as e:
                logger.error(f"Error cleaning up {resource_type}: {e}")


class ConcurrencyLimiter:
    """Limit concurrent operations to prevent resource exhaustion."""

    def __init__(self, max_concurrent: int = 10):
        """Initialize the concurrency limiter.

        Args:
            max_concurrent: Maximum concurrent operations
        """
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active = 0
        self._peak = 0
        self._lock = threading.Lock()

    @contextmanager
    def limit(self):
        """Context manager to limit concurrency."""
        self._semaphore.acquire()
        with self._lock:
            self._active += 1
            self._peak = max(self._peak, self._active)

        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
            self._semaphore.release()

    def get_stats(self) -> Dict[str, int]:
        """Get concurrency statistics."""
        with self._lock:
            return {"active": self._active, "peak": self._peak}


class AsyncConcurrencyLimiter:
    """Async version of ConcurrencyLimiter."""

    def __init__(self, max_concurrent: int = 10):
        """Initialize the async concurrency limiter.

        Args:
            max_concurrent: Maximum concurrent operations
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0
        self._peak = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def limit(self):
        """Async context manager to limit concurrency."""
        await self._semaphore.acquire()
        async with self._lock:
            self._active += 1
            self._peak = max(self._peak, self._active)

        try:
            yield
        finally:
            async with self._lock:
                self._active -= 1
            self._semaphore.release()

    async def get_stats(self) -> Dict[str, int]:
        """Get concurrency statistics."""
        async with self._lock:
            return {"active": self._active, "peak": self._peak}
