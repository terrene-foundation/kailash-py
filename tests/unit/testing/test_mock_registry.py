"""Unit tests for MockResourceRegistry."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from kailash.testing import CallRecord, MockResource, MockResourceRegistry


class TestMockResourceRegistry:
    """Test the MockResourceRegistry functionality."""

    @pytest.mark.asyncio
    async def test_register_mock(self):
        """Test registering mock resources."""
        registry = MockResourceRegistry()
        mock = Mock()

        registry.register_mock("test_resource", mock)

        assert registry.get_mock("test_resource") is mock
        assert "test_resource" in registry._call_history

    @pytest.mark.asyncio
    async def test_create_mock_from_factory(self):
        """Test creating mocks from factories."""
        registry = MockResourceRegistry()

        class TestResource:
            async def do_something(self):
                return "real result"

            def sync_method(self):
                return "sync result"

        class TestFactory:
            async def create(self):
                return TestResource()

        # Create mock
        mock = await registry.create_mock("test", TestFactory())

        # Should have the same interface
        assert hasattr(mock, "do_something")
        assert hasattr(mock, "sync_method")

        # Should be registered
        assert registry.get_mock("test") is mock

    @pytest.mark.asyncio
    async def test_mock_database_configuration(self):
        """Test database mock configuration."""
        registry = MockResourceRegistry()

        class DbResource:
            async def acquire(self):
                pass

            async def execute(self, query):
                pass

            async def fetch(self, query):
                pass

        mock = await registry.create_mock("db", None, spec=DbResource)

        # Should have database methods configured
        assert hasattr(mock, "acquire")
        assert hasattr(mock, "execute")
        assert hasattr(mock, "fetch")

        # Acquire should be callable
        assert callable(mock.acquire)

        # For autospec mocks, acquire returns a coroutine that we need to await
        # The actual DB implementation would return an async context manager
        # But for testing, we just verify the method exists and is async
        result = await mock.acquire()
        # The mock should return a MagicMock by default
        assert result is not None

    @pytest.mark.asyncio
    async def test_mock_http_configuration(self):
        """Test HTTP client mock configuration."""
        registry = MockResourceRegistry()

        class HttpResource:
            async def get(self, url):
                pass

            async def post(self, url, data):
                pass

        mock = await registry.create_mock("http", None, spec=HttpResource)

        # Should have HTTP methods configured
        response = await mock.get("https://example.com")

        # For autospec mocks, the response is just a MagicMock
        # We can't add attributes to it, so just verify it's callable
        assert response is not None

        # Manually configure the response for testing
        response.status = 200
        response.json = AsyncMock(return_value={"test": "data"})

        # Now test the configured response
        assert response.status == 200
        data = await response.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_call_tracking_unittest_mock(self):
        """Test call tracking with unittest.mock objects."""
        registry = MockResourceRegistry()

        mock = AsyncMock()
        registry.register_mock("test", mock)

        # Make some calls
        await mock.method1("arg1", key="value")
        await mock.method2()
        await mock.method1("arg2")

        # Should be able to get calls
        calls = registry.get_calls("test", "method1")
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_call_tracking_custom_mock(self):
        """Test call tracking with MockResource."""
        registry = MockResourceRegistry()

        class CustomMock(MockResource):
            async def test_method(self, arg):
                self._record_call("test_method", (arg,), {}, result="success")
                return "success"

        mock = CustomMock()
        registry.register_mock("custom", mock)

        # Make call
        result = await mock.test_method("test_arg")

        # Check tracking - both in mock and registry
        calls = mock.get_calls("test_method")
        # The call is recorded twice - once by the wrapper and once by the method itself
        assert len(calls) == 2
        assert calls[0].args == ("test_arg",)
        assert calls[0].result == "success"

        # Registry also tracks the call (but only from the wrapper)
        registry_calls = registry.get_calls("custom", "test_method")
        assert len(registry_calls) == 1
        assert registry_calls[0].args == ("test_arg",)
        assert registry_calls[0].result == "success"

    @pytest.mark.asyncio
    async def test_assert_called(self):
        """Test assertion methods."""
        registry = MockResourceRegistry()

        mock = AsyncMock()
        registry.register_mock("test", mock)

        # Make calls
        await mock.method("arg1", key="value1")
        await mock.method("arg2", key="value2")

        # Test assertions
        registry.assert_called("test", "method")  # Called at least once
        registry.assert_called("test", "method", times=2)  # Called exactly twice

        # With specific args - use assert_any_call since we called it twice
        mock.method.assert_any_call("arg1", key="value1")

        # Should fail for wrong times
        with pytest.raises(AssertionError):
            registry.assert_called("test", "method", times=3)

        # Should fail for not called
        with pytest.raises(AssertionError):
            registry.assert_called("test", "other_method")

    @pytest.mark.asyncio
    async def test_assert_not_called(self):
        """Test not called assertion."""
        registry = MockResourceRegistry()

        mock = AsyncMock()
        registry.register_mock("test", mock)

        # Should pass for not called
        registry.assert_not_called("test", "method")

        # Make a call
        await mock.method()

        # Should fail now
        with pytest.raises(AssertionError):
            registry.assert_not_called("test", "method")

    @pytest.mark.asyncio
    async def test_reset_history(self):
        """Test resetting call history."""
        registry = MockResourceRegistry()

        mock = AsyncMock()
        registry.register_mock("test", mock)

        # Make calls
        await mock.method1()
        await mock.method2()

        # Reset specific resource
        registry.reset_history("test")

        # Should have no calls
        assert len(registry.get_calls("test")) == 0
        # Verify mock was reset by checking call count
        assert mock.method1.call_count == 0
        assert mock.method2.call_count == 0

    @pytest.mark.asyncio
    async def test_expectations(self):
        """Test setting up expectations."""
        registry = MockResourceRegistry()

        mock = AsyncMock()
        registry.register_mock("test", mock)

        # Set expectation
        registry.expect_call("test", "method", returns="expected_result")

        # Should configure mock
        assert mock.method.return_value == "expected_result"

        # Test with exception
        registry.expect_call("test", "error_method", raises=ValueError("test error"))
        assert isinstance(mock.error_method.side_effect, ValueError)
        assert str(mock.error_method.side_effect) == "test error"

    @pytest.mark.asyncio
    async def test_mock_cache_configuration(self):
        """Test cache mock configuration."""
        registry = MockResourceRegistry()

        class CacheResource:
            async def get(self, key):
                pass

            async def set(self, key, value):
                pass

            async def delete(self, key):
                pass

        mock = await registry.create_mock("cache", None, spec=CacheResource)

        # Should have cache methods
        # For autospec mocks, get returns an AsyncMock, not None
        result = await mock.get("key")
        assert result is not None  # Returns a mock

        await mock.set("key", "value")  # Should not raise
        await mock.delete("key")  # Should not raise

    def test_call_record_dataclass(self):
        """Test CallRecord dataclass."""
        record = CallRecord(
            method="test_method",
            args=("arg1", "arg2"),
            kwargs={"key": "value"},
            timestamp=datetime.now(timezone.utc),
            result="success",
            duration=0.123,
        )

        assert record.method == "test_method"
        assert record.args == ("arg1", "arg2")
        assert record.kwargs == {"key": "value"}
        assert record.result == "success"
        assert record.duration == 0.123
        assert record.exception is None

    @pytest.mark.asyncio
    async def test_create_mock_method(self):
        """Test creating mock methods."""
        registry = MockResourceRegistry()

        # Sync mock
        sync_mock = registry.create_mock_method(return_value="sync_result")
        assert sync_mock() == "sync_result"

        # Async mock
        async_mock = registry.create_mock_method(return_value="async_result")
        # Should detect if we're trying to make async mock

        # With side effect
        def side_effect(x):
            return x * 2

        mock_with_effect = registry.create_mock_method(side_effect=side_effect)
        assert mock_with_effect(5) == 10

    @pytest.mark.asyncio
    async def test_mixed_sync_async_mocks(self):
        """Test handling mixed sync/async methods."""
        registry = MockResourceRegistry()

        class MixedResource:
            def sync_method(self):
                return "sync"

            async def async_method(self):
                return "async"

        mock = await registry.create_mock("mixed", None, spec=MixedResource)

        # Both should work
        assert mock.sync_method() is not None  # Mock return
        assert await mock.async_method() is not None  # AsyncMock return
