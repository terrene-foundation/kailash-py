"""Unit tests for test fixtures."""

import asyncio
import json
import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from kailash.testing.fixtures import (
    HAS_DOCKER,
    AsyncWorkflowFixtures,
    DatabaseFixture,
    HttpCall,
    MockCache,
    MockHttpClient,
)


@pytest.mark.unit
class TestAsyncWorkflowFixtures:
    """Test AsyncWorkflowFixtures functionality."""

    @pytest.mark.asyncio
    async def test_temp_directory(self):
        """Test temporary directory creation and cleanup."""
        temp_path = None

        async with AsyncWorkflowFixtures.temp_directory() as temp_dir:
            temp_path = temp_dir
            assert os.path.exists(temp_dir)
            assert os.path.isdir(temp_dir)

            # Create a file in it
            test_file = os.path.join(temp_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")
            assert os.path.exists(test_file)

        # Should be cleaned up
        assert not os.path.exists(temp_path)

    @pytest.mark.asyncio
    async def test_create_test_files(self):
        """Test creating test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            files = {
                "file1.txt": "content1",
                "subdir/file2.txt": "content2",
                "data.json": {"key": "value", "number": 42},
            }

            await AsyncWorkflowFixtures.create_test_files(temp_dir, files)

            # Check files exist
            assert os.path.exists(os.path.join(temp_dir, "file1.txt"))
            assert os.path.exists(os.path.join(temp_dir, "subdir/file2.txt"))
            assert os.path.exists(os.path.join(temp_dir, "data.json"))

            # Check content
            with open(os.path.join(temp_dir, "file1.txt")) as f:
                assert f.read() == "content1"

            with open(os.path.join(temp_dir, "data.json")) as f:
                data = json.load(f)
                assert data == {"key": "value", "number": 42}

    def test_create_mock_http_client(self):
        """Test creating mock HTTP client."""
        client = AsyncWorkflowFixtures.create_mock_http_client()
        assert isinstance(client, MockHttpClient)

    @pytest.mark.asyncio
    async def test_create_test_cache(self):
        """Test creating mock cache."""
        cache = await AsyncWorkflowFixtures.create_test_cache()
        assert isinstance(cache, MockCache)

    @pytest.mark.asyncio
    async def test_mock_time(self):
        """Test time mocking."""
        import time as time_module

        original_time = time_module.time()

        # Test normal speed
        async with AsyncWorkflowFixtures.mock_time(start_time=1000.0) as mock_time:
            assert abs(mock_time() - 1000.0) < 0.1
            await asyncio.sleep(0.1)
            assert abs(mock_time() - 1000.1) < 0.05

        # Time should be restored
        assert abs(time_module.time() - original_time) < 1.0

        # Test accelerated time
        async with AsyncWorkflowFixtures.mock_time(start_time=0.0, speed=10.0):
            start = time_module.time()
            await asyncio.sleep(0.1)
            elapsed = time_module.time() - start
            # Should be ~1 second in mock time (0.1 * 10)
            assert 0.5 < elapsed < 1.5

    # NOTE: test_create_test_database has been moved to
    # tests/integration/testing/test_fixtures.py as it requires Docker


@pytest.mark.unit
class TestMockHttpClient:
    """Test MockHttpClient functionality."""

    @pytest.mark.asyncio
    async def test_basic_requests(self):
        """Test basic HTTP requests."""
        client = MockHttpClient()

        # Add responses
        client.add_response("GET", "/users", [{"id": 1, "name": "User 1"}])
        client.add_response("POST", "/users", {"id": 2, "name": "User 2"}, status=201)

        # Make requests
        resp1 = await client.get("/users")
        assert resp1.status == 200
        data1 = await resp1.json()
        assert data1 == [{"id": 1, "name": "User 1"}]

        resp2 = await client.post("/users", json={"name": "User 2"})
        assert resp2.status == 201
        data2 = await resp2.json()
        assert data2 == {"id": 2, "name": "User 2"}

    @pytest.mark.asyncio
    async def test_default_response(self):
        """Test default response for unmatched requests."""
        client = MockHttpClient()
        client.set_default_response({"error": "Not implemented"}, status=501)

        resp = await client.get("/unknown")
        assert resp.status == 501
        data = await resp.json()
        assert data == {"error": "Not implemented"}

    @pytest.mark.asyncio
    async def test_call_tracking(self):
        """Test HTTP call tracking."""
        client = MockHttpClient()

        # Make some calls
        await client.get("/users")
        await client.post("/users", json={"name": "New"})
        await client.get("/users")
        await client.delete("/users/1")

        # Check calls
        all_calls = client.get_calls()
        assert len(all_calls) == 4

        get_calls = client.get_calls(method="GET")
        assert len(get_calls) == 2

        user_calls = client.get_calls(url="/users")
        assert len(user_calls) == 3

    def test_assert_called(self):
        """Test call assertions."""
        client = MockHttpClient()

        # Should fail when not called
        with pytest.raises(AssertionError, match="was not called"):
            client.assert_called("GET", "/users")

        # Make call
        asyncio.run(client.get("/users"))

        # Should pass
        client.assert_called("GET", "/users")
        client.assert_called("GET", "/users", times=1)

        # Should fail for wrong times
        with pytest.raises(AssertionError, match="expected 2"):
            client.assert_called("GET", "/users", times=2)

    @pytest.mark.asyncio
    async def test_response_methods(self):
        """Test MockResponse methods."""
        client = MockHttpClient()

        # JSON response
        client.add_response("GET", "/json", {"key": "value"})
        resp = await client.get("/json")
        assert await resp.json() == {"key": "value"}
        assert await resp.text() == '{"key": "value"}'

        # Text response
        client.add_response("GET", "/text", "plain text")
        resp = await client.get("/text")
        assert await resp.text() == "plain text"
        # json() should raise JSONDecodeError for non-JSON text
        with pytest.raises(json.JSONDecodeError):
            await resp.json()

        # Error response
        client.add_response("GET", "/error", {"error": "Server error"}, status=500)
        resp = await client.get("/error")
        with pytest.raises(Exception, match="HTTP 500"):
            resp.raise_for_status()

    def test_add_responses_batch(self):
        """Test adding multiple responses at once."""
        client = MockHttpClient()

        client.add_responses(
            {
                "GET:/users": [{"id": 1}],
                "POST:/users": {"created": True},
                "/items": [1, 2, 3],  # Default to GET
            }
        )

        # All should work
        async def check_responses():
            resp1 = await client.get("/users")
            assert await resp1.json() == [{"id": 1}]

            resp2 = await client.post("/users")
            assert await resp2.json() == {"created": True}

            resp3 = await client.get("/items")
            assert await resp3.json() == [1, 2, 3]

        asyncio.run(check_responses())

    def test_reset(self):
        """Test resetting client."""
        client = MockHttpClient()

        # Make calls
        asyncio.run(client.get("/test"))
        assert len(client._calls) == 1

        # Reset
        client.reset()
        assert len(client._calls) == 0


@pytest.mark.unit
class TestMockCache:
    """Test MockCache functionality."""

    @pytest.mark.asyncio
    async def test_basic_operations(self):
        """Test basic cache operations."""
        cache = MockCache()

        # Get non-existent
        assert await cache.get("key") is None

        # Set and get
        await cache.set("key", "value")
        assert await cache.get("key") == "value"

        # Delete
        await cache.delete("key")
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_expiration(self):
        """Test cache expiration."""
        cache = MockCache()

        # Set with TTL
        await cache.set("key", "value", ttl=0.1)
        assert await cache.get("key") == "value"

        # Wait for expiration
        await asyncio.sleep(0.15)
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_setex(self):
        """Test Redis-style setex."""
        cache = MockCache()

        await cache.setex("key", 1, "value")
        assert await cache.get("key") == "value"

    @pytest.mark.asyncio
    async def test_expire(self):
        """Test setting expiration on existing key."""
        cache = MockCache()

        # Set without expiration
        await cache.set("key", "value")

        # Add expiration
        await cache.expire("key", 0.1)
        assert await cache.get("key") == "value"

        # Should expire
        await asyncio.sleep(0.15)
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing cache."""
        cache = MockCache()

        # Add multiple items
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # Clear
        await cache.clear()

        # All should be gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_call_tracking(self):
        """Test cache call tracking."""
        cache = MockCache()

        # Make various calls
        await cache.get("key1")
        await cache.set("key1", "value1")
        await cache.get("key1")
        await cache.delete("key1")

        # Check calls
        all_calls = cache.get_calls()
        assert len(all_calls) == 4

        get_calls = cache.get_calls("get")
        assert len(get_calls) == 2

        set_calls = cache.get_calls("set")
        assert len(set_calls) == 1

    def test_assert_called(self):
        """Test cache call assertions."""
        cache = MockCache()

        # Make some calls
        asyncio.run(cache.set("key", "value"))
        asyncio.run(cache.get("key"))
        asyncio.run(cache.get("key"))

        # Test assertions
        cache.assert_called("set", times=1)
        cache.assert_called("get", times=2)

        # Should fail
        with pytest.raises(AssertionError):
            cache.assert_called("delete")


@pytest.mark.unit
class TestHttpCall:
    """Test HttpCall dataclass."""

    def test_http_call(self):
        """Test HttpCall creation."""
        call = HttpCall(
            method="GET",
            url="/test",
            kwargs={"headers": {"Authorization": "Bearer token"}},
        )

        assert call.method == "GET"
        assert call.url == "/test"
        assert call.kwargs == {"headers": {"Authorization": "Bearer token"}}
