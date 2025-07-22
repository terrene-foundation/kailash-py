"""
Complete MCP Transport Implementations.

This module provides comprehensive transport layer implementations for MCP,
including enhanced STDIO, SSE, StreamableHTTP, and WebSocket transports.
All implementations build on the official MCP Python SDK while adding
production-ready features like security, connection management, and monitoring.

Features:
- Enhanced STDIO transport with proper process management
- Complete SSE transport with endpoint negotiation
- StreamableHTTP transport with session management
- WebSocket transport for real-time communication
- Transport security and validation
- Connection pooling and management
- Health checking and monitoring

Examples:
    Enhanced STDIO transport:

    >>> from kailash.mcp_server.transports import EnhancedStdioTransport
    >>> transport = EnhancedStdioTransport(
    ...     command="python",
    ...     args=["-m", "my_mcp_server"],
    ...     environment_filter=["PATH", "PYTHONPATH"]
    ... )
    >>> async with transport:
    ...     session = await transport.create_session()

    SSE transport with security:

    >>> from kailash.mcp_server.transports import SSETransport
    >>> transport = SSETransport(
    ...     base_url="https://api.example.com/mcp",
    ...     auth_header="Bearer token123",
    ...     validate_origin=True
    ... )

    StreamableHTTP with session management:

    >>> from kailash.mcp_server.transports import StreamableHTTPTransport
    >>> transport = StreamableHTTPTransport(
    ...     base_url="https://api.example.com/mcp",
    ...     session_management=True,
    ...     streaming_threshold=1024
    ... )
"""

import asyncio
import json
import logging
import os
import platform
import signal
import socket
import subprocess
import time
import uuid
import weakref
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

import aiohttp
import websockets

from .auth import AuthProvider
from .errors import MCPError, MCPErrorCode, TransportError
from .protocol import MetaData, ProtocolManager

logger = logging.getLogger(__name__)


class TransportSecurity:
    """Security utilities for MCP transports."""

    ALLOWED_SCHEMES = {"http", "https", "ws", "wss"}
    BLOCKED_HOSTS = {
        "169.254.169.254",
        "localhost",
        "127.0.0.1",
    }  # Basic DNS rebinding protection

    @classmethod
    def validate_url(cls, url: str, allow_localhost: bool = False) -> bool:
        """Validate URL for security.

        Args:
            url: URL to validate
            allow_localhost: Allow localhost connections

        Returns:
            True if URL is safe
        """
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in cls.ALLOWED_SCHEMES:
                logger.warning(f"Blocked unsafe scheme: {parsed.scheme}")
                return False

            # Check host
            if not allow_localhost and parsed.hostname in cls.BLOCKED_HOSTS:
                logger.warning(f"Blocked potentially unsafe host: {parsed.hostname}")
                return False

            # Check for IP address patterns that could be exploited
            if parsed.hostname and parsed.hostname.startswith("0."):
                logger.warning(f"Blocked potentially unsafe IP: {parsed.hostname}")
                return False

            return True

        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False

    @classmethod
    def validate_origin(cls, origin: str, expected_origins: List[str]) -> bool:
        """Validate request origin.

        Args:
            origin: Request origin
            expected_origins: List of allowed origins

        Returns:
            True if origin is allowed
        """
        if not origin:
            return False

        # Exact match
        if origin in expected_origins:
            return True

        # Wildcard patterns
        for expected in expected_origins:
            if "*" in expected:
                # Convert wildcard pattern to regex
                import re

                pattern = expected.replace(".", r"\.").replace("*", ".*")
                if re.match(f"^{pattern}$", origin):
                    return True

        return False


class BaseTransport(ABC):
    """Base class for MCP transports."""

    def __init__(
        self,
        name: str,
        auth_provider: Optional[AuthProvider] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        enable_metrics: bool = True,
    ):
        """Initialize base transport.

        Args:
            name: Transport name
            auth_provider: Authentication provider
            timeout: Connection timeout
            max_retries: Maximum retry attempts
            enable_metrics: Enable metrics collection
        """
        self.name = name
        self.auth_provider = auth_provider
        self.timeout = timeout
        self.max_retries = max_retries
        self.enable_metrics = enable_metrics

        # State
        self._connected = False
        self._sessions: Set[weakref.ref] = set()
        self._metrics: Dict[str, Any] = {}

        # Initialize metrics
        if enable_metrics:
            self._metrics = {
                "connections_total": 0,
                "connections_failed": 0,
                "messages_sent": 0,
                "messages_received": 0,
                "bytes_sent": 0,
                "bytes_received": 0,
                "errors_total": 0,
                "start_time": time.time(),
            }

    @abstractmethod
    async def connect(self) -> None:
        """Connect the transport."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect the transport."""
        pass

    @abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send a message."""
        pass

    @abstractmethod
    async def receive_message(self) -> Dict[str, Any]:
        """Receive a message."""
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self._connected

    def get_metrics(self) -> Dict[str, Any]:
        """Get transport metrics."""
        if not self.enable_metrics:
            return {}

        metrics = self._metrics.copy()
        metrics["uptime"] = time.time() - metrics["start_time"]
        metrics["active_sessions"] = len(self._sessions)
        return metrics

    def _update_metrics(self, metric: str, value: Union[int, float] = 1):
        """Update metrics."""
        if self.enable_metrics and metric in self._metrics:
            self._metrics[metric] += value


class EnhancedStdioTransport(BaseTransport):
    """Enhanced STDIO transport with proper process management."""

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        working_directory: Optional[str] = None,
        environment_filter: Optional[List[str]] = None,
        **kwargs,
    ):
        """Initialize enhanced STDIO transport.

        Args:
            command: Command to execute
            args: Command arguments
            env: Environment variables
            working_directory: Working directory
            environment_filter: Allowed environment variables
            **kwargs: Base transport arguments
        """
        super().__init__("stdio", **kwargs)

        self.command = command
        self.args = args or []
        self.env = env or {}
        self.working_directory = working_directory
        self.environment_filter = environment_filter

        # Process management
        self.process: Optional[asyncio.subprocess.Process] = None
        self._read_task: Optional[asyncio.Task] = None
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._message_buffer: List[str] = []

    async def connect(self) -> None:
        """Start the subprocess and connect."""
        if self._connected:
            return

        try:
            # Prepare environment
            process_env = self._prepare_environment()

            # Start process
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
                cwd=self.working_directory,
            )

            # Start I/O tasks
            self._read_task = asyncio.create_task(self._read_loop())

            self._connected = True
            self._update_metrics("connections_total")

            logger.info(f"STDIO transport connected: {self.command}")

        except Exception as e:
            self._update_metrics("connections_failed")
            raise TransportError(
                f"Failed to start process: {e}", transport_type="stdio"
            )

    async def disconnect(self) -> None:
        """Terminate the subprocess."""
        if not self._connected:
            return

        self._connected = False

        # Cancel read task
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Terminate process
        if self.process:
            try:
                # Try graceful termination first
                self.process.terminate()

                # Wait with timeout
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Force kill if needed
                    if platform.system() != "Windows":
                        self.process.kill()
                    await self.process.wait()

            except Exception as e:
                logger.error(f"Error terminating process: {e}")

            finally:
                self.process = None

        logger.info("STDIO transport disconnected")

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message to subprocess."""
        if not self._connected or not self.process:
            raise TransportError("Transport not connected", transport_type="stdio")

        try:
            # Serialize message
            message_data = json.dumps(message) + "\n"
            message_bytes = message_data.encode("utf-8")

            # Send to subprocess
            self.process.stdin.write(message_bytes)
            await self.process.stdin.drain()

            self._update_metrics("messages_sent")
            self._update_metrics("bytes_sent", len(message_bytes))

        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(f"Failed to send message: {e}", transport_type="stdio")

    async def receive_message(self) -> Dict[str, Any]:
        """Receive message from subprocess."""
        if not self._connected:
            raise TransportError("Transport not connected", transport_type="stdio")

        try:
            # Wait for message in buffer
            while not self._message_buffer:
                await asyncio.sleep(0.01)  # Small delay to prevent busy waiting

                if not self._connected:
                    raise TransportError(
                        "Transport disconnected", transport_type="stdio"
                    )

            # Get message from buffer
            message_data = self._message_buffer.pop(0)
            message = json.loads(message_data)

            self._update_metrics("messages_received")
            self._update_metrics("bytes_received", len(message_data))

            return message

        except json.JSONDecodeError as e:
            self._update_metrics("errors_total")
            raise TransportError(f"Invalid JSON received: {e}", transport_type="stdio")
        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(
                f"Failed to receive message: {e}", transport_type="stdio"
            )

    async def _read_loop(self):
        """Background task to read from subprocess."""
        if not self.process:
            return

        try:
            while self._connected and self.process:
                # Read line from stdout
                line = await self.process.stdout.readline()

                if not line:
                    # Process ended
                    break

                # Decode and strip
                line_str = line.decode("utf-8").strip()

                if line_str:
                    self._message_buffer.append(line_str)

        except Exception as e:
            logger.error(f"STDIO read loop error: {e}")
        finally:
            if self._connected:
                await self.disconnect()

    def _prepare_environment(self) -> Dict[str, str]:
        """Prepare process environment variables."""
        # Start with filtered parent environment
        if self.environment_filter:
            process_env = {
                key: value
                for key, value in os.environ.items()
                if key in self.environment_filter
            }
        else:
            process_env = os.environ.copy()

        # Add custom environment variables
        process_env.update(self.env)

        return process_env

    async def get_process_info(self) -> Dict[str, Any]:
        """Get information about the subprocess."""
        if not self.process:
            return {}

        return {
            "pid": self.process.pid,
            "returncode": self.process.returncode,
            "command": [self.command] + self.args,
            "working_directory": self.working_directory,
        }


class SSETransport(BaseTransport):
    """Server-Sent Events transport with endpoint negotiation."""

    def __init__(
        self,
        base_url: str,
        auth_header: Optional[str] = None,
        validate_origin: bool = True,
        allowed_origins: Optional[List[str]] = None,
        endpoint_path: str = "/sse",
        message_path: str = "/message",
        allow_localhost: bool = False,
        skip_security_validation: bool = False,
        **kwargs,
    ):
        """Initialize SSE transport.

        Args:
            base_url: Base URL for the server
            auth_header: Authorization header
            validate_origin: Enable origin validation
            allowed_origins: List of allowed origins
            endpoint_path: SSE endpoint path
            message_path: Message posting path
            allow_localhost: Allow connections to localhost (for testing)
            skip_security_validation: Skip all security validation (for testing)
            **kwargs: Base transport arguments
        """
        super().__init__("sse", **kwargs)

        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header
        self.validate_origin = validate_origin
        self.allowed_origins = allowed_origins or [base_url]
        self.endpoint_path = endpoint_path
        self.message_path = message_path
        self.allow_localhost = allow_localhost
        self.skip_security_validation = skip_security_validation

        # Connection state
        self.session: Optional[aiohttp.ClientSession] = None
        self.sse_response: Optional[aiohttp.ClientResponse] = None
        self._read_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> None:
        """Connect to SSE endpoint."""
        if self._connected:
            return

        # Validate URL (with configurable security)
        if not self.skip_security_validation:
            if not TransportSecurity.validate_url(
                self.base_url, allow_localhost=self.allow_localhost
            ):
                raise TransportError("Invalid or unsafe URL", transport_type="sse")

        try:
            # Create session
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            # Add CORS headers if origin validation is enabled
            if self.validate_origin:
                headers["Origin"] = self.base_url

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)

            # Connect to SSE endpoint
            sse_url = urljoin(self.base_url, self.endpoint_path)
            self.sse_response = await self.session.get(
                sse_url,
                headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
            )

            if self.sse_response.status != 200:
                raise TransportError(
                    f"SSE connection failed: {self.sse_response.status}",
                    transport_type="sse",
                )

            # Start reading SSE events
            self._read_task = asyncio.create_task(self._read_sse_events())

            self._connected = True
            self._update_metrics("connections_total")

            logger.info(f"SSE transport connected: {sse_url}")

        except Exception as e:
            self._update_metrics("connections_failed")
            await self._cleanup_connection()
            raise TransportError(f"SSE connection failed: {e}", transport_type="sse")

    async def disconnect(self) -> None:
        """Disconnect from SSE endpoint."""
        if not self._connected:
            return

        self._connected = False
        await self._cleanup_connection()

        logger.info("SSE transport disconnected")

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message via HTTP POST."""
        if not self._connected or not self.session:
            raise TransportError("Transport not connected", transport_type="sse")

        try:
            message_url = urljoin(self.base_url, self.message_path)

            async with self.session.post(
                message_url, json=message, headers={"Content-Type": "application/json"}
            ) as response:
                if response.status not in (200, 201, 202):
                    raise TransportError(
                        f"Message send failed: {response.status}", transport_type="sse"
                    )

            self._update_metrics("messages_sent")
            self._update_metrics("bytes_sent", len(json.dumps(message)))

        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(f"Failed to send message: {e}", transport_type="sse")

    async def receive_message(self) -> Dict[str, Any]:
        """Receive message from SSE stream."""
        if not self._connected:
            raise TransportError("Transport not connected", transport_type="sse")

        try:
            # Wait for message from queue
            message = await asyncio.wait_for(
                self._message_queue.get(), timeout=self.timeout
            )

            self._update_metrics("messages_received")
            self._update_metrics("bytes_received", len(json.dumps(message)))

            return message

        except asyncio.TimeoutError:
            raise TransportError("Receive timeout", transport_type="sse")
        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(
                f"Failed to receive message: {e}", transport_type="sse"
            )

    async def _read_sse_events(self):
        """Background task to read SSE events."""
        if not self.sse_response:
            return

        try:
            async for line in self.sse_response.content:
                if not self._connected:
                    break

                line_str = line.decode("utf-8").strip()

                # Parse SSE event
                if line_str.startswith("data: "):
                    data_str = line_str[6:]  # Remove "data: " prefix

                    try:
                        message = json.loads(data_str)
                        await self._message_queue.put(message)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in SSE event: {data_str}")

        except Exception as e:
            logger.error(f"SSE read error: {e}")
        finally:
            if self._connected:
                await self.disconnect()

    async def _cleanup_connection(self):
        """Clean up connection resources."""
        # Cancel read task
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Close SSE response
        if self.sse_response:
            self.sse_response.close()
            self.sse_response = None

        # Close session
        if self.session:
            await self.session.close()
            self.session = None


class StreamableHTTPTransport(BaseTransport):
    """StreamableHTTP transport with session management."""

    def __init__(
        self,
        base_url: str,
        session_management: bool = True,
        streaming_threshold: int = 1024,
        chunk_size: int = 8192,
        allow_localhost: bool = False,
        skip_security_validation: bool = False,
        **kwargs,
    ):
        """Initialize StreamableHTTP transport.

        Args:
            base_url: Base URL for the server
            session_management: Enable session management
            streaming_threshold: Size threshold for streaming
            chunk_size: Chunk size for streaming
            allow_localhost: Allow connections to localhost (for testing)
            skip_security_validation: Skip all security validation (for testing)
            **kwargs: Base transport arguments
        """
        super().__init__("streamable_http", **kwargs)

        self.base_url = base_url.rstrip("/")
        self.session_management = session_management
        self.streaming_threshold = streaming_threshold
        self.chunk_size = chunk_size
        self.allow_localhost = allow_localhost
        self.skip_security_validation = skip_security_validation

        # Session state
        self.session: Optional[aiohttp.ClientSession] = None
        self.session_id: Optional[str] = None

    async def connect(self) -> None:
        """Connect and optionally create session."""
        if self._connected:
            return

        # Validate URL (with configurable security)
        if not self.skip_security_validation:
            if not TransportSecurity.validate_url(
                self.base_url, allow_localhost=self.allow_localhost
            ):
                raise TransportError(
                    "Invalid or unsafe URL", transport_type="streamable_http"
                )

        try:
            # Create HTTP session
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)

            # Create server session if enabled
            if self.session_management:
                await self._create_server_session()

            self._connected = True
            self._update_metrics("connections_total")

            logger.info(f"StreamableHTTP transport connected: {self.base_url}")

        except Exception as e:
            self._update_metrics("connections_failed")
            await self._cleanup_connection()
            raise TransportError(
                f"HTTP connection failed: {e}", transport_type="streamable_http"
            )

    async def disconnect(self) -> None:
        """Disconnect and cleanup session."""
        if not self._connected:
            return

        self._connected = False

        # Close server session
        if self.session_management and self.session_id:
            await self._close_server_session()

        await self._cleanup_connection()

        logger.info("StreamableHTTP transport disconnected")

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message via HTTP POST."""
        if not self._connected or not self.session:
            raise TransportError(
                "Transport not connected", transport_type="streamable_http"
            )

        try:
            # Prepare URL
            url = urljoin(self.base_url, "/message")

            # Add session ID if using session management
            headers = {"Content-Type": "application/json"}
            if self.session_id:
                headers["X-Session-ID"] = self.session_id

            # Determine if streaming is needed
            message_data = json.dumps(message)
            use_streaming = len(message_data) > self.streaming_threshold

            if use_streaming:
                # Stream large message
                await self._send_streamed_message(url, message_data, headers)
            else:
                # Send normal message
                async with self.session.post(
                    url, json=message, headers=headers
                ) as response:
                    if response.status not in (200, 201, 202):
                        raise TransportError(
                            f"Message send failed: {response.status}",
                            transport_type="streamable_http",
                        )

            self._update_metrics("messages_sent")
            self._update_metrics("bytes_sent", len(message_data))

        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(
                f"Failed to send message: {e}", transport_type="streamable_http"
            )

    async def receive_message(self) -> Dict[str, Any]:
        """Receive message via HTTP GET/POST."""
        if not self._connected or not self.session:
            raise TransportError(
                "Transport not connected", transport_type="streamable_http"
            )

        try:
            # Prepare URL
            url = urljoin(self.base_url, "/receive")

            # Add session ID if using session management
            headers = {}
            if self.session_id:
                headers["X-Session-ID"] = self.session_id

            # Receive message
            async with self.session.get(url, headers=headers) as response:
                if response.status == 204:
                    # No message available
                    await asyncio.sleep(0.1)  # Brief delay before retry
                    return await self.receive_message()

                if response.status != 200:
                    raise TransportError(
                        f"Message receive failed: {response.status}",
                        transport_type="streamable_http",
                    )

                # Check if response is streamed
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self.streaming_threshold:
                    message = await self._receive_streamed_message(response)
                else:
                    message = await response.json()

            self._update_metrics("messages_received")
            self._update_metrics("bytes_received", len(json.dumps(message)))

            return message

        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(
                f"Failed to receive message: {e}", transport_type="streamable_http"
            )

    async def _create_server_session(self):
        """Create session with server."""
        if not self.session:
            return

        url = urljoin(self.base_url, "/session")

        async with self.session.post(url) as response:
            if response.status == 201:
                session_data = await response.json()
                self.session_id = session_data.get("session_id")
                logger.info(f"Created server session: {self.session_id}")
            else:
                logger.warning(f"Failed to create server session: {response.status}")

    async def _close_server_session(self):
        """Close session with server."""
        if not self.session or not self.session_id:
            return

        url = urljoin(self.base_url, f"/session/{self.session_id}")

        try:
            async with self.session.delete(url) as response:
                if response.status in (200, 204):
                    logger.info(f"Closed server session: {self.session_id}")
                else:
                    logger.warning(f"Failed to close server session: {response.status}")
        except Exception as e:
            logger.error(f"Error closing server session: {e}")
        finally:
            self.session_id = None

    async def _send_streamed_message(
        self, url: str, message_data: str, headers: Dict[str, str]
    ):
        """Send message using streaming."""
        headers["Transfer-Encoding"] = "chunked"

        async def message_chunks():
            for i in range(0, len(message_data), self.chunk_size):
                yield message_data[i : i + self.chunk_size].encode("utf-8")

        async with self.session.post(
            url, data=message_chunks(), headers=headers
        ) as response:
            if response.status not in (200, 201, 202):
                raise TransportError(
                    f"Streamed message send failed: {response.status}",
                    transport_type="streamable_http",
                )

    async def _receive_streamed_message(
        self, response: aiohttp.ClientResponse
    ) -> Dict[str, Any]:
        """Receive streamed message."""
        chunks = []

        async for chunk in response.content.iter_chunked(self.chunk_size):
            chunks.append(chunk.decode("utf-8"))

        message_data = "".join(chunks)
        return json.loads(message_data)

    async def _cleanup_connection(self):
        """Clean up connection resources."""
        if self.session:
            await self.session.close()
            self.session = None


class WebSocketTransport(BaseTransport):
    """WebSocket transport for real-time communication."""

    def __init__(
        self,
        url: str,
        subprotocols: Optional[List[str]] = None,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
        allow_localhost: bool = False,
        skip_security_validation: bool = False,
        **kwargs,
    ):
        """Initialize WebSocket transport.

        Args:
            url: WebSocket URL
            subprotocols: WebSocket subprotocols
            ping_interval: Ping interval in seconds
            ping_timeout: Ping timeout in seconds
            allow_localhost: Allow connections to localhost (for testing)
            skip_security_validation: Skip all security validation (for testing)
            **kwargs: Base transport arguments
        """
        super().__init__("websocket", **kwargs)

        self.url = url
        self.subprotocols = subprotocols or ["mcp-v1"]
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.allow_localhost = allow_localhost
        self.skip_security_validation = skip_security_validation

        # Connection state
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self._read_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> None:
        """Connect to WebSocket server."""
        if self._connected:
            return

        # Validate URL (with configurable security)
        if not self.skip_security_validation:
            if not TransportSecurity.validate_url(
                self.url, allow_localhost=self.allow_localhost
            ):
                raise TransportError(
                    "Invalid or unsafe URL", transport_type="websocket"
                )

        try:
            # Connect to WebSocket
            extra_headers = {}
            if self.auth_provider:
                # Add authentication headers
                auth_headers = await self.auth_provider.get_headers()
                extra_headers.update(auth_headers)

            self.websocket = await websockets.connect(
                self.url,
                subprotocols=self.subprotocols,
                extra_headers=extra_headers,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
            )

            # Start reading messages
            self._read_task = asyncio.create_task(self._read_messages())

            self._connected = True
            self._update_metrics("connections_total")

            logger.info(f"WebSocket transport connected: {self.url}")

        except Exception as e:
            self._update_metrics("connections_failed")
            await self._cleanup_connection()
            raise TransportError(
                f"WebSocket connection failed: {e}", transport_type="websocket"
            )

    async def disconnect(self) -> None:
        """Disconnect from WebSocket server."""
        if not self._connected:
            return

        self._connected = False
        await self._cleanup_connection()

        logger.info("WebSocket transport disconnected")

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message via WebSocket."""
        if not self._connected or not self.websocket:
            raise TransportError("Transport not connected", transport_type="websocket")

        try:
            message_data = json.dumps(message)
            await self.websocket.send(message_data)

            self._update_metrics("messages_sent")
            self._update_metrics("bytes_sent", len(message_data))

        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(
                f"Failed to send message: {e}", transport_type="websocket"
            )

    async def receive_message(self) -> Dict[str, Any]:
        """Receive message from WebSocket."""
        if not self._connected:
            raise TransportError("Transport not connected", transport_type="websocket")

        try:
            message = await asyncio.wait_for(
                self._message_queue.get(), timeout=self.timeout
            )

            self._update_metrics("messages_received")
            self._update_metrics("bytes_received", len(json.dumps(message)))

            return message

        except asyncio.TimeoutError:
            raise TransportError("Receive timeout", transport_type="websocket")
        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(
                f"Failed to receive message: {e}", transport_type="websocket"
            )

    async def _read_messages(self):
        """Background task to read WebSocket messages."""
        if not self.websocket:
            return

        try:
            async for message_data in self.websocket:
                if not self._connected:
                    break

                try:
                    message = json.loads(message_data)
                    await self._message_queue.put(message)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in WebSocket message: {message_data}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket read error: {e}")
        finally:
            if self._connected:
                await self.disconnect()

    async def _cleanup_connection(self):
        """Clean up connection resources."""
        # Cancel read task
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self.websocket:
            await self.websocket.close()
            self.websocket = None


class WebSocketServerTransport(BaseTransport):
    """WebSocket server transport for accepting MCP connections."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 3001,
        message_handler: Optional[
            Callable[[Dict[str, Any], str], Dict[str, Any]]
        ] = None,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
        max_message_size: int = 10 * 1024 * 1024,  # 10MB
        **kwargs,
    ):
        """Initialize WebSocket server transport.

        Args:
            host: Host to bind to
            port: Port to listen on
            message_handler: Handler for incoming messages
            ping_interval: Ping interval in seconds
            ping_timeout: Ping timeout in seconds
            max_message_size: Maximum message size in bytes
            **kwargs: Base transport arguments
        """
        super().__init__("websocket_server", **kwargs)

        self.host = host
        self.port = port
        self.message_handler = message_handler
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.max_message_size = max_message_size

        # Server state
        self.server: Optional[websockets.WebSocketServer] = None
        self._clients: Dict[str, Any] = {}  # websockets.WebSocketServerProtocol
        self._client_sessions: Dict[str, Dict[str, Any]] = {}
        self._server_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Start the WebSocket server."""
        if self._connected:
            return

        try:
            # Create handler that works with new websockets API
            async def connection_handler(websocket):
                # Get path from the websocket's request path
                path = websocket.path if hasattr(websocket, "path") else "/"
                await self.handle_client(websocket, path)

            # Start WebSocket server
            self.server = await websockets.serve(
                connection_handler,
                self.host,
                self.port,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                max_size=self.max_message_size,
            )

            self._connected = True
            self._update_metrics("connections_total")

            logger.info(f"WebSocket server listening on {self.host}:{self.port}")

        except Exception as e:
            self._update_metrics("connections_failed")
            raise TransportError(
                f"Failed to start WebSocket server: {e}",
                transport_type="websocket_server",
            )

    async def disconnect(self) -> None:
        """Stop the WebSocket server."""
        if not self._connected:
            return

        self._connected = False

        # Close all client connections
        clients = list(self._clients.values())
        for client in clients:
            await client.close()

        # Stop server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        # Clear client tracking
        self._clients.clear()
        self._client_sessions.clear()

        logger.info("WebSocket server stopped")

    async def send_message(
        self, message: Dict[str, Any], client_id: Optional[str] = None
    ) -> None:
        """Send message to specific client or broadcast to all.

        Args:
            message: Message to send
            client_id: Target client ID (None for broadcast)
        """
        if not self._connected:
            raise TransportError(
                "Transport not connected", transport_type="websocket_server"
            )

        message_data = json.dumps(message)

        try:
            if client_id:
                # Send to specific client
                if client_id in self._clients:
                    await self._clients[client_id].send(message_data)
                    self._update_metrics("messages_sent")
                    self._update_metrics("bytes_sent", len(message_data))
                else:
                    raise TransportError(
                        f"Client {client_id} not found",
                        transport_type="websocket_server",
                    )
            else:
                # Broadcast to all clients
                if self._clients:
                    await asyncio.gather(
                        *[
                            client.send(message_data)
                            for client in self._clients.values()
                        ],
                        return_exceptions=True,
                    )
                    self._update_metrics("messages_sent", len(self._clients))
                    self._update_metrics(
                        "bytes_sent", len(message_data) * len(self._clients)
                    )

        except Exception as e:
            self._update_metrics("errors_total")
            raise TransportError(
                f"Failed to send message: {e}", transport_type="websocket_server"
            )

    async def receive_message(self) -> Dict[str, Any]:
        """Not implemented for server transport."""
        raise NotImplementedError(
            "Server transport doesn't support receive_message. "
            "Messages are handled via handle_client callback."
        )

    async def handle_client(self, websocket, path: str):
        """Handle a client connection.

        Args:
            websocket: WebSocket connection
            path: Request path
        """
        client_id = str(uuid.uuid4())
        self._clients[client_id] = websocket
        self._client_sessions[client_id] = {
            "connected_at": time.time(),
            "path": path,
            "remote_address": websocket.remote_address,
        }

        logger.info(f"Client {client_id} connected from {websocket.remote_address}")
        self._update_metrics("connections_total")

        try:
            async for message in websocket:
                try:
                    # Parse message
                    request = json.loads(message)

                    # Update metrics
                    self._update_metrics("messages_received")
                    self._update_metrics("bytes_received", len(message))

                    # Handle message
                    if self.message_handler:
                        response = await self._handle_message_safely(request, client_id)
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": -32601,
                                "message": "No message handler configured",
                            },
                            "id": request.get("id"),
                        }

                    # Send response
                    await websocket.send(json.dumps(response))
                    self._update_metrics("messages_sent")
                    self._update_metrics("bytes_sent", len(json.dumps(response)))

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from client {client_id}: {e}")
                    self._update_metrics("errors_total")

                    error_response = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32700,
                            "message": "Parse error: Invalid JSON",
                        },
                        "id": None,
                    }
                    await websocket.send(json.dumps(error_response))

                except Exception as e:
                    logger.error(f"Error handling message from client {client_id}: {e}")
                    self._update_metrics("errors_total")

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Error in client handler for {client_id}: {e}")
        finally:
            # Clean up client
            del self._clients[client_id]
            del self._client_sessions[client_id]

    async def _handle_message_safely(
        self, request: Dict[str, Any], client_id: str
    ) -> Dict[str, Any]:
        """Handle message with error handling.

        Args:
            request: JSON-RPC request
            client_id: Client identifier

        Returns:
            JSON-RPC response
        """
        try:
            if asyncio.iscoroutinefunction(self.message_handler):
                return await self.message_handler(request, client_id)
            else:
                return self.message_handler(request, client_id)
        except Exception as e:
            logger.error(f"Message handler error: {e}")
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}",
                },
                "id": request.get("id"),
            }

    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a connected client.

        Args:
            client_id: Client identifier

        Returns:
            Client information or None
        """
        if client_id not in self._client_sessions:
            return None

        session = self._client_sessions[client_id]
        return {
            "client_id": client_id,
            "connected_at": session["connected_at"],
            "connection_duration": time.time() - session["connected_at"],
            "path": session["path"],
            "remote_address": session["remote_address"],
        }

    def list_clients(self) -> List[Dict[str, Any]]:
        """List all connected clients.

        Returns:
            List of client information
        """
        return [self.get_client_info(client_id) for client_id in self._client_sessions]

    async def close_client(
        self, client_id: str, code: int = 1000, reason: str = ""
    ) -> bool:
        """Close a specific client connection.

        Args:
            client_id: Client to disconnect
            code: WebSocket close code
            reason: Close reason

        Returns:
            True if client was closed
        """
        if client_id in self._clients:
            await self._clients[client_id].close(code, reason)
            return True
        return False


class TransportManager:
    """Manager for MCP transport instances."""

    def __init__(self):
        """Initialize transport manager."""
        self._transports: Dict[str, BaseTransport] = {}
        self._transport_factories: Dict[str, Callable] = {
            "stdio": EnhancedStdioTransport,
            "sse": SSETransport,
            "streamable_http": StreamableHTTPTransport,
            "websocket": WebSocketTransport,
            "websocket_server": WebSocketServerTransport,
        }

    def register_transport_factory(self, transport_type: str, factory: Callable):
        """Register transport factory.

        Args:
            transport_type: Transport type name
            factory: Factory function
        """
        self._transport_factories[transport_type] = factory

    def create_transport(self, transport_type: str, **kwargs) -> BaseTransport:
        """Create transport instance.

        Args:
            transport_type: Transport type
            **kwargs: Transport arguments

        Returns:
            Transport instance
        """
        factory = self._transport_factories.get(transport_type)
        if not factory:
            raise ValueError(f"Unknown transport type: {transport_type}")

        return factory(**kwargs)

    def register_transport(self, name: str, transport: BaseTransport):
        """Register transport instance.

        Args:
            name: Transport name
            transport: Transport instance
        """
        self._transports[name] = transport

    def get_transport(self, name: str) -> Optional[BaseTransport]:
        """Get registered transport.

        Args:
            name: Transport name

        Returns:
            Transport instance or None
        """
        return self._transports.get(name)

    def list_transports(self) -> List[str]:
        """List registered transport names."""
        return list(self._transports.keys())

    async def disconnect_all(self):
        """Disconnect all registered transports."""
        for transport in self._transports.values():
            try:
                await transport.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting transport: {e}")

        self._transports.clear()


# Global transport manager
_transport_manager: Optional[TransportManager] = None


def get_transport_manager() -> TransportManager:
    """Get global transport manager."""
    global _transport_manager
    if _transport_manager is None:
        _transport_manager = TransportManager()
    return _transport_manager
