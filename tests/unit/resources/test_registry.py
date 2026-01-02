"""
Unit tests for Resource Registry.

Tests core functionality of the ResourceRegistry including:
- Factory registration and resource creation
- Health checking and automatic recovery
- Circuit breaker pattern
- Metrics collection
- Resource lifecycle management
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.resources.factory import ResourceFactory
from kailash.resources.health import HealthState, HealthStatus
from kailash.resources.registry import ResourceNotFoundError, ResourceRegistry


class MockFactory(ResourceFactory):
    """Mock resource factory for testing."""

    def __init__(self, resource_value="test_resource", should_fail=False):
        self.resource_value = resource_value
        self.should_fail = should_fail
        self.create_count = 0

    async def create(self):
        self.create_count += 1
        if self.should_fail:
            raise Exception("Factory failed")
        return self.resource_value

    def get_config(self):
        return {"value": self.resource_value}


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    return ResourceRegistry()


@pytest.mark.asyncio
class TestResourceRegistry:
    """Test Resource Registry functionality."""

    async def test_register_and_get_resource(self, registry):
        """Test basic resource registration and retrieval."""
        factory = MockFactory("test_value")
        registry.register_factory("test_resource", factory)

        # Resource should be created on first access
        resource = await registry.get_resource("test_resource")
        assert resource == "test_value"
        assert factory.create_count == 1

        # Second access should return same resource
        resource2 = await registry.get_resource("test_resource")
        assert resource2 == "test_value"
        assert factory.create_count == 1  # No additional creation

    async def test_resource_not_found(self, registry):
        """Test error when requesting non-existent resource."""
        with pytest.raises(ResourceNotFoundError):
            await registry.get_resource("nonexistent")

    async def test_health_check_healthy(self, registry):
        """Test health check for healthy resource."""
        factory = MockFactory("healthy_resource")

        async def health_check(resource):
            return True

        registry.register_factory(
            "healthy_resource", factory, health_check=health_check
        )

        # Get resource twice - should not recreate if healthy
        resource1 = await registry.get_resource("healthy_resource")
        resource2 = await registry.get_resource("healthy_resource")

        assert resource1 == resource2
        assert factory.create_count == 1

    async def test_health_check_unhealthy_recreation(self, registry):
        """Test resource recreation when health check fails."""
        factory = MockFactory("recreated_resource")
        health_check_results = [
            True,
            False,
            True,
        ]  # First healthy, then unhealthy, then healthy
        call_count = 0

        async def health_check(resource):
            nonlocal call_count
            result = health_check_results[call_count % len(health_check_results)]
            call_count += 1
            return result

        registry.register_factory(
            "unhealthy_resource", factory, health_check=health_check
        )

        # First access - create resource
        resource1 = await registry.get_resource("unhealthy_resource")
        assert factory.create_count == 1
        assert call_count == 0  # Health check not called on creation

        # Second access - health check returns True (healthy)
        resource2 = await registry.get_resource("unhealthy_resource")
        assert call_count == 1  # First health check
        assert factory.create_count == 1  # No recreation needed

        # Third access - health check returns False (unhealthy), should recreate
        resource3 = await registry.get_resource("unhealthy_resource")
        assert call_count == 2  # Second health check
        assert factory.create_count == 2  # Resource recreated

    async def test_health_status_object(self, registry):
        """Test health check returning HealthStatus object."""
        factory = MockFactory("status_resource")

        async def health_check(resource):
            return HealthStatus.healthy("All good")

        registry.register_factory("status_resource", factory, health_check=health_check)

        resource = await registry.get_resource("status_resource")
        assert resource == "status_resource"

    async def test_circuit_breaker_open(self, registry):
        """Test circuit breaker opening after failures."""
        factory = MockFactory("failing_resource", should_fail=True)

        registry.register_factory(
            "failing_resource", factory, metadata={"circuit_breaker_threshold": 2}
        )

        # First failure
        with pytest.raises(Exception):
            await registry.get_resource("failing_resource")

        # Second failure - should open circuit
        with pytest.raises(Exception):
            await registry.get_resource("failing_resource")

        # Third attempt - circuit should be open
        with pytest.raises(ResourceNotFoundError, match="Circuit breaker open"):
            await registry.get_resource("failing_resource")

    async def test_circuit_breaker_half_open(self, registry):
        """Test circuit breaker transitioning to half-open."""
        factory = MockFactory("recovery_resource", should_fail=True)

        registry.register_factory(
            "recovery_resource", factory, metadata={"circuit_breaker_threshold": 1}
        )

        # Cause failure to open circuit
        with pytest.raises(Exception):
            await registry.get_resource("recovery_resource")

        # Manually set last failure time to simulate timeout
        breaker = registry._circuit_breakers["recovery_resource"]
        breaker["last_failure"] = datetime.now() - timedelta(seconds=35)

        # Should allow attempt (half-open state)
        factory.should_fail = False  # Make it succeed
        resource = await registry.get_resource("recovery_resource")
        assert resource == "recovery_resource"

        # Circuit should be closed now
        assert breaker["state"] == "closed"
        assert breaker["failures"] == 0

    async def test_cleanup_single_resource(self, registry):
        """Test cleanup of a single resource."""
        mock_resource = MagicMock()
        mock_resource.close = AsyncMock()
        # Ensure aclose doesn't exist so registry falls back to close
        del mock_resource.aclose

        factory = MockFactory()
        factory.resource_value = mock_resource

        registry.register_factory("cleanup_test", factory)

        # Get resource to create it
        resource = await registry.get_resource("cleanup_test")
        assert resource == mock_resource

        # Cleanup specific resource
        await registry._cleanup_resource("cleanup_test")

        # Should have called close
        mock_resource.close.assert_called_once()

        # Resource should be removed
        assert not registry.has_resource("cleanup_test")

    async def test_cleanup_all_resources(self, registry):
        """Test cleanup of all resources."""
        # Create multiple resources with cleanup methods
        resources = []
        for i in range(3):
            mock_resource = MagicMock()
            mock_resource.close = AsyncMock()
            # Ensure aclose doesn't exist so registry falls back to close
            del mock_resource.aclose
            resources.append(mock_resource)

            factory = MockFactory()
            factory.resource_value = mock_resource

            registry.register_factory(f"resource_{i}", factory)
            await registry.get_resource(f"resource_{i}")

        # Cleanup all
        await registry.cleanup()

        # All resources should have been cleaned up
        for resource in resources:
            resource.close.assert_called_once()

        assert len(registry._resources) == 0

    async def test_custom_cleanup_handler(self, registry):
        """Test custom cleanup handler."""
        mock_resource = MagicMock()
        cleanup_called = False

        async def custom_cleanup(resource):
            nonlocal cleanup_called
            cleanup_called = True
            assert resource == mock_resource

        factory = MockFactory()
        factory.resource_value = mock_resource

        registry.register_factory(
            "custom_cleanup", factory, cleanup_handler=custom_cleanup
        )

        await registry.get_resource("custom_cleanup")
        await registry._cleanup_resource("custom_cleanup")

        assert cleanup_called

    async def test_has_resource_and_factory(self, registry):
        """Test resource and factory existence checks."""
        factory = MockFactory()
        registry.register_factory("test_check", factory)

        # Factory exists but resource not created yet
        assert registry.has_factory("test_check")
        assert not registry.has_resource("test_check")

        # Non-existent
        assert not registry.has_factory("nonexistent")
        assert not registry.has_resource("nonexistent")

    async def test_list_resources(self, registry):
        """Test listing registered resources."""
        factory1 = MockFactory()
        factory2 = MockFactory()

        registry.register_factory("resource1", factory1)
        registry.register_factory("resource2", factory2)

        resources = registry.list_resources()
        assert resources == {"resource1", "resource2"}

    async def test_metrics_collection(self, registry):
        """Test metrics collection."""
        factory = MockFactory()
        registry.register_factory("metrics_test", factory)

        # Create and access resource multiple times
        await registry.get_resource("metrics_test")
        await registry.get_resource("metrics_test")
        await registry.get_resource("metrics_test")

        metrics = registry.get_metrics()

        assert "resources" in metrics
        assert "metrics_test" in metrics["resources"]

        resource_metrics = metrics["resources"]["metrics_test"]
        assert resource_metrics["created"] == 1
        assert resource_metrics["accessed"] == 3

    async def test_metrics_disabled(self):
        """Test registry with metrics disabled."""
        registry = ResourceRegistry(enable_metrics=False)
        factory = MockFactory()
        registry.register_factory("no_metrics", factory)

        await registry.get_resource("no_metrics")

        metrics = registry.get_metrics()
        assert metrics == {}

    async def test_concurrent_access(self, registry):
        """Test concurrent access to same resource."""
        factory = MockFactory()
        registry.register_factory("concurrent_test", factory)

        # Multiple concurrent requests
        tasks = [registry.get_resource("concurrent_test") for _ in range(10)]

        results = await asyncio.gather(*tasks)

        # All should get same resource
        assert all(r == "test_resource" for r in results)

        # Resource should only be created once
        assert factory.create_count == 1

    async def test_health_check_exception_handling(self, registry):
        """Test health check that raises exceptions."""
        factory = MockFactory()

        async def failing_health_check(resource):
            raise Exception("Health check failed")

        registry.register_factory(
            "health_exception", factory, health_check=failing_health_check
        )

        # First access should create resource
        resource1 = await registry.get_resource("health_exception")
        assert factory.create_count == 1

        # Second access should recreate due to health check failure
        resource2 = await registry.get_resource("health_exception")
        assert factory.create_count == 2

    async def test_sync_health_check(self, registry):
        """Test synchronous health check function."""
        factory = MockFactory()

        def sync_health_check(resource):
            return True

        registry.register_factory(
            "sync_health", factory, health_check=sync_health_check
        )

        # Should work with sync health check
        resource = await registry.get_resource("sync_health")
        assert resource == "test_resource"

    async def test_metadata_storage(self, registry):
        """Test metadata storage and retrieval."""
        factory = MockFactory()
        metadata = {
            "description": "Test resource",
            "tags": ["test", "mock"],
            "circuit_breaker_threshold": 5,
        }

        registry.register_factory("metadata_test", factory, metadata=metadata)

        # Metadata should be stored
        assert registry._resource_metadata["metadata_test"] == metadata

        # Circuit breaker threshold should be used
        assert registry._circuit_breakers["metadata_test"]["threshold"] == 5
