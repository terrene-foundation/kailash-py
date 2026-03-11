"""
TestHTTPServer - HTTP Test Server for HTTPTransport Integration Testing

Provides a real HTTP server with Server-Sent Events (SSE) support for testing
HTTPTransport in Tier 2 integration tests.

Features:
- HTTP endpoints: POST /control, GET /stream, GET /health (optional)
- Server-Sent Events (SSE) streaming for /stream endpoint
- Request/response pairing by request_id
- Async context manager support
- Thread-safe message queue
- Handles multiple concurrent clients

Endpoints:
    POST /control:
        - Receives control messages from agent
        - Stores messages in queue for processing
        - Returns 200 OK on success

    GET /stream:
        - Returns SSE stream of responses
        - Format: data: {json}\n\n
        - Sends keep-alive comments periodically
        - Matches responses with requests by request_id

    GET /health (optional):
        - Simple health check endpoint
        - Returns 200 OK with status JSON

Usage:
    # As context manager (recommended)
    async with TestHTTPServer(host="127.0.0.1", port=8765) as server:
        # Server is running
        await client.post("http://127.0.0.1:8765/control", json=data)

    # Manual lifecycle
    server = TestHTTPServer(host="127.0.0.1", port=8765)
    await server.start()
    # ... use server ...
    await server.stop()

See Also:
    - tests/unit/core/autonomy/control/test_http_server_utils.py
    - tests/integration/autonomy/control/test_http_transport.py
"""

import asyncio
import json
from typing import Optional

from aiohttp import web


class TestHTTPServer:
    """
    HTTP test server with SSE support for integration testing.

    Note: __test__ = False tells pytest not to collect this as a test class.

    Provides HTTP endpoints for testing HTTPTransport:
    - POST /control: Receive messages from agent
    - GET /stream: Send messages via SSE to agent
    - GET /health: Health check (optional)

    The server maintains a queue of messages and supports request/response
    pairing via request_id.

    Lifecycle:
        1. Create: server = TestHTTPServer(host="127.0.0.1", port=8765)
        2. Start: await server.start()
        3. Use: Server accepts HTTP requests
        4. Stop: await server.stop()

    Thread Safety:
        - Uses asyncio.Queue for thread-safe message passing
        - Multiple concurrent clients supported
        - SSE streams are independent per client

    Example:
        async with TestHTTPServer(host="127.0.0.1", port=8765) as server:
            # Server is running
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "http://127.0.0.1:8765/control",
                    json={"data": json.dumps({"test": "message"})}
                )
    """

    __test__ = False  # Exclude from pytest collection (utility class, not a test)

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        """
        Initialize HTTP test server.

        Args:
            host: Host to bind to (default: "127.0.0.1")
            port: Port to bind to (default: 8765)

        Example:
            server = TestHTTPServer(host="127.0.0.1", port=8765)
        """
        self._host = host
        self._port = port
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._running = False

        # Message queue for request/response pairing
        # Stores messages posted to /control endpoint
        self._message_queue: asyncio.Queue = asyncio.Queue()

        # Active SSE connections (for broadcasting)
        self._sse_queues: list[asyncio.Queue] = []

    @property
    def base_url(self) -> str:
        """Get base URL for HTTP requests."""
        return f"http://{self._host}:{self._port}"

    async def start(self) -> None:
        """
        Start HTTP server.

        Creates aiohttp web application and starts listening on configured
        host/port. This operation is idempotent - safe to call multiple times.

        Raises:
            RuntimeError: If server fails to start (e.g., port in use)

        Example:
            server = TestHTTPServer(host="127.0.0.1", port=8765)
            await server.start()
            assert server.is_running()
        """
        if self._running:
            # Idempotent: already started
            return

        # Create aiohttp application
        self._app = web.Application()

        # Register routes
        self._app.router.add_post("/control", self._handle_control)
        self._app.router.add_get("/stream", self._handle_stream)
        self._app.router.add_get("/health", self._handle_health)

        # Start runner
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # Create site and start
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

        self._running = True

    async def stop(self) -> None:
        """
        Stop HTTP server.

        Gracefully shuts down the server and cleans up resources.
        This operation is idempotent - safe to call multiple times.

        Example:
            await server.stop()
            assert not server.is_running()
        """
        if not self._running:
            # Idempotent: already stopped
            return

        # Cleanup
        if self._site:
            await self._site.stop()

        if self._runner:
            await self._runner.cleanup()

        self._app = None
        self._runner = None
        self._site = None
        self._running = False

    def is_running(self) -> bool:
        """
        Check if server is running.

        Returns:
            bool: True if server is running, False otherwise

        Example:
            if server.is_running():
                await server.stop()
        """
        return self._running

    async def __aenter__(self):
        """
        Async context manager entry.

        Starts the server when entering context.

        Example:
            async with TestHTTPServer() as server:
                # Server is running
                pass
        """
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.

        Stops the server when exiting context.
        """
        await self.stop()
        return False

    # ============================================
    # HTTP Endpoint Handlers
    # ============================================

    async def _handle_control(self, request: web.Request) -> web.Response:
        """
        Handle POST /control endpoint.

        Receives control messages from agent and stores them in queue.
        Also broadcasts messages to all active SSE streams for echo/response.

        Request body format:
            {
                "data": "<json_string>"  // JSON string of ControlRequest
            }

        Returns:
            200 OK on success
            400 Bad Request if JSON is invalid

        Example:
            POST /control
            {"data": "{\"request_id\": \"req_123\", \"type\": \"question\"}"}
        """
        try:
            # Parse request body
            body = await request.json()

            # Extract data field
            if "data" not in body:
                return web.Response(
                    status=400, text="Missing 'data' field in request body"
                )

            data_str = body["data"]

            # Parse inner JSON
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError as e:
                return web.Response(
                    status=400, text=f"Invalid JSON in 'data' field: {e}"
                )

            # Store in message queue
            await self._message_queue.put(data)

            # Echo to all SSE streams (for testing bidirectional communication)
            # In production, server would process and respond differently
            for sse_queue in self._sse_queues:
                try:
                    # Echo the message back as SSE data
                    await sse_queue.put(data)
                except Exception:
                    # Queue might be closed, skip
                    pass

            return web.Response(status=200, text="OK")

        except Exception as e:
            return web.Response(status=500, text=f"Internal server error: {e}")

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """
        Handle GET /stream endpoint.

        Returns Server-Sent Events (SSE) stream of messages.

        SSE Format:
            data: {"request_id": "req_123", "type": "question"}

            : this is a comment (keep-alive)

            data: {"request_id": "req_124", "type": "approval"}

        Headers:
            Content-Type: text/event-stream
            Cache-Control: no-cache
            Connection: keep-alive

        Example:
            GET /stream
            => (SSE stream)
        """
        # Create SSE response
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

        await response.prepare(request)

        # Create queue for this SSE connection
        sse_queue: asyncio.Queue = asyncio.Queue()
        self._sse_queues.append(sse_queue)

        try:
            # Send keep-alive comment immediately
            await response.write(b": keepalive\n\n")

            # Stream messages from queue
            while True:
                try:
                    # Wait for message with timeout (for keep-alive)
                    message = await asyncio.wait_for(sse_queue.get(), timeout=5.0)

                    # Format as SSE data line
                    message_json = json.dumps(message)
                    sse_data = f"data: {message_json}\n\n"

                    # Send to client
                    await response.write(sse_data.encode("utf-8"))

                except asyncio.TimeoutError:
                    # Send keep-alive comment
                    await response.write(b": keepalive\n\n")
                    continue

                except Exception:
                    # Connection closed or other error
                    break

        finally:
            # Cleanup: remove queue from active list
            if sse_queue in self._sse_queues:
                self._sse_queues.remove(sse_queue)

        return response

    async def _handle_health(self, request: web.Request) -> web.Response:
        """
        Handle GET /health endpoint.

        Simple health check endpoint for testing.

        Returns:
            200 OK with status JSON

        Example:
            GET /health
            => {"status": "ok", "running": true}
        """
        return web.json_response(
            {
                "status": "ok",
                "running": self._running,
                "host": self._host,
                "port": self._port,
            }
        )


# Public API exports
__all__ = ["TestHTTPServer"]
