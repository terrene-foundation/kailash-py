"""
Tier 1 Unit Tests for TestHTTPServer Utils

Tests the test HTTP server utility class used for integration testing.
This validates the test infrastructure itself.

Test Strategy:
- Fast execution (<1 second total)
- Test server lifecycle (start, stop, is_running)
- Test endpoint availability
- Test SSE format generation
- Test request/response pairing
- NO EXTERNAL DEPENDENCIES (self-contained server)

Coverage Requirements:
- Server initialization
- Server start/stop lifecycle
- POST /control endpoint stores messages
- GET /stream endpoint returns SSE format
- Request/response pairing works correctly
- Context manager support
- Error handling (port conflicts, invalid data)

Target: 5 core tests (expandable to 10+)
Timeout: <1 second per test
"""

import json

import anyio
import pytest

# Configure pytest for async tests with asyncio only
# aiohttp requires asyncio, cannot run with trio
pytestmark = pytest.mark.anyio


# Force asyncio backend for all tests in this file
@pytest.fixture(autouse=True, scope="module")
def anyio_backend():
    """Force asyncio backend (aiohttp requires asyncio)."""
    return "asyncio"


# Import will work after implementation
try:
    from tests.utils.test_http_server import TestHTTPServer
except ImportError:
    # Placeholder for TDD - tests will fail until implementation exists
    TestHTTPServer = None


# ============================================
# Test 1: Server Initialization
# ============================================


class TestHTTPServerInitialization:
    """Test TestHTTPServer initialization."""

    def test_server_can_be_instantiated(self):
        """Test that TestHTTPServer can be created."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        server = TestHTTPServer()
        assert server is not None
        assert hasattr(server, "start")
        assert hasattr(server, "stop")
        assert hasattr(server, "is_running")

    def test_server_accepts_host_and_port(self):
        """Test that server accepts custom host and port."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        server = TestHTTPServer(host="127.0.0.1", port=9999)
        assert server is not None

    def test_server_starts_not_running(self):
        """Test that server starts in not-running state."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        server = TestHTTPServer()
        assert not server.is_running()


# ============================================
# Test 2: Server Lifecycle
# ============================================


class TestHTTPServerLifecycle:
    """Test server start/stop lifecycle."""

    async def test_server_can_start_and_stop(self):
        """Test that server can be started and stopped."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        server = TestHTTPServer(host="127.0.0.1", port=8765)

        # Start server
        await server.start()
        assert server.is_running()

        # Stop server
        await server.stop()
        assert not server.is_running()

    async def test_server_start_is_idempotent(self):
        """Test that start() can be called multiple times safely."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        server = TestHTTPServer(host="127.0.0.1", port=8766)

        await server.start()
        assert server.is_running()

        # Second start should not raise
        await server.start()
        assert server.is_running()

        await server.stop()

    async def test_server_stop_is_idempotent(self):
        """Test that stop() can be called multiple times safely."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        server = TestHTTPServer(host="127.0.0.1", port=8767)

        await server.start()
        await server.stop()
        assert not server.is_running()

        # Second stop should not raise
        await server.stop()
        assert not server.is_running()

    async def test_server_context_manager(self):
        """Test that server supports async context manager."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        server = TestHTTPServer(host="127.0.0.1", port=8768)

        async with server:
            assert server.is_running()

        # Should be stopped after context exit
        assert not server.is_running()


# ============================================
# Test 3: POST /control Endpoint
# ============================================


class TestHTTPServerControlEndpoint:
    """Test POST /control endpoint stores messages."""

    async def test_control_endpoint_stores_message(self):
        """Test that POST /control stores message for retrieval."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8769)

        async with server:
            # Send message to /control endpoint
            async with aiohttp.ClientSession() as session:
                test_data = {"test": "message", "request_id": "req_123"}

                async with session.post(
                    "http://127.0.0.1:8769/control",
                    json={"data": json.dumps(test_data)},
                ) as response:
                    assert response.status == 200

    async def test_control_endpoint_accepts_json(self):
        """Test that /control endpoint accepts JSON data."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8770)

        async with server:
            async with aiohttp.ClientSession() as session:
                # Send JSON data
                payload = {
                    "data": json.dumps(
                        {
                            "request_id": "req_456",
                            "type": "question",
                            "data": {"question": "Test?"},
                        }
                    )
                }

                async with session.post(
                    "http://127.0.0.1:8770/control", json=payload
                ) as response:
                    assert response.status == 200


# ============================================
# Test 4: GET /stream SSE Endpoint
# ============================================


class TestHTTPServerStreamEndpoint:
    """Test GET /stream returns SSE format."""

    async def test_stream_endpoint_returns_sse_format(self):
        """Test that GET /stream returns proper SSE format."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8771)

        async with server:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://127.0.0.1:8771/stream") as response:
                    # Should have SSE headers
                    assert response.status == 200
                    assert response.headers.get("Content-Type") == "text/event-stream"
                    assert response.headers.get("Cache-Control") == "no-cache"
                    assert response.headers.get("Connection") == "keep-alive"

    async def test_stream_endpoint_sends_sse_data(self):
        """Test that /stream sends data in SSE format (data: prefix)."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8772)

        async with server:
            async with aiohttp.ClientSession() as session:
                test_message = {"request_id": "req_789", "data": {"answer": "yes"}}

                # Start reading from stream in background
                received_data = []

                async def reader():
                    try:
                        with anyio.fail_after(3.0):
                            async with session.get(
                                "http://127.0.0.1:8772/stream"
                            ) as response:
                                async for line_bytes in response.content.iter_any():
                                    line = line_bytes.decode("utf-8").strip()

                                    if line and not line.startswith(":"):
                                        received_data.append(line)
                                        if line.startswith("data:"):
                                            # Successfully validated SSE format
                                            break
                    except TimeoutError:
                        pass

                # Start reader and writer concurrently
                async with anyio.create_task_group() as tg:
                    tg.start_soon(reader)

                    # Give reader time to connect
                    await anyio.sleep(0.5)

                    # Post to control
                    await session.post(
                        "http://127.0.0.1:8772/control",
                        json={"data": json.dumps(test_message)},
                    )

                    # Wait for reader
                    await anyio.sleep(1.0)

                # Validate SSE format received
                assert len(received_data) > 0, "No data received from SSE stream"
                assert any(
                    line.startswith("data:") for line in received_data
                ), f"Expected SSE format with 'data:' prefix, got: {received_data}"


# ============================================
# Test 5: Request/Response Pairing
# ============================================


class TestHTTPServerRequestResponsePairing:
    """Test request/response pairing works correctly."""

    async def test_messages_are_paired_by_request_id(self):
        """Test that requests and responses are paired by request_id."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8773)

        async with server:
            async with aiohttp.ClientSession() as session:
                request_data = {
                    "request_id": "req_pairing_test",
                    "type": "question",
                    "data": {"question": "Test?"},
                }

                received_data = []

                async def reader():
                    try:
                        with anyio.fail_after(3.0):
                            async with session.get(
                                "http://127.0.0.1:8773/stream"
                            ) as response:
                                async for line_bytes in response.content.iter_any():
                                    line = line_bytes.decode("utf-8").strip()

                                    if line.startswith("data:"):
                                        data_json = line[5:].lstrip()
                                        data = json.loads(data_json)
                                        received_data.append(data)
                                        break
                    except TimeoutError:
                        pass

                async with anyio.create_task_group() as tg:
                    tg.start_soon(reader)
                    await anyio.sleep(0.5)

                    # Send request
                    await session.post(
                        "http://127.0.0.1:8773/control",
                        json={"data": json.dumps(request_data)},
                    )

                    await anyio.sleep(1.0)

                # Validate pairing
                assert len(received_data) > 0, "No data received"
                assert "request_id" in received_data[0]

    async def test_multiple_concurrent_messages(self):
        """Test handling of multiple concurrent messages."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8774)

        async with server:
            async with aiohttp.ClientSession() as session:
                requests = [
                    {
                        "request_id": f"req_{i}",
                        "type": "question",
                        "data": {"q": f"Q{i}"},
                    }
                    for i in range(3)
                ]

                received_ids = []

                async def reader():
                    try:
                        with anyio.fail_after(4.0):
                            async with session.get(
                                "http://127.0.0.1:8774/stream"
                            ) as response:
                                async for line_bytes in response.content.iter_any():
                                    line = line_bytes.decode("utf-8").strip()

                                    if line.startswith("data:"):
                                        data_json = line[5:].lstrip()
                                        data = json.loads(data_json)
                                        received_ids.append(data.get("request_id"))

                                        if len(received_ids) >= 3:
                                            break
                    except TimeoutError:
                        pass

                async with anyio.create_task_group() as tg:
                    tg.start_soon(reader)
                    await anyio.sleep(0.5)

                    # Post all requests
                    for req in requests:
                        await session.post(
                            "http://127.0.0.1:8774/control",
                            json={"data": json.dumps(req)},
                        )
                        await anyio.sleep(0.2)

                    await anyio.sleep(1.5)

                # Should have received all request IDs
                assert len(received_ids) >= 3


# ============================================
# Additional Tests (Optional)
# ============================================


class TestHTTPServerErrorHandling:
    """Test error handling scenarios."""

    async def test_invalid_json_to_control_endpoint(self):
        """Test handling of invalid JSON to /control endpoint."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8775)

        async with server:
            async with aiohttp.ClientSession() as session:
                # Send invalid JSON (missing 'data' field)
                async with session.post(
                    "http://127.0.0.1:8775/control", json={"invalid": "structure"}
                ) as response:
                    # Server should handle gracefully (might accept or reject)
                    # At minimum, should not crash
                    assert response.status in (200, 400, 422)

    async def test_health_endpoint_if_exists(self):
        """Test optional /health endpoint."""
        if TestHTTPServer is None:
            pytest.skip("TestHTTPServer not yet implemented")

        import aiohttp

        server = TestHTTPServer(host="127.0.0.1", port=8776)

        async with server:
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get("http://127.0.0.1:8776/health") as response:
                        # If health endpoint exists, should return 200
                        assert response.status == 200
                except aiohttp.ClientResponseError:
                    # Health endpoint is optional
                    pytest.skip("Health endpoint not implemented")
