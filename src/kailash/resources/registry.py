"""
Resource Registry - Central management for shared resources in Kailash workflows.

This registry solves the JSON serialization problem by allowing workflows to
reference resources by name rather than passing the actual objects.
"""

import asyncio
import logging
import time
import weakref
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Set

from .factory import ResourceFactory
from .health import HealthCheck, HealthStatus

logger = logging.getLogger(__name__)


class ResourceNotFoundError(Exception):
    """Raised when a requested resource is not found in the registry."""

    pass


class ResourceRegistry:
    """
    Central registry for shared resources in Kailash workflows.

    This registry provides:
    - Lazy initialization of resources
    - Health checking and automatic recovery
    - Resource lifecycle management
    - Thread-safe access with async locks
    - Metrics collection for monitoring

    Example:
        ```python
        # Create registry
        registry = ResourceRegistry()

        # Register a database factory
        registry.register_factory(
            'main_db',
            DatabasePoolFactory(host='localhost', database='myapp'),
            health_check=lambda pool: pool.ping()
        )

        # Get resource in workflow
        db = await registry.get_resource('main_db')
        ```
    """

    def __init__(self, enable_metrics: bool = True):
        """
        Initialize the resource registry.

        Args:
            enable_metrics: Whether to collect usage metrics
        """
        self._resources: Dict[str, Any] = {}
        self._factories: Dict[str, ResourceFactory] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._health_checks: Dict[str, HealthCheck] = {}
        self._cleanup_handlers: Dict[str, Callable] = {}
        self._resource_metadata: Dict[str, Dict[str, Any]] = {}
        self._global_lock = asyncio.Lock()
        self._enable_metrics = enable_metrics

        # Metrics tracking
        self._metrics = {
            "resource_creations": {},
            "resource_accesses": {},
            "health_check_failures": {},
            "resource_recreations": {},
        }

        # Circuit breaker state
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}

        # Weak references for garbage collection
        self._weak_refs: Dict[str, weakref.ref] = {}

    def register_factory(
        self,
        name: str,
        factory: ResourceFactory,
        health_check: Optional[HealthCheck] = None,
        cleanup_handler: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a resource factory with optional health check.

        Args:
            name: Unique name for the resource
            factory: Factory that creates the resource
            health_check: Optional health check callable
            cleanup_handler: Optional cleanup callable
            metadata: Optional metadata about the resource
        """
        if name in self._factories:
            logger.warning(f"Overwriting existing factory for resource: {name}")

        self._factories[name] = factory
        self._locks[name] = asyncio.Lock()

        if health_check:
            self._health_checks[name] = health_check

        if cleanup_handler:
            self._cleanup_handlers[name] = cleanup_handler

        if metadata:
            self._resource_metadata[name] = metadata

        # Initialize circuit breaker
        self._circuit_breakers[name] = {
            "failures": 0,
            "last_failure": None,
            "state": "closed",  # closed, open, half-open
            "threshold": (
                metadata.get("circuit_breaker_threshold", 5) if metadata else 5
            ),
        }

        logger.info(f"Registered factory for resource: {name}")

    async def get_resource(self, name: str) -> Any:
        """
        Get or create a resource by name.

        This method:
        1. Checks if resource exists and is healthy
        2. Creates the resource if needed
        3. Implements circuit breaker pattern
        4. Tracks metrics

        Args:
            name: Name of the resource

        Returns:
            The requested resource

        Raises:
            ResourceNotFoundError: If no factory is registered
            Exception: If resource creation fails
        """
        # Check circuit breaker
        if self._is_circuit_open(name):
            raise ResourceNotFoundError(f"Circuit breaker open for resource: {name}")

        async with self._locks.get(name, self._global_lock):
            try:
                # Track access
                if self._enable_metrics:
                    self._track_access(name)

                # Check if resource exists and is healthy
                if name in self._resources:
                    if await self._is_healthy(name):
                        self._reset_circuit_breaker(name)
                        return self._resources[name]
                    else:
                        # Recreate unhealthy resource
                        logger.warning(f"Resource {name} is unhealthy, recreating")
                        await self._cleanup_resource(name)
                        if self._enable_metrics:
                            self._metrics["resource_recreations"][name] = (
                                self._metrics["resource_recreations"].get(name, 0) + 1
                            )

                # Create resource
                if name not in self._factories:
                    raise ResourceNotFoundError(
                        f"No factory registered for resource: {name}"
                    )

                logger.info(f"Creating resource: {name}")
                start_time = time.time()

                resource = await self._factories[name].create()

                # Store resource
                self._resources[name] = resource

                # Store weak reference if possible
                try:
                    self._weak_refs[name] = weakref.ref(
                        resource, lambda ref: self._on_resource_collected(name)
                    )
                except TypeError:
                    # Some objects don't support weak references
                    pass

                # Track creation time
                if self._enable_metrics:
                    creation_time = time.time() - start_time
                    self._metrics["resource_creations"][name] = (
                        self._metrics["resource_creations"].get(name, 0) + 1
                    )
                    logger.info(f"Created resource {name} in {creation_time:.2f}s")

                self._reset_circuit_breaker(name)
                return resource

            except Exception as e:
                self._record_circuit_breaker_failure(name)
                logger.error(f"Failed to get resource {name}: {e}")
                raise

    async def _is_healthy(self, name: str) -> bool:
        """Check if a resource is healthy."""
        if name not in self._health_checks:
            return True  # No health check = assume healthy

        try:
            health_check = self._health_checks[name]
            resource = self._resources[name]

            # Support both sync and async health checks
            if asyncio.iscoroutinefunction(health_check):
                result = await health_check(resource)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, health_check, resource
                )

            # Handle different return types
            if isinstance(result, bool):
                return result
            elif isinstance(result, HealthStatus):
                return result.is_healthy
            else:
                return bool(result)

        except Exception as e:
            logger.error(f"Health check failed for {name}: {e}")
            if self._enable_metrics:
                self._metrics["health_check_failures"][name] = (
                    self._metrics["health_check_failures"].get(name, 0) + 1
                )
            return False

    async def _cleanup_resource(self, name: str) -> None:
        """Clean up a resource."""
        if name not in self._resources:
            return

        try:
            resource = self._resources.pop(name)

            # Remove weak reference
            if name in self._weak_refs:
                del self._weak_refs[name]

            # Call cleanup handler if available
            if name in self._cleanup_handlers:
                cleanup = self._cleanup_handlers[name]
                if asyncio.iscoroutinefunction(cleanup):
                    await cleanup(resource)
                else:
                    await asyncio.get_event_loop().run_in_executor(
                        None, cleanup, resource
                    )

            # Try generic cleanup methods
            elif hasattr(resource, "aclose"):
                # Use aclose for modern async resources (e.g., Redis)
                if asyncio.iscoroutinefunction(resource.aclose):
                    await resource.aclose()
                else:
                    resource.aclose()
            elif hasattr(resource, "close"):
                if asyncio.iscoroutinefunction(resource.close):
                    await resource.close()
                else:
                    resource.close()
            elif hasattr(resource, "cleanup"):
                if asyncio.iscoroutinefunction(resource.cleanup):
                    await resource.cleanup()
                else:
                    resource.cleanup()
            elif hasattr(resource, "disconnect"):
                if asyncio.iscoroutinefunction(resource.disconnect):
                    await resource.disconnect()
                else:
                    resource.disconnect()

            logger.info(f"Cleaned up resource: {name}")

        except Exception as e:
            logger.error(f"Error cleaning up resource {name}: {e}")

    async def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up all resources")

        # Clean up in parallel
        tasks = []
        for name in list(self._resources.keys()):
            tasks.append(self._cleanup_resource(name))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Clear all state
        self._resources.clear()
        self._weak_refs.clear()
        self._circuit_breakers.clear()

    def has_resource(self, name: str) -> bool:
        """Check if a resource exists in the registry."""
        return name in self._resources

    def has_factory(self, name: str) -> bool:
        """Check if a factory is registered."""
        return name in self._factories

    def list_resources(self) -> Set[str]:
        """List all registered resource names."""
        return set(self._factories.keys())

    def get_metrics(self) -> Dict[str, Any]:
        """Get resource usage metrics."""
        if not self._enable_metrics:
            return {}

        return {
            "resources": {
                name: {
                    "created": self._metrics["resource_creations"].get(name, 0),
                    "accessed": self._metrics["resource_accesses"].get(name, 0),
                    "health_failures": self._metrics["health_check_failures"].get(
                        name, 0
                    ),
                    "recreations": self._metrics["resource_recreations"].get(name, 0),
                    "circuit_breaker": self._circuit_breakers.get(name, {}),
                }
                for name in self._factories.keys()
            }
        }

    # Circuit breaker methods
    def _is_circuit_open(self, name: str) -> bool:
        """Check if circuit breaker is open."""
        if name not in self._circuit_breakers:
            return False

        breaker = self._circuit_breakers[name]

        if breaker["state"] == "open":
            # Check if we should try half-open
            if breaker["last_failure"]:
                time_since_failure = datetime.now() - breaker["last_failure"]
                if time_since_failure > timedelta(seconds=30):
                    breaker["state"] = "half-open"
                    return False
            return True

        return False

    def _record_circuit_breaker_failure(self, name: str) -> None:
        """Record a failure for circuit breaker."""
        if name not in self._circuit_breakers:
            return

        breaker = self._circuit_breakers[name]
        breaker["failures"] += 1
        breaker["last_failure"] = datetime.now()

        if breaker["failures"] >= breaker["threshold"]:
            breaker["state"] = "open"
            logger.error(f"Circuit breaker opened for resource: {name}")

    def _reset_circuit_breaker(self, name: str) -> None:
        """Reset circuit breaker on success."""
        if name not in self._circuit_breakers:
            return

        breaker = self._circuit_breakers[name]
        breaker["failures"] = 0
        breaker["last_failure"] = None
        breaker["state"] = "closed"

    # Metrics tracking
    def _track_access(self, name: str) -> None:
        """Track resource access."""
        self._metrics["resource_accesses"][name] = (
            self._metrics["resource_accesses"].get(name, 0) + 1
        )

    def _on_resource_collected(self, name: str) -> None:
        """Callback when a resource is garbage collected."""
        logger.debug(f"Resource {name} was garbage collected")
        # Remove from resources dict if still there
        self._resources.pop(name, None)
