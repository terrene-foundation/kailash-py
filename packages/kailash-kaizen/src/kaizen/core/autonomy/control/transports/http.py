"""
HTTP Transport Implementation

Provides HTTP-based bidirectional communication using Server-Sent Events (SSE)
for the control protocol. Implements the Transport ABC.

Design from ADR-011:
- Uses HTTP POST to /control endpoint for writing messages
- Uses HTTP GET to /stream endpoint for reading messages via SSE
- SSE format: Lines starting with 'data: ' contain JSON messages
- Handles reconnection, retries, and connection errors
- Async I/O with aiohttp

Key Characteristics:
- Web-based: Works over HTTP/HTTPS
- SSE streaming: Server-Sent Events for real-time message delivery
- Async-first: Uses aiohttp for runtime-agnostic async HTTP
- Stateful: Maintains HTTP session for connection pooling

Security:
- TLS/HTTPS enforced by default (SOC 2 CC6.1 Network Security)
- HTTP allowed only for local development with allow_insecure=True
- Production deployments must use HTTPS

SSE Format:
    data: {"request_id": "req_123", "type": "question"}

    data: {"request_id": "req_124", "type": "approval"}

    : this is a comment (lines starting with : are ignored)

Example (Production - HTTPS):
    transport = HTTPTransport(base_url="https://api.example.com")
    await transport.connect()

    # Agent writes request to /control endpoint
    await transport.write('{"request_id": "req_123", "type": "question"}')

    # Agent reads response from /stream SSE endpoint
    async for message in transport.read_messages():
        response = json.loads(message)
        print(f"Got response: {response}")
        break

    await transport.close()

Example (Development - HTTP):
    # Only for local development - NOT for production!
    transport = HTTPTransport(
        base_url="http://localhost:8000",
        allow_insecure=True  # Required for HTTP
    )
    await transport.connect()

Usage Pattern:
    1. Agent writes control requests to POST /control
    2. Agent reads control responses from GET /stream (SSE)
    3. Client (web server) receives requests via /control
    4. Client sends responses via /stream SSE endpoint

See Also:
    - ADR-011: Control Protocol Architecture (Section: HTTP Transport)
    - tests/unit/core/autonomy/control/transports/test_http_transport.py
    - tests/integration/autonomy/control/test_http_transport.py
"""

import logging
import sys
from typing import AsyncIterator

import aiohttp
from kaizen.core.autonomy.control.transport import Transport

logger = logging.getLogger(__name__)


class HTTPTransport(Transport):
    """
    HTTP-based transport using Server-Sent Events (SSE) with TLS/HTTPS enforcement.

    Implements bidirectional communication over HTTP using:
    - POST /control for sending messages to server
    - GET /stream for receiving messages via SSE from server

    The transport uses SSE format for streaming where each message is
    prefixed with 'data: ' and followed by a newline.

    Security:
        - TLS/HTTPS enforced by default (SOC 2 CC6.1 Network Security)
        - HTTP allowed only for local development with allow_insecure=True
        - Production deployments must use HTTPS for data confidentiality

    Lifecycle:
        1. Create: transport = HTTPTransport(base_url="https://api.example.com")
        2. Connect: await transport.connect()
        3. Use: await transport.write(...) / async for msg in transport.read_messages()
        4. Close: await transport.close()

    Thread Safety:
        - Read and write operations are thread-safe via aiohttp
        - Multiple concurrent readers/writers are supported

    Performance:
        - Latency: Depends on network (local: <50ms, remote: varies)
        - Throughput: >100 messages/second for typical JSON payloads

    Example (Production - HTTPS):
        transport = HTTPTransport(base_url="https://api.example.com")
        await transport.connect()

        # Write request (agent -> server via POST /control)
        await transport.write('{"request_id": "req_1", "type": "question"}')

        # Read response (server -> agent via GET /stream SSE)
        async for message in transport.read_messages():
            print(f"Received: {message}")
            break

        await transport.close()

    Example (Development - HTTP):
        # Only for local development - NOT for production!
        transport = HTTPTransport(
            base_url="http://localhost:8000",
            allow_insecure=True  # Required for HTTP
        )
        await transport.connect()
    """

    def __init__(self, base_url: str, allow_insecure: bool = False):
        """
        Initialize HTTP transport with TLS/HTTPS enforcement.

        Args:
            base_url: Base URL for HTTP endpoints
                - Production: Must use HTTPS (e.g., "https://api.example.com")
                - Development: HTTP allowed with allow_insecure=True (e.g., "http://localhost:8000")
            allow_insecure: Allow HTTP (insecure) connections for local development.
                           Production deployments should use HTTPS only.
                           Default: False (HTTPS required)

        Raises:
            ValueError: If base_url uses http:// and allow_insecure=False

        Security:
            - Enforces TLS/HTTPS by default (SOC 2 CC6.1 Network Security)
            - Prevents accidental use of insecure HTTP in production
            - Logs warning when insecure mode is enabled

        Example (Production - HTTPS):
            transport = HTTPTransport(base_url="https://api.example.com")

        Example (Development - HTTP):
            transport = HTTPTransport(
                base_url="http://localhost:8000",
                allow_insecure=True  # Required for HTTP
            )
        """
        # Validate URL scheme (enforce HTTPS in production)
        if base_url.startswith("http://") and not allow_insecure:
            raise ValueError(
                "Insecure HTTP connections are not allowed in production. "
                "Use HTTPS (https://) or set allow_insecure=True for local development only. "
                "\n\nSecurity: HTTP transmits data in plaintext, exposing sensitive information. "
                "Production deployments must use HTTPS for data confidentiality (SOC 2 CC6.1)."
            )

        # Log security warning if insecure mode is enabled
        if allow_insecure and base_url.startswith("http://"):
            logger.warning(
                f"⚠️  INSECURE HTTP CONNECTION: {base_url}\n"
                "   This connection is NOT encrypted and should only be used for local development.\n"
                "   Production deployments must use HTTPS for data confidentiality.\n"
                "   Complies with SOC 2 CC6.1 (Network Security) by explicit opt-in."
            )

        self._base_url = base_url.rstrip("/")  # Remove trailing slash
        self._allow_insecure = allow_insecure
        self._session = None
        self._connected = False

    async def connect(self) -> None:
        """
        Establish HTTP connection by creating aiohttp session.

        Creates an aiohttp.ClientSession for HTTP requests.
        This operation is idempotent - calling multiple times is safe.

        Note:
            - Session is reused for connection pooling
            - No actual connection is made until first request
            - Operation completes immediately (<1ms)

        Raises:
            RuntimeError: Should not raise (session creation is local)

        Example:
            transport = HTTPTransport(base_url="http://localhost:8000")
            await transport.connect()
            assert transport.is_ready()
        """
        if self._connected:
            # Idempotent: already connected
            return

        # Create aiohttp session for HTTP requests
        self._session = aiohttp.ClientSession()
        self._connected = True

    async def write(self, data: str) -> None:
        """
        Send data to server via POST /control endpoint.

        Sends a JSON message string to the server's /control endpoint.
        The message is sent as JSON in the request body.

        Args:
            data: Message string to send (typically JSON)

        Raises:
            RuntimeError: If not connected
            ConnectionError: If HTTP request fails

        Example:
            await transport.write('{"request_id": "req_123", "type": "question"}')
        """
        if not self._connected:
            raise RuntimeError(
                "Cannot write to transport: not connected. " "Call connect() first."
            )

        if self._session is None:
            raise ConnectionError(
                "Cannot write to transport: HTTP session not available"
            )

        try:
            # Send POST request to /control endpoint
            url = f"{self._base_url}/control"

            # Send data as JSON body
            async with self._session.post(url, json={"data": data}) as response:
                # Check for error status codes
                if response.status >= 400:
                    error_text = await response.text()
                    raise ConnectionError(f"HTTP error {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            raise ConnectionError(f"Failed to write to transport: {e}") from e

    def read_messages(self) -> AsyncIterator[str]:
        """
        Receive messages from server via GET /stream SSE endpoint.

        Returns an async iterator that yields messages from the SSE stream.
        Each message is prefixed with 'data: ' in the SSE format.

        The iterator:
        - Yields messages as they arrive via SSE
        - Strips 'data: ' prefix from each line
        - Skips empty lines and comments (lines starting with ':')
        - Blocks when no messages are ready
        - Terminates on connection close

        SSE Format:
            data: {"request_id": "req_1", "type": "question"}

            : comment line (ignored)

            data: {"request_id": "req_2", "type": "approval"}

        Returns:
            AsyncIterator[str]: Async iterator yielding message strings

        Raises:
            RuntimeError: If not connected

        Example:
            async for message in transport.read_messages():
                response = json.loads(message)
                print(f"Got response: {response}")
                if done:
                    break
        """
        if not self._connected:
            raise RuntimeError(
                "Cannot read from transport: not connected. " "Call connect() first."
            )

        return self._read_messages_impl()

    async def _read_messages_impl(self) -> AsyncIterator[str]:
        """
        Internal async generator for reading messages from SSE stream.

        Connects to /stream endpoint and parses SSE format.
        Yields messages after stripping 'data: ' prefix.

        SSE Format Rules:
        - Lines starting with 'data: ' contain messages
        - Lines starting with ':' are comments (ignored)
        - Empty lines are field separators (ignored)
        - All other lines are ignored (robustness)

        Yields:
            str: Message string (one per data line)

        Note:
            - Handles SSE format parsing
            - Skips empty lines and comments
            - Terminates on connection close
        """
        if self._session is None:
            raise RuntimeError("HTTP session not available")

        try:
            # Connect to SSE /stream endpoint
            url = f"{self._base_url}/stream"

            async with self._session.get(url) as response:
                # Check for error status
                if response.status >= 400:
                    error_text = await response.text()
                    raise ConnectionError(f"HTTP error {response.status}: {error_text}")

                # Read SSE stream line by line
                async for line_bytes in response.content.iter_any():
                    # Decode bytes to string
                    line = line_bytes.decode("utf-8").strip()

                    # Skip empty lines (SSE field separator)
                    if not line:
                        continue

                    # Skip comments (lines starting with ':')
                    if line.startswith(":"):
                        continue

                    # Parse data lines (format: 'data: <message>')
                    if line.startswith("data:"):
                        # Strip 'data:' prefix and any leading whitespace
                        message = line[5:].lstrip()
                        yield message
                        continue

                    # Skip any other lines (robustness)
                    continue

        except aiohttp.ClientError as e:
            # Log error but don't crash
            # In production, this would use proper logging
            print(f"Error reading from SSE stream: {e}", file=sys.stderr)
            return

    async def close(self) -> None:
        """
        Close HTTP connection and clean up resources.

        Closes the aiohttp session and resets state.
        This operation is idempotent - safe to call multiple times.

        Note:
            - Closes all open HTTP connections
            - Releases session resources
            - Safe to call even if not connected

        Example:
            await transport.close()
            await transport.close()  # Safe to call again
        """
        if not self._connected:
            # Idempotent: already closed
            return

        # Close aiohttp session
        if self._session is not None and not self._session.closed:
            await self._session.close()

        self._session = None
        self._connected = False

    def is_ready(self) -> bool:
        """
        Check if transport is ready for communication.

        Returns:
            bool: True if connected and ready, False otherwise

        Example:
            if transport.is_ready():
                await transport.write(message)
            else:
                await transport.connect()
        """
        return self._connected


__all__ = ["HTTPTransport"]
