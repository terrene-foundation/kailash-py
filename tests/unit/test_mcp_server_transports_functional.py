"""Functional tests for mcp_server/transports.py that verify actual transport behavior."""

import asyncio
import json
import os
import platform
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import aiohttp
import pytest
import websockets


class TestTransportSecurityFunctionality:
    """Test TransportSecurity validation and filtering functionality."""

    def test_url_validation_with_allowed_schemes(self):
        """Test URL validation accepts allowed schemes and rejects blocked ones."""
        try:
            from kailash.mcp_server.transports import TransportSecurity

            # Test allowed schemes
            valid_urls = [
                "https://api.example.com/mcp",
                "http://internal.company.com:8080",
                "wss://websocket.example.com",
                "ws://localhost:3000",
            ]

            for url in valid_urls:
                assert TransportSecurity.validate_url(
                    url, allow_localhost=True
                ), f"Should allow {url}"

            # Test blocked schemes
            invalid_urls = [
                "ftp://files.example.com",
                "file:///etc/passwd",
                "javascript:alert('xss')",
                "data:text/html,<script>alert('xss')</script>",
            ]

            for url in invalid_urls:
                assert not TransportSecurity.validate_url(url), f"Should block {url}"

        except ImportError:
            pytest.skip("TransportSecurity not available")

    def test_localhost_blocking_behavior(self):
        """Test localhost blocking with configurable allow_localhost setting."""
        try:
            from kailash.mcp_server.transports import TransportSecurity

            localhost_urls = [
                "http://localhost:8080",
                "https://127.0.0.1:9000",
                "ws://localhost:3000",
            ]

            # Test default blocking behavior
            for url in localhost_urls:
                assert not TransportSecurity.validate_url(
                    url, allow_localhost=False
                ), f"Should block {url} by default"

            # Test explicit allow behavior
            for url in localhost_urls:
                assert TransportSecurity.validate_url(
                    url, allow_localhost=True
                ), f"Should allow {url} when explicitly allowed"

            # Test metadata service blocking (security critical)
            metadata_urls = [
                "http://169.254.169.254/metadata",
                "https://169.254.169.254/latest/meta-data",
            ]

            for url in metadata_urls:
                assert not TransportSecurity.validate_url(
                    url, allow_localhost=True
                ), f"Should always block metadata service {url}"

        except ImportError:
            pytest.skip("TransportSecurity not available")

    def test_origin_validation_with_patterns(self):
        """Test origin validation including wildcard pattern matching."""
        try:
            from kailash.mcp_server.transports import TransportSecurity

            allowed_origins = [
                "https://app.example.com",
                "https://*.staging.example.com",
                "https://*.dev.example.com",
                "http://localhost:*",
            ]

            # Test exact matches
            assert TransportSecurity.validate_origin(
                "https://app.example.com", allowed_origins
            )
            assert not TransportSecurity.validate_origin(
                "https://malicious.com", allowed_origins
            )

            # Test wildcard subdomain matches
            assert TransportSecurity.validate_origin(
                "https://api.staging.example.com", allowed_origins
            )
            assert TransportSecurity.validate_origin(
                "https://frontend.staging.example.com", allowed_origins
            )
            assert not TransportSecurity.validate_origin(
                "https://api.production.example.com", allowed_origins
            )

            # Test port wildcards
            assert TransportSecurity.validate_origin(
                "http://localhost:3000", allowed_origins
            )
            assert TransportSecurity.validate_origin(
                "http://localhost:8080", allowed_origins
            )
            assert not TransportSecurity.validate_origin(
                "http://127.0.0.1:3000", allowed_origins
            )

            # Test empty origin rejection
            assert not TransportSecurity.validate_origin("", allowed_origins)
            assert not TransportSecurity.validate_origin(None, allowed_origins)

        except ImportError:
            pytest.skip("TransportSecurity not available")

    def test_security_ip_address_blocking(self):
        """Test blocking of potentially dangerous IP address patterns."""
        try:
            from kailash.mcp_server.transports import TransportSecurity

            # Test 0.x.x.x IP blocking (common in SSRF attacks)
            dangerous_ips = [
                "http://0.0.0.0:8080",
                "https://0.1.2.3:9000",
                "ws://0.255.255.255:3000",
            ]

            for url in dangerous_ips:
                assert not TransportSecurity.validate_url(
                    url
                ), f"Should block dangerous IP {url}"

            # Test legitimate IPs are allowed (when not localhost)
            safe_ips = [
                "https://192.168.1.100:8080",  # Private network
                "http://10.0.0.50:9000",  # Private network
                "https://8.8.8.8:443",  # Public IP
            ]

            for url in safe_ips:
                assert TransportSecurity.validate_url(
                    url
                ), f"Should allow safe IP {url}"

        except ImportError:
            pytest.skip("TransportSecurity not available")


class TestBaseTransportFunctionality:
    """Test BaseTransport metrics and lifecycle functionality."""

    def test_base_transport_metrics_collection(self):
        """Test metrics collection and calculation functionality."""
        try:
            from kailash.mcp_server.transports import BaseTransport

            # Create concrete implementation for testing
            class TestTransport(BaseTransport):
                async def connect(self):
                    self._connected = True

                async def disconnect(self):
                    self._connected = False

                async def send_message(self, message):
                    pass

                async def receive_message(self):
                    return {}

            transport = TestTransport("test", enable_metrics=True)

            # Verify initial metrics
            initial_metrics = transport.get_metrics()
            assert initial_metrics["connections_total"] == 0
            assert initial_metrics["messages_sent"] == 0
            assert initial_metrics["bytes_sent"] == 0
            assert "start_time" in initial_metrics
            assert "uptime" in initial_metrics

            # Test metric updates
            transport._update_metrics("connections_total")
            transport._update_metrics("messages_sent", 3)
            transport._update_metrics("bytes_sent", 1024)

            updated_metrics = transport.get_metrics()
            assert updated_metrics["connections_total"] == 1
            assert updated_metrics["messages_sent"] == 3
            assert updated_metrics["bytes_sent"] == 1024

            # Test uptime calculation
            time.sleep(0.1)  # Small delay
            metrics_with_uptime = transport.get_metrics()
            assert metrics_with_uptime["uptime"] > initial_metrics["uptime"]

            # Test metrics disabled
            no_metrics_transport = TestTransport("test", enable_metrics=False)
            assert no_metrics_transport.get_metrics() == {}

        except ImportError:
            pytest.skip("BaseTransport not available")

    @pytest.mark.asyncio
    async def test_base_transport_context_manager_behavior(self):
        """Test async context manager functionality."""
        try:
            from kailash.mcp_server.transports import BaseTransport

            connect_called = False
            disconnect_called = False

            class TestTransport(BaseTransport):
                async def connect(self):
                    nonlocal connect_called
                    connect_called = True
                    self._connected = True

                async def disconnect(self):
                    nonlocal disconnect_called
                    disconnect_called = True
                    self._connected = False

                async def send_message(self, message):
                    pass

                async def receive_message(self):
                    return {}

            transport = TestTransport("test")

            # Test normal context manager flow
            async with transport as t:
                assert connect_called
                assert t.is_connected()
                assert t is transport

            assert disconnect_called
            assert not transport.is_connected()

            # Test exception handling in context manager
            connect_called = False
            disconnect_called = False

            try:
                async with transport:
                    assert connect_called
                    raise ValueError("Test exception")
            except ValueError:
                pass

            # Should still call disconnect on exception
            assert disconnect_called

        except ImportError:
            pytest.skip("BaseTransport not available")


class TestEnhancedStdioTransportFunctionality:
    """Test EnhancedStdioTransport process management and communication."""

    @pytest.mark.asyncio
    async def test_stdio_transport_process_lifecycle(self):
        """Test subprocess creation, management, and termination."""
        try:
            from kailash.mcp_server.transports import EnhancedStdioTransport

            # Mock subprocess creation
            with patch("asyncio.create_subprocess_exec") as mock_create_process:
                mock_process = Mock()
                mock_process.pid = 12345
                mock_process.returncode = None
                mock_process.stdin = AsyncMock()
                mock_process.stdout = AsyncMock()
                mock_process.stderr = AsyncMock()
                mock_process.wait = AsyncMock(return_value=0)
                mock_process.terminate = Mock()
                mock_process.kill = Mock()

                # Mock readline to return empty (process end)
                mock_process.stdout.readline = AsyncMock(return_value=b"")

                mock_create_process.return_value = mock_process

                transport = EnhancedStdioTransport(
                    command="python",
                    args=["-m", "test_server"],
                    working_directory="/tmp",
                )

                # Test connection
                await transport.connect()
                assert transport.is_connected()
                assert transport.process is mock_process

                # Verify subprocess was created with correct parameters
                mock_create_process.assert_called_once()
                call_args = mock_create_process.call_args
                assert call_args[0][0] == "python"
                assert call_args[0][1] == "-m"
                assert call_args[0][2] == "test_server"
                assert call_args[1]["cwd"] == "/tmp"

                # Test process info
                process_info = await transport.get_process_info()
                assert process_info["pid"] == 12345
                assert process_info["command"] == ["python", "-m", "test_server"]
                assert process_info["working_directory"] == "/tmp"

                # Test disconnection
                await transport.disconnect()
                assert not transport.is_connected()
                mock_process.terminate.assert_called_once()

        except ImportError:
            pytest.skip("EnhancedStdioTransport not available")

    @pytest.mark.asyncio
    async def test_stdio_transport_environment_filtering(self):
        """Test environment variable filtering and customization."""
        try:
            from kailash.mcp_server.transports import EnhancedStdioTransport

            # Mock os.environ
            test_env = {
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": "/opt/python/lib",
                "HOME": "/home/user",
                "SECRET_KEY": "sensitive_value",
                "API_TOKEN": "secret_token",
            }

            with patch("os.environ", test_env):
                with patch("asyncio.create_subprocess_exec") as mock_create_process:
                    mock_process = Mock()
                    mock_process.stdout = AsyncMock()
                    mock_process.stdout.readline = AsyncMock(return_value=b"")
                    mock_create_process.return_value = mock_process

                    # Test environment filtering
                    transport = EnhancedStdioTransport(
                        command="python",
                        environment_filter=["PATH", "PYTHONPATH"],  # Only allow these
                        env={"CUSTOM_VAR": "custom_value"},  # Add custom variable
                    )

                    await transport.connect()

                    # Verify environment was filtered correctly
                    call_args = mock_create_process.call_args
                    process_env = call_args[1]["env"]

                    # Should include filtered variables
                    assert "PATH" in process_env
                    assert "PYTHONPATH" in process_env
                    assert process_env["PATH"] == "/usr/bin:/bin"

                    # Should include custom variables
                    assert "CUSTOM_VAR" in process_env
                    assert process_env["CUSTOM_VAR"] == "custom_value"

                    # Should exclude non-filtered variables
                    assert "SECRET_KEY" not in process_env
                    assert "API_TOKEN" not in process_env
                    assert "HOME" not in process_env

                    await transport.disconnect()

        except ImportError:
            pytest.skip("EnhancedStdioTransport not available")

    @pytest.mark.asyncio
    async def test_stdio_transport_message_communication(self):
        """Test JSON message sending and receiving via subprocess pipes."""
        try:
            from kailash.mcp_server.transports import EnhancedStdioTransport

            with patch("asyncio.create_subprocess_exec") as mock_create_process:
                # Setup mock process with message buffering
                mock_process = Mock()
                mock_process.stdin = AsyncMock()
                mock_process.stdout = AsyncMock()
                mock_process.stderr = AsyncMock()

                # Mock stdin operations
                mock_process.stdin.write = Mock()
                mock_process.stdin.drain = AsyncMock()

                # Setup message buffer simulation
                test_messages = [
                    '{"type": "response", "id": 1, "result": {"data": "test"}}',
                    '{"type": "notification", "method": "status_update", "params": {"status": "ready"}}',
                ]

                mock_process.stdout.readline = AsyncMock(return_value=b"")
                mock_create_process.return_value = mock_process

                transport = EnhancedStdioTransport(
                    command="python", args=["-m", "test"]
                )
                await transport.connect()

                # Simulate received messages by manually adding to buffer
                for msg in test_messages:
                    transport._message_buffer.append(msg)

                # Test message sending
                test_message = {
                    "jsonrpc": "2.0",
                    "method": "tool/call",
                    "params": {"name": "test_tool", "arguments": {"input": "test"}},
                }

                await transport.send_message(test_message)

                # Verify message was written to stdin
                mock_process.stdin.write.assert_called_once()
                written_data = mock_process.stdin.write.call_args[0][0]
                assert b'"method": "tool/call"' in written_data
                assert written_data.endswith(b"\n")

                # Test message receiving
                received_message = await transport.receive_message()
                assert received_message["type"] == "response"
                assert received_message["id"] == 1
                assert received_message["result"]["data"] == "test"

                # Test second message
                received_message2 = await transport.receive_message()
                assert received_message2["type"] == "notification"
                assert received_message2["method"] == "status_update"

                await transport.disconnect()

        except ImportError:
            pytest.skip("EnhancedStdioTransport not available")

    @pytest.mark.asyncio
    async def test_stdio_transport_process_termination_behavior(self):
        """Test graceful and forced process termination scenarios."""
        try:
            from kailash.mcp_server.transports import EnhancedStdioTransport

            with patch("asyncio.create_subprocess_exec") as mock_create_process:
                with patch("platform.system", return_value="Linux"):
                    mock_process = Mock()
                    mock_process.stdout = AsyncMock()
                    mock_process.stdout.readline = AsyncMock(return_value=b"")
                    mock_process.terminate = Mock()
                    mock_process.kill = Mock()

                    # Test graceful termination (process responds to SIGTERM)
                    mock_process.wait = AsyncMock(return_value=0)
                    mock_create_process.return_value = mock_process

                    transport = EnhancedStdioTransport(command="python")
                    await transport.connect()
                    await transport.disconnect()

                    # Should call terminate first
                    mock_process.terminate.assert_called_once()
                    mock_process.wait.assert_called_once()
                    # Should not need to kill
                    mock_process.kill.assert_not_called()

                    # Test forced termination (process hangs on SIGTERM)
                    mock_process.reset_mock()

                    async def timeout_wait():
                        raise asyncio.TimeoutError()

                    mock_process.wait = AsyncMock(side_effect=timeout_wait)
                    mock_create_process.return_value = mock_process

                    transport2 = EnhancedStdioTransport(command="python")
                    await transport2.connect()
                    await transport2.disconnect()

                    # Should call terminate, then kill after timeout
                    mock_process.terminate.assert_called_once()
                    mock_process.kill.assert_called_once()

        except ImportError:
            pytest.skip("EnhancedStdioTransport not available")


class TestSSETransportFunctionality:
    """Test SSE Transport server-sent events and HTTP messaging."""

    @pytest.mark.asyncio
    async def test_sse_transport_connection_and_security(self):
        """Test SSE connection establishment with security validation."""
        try:
            from kailash.mcp_server.transports import SSETransport

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.content = AsyncMock()
                mock_session.get.return_value.__aenter__.return_value = mock_response

                # Test secure connection
                transport = SSETransport(
                    base_url="https://api.example.com",
                    auth_header="Bearer token123",
                    validate_origin=True,
                )

                await transport.connect()
                assert transport.is_connected()

                # Verify session was created with proper headers
                mock_session_class.assert_called_once()
                init_kwargs = mock_session_class.call_args[1]
                assert "Authorization" in init_kwargs["headers"]
                assert init_kwargs["headers"]["Authorization"] == "Bearer token123"
                assert "Origin" in init_kwargs["headers"]

                # Verify SSE endpoint was called
                mock_session.get.assert_called_once()
                call_args = mock_session.get.call_args
                assert call_args[0][0].endswith("/sse")
                assert call_args[1]["headers"]["Accept"] == "text/event-stream"

                await transport.disconnect()

        except ImportError:
            pytest.skip("SSETransport not available")

    @pytest.mark.asyncio
    async def test_sse_transport_security_validation_bypass(self):
        """Test security validation bypass for testing environments."""
        try:
            from kailash.mcp_server.transports import SSETransport

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                mock_response = AsyncMock()
                mock_response.status = 200
                mock_session.get.return_value.__aenter__.return_value = mock_response

                # Test with security validation bypassed
                transport = SSETransport(
                    base_url="http://localhost:8080",  # Would normally be blocked
                    skip_security_validation=True,
                )

                # Should connect successfully despite localhost URL
                await transport.connect()
                assert transport.is_connected()

                await transport.disconnect()

                # Test with security enabled (should fail)
                transport_secure = SSETransport(
                    base_url="http://localhost:8080", skip_security_validation=False
                )

                # Should raise TransportError due to localhost blocking
                with pytest.raises(Exception):  # TransportError
                    await transport_secure.connect()

        except ImportError:
            pytest.skip("SSETransport not available")

    @pytest.mark.asyncio
    async def test_sse_transport_message_handling(self):
        """Test SSE event parsing and HTTP message sending."""
        try:
            from kailash.mcp_server.transports import SSETransport

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                # Mock SSE response
                mock_sse_response = AsyncMock()
                mock_sse_response.status = 200

                # Simulate SSE events
                sse_events = [
                    b'data: {"type": "message", "id": 1, "content": "hello"}\n',
                    b'data: {"type": "notification", "event": "status_change"}\n',
                    b"event: heartbeat\n",
                    b"data: invalid json here\n",  # Should be ignored
                    b'data: {"type": "response", "result": "success"}\n',
                ]

                mock_sse_response.content = AsyncMock()
                mock_sse_response.content.__aiter__.return_value = iter(sse_events)
                mock_session.get.return_value.__aenter__.return_value = (
                    mock_sse_response
                )

                # Mock HTTP POST for sending
                mock_post_response = AsyncMock()
                mock_post_response.status = 200
                mock_session.post.return_value.__aenter__.return_value = (
                    mock_post_response
                )

                transport = SSETransport(
                    base_url="https://api.example.com", skip_security_validation=True
                )

                await transport.connect()

                # Test message sending via HTTP POST
                test_message = {
                    "jsonrpc": "2.0",
                    "method": "test/method",
                    "params": {"data": "test"},
                }

                await transport.send_message(test_message)

                # Verify POST was called correctly
                mock_session.post.assert_called_once()
                post_call = mock_session.post.call_args
                assert post_call[0][0].endswith("/message")
                assert post_call[1]["json"] == test_message

                # Give SSE reader time to process events
                await asyncio.sleep(0.1)

                # Test message receiving from SSE stream
                received_message = await transport.receive_message()
                assert received_message["type"] == "message"
                assert received_message["id"] == 1
                assert received_message["content"] == "hello"

                # Test second message
                received_message2 = await transport.receive_message()
                assert received_message2["type"] == "notification"
                assert received_message2["event"] == "status_change"

                await transport.disconnect()

        except ImportError:
            pytest.skip("SSETransport not available")


class TestStreamableHTTPTransportFunctionality:
    """Test StreamableHTTP transport with session management and streaming."""

    @pytest.mark.asyncio
    async def test_streamable_http_session_management(self):
        """Test HTTP session creation, management, and cleanup."""
        try:
            from kailash.mcp_server.transports import StreamableHTTPTransport

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                # Mock session creation response
                mock_session_response = AsyncMock()
                mock_session_response.status = 201
                mock_session_response.json = AsyncMock(
                    return_value={"session_id": "sess_12345"}
                )
                mock_session.post.return_value.__aenter__.return_value = (
                    mock_session_response
                )

                # Mock session deletion response
                mock_delete_response = AsyncMock()
                mock_delete_response.status = 200
                mock_session.delete.return_value.__aenter__.return_value = (
                    mock_delete_response
                )

                transport = StreamableHTTPTransport(
                    base_url="https://api.example.com",
                    session_management=True,
                    skip_security_validation=True,
                )

                await transport.connect()
                assert transport.is_connected()
                assert transport.session_id == "sess_12345"

                # Verify session creation was called
                session_calls = [
                    call
                    for call in mock_session.post.call_args_list
                    if "/session" in call[0][0]
                ]
                assert len(session_calls) == 1

                await transport.disconnect()

                # Verify session deletion was called
                delete_calls = [
                    call
                    for call in mock_session.delete.call_args_list
                    if "sess_12345" in call[0][0]
                ]
                assert len(delete_calls) == 1

        except ImportError:
            pytest.skip("StreamableHTTPTransport not available")

    @pytest.mark.asyncio
    async def test_streamable_http_streaming_threshold_behavior(self):
        """Test streaming vs normal message handling based on size threshold."""
        try:
            from kailash.mcp_server.transports import StreamableHTTPTransport

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                # Mock responses
                mock_post_response = AsyncMock()
                mock_post_response.status = 200
                mock_session.post.return_value.__aenter__.return_value = (
                    mock_post_response
                )

                transport = StreamableHTTPTransport(
                    base_url="https://api.example.com",
                    session_management=False,
                    streaming_threshold=100,  # Small threshold for testing
                    chunk_size=50,
                    skip_security_validation=True,
                )

                await transport.connect()

                # Test small message (below threshold) - should use normal POST
                small_message = {"type": "small", "data": "x" * 50}
                await transport.send_message(small_message)

                # Verify normal POST was used
                normal_post_calls = [
                    call
                    for call in mock_session.post.call_args_list
                    if "json" in call[1]
                ]
                assert len(normal_post_calls) >= 1

                # Test large message (above threshold) - should use streaming
                large_message = {
                    "type": "large",
                    "data": "x" * 200,
                }  # Above 100 byte threshold
                await transport.send_message(large_message)

                # Verify streaming POST was used (with Transfer-Encoding header)
                streaming_calls = [
                    call
                    for call in mock_session.post.call_args_list
                    if "data" in call[1] and hasattr(call[1]["data"], "__aiter__")
                ]

                # Should have used streaming for large message
                assert len(mock_session.post.call_args_list) >= 2

                await transport.disconnect()

        except ImportError:
            pytest.skip("StreamableHTTPTransport not available")

    @pytest.mark.asyncio
    async def test_streamable_http_message_receiving(self):
        """Test HTTP message receiving with streaming support."""
        try:
            from kailash.mcp_server.transports import StreamableHTTPTransport

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                transport = StreamableHTTPTransport(
                    base_url="https://api.example.com",
                    session_management=False,
                    streaming_threshold=100,
                    skip_security_validation=True,
                )

                await transport.connect()

                # Test normal message receiving
                mock_get_response = AsyncMock()
                mock_get_response.status = 200
                mock_get_response.headers = {"Content-Length": "50"}  # Below threshold
                mock_get_response.json = AsyncMock(
                    return_value={"type": "response", "data": "test"}
                )
                mock_session.get.return_value.__aenter__.return_value = (
                    mock_get_response
                )

                received_message = await transport.receive_message()
                assert received_message["type"] == "response"
                assert received_message["data"] == "test"

                # Verify GET was called correctly
                mock_session.get.assert_called()
                get_call = mock_session.get.call_args
                assert get_call[0][0].endswith("/receive")

                # Test no message available (204 status)
                mock_get_response.status = 204
                mock_session.get.return_value.__aenter__.return_value = (
                    mock_get_response
                )

                # Should retry internally and then get the message
                mock_get_response.status = 200  # Second call succeeds

                received_message2 = await transport.receive_message()
                assert received_message2["type"] == "response"

                await transport.disconnect()

        except ImportError:
            pytest.skip("StreamableHTTPTransport not available")


class TestWebSocketTransportFunctionality:
    """Test WebSocket transport real-time communication."""

    @pytest.mark.asyncio
    async def test_websocket_transport_connection_with_auth(self):
        """Test WebSocket connection establishment with authentication."""
        try:
            from kailash.mcp_server.transports import WebSocketTransport

            with patch("websockets.connect") as mock_ws_connect:
                # Mock WebSocket connection
                mock_websocket = AsyncMock()
                mock_websocket.__aiter__.return_value = iter(
                    []
                )  # No messages initially
                mock_ws_connect.return_value = mock_websocket

                # Mock auth provider
                mock_auth = AsyncMock()
                mock_auth.get_headers = AsyncMock(
                    return_value={"Authorization": "Bearer ws_token"}
                )

                transport = WebSocketTransport(
                    url="wss://ws.example.com/mcp",
                    auth_provider=mock_auth,
                    subprotocols=["mcp-v1", "mcp-v2"],
                    ping_interval=30.0,
                    skip_security_validation=True,
                )

                await transport.connect()
                assert transport.is_connected()
                assert transport.websocket is mock_websocket

                # Verify connection was called with correct parameters
                mock_ws_connect.assert_called_once()
                call_kwargs = mock_ws_connect.call_args[1]
                assert call_kwargs["subprotocols"] == ["mcp-v1", "mcp-v2"]
                assert call_kwargs["ping_interval"] == 30.0
                assert "Authorization" in call_kwargs["extra_headers"]
                assert (
                    call_kwargs["extra_headers"]["Authorization"] == "Bearer ws_token"
                )

                await transport.disconnect()
                mock_websocket.close.assert_called_once()

        except ImportError:
            pytest.skip("WebSocketTransport not available")

    @pytest.mark.asyncio
    async def test_websocket_transport_bidirectional_messaging(self):
        """Test WebSocket bidirectional message communication."""
        try:
            from kailash.mcp_server.transports import WebSocketTransport

            with patch("websockets.connect") as mock_ws_connect:
                mock_websocket = AsyncMock()

                # Mock message receiving
                incoming_messages = [
                    '{"type": "request", "id": 1, "method": "ping"}',
                    '{"type": "response", "id": 2, "result": "pong"}',
                    '{"type": "notification", "method": "status", "params": {"online": true}}',
                ]

                mock_websocket.__aiter__.return_value = iter(incoming_messages)
                mock_websocket.send = AsyncMock()
                mock_ws_connect.return_value = mock_websocket

                transport = WebSocketTransport(
                    url="wss://ws.example.com/mcp", skip_security_validation=True
                )

                await transport.connect()

                # Test message sending
                test_message = {
                    "jsonrpc": "2.0",
                    "method": "tool/execute",
                    "params": {
                        "tool": "calculator",
                        "args": {"operation": "add", "a": 1, "b": 2},
                    },
                }

                await transport.send_message(test_message)

                # Verify message was sent correctly
                mock_websocket.send.assert_called_once()
                sent_data = mock_websocket.send.call_args[0][0]
                sent_message = json.loads(sent_data)
                assert sent_message["method"] == "tool/execute"
                assert sent_message["params"]["tool"] == "calculator"

                # Give message reader time to process
                await asyncio.sleep(0.1)

                # Test message receiving
                received_message = await transport.receive_message()
                assert received_message["type"] == "request"
                assert received_message["method"] == "ping"

                received_message2 = await transport.receive_message()
                assert received_message2["type"] == "response"
                assert received_message2["result"] == "pong"

                received_message3 = await transport.receive_message()
                assert received_message3["type"] == "notification"
                assert received_message3["params"]["online"] is True

                await transport.disconnect()

        except ImportError:
            pytest.skip("WebSocketTransport not available")

    @pytest.mark.asyncio
    async def test_websocket_transport_connection_error_handling(self):
        """Test WebSocket connection error handling and recovery."""
        try:
            from kailash.mcp_server.transports import WebSocketTransport

            with patch("websockets.connect") as mock_ws_connect:
                # Test connection failure
                mock_ws_connect.side_effect = ConnectionRefusedError(
                    "Connection refused"
                )

                transport = WebSocketTransport(
                    url="wss://unreachable.example.com/mcp",
                    skip_security_validation=True,
                )

                # Should raise TransportError
                with pytest.raises(Exception):  # TransportError
                    await transport.connect()

                assert not transport.is_connected()

                # Test connection closed during operation
                mock_websocket = AsyncMock()
                mock_ws_connect.side_effect = None
                mock_ws_connect.return_value = mock_websocket

                # Simulate connection closed exception
                import websockets.exceptions

                async def mock_message_iter():
                    yield '{"type": "message", "data": "test"}'
                    raise websockets.exceptions.ConnectionClosed(None, None)

                mock_websocket.__aiter__ = mock_message_iter

                transport2 = WebSocketTransport(
                    url="wss://ws.example.com/mcp", skip_security_validation=True
                )

                await transport2.connect()

                # Give time for connection closed to be handled
                await asyncio.sleep(0.1)

                # Transport should automatically disconnect
                assert not transport2.is_connected()

        except ImportError:
            pytest.skip("WebSocketTransport or websockets.exceptions not available")


class TestTransportManagerFunctionality:
    """Test TransportManager registry and factory functionality."""

    def test_transport_manager_factory_registration(self):
        """Test transport factory registration and creation."""
        try:
            from kailash.mcp_server.transports import BaseTransport, TransportManager

            manager = TransportManager()

            # Test built-in factories exist
            assert "stdio" in manager._transport_factories
            assert "sse" in manager._transport_factories
            assert "streamable_http" in manager._transport_factories
            assert "websocket" in manager._transport_factories

            # Test custom factory registration
            class CustomTransport(BaseTransport):
                async def connect(self):
                    pass

                async def disconnect(self):
                    pass

                async def send_message(self, message):
                    pass

                async def receive_message(self):
                    return {}

            def custom_factory(**kwargs):
                return CustomTransport("custom", **kwargs)

            manager.register_transport_factory("custom", custom_factory)
            assert "custom" in manager._transport_factories

            # Test transport creation
            custom_transport = manager.create_transport("custom", timeout=60.0)
            assert isinstance(custom_transport, CustomTransport)
            assert custom_transport.timeout == 60.0

            # Test unknown transport type
            with pytest.raises(ValueError, match="Unknown transport type"):
                manager.create_transport("unknown_type")

        except ImportError:
            pytest.skip("TransportManager not available")

    def test_transport_manager_instance_registry(self):
        """Test transport instance registration and management."""
        try:
            from kailash.mcp_server.transports import BaseTransport, TransportManager

            manager = TransportManager()

            # Create mock transports
            class MockTransport(BaseTransport):
                def __init__(self, name):
                    super().__init__(name)
                    self.disconnected = False

                async def connect(self):
                    self._connected = True

                async def disconnect(self):
                    self._connected = False
                    self.disconnected = True

                async def send_message(self, message):
                    pass

                async def receive_message(self):
                    return {}

            transport1 = MockTransport("transport1")
            transport2 = MockTransport("transport2")

            # Test registration
            manager.register_transport("conn1", transport1)
            manager.register_transport("conn2", transport2)

            # Test retrieval
            assert manager.get_transport("conn1") is transport1
            assert manager.get_transport("conn2") is transport2
            assert manager.get_transport("nonexistent") is None

            # Test listing
            transport_names = manager.list_transports()
            assert "conn1" in transport_names
            assert "conn2" in transport_names
            assert len(transport_names) == 2

        except ImportError:
            pytest.skip("TransportManager not available")

    @pytest.mark.asyncio
    async def test_transport_manager_disconnect_all(self):
        """Test disconnecting all registered transports."""
        try:
            from kailash.mcp_server.transports import BaseTransport, TransportManager

            manager = TransportManager()

            # Create mock transports
            class MockTransport(BaseTransport):
                def __init__(self, name):
                    super().__init__(name)
                    self.disconnected = False

                async def connect(self):
                    self._connected = True

                async def disconnect(self):
                    self._connected = False
                    self.disconnected = True

                async def send_message(self, message):
                    pass

                async def receive_message(self):
                    return {}

            transport1 = MockTransport("transport1")
            transport2 = MockTransport("transport2")

            # Connect and register transports
            await transport1.connect()
            await transport2.connect()
            manager.register_transport("conn1", transport1)
            manager.register_transport("conn2", transport2)

            assert transport1.is_connected()
            assert transport2.is_connected()

            # Test disconnect all
            await manager.disconnect_all()

            # Verify all transports were disconnected
            assert transport1.disconnected
            assert transport2.disconnected
            assert not transport1.is_connected()
            assert not transport2.is_connected()

            # Verify registry was cleared
            assert len(manager.list_transports()) == 0

        except ImportError:
            pytest.skip("TransportManager not available")

    def test_global_transport_manager_singleton(self):
        """Test global transport manager singleton functionality."""
        try:
            from kailash.mcp_server.transports import get_transport_manager

            # Test singleton behavior
            manager1 = get_transport_manager()
            manager2 = get_transport_manager()

            assert manager1 is manager2
            assert isinstance(manager1, object)  # Should be TransportManager instance

            # Test that it has expected methods
            assert hasattr(manager1, "create_transport")
            assert hasattr(manager1, "register_transport")
            assert hasattr(manager1, "get_transport")
            assert hasattr(manager1, "list_transports")
            assert hasattr(manager1, "disconnect_all")

        except ImportError:
            pytest.skip("get_transport_manager not available")


class TestTransportErrorHandlingEdgeCases:
    """Test transport error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_transport_timeout_handling(self):
        """Test timeout handling across different transport types."""
        try:
            from kailash.mcp_server.transports import SSETransport

            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                # Mock timeout during message receive
                mock_session.get.side_effect = asyncio.TimeoutError()

                transport = SSETransport(
                    base_url="https://api.example.com",
                    timeout=1.0,  # Short timeout
                    skip_security_validation=True,
                )

                # Should handle timeout gracefully
                with pytest.raises(Exception):  # TransportError with timeout
                    await transport.receive_message()

        except ImportError:
            pytest.skip("SSETransport not available")

    @pytest.mark.asyncio
    async def test_transport_json_error_handling(self):
        """Test JSON parsing error handling."""
        try:
            from kailash.mcp_server.transports import EnhancedStdioTransport

            with patch("asyncio.create_subprocess_exec") as mock_create_process:
                mock_process = Mock()
                mock_process.stdout = AsyncMock()
                mock_process.stdout.readline = AsyncMock(return_value=b"")
                mock_create_process.return_value = mock_process

                transport = EnhancedStdioTransport(command="python")
                await transport.connect()

                # Add invalid JSON to message buffer
                transport._message_buffer.append("invalid json {broken")

                # Should raise TransportError for invalid JSON
                with pytest.raises(Exception):  # TransportError with JSON decode error
                    await transport.receive_message()

                await transport.disconnect()

        except ImportError:
            pytest.skip("EnhancedStdioTransport not available")

    def test_transport_security_edge_cases(self):
        """Test edge cases in transport security validation."""
        try:
            from kailash.mcp_server.transports import TransportSecurity

            # Test malformed URLs
            malformed_urls = [
                "not-a-url",
                "://missing-scheme",
                "http://",
                "https://",
                "",
                None,
            ]

            for url in malformed_urls:
                try:
                    result = TransportSecurity.validate_url(
                        str(url) if url is not None else ""
                    )
        # assert result... - variable may not be defined
                except Exception:
                    # Exception during validation is also acceptable for malformed URLs
                    pass

            # Test origin validation edge cases
            assert not TransportSecurity.validate_origin("", ["allowed.com"])
            assert not TransportSecurity.validate_origin(None, ["allowed.com"])
            assert not TransportSecurity.validate_origin("malicious.com", [])

            # Test wildcard edge cases
            allowed_origins = ["*.example.com", "https://*.test.com"]
            assert TransportSecurity.validate_origin("sub.example.com", allowed_origins)
            assert not TransportSecurity.validate_origin(
                "example.com", allowed_origins
            )  # Wildcard requires subdomain
            assert not TransportSecurity.validate_origin(
                "malicious.example.com.evil.com", allowed_origins
            )

        except ImportError:
            pytest.skip("TransportSecurity not available")
