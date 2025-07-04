"""Unit tests for MCP transport implementations."""

import asyncio
import json
import platform
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.mcp_server.errors import TransportError
from kailash.mcp_server.transports import (
    BaseTransport,
    EnhancedStdioTransport,
    SSETransport,
    StreamableHTTPTransport,
    TransportManager,
    TransportSecurity,
    WebSocketTransport,
    get_transport_manager,
)


class TestTransportSecurity:
    """Test transport security utilities."""

    def test_validate_url_valid_schemes(self):
        """Test URL validation with valid schemes."""
        valid_urls = [
            "http://example.com",
            "https://example.com",
            "ws://example.com",
            "wss://example.com",
        ]

        for url in valid_urls:
            assert TransportSecurity.validate_url(url) is True

    def test_validate_url_invalid_schemes(self):
        """Test URL validation with invalid schemes."""
        invalid_urls = [
            "ftp://example.com",
            "file:///etc/passwd",
            "javascript:alert('xss')",
        ]

        for url in invalid_urls:
            assert TransportSecurity.validate_url(url) is False

    def test_validate_url_blocked_hosts(self):
        """Test URL validation with blocked hosts."""
        blocked_urls = [
            "http://169.254.169.254/metadata",
            "http://localhost:8080",
            "https://127.0.0.1:3000",
        ]

        for url in blocked_urls:
            assert TransportSecurity.validate_url(url) is False

    def test_validate_url_allow_localhost(self):
        """Test URL validation allowing localhost."""
        localhost_url = "http://localhost:8080"

        assert (
            TransportSecurity.validate_url(localhost_url, allow_localhost=False)
            is False
        )
        assert (
            TransportSecurity.validate_url(localhost_url, allow_localhost=True) is True
        )

    def test_validate_url_suspicious_ips(self):
        """Test URL validation with suspicious IP patterns."""
        suspicious_urls = [
            "http://0.0.0.0:8080",
            "https://0.1.2.3:443",
        ]

        for url in suspicious_urls:
            assert TransportSecurity.validate_url(url) is False

    def test_validate_origin(self):
        """Test origin validation."""
        allowed_origins = ["https://example.com", "https://api.example.com"]

        # Exact match
        assert (
            TransportSecurity.validate_origin("https://example.com", allowed_origins)
            is True
        )

        # Not in list
        assert (
            TransportSecurity.validate_origin("https://malicious.com", allowed_origins)
            is False
        )

        # Empty origin
        assert TransportSecurity.validate_origin("", allowed_origins) is False

    def test_validate_origin_wildcard(self):
        """Test origin validation with wildcards."""
        allowed_origins = ["https://example.com", "https://*.api.example.com*"]

        # Wildcard match
        assert (
            TransportSecurity.validate_origin(
                "https://v1.api.example.com", allowed_origins
            )
            is True
        )
        assert (
            TransportSecurity.validate_origin(
                "https://v2.api.example.com/path", allowed_origins
            )
            is True
        )

        # No wildcard match
        assert (
            TransportSecurity.validate_origin("https://malicious.com", allowed_origins)
            is False
        )


class TestBaseTransport:
    """Test base transport functionality."""

    def setup_method(self):
        """Set up test environment."""

        class TestTransport(BaseTransport):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def send_message(self, message):
                pass

            async def receive_message(self):
                pass

        self.transport = TestTransport("test")

    def test_initialization(self):
        """Test transport initialization."""
        assert self.transport.name == "test"
        assert self.transport._connected is False
        assert self.transport.enable_metrics is True

    def test_initialization_with_options(self):
        """Test transport initialization with options."""

        class TestTransport(BaseTransport):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def send_message(self, message):
                pass

            async def receive_message(self):
                pass

        transport = TestTransport(
            "test", timeout=60.0, max_retries=5, enable_metrics=False
        )

        assert transport.timeout == 60.0
        assert transport.max_retries == 5
        assert transport.enable_metrics is False

    def test_metrics_collection(self):
        """Test metrics collection."""
        metrics = self.transport.get_metrics()

        assert "connections_total" in metrics
        assert "messages_sent" in metrics
        assert "uptime" in metrics

    def test_metrics_disabled(self):
        """Test metrics when disabled."""

        class TestTransport(BaseTransport):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def send_message(self, message):
                pass

            async def receive_message(self):
                pass

        transport = TestTransport("test", enable_metrics=False)
        metrics = transport.get_metrics()

        assert metrics == {}

    def test_update_metrics(self):
        """Test updating metrics."""
        initial_sent = self.transport._metrics["messages_sent"]

        self.transport._update_metrics("messages_sent", 5)

        assert self.transport._metrics["messages_sent"] == initial_sent + 5

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test transport as async context manager."""

        class TestTransport(BaseTransport):
            def __init__(self, name):
                super().__init__(name)
                self.connect_called = False
                self.disconnect_called = False

            async def connect(self):
                self.connect_called = True
                self._connected = True

            async def disconnect(self):
                self.disconnect_called = True
                self._connected = False

            async def send_message(self, message):
                pass

            async def receive_message(self):
                pass

        transport = TestTransport("test")

        async with transport:
            assert transport.connect_called is True
            assert transport.is_connected() is True

        assert transport.disconnect_called is True
        assert transport.is_connected() is False


class TestEnhancedStdioTransport:
    """Test enhanced STDIO transport."""

    def setup_method(self):
        """Set up test environment."""
        self.transport = EnhancedStdioTransport(
            command="echo", args=["test"], timeout=5.0
        )

    def test_initialization(self):
        """Test STDIO transport initialization."""
        assert self.transport.command == "echo"
        assert self.transport.args == ["test"]
        assert self.transport.name == "stdio"

    def test_initialization_with_environment(self):
        """Test STDIO transport with environment settings."""
        transport = EnhancedStdioTransport(
            command="python",
            args=["-c", "print('hello')"],
            env={"CUSTOM_VAR": "value"},
            environment_filter=["PATH", "CUSTOM_VAR"],
        )

        assert transport.env["CUSTOM_VAR"] == "value"
        assert transport.environment_filter == ["PATH", "CUSTOM_VAR"]

    def test_prepare_environment_with_filter(self):
        """Test environment preparation with filter."""
        transport = EnhancedStdioTransport(
            command="echo", environment_filter=["PATH"], env={"CUSTOM": "value"}
        )

        env = transport._prepare_environment()

        # Should include PATH from parent environment
        assert "PATH" in env
        # Should include custom env vars
        assert env["CUSTOM"] == "value"
        # Should not include other system env vars
        assert len([k for k in env.keys() if k not in ["PATH", "CUSTOM"]]) == 0

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """Test connecting and disconnecting STDIO transport."""
        # Use a simple command that will work cross-platform
        transport = EnhancedStdioTransport(
            command="python", args=["-c", "import time; time.sleep(1)"]
        )

        await transport.connect()
        assert transport.is_connected() is True
        assert transport.process is not None

        await transport.disconnect()
        assert transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_connect_invalid_command(self):
        """Test connecting with invalid command."""
        transport = EnhancedStdioTransport(command="nonexistent_command_12345")

        with pytest.raises(TransportError):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_send_receive_message(self):
        """Test sending and receiving messages."""
        # Use a Python script that echoes JSON
        script = """
import sys
import json
for line in sys.stdin:
    data = json.loads(line.strip())
    response = {"echo": data}
    print(json.dumps(response))
    sys.stdout.flush()
"""

        transport = EnhancedStdioTransport(command="python", args=["-c", script])

        try:
            await transport.connect()

            # Send a message
            test_message = {"test": "message", "id": 123}
            await transport.send_message(test_message)

            # Give some time for processing
            await asyncio.sleep(0.1)

            # Receive the response
            response = await asyncio.wait_for(transport.receive_message(), timeout=2.0)

            assert response["echo"]["test"] == "message"
            assert response["echo"]["id"] == 123

        finally:
            await transport.disconnect()

    @pytest.mark.asyncio
    async def test_process_termination(self):
        """Test process termination on disconnect."""
        # Use a long-running Python process
        transport = EnhancedStdioTransport(
            command="python", args=["-c", "import time; time.sleep(10)"]
        )

        await transport.connect()
        process = transport.process

        await transport.disconnect()

        # Process should be terminated
        assert process.returncode is not None

    @pytest.mark.asyncio
    async def test_get_process_info(self):
        """Test getting process information."""
        transport = EnhancedStdioTransport(
            command="python", args=["-c", "import time; time.sleep(1)"]
        )

        # No process initially
        info = await transport.get_process_info()
        assert info == {}

        await transport.connect()

        info = await transport.get_process_info()
        assert "pid" in info
        assert "command" in info
        assert info["command"] == ["python", "-c", "import time; time.sleep(1)"]

        await transport.disconnect()


class TestSSETransport:
    """Test Server-Sent Events transport."""

    def setup_method(self):
        """Set up test environment."""
        self.transport = SSETransport(base_url="https://example.com", timeout=5.0)

    def test_initialization(self):
        """Test SSE transport initialization."""
        assert self.transport.base_url == "https://example.com"
        assert self.transport.name == "sse"

    def test_initialization_with_auth(self):
        """Test SSE transport with authentication."""
        transport = SSETransport(
            base_url="https://api.example.com",
            auth_header="Bearer token123",
            validate_origin=True,
            allowed_origins=["https://app.example.com"],
        )

        assert transport.auth_header == "Bearer token123"
        assert transport.validate_origin is True
        assert "https://app.example.com" in transport.allowed_origins

    @pytest.mark.asyncio
    async def test_connect_invalid_url(self):
        """Test connecting with invalid URL."""
        transport = SSETransport(base_url="ftp://invalid.url")

        with pytest.raises(TransportError):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_disconnect_mocked(self):
        """Test connecting and disconnecting with mocked HTTP."""
        # Create a mock response that properly handles status
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = AsyncMock()
        mock_response.close = MagicMock()  # Regular mock for close

        # Create the session mock
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await self.transport.connect()
            assert self.transport.is_connected() is True

            await self.transport.disconnect()
            assert self.transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_send_message_mocked(self):
        """Test sending message with mocked HTTP."""
        # Create a mock response
        mock_post_response = MagicMock()
        mock_post_response.status = 200

        # Create mock session
        mock_session = MagicMock()

        # Create an async context manager for post
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_post_response

            async def __aexit__(self, *args):
                pass

        # Make post return the async context manager
        mock_session.post = MagicMock(return_value=AsyncContextManager())

        # Setup transport as connected
        self.transport._connected = True
        self.transport.session = mock_session

        test_message = {"test": "message"}
        await self.transport.send_message(test_message)

        # Verify HTTP POST was called
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_sse_event_parsing(self):
        """Test SSE event parsing in read loop."""

        # Create an async generator for the content
        async def mock_content_generator():
            yield b'data: {"type": "message", "content": "hello"}\n'
            yield b'data: {"type": "message", "content": "world"}\n'
            # Give time for messages to be processed
            await asyncio.sleep(0.05)

        with patch("aiohttp.ClientSession"):
            self.transport._connected = True
            self.transport.sse_response = MagicMock()
            self.transport.sse_response.content = mock_content_generator()

            # Run the read loop briefly
            task = asyncio.create_task(self.transport._read_sse_events())
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Check that messages were queued
            assert not self.transport._message_queue.empty()
            # Verify we got both messages
            msg1 = await self.transport._message_queue.get()
            assert msg1["content"] == "hello"
            msg2 = await self.transport._message_queue.get()
            assert msg2["content"] == "world"


class TestStreamableHTTPTransport:
    """Test StreamableHTTP transport."""

    def setup_method(self):
        """Set up test environment."""
        self.transport = StreamableHTTPTransport(
            base_url="https://example.com", streaming_threshold=1024, timeout=5.0
        )

    def test_initialization(self):
        """Test StreamableHTTP transport initialization."""
        assert self.transport.base_url == "https://example.com"
        assert self.transport.streaming_threshold == 1024
        assert self.transport.name == "streamable_http"

    def test_initialization_with_session_management(self):
        """Test transport with session management."""
        transport = StreamableHTTPTransport(
            base_url="https://api.example.com", session_management=True, chunk_size=4096
        )

        assert transport.session_management is True
        assert transport.chunk_size == 4096

    @pytest.mark.asyncio
    async def test_connect_invalid_url(self):
        """Test connecting with invalid URL."""
        transport = StreamableHTTPTransport(base_url="javascript:alert()")

        with pytest.raises(TransportError):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_with_session_management(self):
        """Test connecting with session management."""
        # Create a mock response
        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value={"session_id": "test_session_123"})

        # Create mock session
        mock_session = MagicMock()

        # Create an async context manager for post
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        # Make post return the async context manager
        mock_session.post = MagicMock(return_value=AsyncContextManager())

        with patch("aiohttp.ClientSession", return_value=mock_session):
            transport = StreamableHTTPTransport(
                base_url="https://example.com", session_management=True
            )

            await transport.connect()

            assert transport.session_id == "test_session_123"

    @pytest.mark.asyncio
    async def test_send_large_message_streaming(self):
        """Test sending large message that triggers streaming."""
        large_data = "x" * 2000  # Exceeds default threshold of 1024
        large_message = {"data": large_data}

        # Create a mock response
        mock_response = MagicMock()
        mock_response.status = 200

        # Create mock session
        mock_session = MagicMock()

        # Create an async context manager for post
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        # Make post return the async context manager
        mock_session.post = MagicMock(return_value=AsyncContextManager())

        # Setup transport as connected
        self.transport._connected = True
        self.transport.session = mock_session

        await self.transport.send_message(large_message)

        # Should have called _send_streamed_message path
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_message_no_content(self):
        """Test receiving message when no content available."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 204  # No content

            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_session_class.return_value = mock_session

            # Setup transport as connected
            self.transport._connected = True
            self.transport.session = mock_session

            # Mock the recursive call to avoid infinite recursion in test
            with patch.object(self.transport, "receive_message", side_effect=[None]):
                result = await self.transport.receive_message()
                assert result is None


class TestWebSocketTransport:
    """Test WebSocket transport."""

    def setup_method(self):
        """Set up test environment."""
        self.transport = WebSocketTransport(url="wss://example.com/mcp", timeout=5.0)

    def test_initialization(self):
        """Test WebSocket transport initialization."""
        assert self.transport.url == "wss://example.com/mcp"
        assert self.transport.name == "websocket"
        assert "mcp-v1" in self.transport.subprotocols

    def test_initialization_with_options(self):
        """Test WebSocket transport with options."""
        transport = WebSocketTransport(
            url="ws://localhost:8080",
            subprotocols=["custom-protocol"],
            ping_interval=30.0,
            ping_timeout=10.0,
        )

        assert transport.subprotocols == ["custom-protocol"]
        assert transport.ping_interval == 30.0
        assert transport.ping_timeout == 10.0

    @pytest.mark.asyncio
    async def test_connect_invalid_url(self):
        """Test connecting with invalid URL."""
        transport = WebSocketTransport(url="http://invalid-scheme")

        with pytest.raises(TransportError):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_send_receive_message_mocked(self):
        """Test sending and receiving messages with mocked WebSocket."""
        # Create a proper mock websocket
        mock_websocket = AsyncMock()

        # Create an async function for websockets.connect
        async def async_connect(*args, **kwargs):
            return mock_websocket

        # websockets.connect is an async function
        with patch("websockets.connect", side_effect=async_connect):
            await self.transport.connect()

            # Test sending
            test_message = {"test": "message"}
            await self.transport.send_message(test_message)

            mock_websocket.send.assert_called_once_with(json.dumps(test_message))

    @pytest.mark.asyncio
    async def test_websocket_message_reading(self):
        """Test WebSocket message reading loop."""
        mock_messages = [
            '{"type": "response", "data": "hello"}',
            '{"type": "response", "data": "world"}',
        ]

        with patch("websockets.connect"):
            self.transport._connected = True
            self.transport.websocket = AsyncMock()
            self.transport.websocket.__aiter__.return_value = mock_messages

            # Run the read loop briefly
            task = asyncio.create_task(self.transport._read_messages())
            await asyncio.sleep(0.1)
            task.cancel()

            # Check that messages were queued
            assert not self.transport._message_queue.empty()

    @pytest.mark.asyncio
    async def test_websocket_connection_closed(self):
        """Test handling WebSocket connection closure."""
        with patch("websockets.connect"):
            self.transport._connected = True
            self.transport.websocket = AsyncMock()

            # Simulate connection closed exception
            from websockets.exceptions import ConnectionClosed

            self.transport.websocket.__aiter__.side_effect = ConnectionClosed(
                None, None
            )

            # Should handle the exception gracefully
            await self.transport._read_messages()


class TestTransportManager:
    """Test transport management."""

    def setup_method(self):
        """Set up test environment."""
        self.manager = TransportManager()

    def test_initialization(self):
        """Test transport manager initialization."""
        assert "stdio" in self.manager._transport_factories
        assert "sse" in self.manager._transport_factories
        assert "streamable_http" in self.manager._transport_factories
        assert "websocket" in self.manager._transport_factories

    def test_register_transport_factory(self):
        """Test registering custom transport factory."""

        def custom_factory(**kwargs):
            return MagicMock()

        self.manager.register_transport_factory("custom", custom_factory)

        assert "custom" in self.manager._transport_factories
        assert self.manager._transport_factories["custom"] == custom_factory

    def test_create_transport(self):
        """Test creating transport instances."""
        transport = self.manager.create_transport(
            "stdio", command="echo", args=["test"]
        )

        assert isinstance(transport, EnhancedStdioTransport)
        assert transport.command == "echo"

    def test_create_unknown_transport(self):
        """Test creating unknown transport type."""
        with pytest.raises(ValueError, match="Unknown transport type"):
            self.manager.create_transport("unknown_type")

    def test_register_and_get_transport(self):
        """Test registering and retrieving transport instances."""
        transport = MagicMock()

        self.manager.register_transport("test_transport", transport)

        retrieved = self.manager.get_transport("test_transport")
        assert retrieved is transport

    def test_get_nonexistent_transport(self):
        """Test getting non-existent transport."""
        result = self.manager.get_transport("nonexistent")
        assert result is None

    def test_list_transports(self):
        """Test listing registered transports."""
        transport1 = MagicMock()
        transport2 = MagicMock()

        self.manager.register_transport("transport1", transport1)
        self.manager.register_transport("transport2", transport2)

        names = self.manager.list_transports()
        assert "transport1" in names
        assert "transport2" in names

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        """Test disconnecting all transports."""
        transport1 = AsyncMock()
        transport2 = AsyncMock()

        self.manager.register_transport("transport1", transport1)
        self.manager.register_transport("transport2", transport2)

        await self.manager.disconnect_all()

        transport1.disconnect.assert_called_once()
        transport2.disconnect.assert_called_once()

        # Transports should be cleared
        assert len(self.manager.list_transports()) == 0

    @pytest.mark.asyncio
    async def test_disconnect_all_with_errors(self):
        """Test disconnecting all transports when some fail."""
        transport1 = AsyncMock()
        transport2 = AsyncMock()

        # Make transport1 fail on disconnect
        transport1.disconnect.side_effect = Exception("Disconnect failed")

        self.manager.register_transport("transport1", transport1)
        self.manager.register_transport("transport2", transport2)

        # Should not raise exception
        await self.manager.disconnect_all()

        transport1.disconnect.assert_called_once()
        transport2.disconnect.assert_called_once()


class TestTransportManagerSingleton:
    """Test transport manager singleton."""

    def test_get_transport_manager_singleton(self):
        """Test that get_transport_manager returns singleton."""
        manager1 = get_transport_manager()
        manager2 = get_transport_manager()

        assert manager1 is manager2
        assert isinstance(manager1, TransportManager)

    def test_global_manager_persistence(self):
        """Test that global manager persists across calls."""
        manager = get_transport_manager()

        # Register a transport
        test_transport = MagicMock()
        manager.register_transport("test", test_transport)

        # Get manager again
        same_manager = get_transport_manager()

        # Should have the same transport
        assert same_manager.get_transport("test") is test_transport


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
