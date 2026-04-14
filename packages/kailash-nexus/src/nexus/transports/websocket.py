# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
import warnings
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from nexus.registry import HandlerDef, HandlerRegistry
from nexus.transports.base import Transport
from nexus.websocket_handlers import MessageHandlerRegistry

logger = logging.getLogger(__name__)

__all__ = ["WebSocketTransport", "ConnectionState"]


class ConnectionState(Enum):
    """State of a WebSocket connection."""

    CONNECTING = "connecting"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


class _TrackedConnection:
    """Server-side tracked client connection with metadata."""

    __slots__ = ("ws", "connection_id", "state", "connected_at", "last_heartbeat")

    def __init__(self, ws: Any, connection_id: str) -> None:
        self.ws = ws
        self.connection_id = connection_id
        self.state = ConnectionState.OPEN
        self.connected_at: float = time.monotonic()
        self.last_heartbeat: float = time.monotonic()


class WebSocketTransport(Transport):
    """WebSocket transport for bidirectional real-time communication.

    Runs a ``websockets`` server in a background thread with its own
    event loop. Clients send JSON-RPC style messages to invoke registered
    handlers and receive responses (and optionally server-push events)
    over the same persistent connection.

    **Message protocol** (JSON over text frames):

    Request::

        {
            "id": "<request-uuid>",
            "method": "<handler-name>",
            "params": { ... }
        }

    Response::

        {
            "id": "<matching-request-uuid>",
            "result": { ... }
        }

    Error::

        {
            "id": "<matching-request-uuid>",
            "error": {
                "code": <int>,
                "message": "<description>"
            }
        }

    Server push (broadcast / event)::

        {
            "event": "<event-type>",
            "data": { ... }
        }

    Heartbeat uses the ``websockets`` library's built-in ping/pong
    mechanism (``ping_interval`` / ``ping_timeout``), so no application-
    level heartbeat frames are needed. The transport exposes configuration
    for those intervals.

    Connection lifecycle:
        1. Client opens WS to ``ws://host:port/ws``
        2. Server assigns a connection ID and tracks the connection
        3. Client sends JSON requests, server dispatches to handlers
        4. Either side may close; server cleans up tracked state

    Args:
        host: Bind address (default ``"127.0.0.1"``).
        port: Bind port (default ``8765``).
        path: URL path for WebSocket endpoint (default ``"/ws"``).
        ping_interval: Seconds between server pings (default ``20``).
        ping_timeout: Seconds to wait for pong before closing
            (default ``20``).
        max_connections: Maximum simultaneous connections (``None``
            for unlimited).
        max_message_size: Maximum inbound message size in bytes
            (default 1 MiB).
        runtime: Optional shared ``AsyncLocalRuntime`` for executing
            workflow-backed handlers.
    """

    # Class-level defaults for __del__ safety
    _running: bool = False
    _thread: Optional[threading.Thread] = None
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _server: Any = None  # websockets.asyncio.server.Server
    _shared_runtime: Any = None

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        path: str = "/ws",
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
        max_connections: Optional[int] = None,
        max_message_size: int = 1_048_576,
        runtime: Any = None,
        message_handlers: Optional[MessageHandlerRegistry] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._path = path
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._max_connections = max_connections
        self._max_message_size = max_message_size
        self._injected_runtime = runtime
        self._message_handlers = message_handlers

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Any = None
        self._shared_runtime: Any = None

        self._registry: Optional[HandlerRegistry] = None
        self._connections: Dict[str, _TrackedConnection] = {}
        self._handler_map: Dict[str, HandlerDef] = {}
        self._on_connect_callbacks: List[Callable] = []
        self._on_disconnect_callbacks: List[Callable] = []

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "websocket"

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def port(self) -> int:
        """The WebSocket server port."""
        return self._port

    @property
    def host(self) -> str:
        """The WebSocket server bind address."""
        return self._host

    @property
    def connection_count(self) -> int:
        """Number of currently active connections."""
        return len(self._connections)

    @property
    def connections(self) -> Dict[str, _TrackedConnection]:
        """Read-only view of tracked connections (keyed by connection ID)."""
        return dict(self._connections)

    async def start(self, registry: HandlerRegistry) -> None:
        """Start the WebSocket server in a background thread.

        Reads all handlers from the registry and builds a dispatch map.
        Then starts a ``websockets.asyncio.server.serve`` instance in
        a daemon thread.
        """
        if self._running:
            return

        self._registry = registry

        # Build handler dispatch map from current registry
        for handler_def in registry.list_handlers():
            self._handler_map[handler_def.name] = handler_def

        # Also register workflow names so we can dispatch to them
        for wf_name in registry.list_workflows():
            if wf_name not in self._handler_map:
                self._handler_map[wf_name] = HandlerDef(
                    name=wf_name,
                    description=f"Execute {wf_name} workflow",
                )

        self._thread = threading.Thread(
            target=self._run_in_thread,
            daemon=True,
            name="nexus-ws-transport",
        )
        self._thread.start()

        # Wait briefly for the server to bind
        deadline = time.monotonic() + 3.0
        while not self._running and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

        if self._running:
            logger.info(
                "WebSocketTransport started on ws://%s:%d%s",
                self._host,
                self._port,
                self._path,
            )
        else:
            logger.error("WebSocketTransport failed to start within 3 seconds")

    async def stop(self) -> None:
        """Stop the WebSocket server and clean up all connections."""
        if not self._running:
            return

        self._running = False

        # Close the websockets server
        if self._server is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._server.close)

        # Join the background thread
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        # Clear tracked connections
        self._connections.clear()

        # Release shared runtime (same pattern as MCPTransport)
        if self._shared_runtime is not None:
            if hasattr(self._shared_runtime, "release"):
                self._shared_runtime.release()
            self._shared_runtime = None

        self._server = None
        logger.info("WebSocketTransport stopped")

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        """Hot-register a handler so it becomes available on existing connections."""
        self._handler_map[handler_def.name] = handler_def

    # ------------------------------------------------------------------
    # Public API — callbacks and broadcast
    # ------------------------------------------------------------------

    def on_connect(self, callback: Callable) -> Callable:
        """Register a callback invoked when a client connects.

        The callback receives ``(connection_id: str)``.
        Can be used as a decorator::

            @ws_transport.on_connect
            async def connected(connection_id):
                print(f"Client {connection_id} connected")
        """
        self._on_connect_callbacks.append(callback)
        return callback

    def on_disconnect(self, callback: Callable) -> Callable:
        """Register a callback invoked when a client disconnects.

        The callback receives ``(connection_id: str)``.
        """
        self._on_disconnect_callbacks.append(callback)
        return callback

    async def broadcast(self, event: str, data: Any) -> None:
        """Broadcast a server-push event to all connected clients.

        Args:
            event: Event type string.
            data: JSON-serializable payload.
        """
        if not self._connections:
            return

        message = json.dumps({"event": event, "data": data})
        dead: List[str] = []

        for conn_id, tracked in self._connections.items():
            try:
                await tracked.ws.send(message)
            except Exception:
                dead.append(conn_id)

        for conn_id in dead:
            self._connections.pop(conn_id, None)

    async def send_to(self, connection_id: str, event: str, data: Any) -> bool:
        """Send a server-push event to a specific client.

        Args:
            connection_id: Target connection ID.
            event: Event type string.
            data: JSON-serializable payload.

        Returns:
            True if the message was sent, False if the connection was
            not found or the send failed.
        """
        tracked = self._connections.get(connection_id)
        if tracked is None:
            return False

        message = json.dumps({"event": event, "data": data})
        try:
            await tracked.ws.send(message)
            return True
        except Exception:
            self._connections.pop(connection_id, None)
            return False

    def health_check(self) -> Dict[str, Any]:
        """WebSocket transport health status."""
        return {
            "transport": "websocket",
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "path": self._path,
            "connections": len(self._connections),
            "handlers": len(self._handler_map),
            "ping_interval": self._ping_interval,
        }

    # ------------------------------------------------------------------
    # Internals — server thread and connection handling
    # ------------------------------------------------------------------

    def _run_in_thread(self) -> None:
        """Run the websockets server in a dedicated background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:
            # CancelledError (BaseException in Python 3.9+) is the normal
            # shutdown path when server.close() cancels serve_forever().
            if self._running and not isinstance(exc, asyncio.CancelledError):
                logger.warning("WebSocket transport error: %s", exc)
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        """Create and run the websockets server until stopped."""
        from websockets.asyncio.server import serve

        async with serve(
            self._connection_handler,
            host=self._host,
            port=self._port,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
            max_size=self._max_message_size,
            logger=logger,
        ) as server:
            self._server = server
            self._running = True
            # Block until the server is closed
            await server.serve_forever()

    async def _connection_handler(self, websocket: Any) -> None:
        """Handle a single WebSocket client connection.

        Validates the request path, assigns a connection ID, runs the
        receive loop, and cleans up on disconnect.

        If a :class:`MessageHandlerRegistry` is attached and the
        requested path matches one of its registered handlers, the
        connection is delegated to the class-based handler's
        lifecycle (on_connect → on_message* → on_disconnect). The
        default JSON-RPC dispatch path is used otherwise.
        """
        # Validate path — websockets 16 exposes request on the connection
        request_path = getattr(websocket, "request", None)
        incoming_path: Optional[str] = None
        if request_path is not None:
            incoming_path = getattr(request_path, "path", None)

        # Class-based MessageHandler routing (issue #448).
        # Checked before the legacy single-path guard so the two modes
        # can coexist on the same transport.
        if (
            self._message_handlers is not None
            and incoming_path is not None
            and incoming_path in self._message_handlers.paths
        ):
            handled = await self._message_handlers.handle_connection(
                websocket, incoming_path
            )
            if handled:
                return

        if incoming_path is not None and incoming_path != self._path:
            await websocket.close(4004, "Invalid path")
            return

        # Enforce max_connections (H2: prevent resource exhaustion)
        if (
            self._max_connections is not None
            and len(self._connections) >= self._max_connections
        ):
            await websocket.close(4013, "Connection limit reached")
            return

        connection_id = uuid.uuid4().hex
        tracked = _TrackedConnection(websocket, connection_id)
        self._connections[connection_id] = tracked

        # Fire on_connect callbacks
        for cb in self._on_connect_callbacks:
            try:
                result = cb(connection_id)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("on_connect callback error: %s", exc)

        # Send connection confirmation
        try:
            await websocket.send(
                json.dumps(
                    {
                        "event": "connected",
                        "data": {"connection_id": connection_id},
                    }
                )
            )
        except Exception:
            self._connections.pop(connection_id, None)
            return

        try:
            await self._receive_loop(tracked)
        except Exception as exc:
            # websockets raises ConnectionClosed variants on disconnect
            logger.debug("Connection %s ended: %s", connection_id, exc)
        finally:
            tracked.state = ConnectionState.CLOSED
            self._connections.pop(connection_id, None)

            # Fire on_disconnect callbacks
            for cb in self._on_disconnect_callbacks:
                try:
                    result = cb(connection_id)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.warning("on_disconnect callback error: %s", exc)

    async def _receive_loop(self, tracked: _TrackedConnection) -> None:
        """Read messages from a client and dispatch to handlers."""
        async for raw_message in tracked.ws:
            tracked.last_heartbeat = time.monotonic()

            # Parse the incoming message
            try:
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8")
                message = json.loads(raw_message)
            except (json.JSONDecodeError, UnicodeDecodeError):
                await self._send_error(
                    tracked.ws, None, -32700, "Parse error: invalid JSON"
                )
                continue

            if not isinstance(message, dict):
                await self._send_error(
                    tracked.ws, None, -32600, "Invalid request: expected JSON object"
                )
                continue

            request_id = message.get("id")
            method = message.get("method")
            params = message.get("params", {})

            if method is None:
                await self._send_error(
                    tracked.ws, request_id, -32600, "Invalid request: missing 'method'"
                )
                continue

            await self._dispatch(tracked, request_id, method, params)

    async def _dispatch(
        self,
        tracked: _TrackedConnection,
        request_id: Optional[str],
        method: str,
        params: Any,
    ) -> None:
        """Dispatch a request to the appropriate handler or workflow."""
        handler_def = self._handler_map.get(method)
        if handler_def is None:
            await self._send_error(
                tracked.ws,
                request_id,
                -32601,
                f"Method not found: {method}",
            )
            return

        try:
            result = await self._invoke_handler(handler_def, params)
            await self._send_result(tracked.ws, request_id, result)
        except Exception:
            logger.exception("Handler '%s' raised an exception", method)
            await self._send_error(
                tracked.ws,
                request_id,
                -32000,
                "Internal handler error",
            )

    async def _invoke_handler(self, handler_def: HandlerDef, params: Any) -> Any:
        """Invoke a handler function or execute a workflow.

        Function-backed handlers are called directly. Workflow-backed
        handlers are executed through the shared runtime. If a guard is
        attached, it is checked before dispatch.
        """
        if handler_def.func is not None:
            # Function-backed handler
            if isinstance(params, dict):
                result = handler_def.func(**params)
            else:
                result = handler_def.func(params)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        # Workflow-backed handler — look up in registry
        if self._registry is not None:
            workflow = self._registry.get_workflow(handler_def.name)
            if workflow is not None:
                runtime = self._get_shared_runtime()
                inputs = params if isinstance(params, dict) else {}
                results, run_id = await runtime.execute_workflow_async(workflow, inputs)
                return {"results": results, "run_id": run_id}

        raise ValueError(
            f"Handler '{handler_def.name}' has no function and no workflow"
        )

    # ------------------------------------------------------------------
    # Message serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _send_result(ws: Any, request_id: Optional[str], result: Any) -> None:
        """Send a success response."""
        response: Dict[str, Any] = {"result": result}
        if request_id is not None:
            response["id"] = request_id
        await ws.send(json.dumps(response, default=str))

    @staticmethod
    async def _send_error(
        ws: Any, request_id: Optional[str], code: int, message: str
    ) -> None:
        """Send an error response."""
        response: Dict[str, Any] = {"error": {"code": code, "message": message}}
        if request_id is not None:
            response["id"] = request_id
        await ws.send(json.dumps(response))

    # ------------------------------------------------------------------
    # Runtime management
    # ------------------------------------------------------------------

    def _get_shared_runtime(self) -> Any:
        """Return a shared AsyncLocalRuntime, creating once on first use.

        Mirrors the MCPTransport pattern: if an injected runtime was
        provided at construction, acquires from it to avoid orphan pools.
        """
        if self._shared_runtime is None:
            if self._injected_runtime is not None:
                self._shared_runtime = self._injected_runtime.acquire()
            else:
                from kailash.runtime import AsyncLocalRuntime

                self._shared_runtime = AsyncLocalRuntime()
        return self._shared_runtime

    # ------------------------------------------------------------------
    # Resource cleanup
    # ------------------------------------------------------------------

    def __del__(self, _warnings: Any = warnings) -> None:
        """Warn if transport was not stopped before garbage collection."""
        if self._running:
            _warnings.warn(
                f"WebSocketTransport on port {self._port} was not stopped. "
                "Call await transport.stop() before discarding.",
                ResourceWarning,
                stacklevel=2,
            )
