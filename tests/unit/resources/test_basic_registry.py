"""
Basic tests for Resource Registry core functionality.

Tests the essential features without mocking complex async libraries.
"""

import asyncio

import pytest
from kailash.resources.factory import ResourceFactory
from kailash.resources.registry import ResourceNotFoundError, ResourceRegistry


class SimpleFactory(ResourceFactory):
    """Simple factory that returns a string."""

    def __init__(self, value="test"):
        self.value = value
        self.create_count = 0

    async def create(self):
        self.create_count += 1
        return f"{self.value}_{self.create_count}"

    def get_config(self):
        return {"value": self.value}


@pytest.mark.asyncio
class TestBasicResourceRegistry:
    """Test basic ResourceRegistry functionality."""

    async def test_register_and_get_resource(self):
        """Test basic resource registration and retrieval."""
        registry = ResourceRegistry()
        factory = SimpleFactory("test")

        registry.register_factory("test_resource", factory)

        # First access creates resource
        resource1 = await registry.get_resource("test_resource")
        assert resource1 == "test_1"
        assert factory.create_count == 1

        # Second access returns same resource
        resource2 = await registry.get_resource("test_resource")
        assert resource2 == "test_1"
        assert factory.create_count == 1

    async def test_resource_not_found(self):
        """Test error when requesting non-existent resource."""
        registry = ResourceRegistry()

        with pytest.raises(ResourceNotFoundError):
            await registry.get_resource("nonexistent")

    async def test_has_factory_and_resource(self):
        """Test existence checks."""
        registry = ResourceRegistry()
        factory = SimpleFactory("test")

        # Initially nothing exists
        assert not registry.has_factory("test")
        assert not registry.has_resource("test")

        # After registering factory
        registry.register_factory("test", factory)
        assert registry.has_factory("test")
        assert not registry.has_resource("test")  # Not created yet

        # After creating resource
        await registry.get_resource("test")
        assert registry.has_factory("test")
        assert registry.has_resource("test")

    async def test_list_resources(self):
        """Test listing registered resources."""
        registry = ResourceRegistry()

        registry.register_factory("resource1", SimpleFactory("r1"))
        registry.register_factory("resource2", SimpleFactory("r2"))

        resources = registry.list_resources()
        assert resources == {"resource1", "resource2"}

    async def test_concurrent_access(self):
        """Test concurrent access to same resource."""
        registry = ResourceRegistry()
        factory = SimpleFactory("concurrent")
        registry.register_factory("test", factory)

        # Multiple concurrent requests
        tasks = [registry.get_resource("test") for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All should get same resource
        assert all(r == "concurrent_1" for r in results)
        assert factory.create_count == 1

    async def test_simple_cleanup(self):
        """Test basic cleanup functionality."""
        registry = ResourceRegistry()
        factory = SimpleFactory("cleanup_test")
        registry.register_factory("test", factory)

        # Create resource
        resource = await registry.get_resource("test")
        assert resource == "cleanup_test_1"

        # Cleanup
        await registry.cleanup()

        # Resource should be removed
        assert not registry.has_resource("test")
        assert len(registry._resources) == 0

    async def test_health_check_boolean(self):
        """Test simple boolean health check."""
        registry = ResourceRegistry()
        factory = SimpleFactory("healthy")

        # Health check that returns True
        async def always_healthy(resource):
            return True

        registry.register_factory("test", factory, health_check=always_healthy)

        # Should only create once even with multiple accesses
        resource1 = await registry.get_resource("test")
        resource2 = await registry.get_resource("test")

        assert resource1 == resource2
        assert factory.create_count == 1

    async def test_health_check_failure(self):
        """Test health check failure triggering recreation."""
        registry = ResourceRegistry()
        factory = SimpleFactory("unhealthy")

        # Health check that fails on first check (causing recreation)
        async def always_unhealthy(resource):
            return False  # Always unhealthy to trigger recreation

        registry.register_factory("test", factory, health_check=always_unhealthy)

        # First access
        resource1 = await registry.get_resource("test")
        assert resource1 == "unhealthy_1"

        # Second access should recreate due to health check failure
        resource2 = await registry.get_resource("test")
        assert resource2 == "unhealthy_2"
        assert factory.create_count == 2

    async def test_metrics_basic(self):
        """Test basic metrics collection."""
        registry = ResourceRegistry(enable_metrics=True)
        factory = SimpleFactory("metrics")
        registry.register_factory("test", factory)

        # Access resource multiple times
        await registry.get_resource("test")
        await registry.get_resource("test")
        await registry.get_resource("test")

        metrics = registry.get_metrics()

        assert "resources" in metrics
        assert "test" in metrics["resources"]

        test_metrics = metrics["resources"]["test"]
        assert test_metrics["created"] == 1
        assert test_metrics["accessed"] == 3

    async def test_metrics_disabled(self):
        """Test registry with metrics disabled."""
        registry = ResourceRegistry(enable_metrics=False)
        factory = SimpleFactory("no_metrics")
        registry.register_factory("test", factory)

        await registry.get_resource("test")

        metrics = registry.get_metrics()
        assert metrics == {}

    async def test_circuit_breaker_basic(self):
        """Test basic circuit breaker functionality."""
        registry = ResourceRegistry()

        # Factory that always fails
        class FailingFactory(ResourceFactory):
            async def create(self):
                raise Exception("Always fails")

            def get_config(self):
                return {"type": "failing"}

        registry.register_factory(
            "failing", FailingFactory(), metadata={"circuit_breaker_threshold": 2}
        )

        # First two failures should open circuit
        with pytest.raises(Exception, match="Always fails"):
            await registry.get_resource("failing")

        with pytest.raises(Exception, match="Always fails"):
            await registry.get_resource("failing")

        # Third attempt should hit circuit breaker
        with pytest.raises(ResourceNotFoundError, match="Circuit breaker open"):
            await registry.get_resource("failing")
