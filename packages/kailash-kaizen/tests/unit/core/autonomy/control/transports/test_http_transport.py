"""
Tier 1 Unit Tests for HTTPTransport Implementation

Tests HTTPTransport with mocked aiohttp for Server-Sent Events (SSE) communication.

Test Coverage (15 tests):
1. HTTPTransport instantiation
2. Inherits from Transport ABC
3. Starts in not-ready state
4. connect() creates aiohttp session
5. connect() makes transport ready
6. connect() is idempotent
7. write() sends POST request to /control
8. write() before connect raises error
9. write() with connection error handling
10. read_messages() connects to /stream SSE endpoint
11. read_messages() parses SSE format (data: prefix)
12. read_messages() skips empty lines and comments
13. read_messages() before connect raises error
14. close() closes aiohttp session
15. close() is idempotent

Test Strategy: TDD - Tests written BEFORE implementation
Infrastructure: Mock aiohttp with unittest.mock
No Integration: Real HTTP testing in Tier 2

SSE Format:
    data: {"request_id": "req_123", "type": "question"}

    data: {"request_id": "req_124", "type": "approval"}

    : this is a comment

    data: {"request_id": "req_125", "type": "progress"}

See Also:
    - ADR-011: Control Protocol Architecture (Section: HTTP Transport)
    - src/kaizen/core/autonomy/control/transports/cli.py (pattern reference)
    - tests/integration/autonomy/control/test_http_transport.py (Tier 2)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

# Import will work after implementation
try:
    from kaizen.core.autonomy.control.transports.http import HTTPTransport
except ImportError:
    # Placeholder for TDD - tests will fail until implementation exists
    HTTPTransport = None

try:
    from kaizen.core.autonomy.control.transport import Transport
except ImportError:
    Transport = None


# ============================================
# Test Fixtures
# ============================================


@pytest.fixture
def base_url() -> str:
    """Base URL for HTTP transport."""
    return "http://localhost:8000"


@pytest.fixture
def transport_kwargs(base_url: str) -> dict:
    """Common kwargs for HTTPTransport instantiation in tests."""
    return {"base_url": base_url, "allow_insecure": True}


@pytest.fixture
def sample_json_messages() -> list[str]:
    """Sample JSON messages for testing."""
    return [
        '{"request_id": "req_1", "type": "question", "data": {"q": "Test?"}}',
        '{"request_id": "req_2", "type": "approval", "data": {"action": "delete"}}',
        '{"request_id": "req_3", "type": "progress_update", "data": {"pct": 50}}',
    ]


@pytest.fixture
def sample_sse_stream() -> str:
    """Sample SSE stream with proper formatting."""
    return (
        'data: {"request_id": "req_1", "type": "question"}\n'
        "\n"
        'data: {"request_id": "req_2", "type": "approval"}\n'
        "\n"
        ": this is a comment\n"
        "\n"
        'data: {"request_id": "req_3", "type": "progress"}\n'
        "\n"
    )


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp.ClientSession."""
    session = AsyncMock()
    session.closed = False
    return session


@pytest.fixture
def mock_aiohttp_response():
    """Mock aiohttp response for POST requests."""
    response = AsyncMock()
    response.status = 200
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def create_mock_sse_response(sse_lines: list[bytes], status: int = 200):
    """
    Helper to create properly mocked SSE response.

    Args:
        sse_lines: List of bytes to yield from SSE stream
        status: HTTP status code

    Returns:
        Mock response object with async context manager support
    """
    mock_response = MagicMock()
    mock_response.status = status

    async def mock_content_iter():
        for line in sse_lines:
            yield line

    mock_response.content = MagicMock()
    mock_response.content.iter_any = mock_content_iter

    # Make __aenter__ and __aexit__ AsyncMock to handle coroutines properly
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_response.text = AsyncMock(return_value="")

    return mock_response


def create_mock_post_response(status: int = 200, text: str = ""):
    """
    Helper to create properly mocked POST response.

    Args:
        status: HTTP status code
        text: Response text

    Returns:
        Mock response object with async context manager support
    """
    mock_response = MagicMock()
    mock_response.status = status

    # Make __aenter__ and __aexit__ AsyncMock to handle coroutines properly
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_response.text = AsyncMock(return_value=text)

    return mock_response


# ============================================
# HTTPTransport Instantiation Tests
# ============================================


class TestHTTPTransportInstantiation:
    """Test HTTPTransport creation and initialization."""

    def test_http_transport_instantiation(self, base_url):
        """Test 1: HTTPTransport can be instantiated with base_url."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)
        assert transport is not None
        assert hasattr(transport, "_base_url")

    def test_http_transport_inherits_from_transport_abc(self, base_url):
        """Test 2: HTTPTransport inherits from Transport ABC."""
        if HTTPTransport is None or Transport is None:
            pytest.skip("HTTPTransport or Transport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)
        assert isinstance(transport, Transport)

    def test_http_transport_starts_in_not_ready_state(self, base_url):
        """Test 3: HTTPTransport starts in not-ready state before connect()."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)
        assert not transport.is_ready()


# ============================================
# Connection Management Tests
# ============================================


class TestHTTPTransportConnection:
    """Test HTTPTransport connection lifecycle."""

    @pytest.mark.anyio
    async def test_connect_creates_aiohttp_session(self, base_url):
        """Test 4: connect() creates aiohttp.ClientSession."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Verify session was created
            mock_session_class.assert_called_once()
            assert hasattr(transport, "_session")

    @pytest.mark.anyio
    async def test_connect_makes_transport_ready(self, base_url):
        """Test 5: connect() makes transport ready."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ):
            assert not transport.is_ready()

            await transport.connect()

            assert transport.is_ready()

    @pytest.mark.anyio
    async def test_connect_is_idempotent(self, base_url):
        """Test 6: connect() can be called multiple times safely."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # Call connect multiple times
            await transport.connect()
            await transport.connect()
            await transport.connect()

            # Session should only be created once
            assert mock_session_class.call_count == 1
            assert transport.is_ready()


# ============================================
# Write Operation Tests
# ============================================


class TestHTTPTransportWrite:
    """Test HTTPTransport write operations."""

    @pytest.mark.anyio
    async def test_write_sends_post_request_to_control_endpoint(
        self, base_url, sample_json_messages
    ):
        """Test 7: write() sends POST request to /control endpoint."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_response = create_mock_post_response(status=200)

            mock_session.post = MagicMock(return_value=mock_response)
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Write a message
            test_message = sample_json_messages[0]
            await transport.write(test_message)

            # Verify POST was called with correct URL and data
            mock_session.post.assert_called_once()
            call_args = mock_session.post.call_args

            # Check URL
            assert call_args[0][0] == f"{base_url}/control"

            # Check data (should be JSON with 'data' key)
            assert "json" in call_args[1] or "data" in call_args[1]

    @pytest.mark.anyio
    async def test_write_before_connect_raises_error(self, base_url):
        """Test 8: write() before connect() raises RuntimeError."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        # Try to write without connecting
        with pytest.raises(RuntimeError, match="not connected"):
            await transport.write("test message")

    @pytest.mark.anyio
    async def test_write_with_connection_error_handling(self, base_url):
        """Test 9: write() handles connection errors gracefully."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()

            # Simulate connection error
            import aiohttp

            mock_session.post.side_effect = aiohttp.ClientError("Connection failed")
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Write should raise ConnectionError
            with pytest.raises(ConnectionError, match="Connection failed"):
                await transport.write("test message")


# ============================================
# Read Messages (SSE) Tests
# ============================================


class TestHTTPTransportReadMessages:
    """Test HTTPTransport read_messages() with SSE parsing."""

    @pytest.mark.anyio
    async def test_read_messages_connects_to_stream_sse_endpoint(self, base_url):
        """Test 10: read_messages() connects to /stream SSE endpoint."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_response = create_mock_sse_response([])  # Empty stream

            mock_session.get = MagicMock(return_value=mock_response)
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Start reading messages (will get none in this test)
            messages_read = []
            try:
                with anyio.fail_after(0.1):
                    async for msg in transport.read_messages():
                        messages_read.append(msg)
                        break
            except TimeoutError:
                pass

            # Verify GET was called with /stream endpoint
            mock_session.get.assert_called_once()
            call_args = mock_session.get.call_args
            assert call_args[0][0] == f"{base_url}/stream"

    @pytest.mark.anyio
    async def test_read_messages_parses_sse_format(
        self, base_url, sample_json_messages
    ):
        """Test 11: read_messages() parses SSE format with 'data: ' prefix."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            sse_lines = [
                b'data: {"request_id": "req_1", "type": "question"}\n',
                b"\n",
                b'data: {"request_id": "req_2", "type": "approval"}\n',
                b"\n",
            ]
            mock_response = create_mock_sse_response(sse_lines)
            mock_session.get = MagicMock(return_value=mock_response)
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Read messages
            messages_read = []
            with anyio.fail_after(1.0):
                async for msg in transport.read_messages():
                    messages_read.append(msg)
                    if len(messages_read) >= 2:
                        break

            # Verify 'data: ' prefix was stripped
            assert len(messages_read) == 2
            assert messages_read[0] == '{"request_id": "req_1", "type": "question"}'
            assert messages_read[1] == '{"request_id": "req_2", "type": "approval"}'

    @pytest.mark.anyio
    async def test_read_messages_skips_empty_lines_and_comments(self, base_url):
        """Test 12: read_messages() skips empty lines and SSE comments."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            # Mock SSE stream with empty lines and comments
            sse_lines = [
                b'data: {"request_id": "req_1"}\n',
                b"\n",  # Empty line - should skip
                b": this is a comment\n",  # Comment - should skip
                b"\n",  # Another empty line
                b'data: {"request_id": "req_2"}\n',
                b": another comment\n",  # Another comment
                b"\n",
            ]

            mock_response = create_mock_sse_response(sse_lines)
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Read messages
            messages_read = []
            with anyio.fail_after(1.0):
                async for msg in transport.read_messages():
                    messages_read.append(msg)
                    if len(messages_read) >= 2:
                        break

            # Verify only data lines were returned (comments and empty lines skipped)
            assert len(messages_read) == 2
            assert messages_read[0] == '{"request_id": "req_1"}'
            assert messages_read[1] == '{"request_id": "req_2"}'

    @pytest.mark.anyio
    async def test_read_messages_before_connect_raises_error(self, base_url):
        """Test 13: read_messages() before connect() raises RuntimeError."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        # Try to read without connecting
        with pytest.raises(RuntimeError, match="not connected"):
            async for _ in transport.read_messages():
                break


# ============================================
# Close and Cleanup Tests
# ============================================


class TestHTTPTransportClose:
    """Test HTTPTransport close() and cleanup."""

    @pytest.mark.anyio
    async def test_close_closes_aiohttp_session(self, base_url):
        """Test 14: close() closes aiohttp session."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session.closed = False
            mock_session_class.return_value = mock_session

            await transport.connect()
            assert transport.is_ready()

            await transport.close()

            # Verify session.close() was called
            mock_session.close.assert_called_once()
            assert not transport.is_ready()

    @pytest.mark.anyio
    async def test_close_is_idempotent(self, base_url):
        """Test 15: close() can be called multiple times safely."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session.closed = False
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Call close multiple times
            await transport.close()
            await transport.close()
            await transport.close()

            # Should not raise error and is_ready should be False
            assert not transport.is_ready()

            # Session.close() should be called (but may be guarded internally)
            # Implementation may choose to only call it once
            assert mock_session.close.call_count >= 1


# ============================================
# Additional Edge Cases
# ============================================


class TestHTTPTransportEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.anyio
    async def test_write_after_close_raises_error(self, base_url):
        """Test that write() after close() raises error."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ):
            await transport.connect()
            await transport.close()

            # Write after close should raise error
            with pytest.raises(RuntimeError, match="not connected"):
                await transport.write("test message")

    @pytest.mark.anyio
    async def test_write_with_invalid_url(self, base_url):
        """Test write() with server error response."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_response = create_mock_post_response(status=500)
            mock_session.post.return_value = mock_response
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Implementation may or may not raise error for 500 status
            # This documents expected behavior (test may need adjustment)
            try:
                await transport.write("test message")
            except ConnectionError:
                # If implementation raises on error status, that's valid
                pass

    @pytest.mark.anyio
    async def test_read_messages_with_malformed_sse(self, base_url):
        """Test read_messages() with malformed SSE data."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()  # Mock SSE stream with malformed data
            mock_session.close = AsyncMock()
            sse_lines = [
                b'data: {"request_id": "req_1"}\n',
                b"malformed line without data prefix\n",  # Should skip
                b'data: {"request_id": "req_2"}\n',
            ]

            mock_response = create_mock_sse_response(sse_lines)
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Read messages
            messages_read = []
            with anyio.fail_after(1.0):
                async for msg in transport.read_messages():
                    messages_read.append(msg)
                    if len(messages_read) >= 2:
                        break

            # Should only get valid data lines
            assert len(messages_read) == 2
            assert messages_read[0] == '{"request_id": "req_1"}'
            assert messages_read[1] == '{"request_id": "req_2"}'

    @pytest.mark.anyio
    async def test_full_lifecycle_with_http_transport(
        self, base_url, sample_json_messages
    ):
        """Test complete lifecycle: connect -> write -> read -> close."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()

            # Mock POST response
            mock_post_response = create_mock_post_response(status=200)
            mock_session.post.return_value = mock_post_response

            # Mock SSE stream response
            sse_lines = [
                b'data: {"response": "answer_1"}\n',
                b"\n",
            ]
            mock_get_response = create_mock_sse_response(sse_lines)
            mock_session.get.return_value = mock_get_response

            mock_session.closed = False
            mock_session_class.return_value = mock_session

            # 1. Connect
            await transport.connect()
            assert transport.is_ready()

            # 2. Write message
            await transport.write(sample_json_messages[0])

            # 3. Read messages
            messages_read = []
            with anyio.fail_after(1.0):
                async for msg in transport.read_messages():
                    messages_read.append(msg)
                    if len(messages_read) >= 1:
                        break

            assert len(messages_read) == 1
            assert messages_read[0] == '{"response": "answer_1"}'

            # 4. Close
            await transport.close()
            assert not transport.is_ready()


# ============================================
# Performance and Concurrency Tests
# ============================================


class TestHTTPTransportPerformance:
    """Test performance characteristics."""

    @pytest.mark.anyio
    async def test_concurrent_writes(self, base_url):
        """Test concurrent write operations."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_response = create_mock_post_response(status=200)
            mock_session.post.return_value = mock_response
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Write 10 messages concurrently
            async def write_message(msg: str):
                await transport.write(msg)

            async with anyio.create_task_group() as tg:
                for i in range(10):
                    tg.start_soon(write_message, f'{{"msg": {i}}}')

            # All writes should complete
            assert mock_session.post.call_count == 10

    @pytest.mark.anyio
    async def test_write_large_message(self, base_url):
        """Test writing large JSON message."""
        if HTTPTransport is None:
            pytest.skip("HTTPTransport not yet implemented")

        transport = HTTPTransport(base_url=base_url, allow_insecure=True)

        with patch(
            "kaizen.core.autonomy.control.transports.http.aiohttp.ClientSession"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_response = create_mock_post_response(status=200)
            mock_session.post.return_value = mock_response
            mock_session_class.return_value = mock_session

            await transport.connect()

            # Large message (1MB of JSON)
            large_data = {"data": "x" * (1024 * 1024)}
            large_message = json.dumps(large_data)

            await transport.write(large_message)

            # Should complete without error
            mock_session.post.assert_called_once()
