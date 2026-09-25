"""Resource management utilities for the Kailash SDK.

This module provides context managers and utilities for efficient resource
management across the SDK, ensuring proper cleanup and preventing memory leaks.
"""

import asyncio
import inspect
import logging
import threading
import weakref
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import Any, Callable, Dict, Generic, Optional, Set, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def _await_cleanup(awaitable):
    """Finish cleanup despite repeated caller cancellation, then propagate it."""
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    while not task.done():
        completed = asyncio.get_running_loop().create_future()

        def finished(_task, completed=completed):
            if not completed.done():
                completed.set_result(None)

        task.add_done_callback(finished)
        try:
            # Cancellation affects only this completion notification, never the
            # resource cleanup task. Its exception is retrieved exactly once.
            await completed
        except asyncio.CancelledError:
            cancelled = True
        finally:
            task.remove_done_callback(finished)
    try:
        result = task.result()
    except Exception as exc:
        if cancelled:
            logger.error("Error cleaning up cancelled resource: %s", exc)
            raise asyncio.CancelledError from exc
        raise
    if cancelled:
        raise asyncio.CancelledError
    return result


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
        self._in_use: Dict[int, T] = {}
        self._retired: Set[int] = set()
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

                self._in_use[id(resource)] = resource

            yield resource

        finally:
            if resource is not None:
                with self._lock:
                    self._in_use.pop(id(resource), None)
                    if id(resource) in self._retired:
                        self._retired.discard(id(resource))
                        self._dispose(resource)
                    else:
                        self._pool.append(resource)
            self._semaphore.release()

    def _dispose(self, resource):
        try:
            if self._cleanup:
                self._cleanup(resource)
        except Exception as exc:
            logger.error("Error cleaning up resource: %s", exc)
        finally:
            self._created_count -= 1

    def cleanup_all(self):
        """Close idle resources and retire active leases when returned."""
        with self._lock:
            self._retired.update(self._in_use)
            for resource in self._pool:
                self._dispose(resource)
            self._pool.clear()


class _AsyncPoolState:
    """Resources belonging to one event loop; guarded by the pool mutex."""

    def __init__(self):
        self.idle = []
        self.borrowed = {}
        self.retired = set()
        self.generation = 0
        self.creating = 0


class AsyncResourcePool(Generic[T]):
    """Reuse async resources only on their owning loop, with one aggregate cap.

    Owners must await ``cleanup_all()`` before closing their event loop. Cleanup
    affects that loop only; borrowed resources remain usable until lease return.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = 10,
        timeout: float = 30.0,
        cleanup: Optional[Callable[[T], Any]] = None,
    ):
        """Initialize a pool with a maximum resource count across all loops."""
        if max_size < 1:
            raise ValueError("max_size must be positive")
        self._factory = factory
        self._max_size = max_size
        self._timeout = timeout
        self._cleanup = cleanup
        self._states = {}
        self._mutex = threading.Lock()
        self._waiters = set()
        self._created_count = 0

    def _state(self, loop):
        return self._states.setdefault(loop, _AsyncPoolState())

    def _prune(self, loop, state):
        if not state.idle and not state.borrowed and not state.creating:
            if self._states.get(loop) is state:
                del self._states[loop]

    @property
    def _pool(self):
        with self._mutex:
            return self._state(asyncio.get_running_loop()).idle

    @property
    def _in_use(self):
        with self._mutex:
            return self._state(asyncio.get_running_loop()).borrowed

    @staticmethod
    def _wake(waiter):
        if not waiter.done():
            waiter.set_result(None)

    def _notify(self):
        # Called under the mutex. Futures belong to their respective loops.
        for waiter in self._waiters:
            loop = waiter.get_loop()
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(self._wake, waiter)
                except RuntimeError:
                    logger.debug("Resource waiter loop closed during notification")

    async def _dispose(self, resource):
        try:
            if self._cleanup:
                result = self._cleanup(resource)
                if inspect.isawaitable(result):
                    await _await_cleanup(result)
        except Exception as exc:
            logger.error("Error cleaning up resource: %s", exc)
        finally:
            with self._mutex:
                self._created_count -= 1
                self._notify()

    @asynccontextmanager
    async def acquire(self):
        """Acquire on the current loop, timing out if aggregate capacity is full."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        while True:
            with self._mutex:
                state = self._state(loop)
                generation = state.generation
                if state.idle:
                    resource = state.idle.pop()
                    state.borrowed[id(resource)] = resource
                    create = False
                    break
                if self._created_count < self._max_size:
                    self._created_count += 1
                    state.creating += 1
                    create = True
                    break
                waiter = loop.create_future()
                self._waiters.add(waiter)
            try:
                await asyncio.wait_for(waiter, max(0, deadline - loop.time()))
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Failed to acquire resource within {self._timeout}s"
                ) from None
            finally:
                with self._mutex:
                    self._waiters.discard(waiter)
                    self._prune(loop, state)
        if create:
            try:
                resource = self._factory()
                if inspect.isawaitable(resource):
                    resource = await resource
            except BaseException:
                with self._mutex:
                    self._created_count -= 1
                    state.creating -= 1
                    self._prune(loop, state)
                    self._notify()
                raise
            with self._mutex:
                state.creating -= 1
                state.borrowed[id(resource)] = resource
                if state.generation != generation:
                    state.retired.add(id(resource))
        try:
            yield resource
        finally:
            with self._mutex:
                state.borrowed.pop(id(resource), None)
                retire = id(resource) in state.retired
                state.retired.discard(id(resource))
                if not retire:
                    state.idle.append(resource)
                self._notify()
            if retire:
                try:
                    await self._dispose(resource)
                finally:
                    with self._mutex:
                        self._prune(loop, state)

    async def cleanup_all(self):
        """Close current-loop idle resources; retire its outstanding leases.

        Resources borrowed by another caller are closed when returned, never
        while that caller is using them. Other event loops are untouched.
        """
        loop = asyncio.get_running_loop()
        with self._mutex:
            state = self._states.get(loop)
            if state is None:
                return
            state.generation += 1
            state.retired.update(state.borrowed)
            idle, state.idle = state.idle, []
        try:
            if idle:
                closing = asyncio.gather(
                    *(self._dispose(resource) for resource in idle)
                )
                await _await_cleanup(closing)
        finally:
            with self._mutex:
                self._prune(loop, state)


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
                result = cleanup(resource)
                if inspect.isawaitable(result):
                    await _await_cleanup(result)
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
