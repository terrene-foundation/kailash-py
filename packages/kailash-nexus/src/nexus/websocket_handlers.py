# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Class-based WebSocket message handlers with per-connection state.

The default :class:`~nexus.transports.websocket.WebSocketTransport` is
transport-level: it accepts WebSocket connections and dispatches JSON-RPC
style requests to functions in the :class:`HandlerRegistry`. That is
sufficient for request/response patterns but does not own any
per-connection state — each message is processed in isolation.

This module adds a **message-level handler** layer where the user
authors a class that owns the lifecycle of each connection and its
state (subscriptions, filters, queues). The handler class is registered
against a URL path and receives :class:`Connection` objects that expose
``conn.state.*`` for arbitrary per-connection bookkeeping.

This enables patterns that cannot be expressed with stateless request/
response handlers — subscription-based event streams, per-connection
rate limiting, server-side filtering, pub/sub fanout.

Example::

    from nexus import Nexus
    from nexus.websocket_handlers import MessageHandler, Connection

    app = Nexus()

    @app.websocket("/events")
    class EventStream(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            conn.state.subscriptions = set()

        async def on_message(self, conn: Connection, msg: dict) -> None:
            action = msg.get("action")
            if action == "subscribe":
                conn.state.subscriptions.add(msg["topic"])
            elif action == "unsubscribe":
                conn.state.subscriptions.discard(msg["topic"])

        async def on_disconnect(self, conn: Connection) -> None:
            # subscriptions cleaned up automatically when conn is removed
            pass

        async def on_event(self, event: dict) -> None:
            # fanout to all connections that subscribed to the topic
            for conn in self.connections:
                if event["topic"] in conn.state.subscriptions:
                    await conn.send_json(event)

    # Publisher triggers fanout
    await app.websocket_broadcast("/events", {"topic": "trades", "price": 42})
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Type

logger = logging.getLogger(__name__)

__all__ = [
    "Connection",
    "MessageHandler",
    "MessageHandlerRegistry",
]


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class Connection:
    """A server-side view of a WebSocket connection with per-connection state.

    Instances are created by :class:`MessageHandlerRegistry` when a
    client opens a WebSocket. Each connection carries:

    - ``connection_id``: a stable UUID hex string unique for the
      lifetime of the connection.
    - ``state``: a :class:`types.SimpleNamespace` for handler-owned
      bookkeeping (subscriptions, filters, authenticated user, etc.).
      The framework never writes to ``state``; it belongs entirely to
      the handler.
    - ``connected_at``: monotonic timestamp of connection open.
    - ``path``: the URL path the client connected on (e.g. ``/events``).

    Handlers send messages back to the client with :meth:`send_json`
    (JSON-serialized) or :meth:`send_text` (raw text frame). Both
    methods return ``True`` on success and ``False`` if the socket has
    already closed — the handler is not expected to wrap every send in
    try/except.

    The underlying ``websockets`` connection is available as ``ws`` for
    advanced use, but handlers should prefer the ``send_*`` helpers so
    the registry can track delivery failures and prune dead
    connections.
    """

    __slots__ = (
        "ws",
        "connection_id",
        "path",
        "state",
        "connected_at",
        "_alive",
    )

    def __init__(self, ws: Any, connection_id: str, path: str) -> None:
        self.ws = ws
        self.connection_id = connection_id
        self.path = path
        # state is a plain namespace — handler owns it entirely
        self.state: SimpleNamespace = SimpleNamespace()
        self.connected_at: float = time.monotonic()
        self._alive: bool = True

    @property
    def alive(self) -> bool:
        """Whether the registry still considers the connection open.

        Becomes ``False`` after the client disconnects or a send fails.
        Handlers that cache ``Connection`` references across calls
        MUST check ``alive`` before sending; sending to a dead
        connection is a no-op returning ``False``.
        """
        return self._alive

    async def send_json(self, payload: Any) -> bool:
        """Send ``payload`` as a JSON text frame.

        Returns ``True`` if the frame was successfully handed to the
        websockets library, ``False`` if the connection was already
        closed or the send raised. A ``False`` return marks the
        connection dead and prunes it from the registry.
        """
        if not self._alive:
            return False
        try:
            await self.ws.send(json.dumps(payload, default=str))
            return True
        except Exception as exc:  # noqa: BLE001 — mark dead, surface at WARN
            logger.debug(
                "ws.connection.send_failed",
                extra={
                    "connection_id": self.connection_id,
                    "path": self.path,
                    "error": str(exc),
                },
            )
            self._alive = False
            return False

    async def send_text(self, message: str) -> bool:
        """Send a raw text frame. See :meth:`send_json` for semantics."""
        if not self._alive:
            return False
        try:
            await self.ws.send(message)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "ws.connection.send_failed",
                extra={
                    "connection_id": self.connection_id,
                    "path": self.path,
                    "error": str(exc),
                },
            )
            self._alive = False
            return False

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket with a status code and reason."""
        self._alive = False
        try:
            await self.ws.close(code, reason)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "ws.connection.close_failed",
                extra={
                    "connection_id": self.connection_id,
                    "error": str(exc),
                },
            )


# ---------------------------------------------------------------------------
# MessageHandler
# ---------------------------------------------------------------------------


class MessageHandler:
    """Base class for WebSocket message handlers with per-connection state.

    Subclass this, override the lifecycle hooks, and register the
    subclass against a path via :meth:`MessageHandlerRegistry.register`
    or the :meth:`Nexus.websocket` decorator.

    Lifecycle hooks (all async, all no-op by default):

    - :meth:`on_connect` — fired after the client completes the
      WebSocket handshake. Initialize per-connection state here.
    - :meth:`on_message` — fired for every client-sent text/binary
      frame. The frame is JSON-decoded to ``dict``; raw text is passed
      to :meth:`on_text` instead.
    - :meth:`on_text` — fired when the client sends a non-JSON text
      frame. Default implementation drops it; override to handle raw
      text protocols.
    - :meth:`on_disconnect` — fired after the client closes (normal or
      abnormal). Use to release external resources the handler
      allocated. The connection is already removed from
      ``self.connections`` by the time this fires.
    - :meth:`on_event` — not fired by the framework directly; called
      by :meth:`broadcast_event` as a fanout hook. Override to
      implement topic-based subscription fanout.

    The handler instance is constructed exactly once and shared across
    all connections, so **instance attributes MUST NOT hold
    per-connection state**. Per-connection state lives on
    ``conn.state``. Cross-connection state (a topic index, a shared
    counter, a pub/sub client) is the one legitimate use of instance
    attributes.

    The ``self.connections`` property returns a live-ish view of the
    currently-open connections for this handler. It is a snapshot:
    iteration is safe even if a connection drops mid-iteration, but
    the snapshot may not reflect connections that opened after the
    iterator started.
    """

    # Set by MessageHandlerRegistry when the handler is registered.
    _registry: Optional["MessageHandlerRegistry"] = None
    _path: Optional[str] = None

    # ------------------------------------------------------------------
    # Framework-provided properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> str:
        """The URL path this handler is registered on."""
        if self._path is None:
            raise RuntimeError(
                "MessageHandler.path accessed before handler was registered — "
                "register via @app.websocket('/path') or "
                "MessageHandlerRegistry.register() first."
            )
        return self._path

    @property
    def connections(self) -> List[Connection]:
        """Snapshot of currently-open connections on this handler's path.

        Returns a new list each call, so iterating is safe even if
        connections are added or removed concurrently. Order is not
        guaranteed.
        """
        if self._registry is None:
            return []
        return self._registry._snapshot_connections(self._path)

    @property
    def connection_count(self) -> int:
        """Number of currently-open connections on this handler's path."""
        if self._registry is None:
            return 0
        return self._registry._count_connections(self._path)

    # ------------------------------------------------------------------
    # Lifecycle hooks — override in subclass
    # ------------------------------------------------------------------

    async def on_connect(self, conn: Connection) -> None:
        """Called once when a client opens a connection.

        Override to initialize ``conn.state.*`` attributes. Raising
        here aborts the connection — the registry will close the
        WebSocket with a 4500 application error.
        """
        return None

    async def on_message(self, conn: Connection, msg: Dict[str, Any]) -> Any:
        """Called for each JSON-decoded message from the client.

        ``msg`` is a dict parsed from the client's JSON frame. For
        non-JSON text frames :meth:`on_text` is called instead.
        Override in subclass.

        **Return value handling (issue #618):** If this method returns a
        non-``None`` value, the registry sends it back to the same
        client on the same connection as a unicast reply:

        - ``dict`` / ``list`` → JSON-encoded text frame via
          :meth:`Connection.send_json`.
        - ``str`` → raw text frame via :meth:`Connection.send_text`.
        - ``bytes`` → decoded as UTF-8 and sent as text frame; raises
          :class:`UnicodeDecodeError` only if the bytes are not valid
          UTF-8 (logged at WARN, frame dropped).
        - ``None`` → no auto-reply; the handler is free to call
          ``await conn.send_*`` explicitly.

        Cross-SDK parity: kailash-rs#589 implements the same
        return-value-as-reply contract on the Rust side.
        """
        return None

    async def on_text(self, conn: Connection, text: str) -> Any:
        """Called for each non-JSON text frame from the client.

        Default implementation logs at DEBUG and drops the frame.
        Override to handle raw text protocols.

        **Return value handling (issue #618):** Same contract as
        :meth:`on_message` — non-``None`` return values are auto-sent
        back to the same client.
        """
        logger.debug(
            "ws.handler.text_frame_dropped",
            extra={
                "connection_id": conn.connection_id,
                "path": conn.path,
                "length": len(text),
            },
        )

    async def on_disconnect(self, conn: Connection) -> None:
        """Called once after a client's connection closes.

        Use to release external resources the handler allocated for
        this connection (DB cursors, timers, etc.). The registry has
        already removed ``conn`` from :attr:`connections`; do not try
        to send through ``conn`` here.
        """
        return None

    async def on_event(self, event: Any) -> None:
        """Fanout hook called by :meth:`broadcast_event`.

        Not invoked by the framework directly. Override to iterate
        ``self.connections`` and filter by per-connection state.
        """
        return None

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def broadcast_event(self, event: Any) -> None:
        """Trigger :meth:`on_event` with ``event``.

        This is the canonical entry point for server-originated events
        (e.g. from a DataFlow change stream, a message queue consumer,
        or another Nexus handler). Handlers override ``on_event`` to
        decide which connections receive it.
        """
        try:
            await self.on_event(event)
        except Exception:  # noqa: BLE001 — don't kill the publisher
            logger.exception(
                "ws.handler.on_event_error",
                extra={"path": self._path or "<unregistered>"},
            )

    async def broadcast_all(self, payload: Any) -> int:
        """Send ``payload`` as JSON to every open connection.

        Returns the number of successful sends. Connections that fail
        are marked dead and the registry will prune them on the next
        receive cycle.
        """
        sent = 0
        for conn in self.connections:
            if await conn.send_json(payload):
                sent += 1
        return sent


# ---------------------------------------------------------------------------
# MessageHandlerRegistry
# ---------------------------------------------------------------------------


class MessageHandlerRegistry:
    """Routes WebSocket connections to class-based message handlers by path.

    The registry is attached to a :class:`Nexus` instance (via
    :meth:`Nexus.websocket`). When a WebSocket client connects, the
    registry:

    1. Matches the request path against registered handlers.
    2. Instantiates a :class:`Connection` and records it in the
       per-path set.
    3. Invokes :meth:`MessageHandler.on_connect`.
    4. Runs a receive loop that dispatches each frame to
       :meth:`MessageHandler.on_message` (for JSON) or
       :meth:`MessageHandler.on_text` (for non-JSON text).
    5. On close, invokes :meth:`MessageHandler.on_disconnect` and
       removes the connection from the per-path set.

    Invariants (enforced by tests):

    - State isolation: every :class:`Connection` has its own
      ``state`` namespace. Two connections on the same handler path
      MUST NOT share state unless the handler explicitly writes to
      its own instance attributes.
    - Connection lifecycle: every :meth:`on_connect` is paired with
      exactly one :meth:`on_disconnect`, even when the handshake
      fails or the connection errors mid-message.
    - Registry consistency: ``handler.connections`` never contains a
      connection whose socket has closed; pruning happens before
      the next receive iteration completes.
    - Broadcast filtering: :meth:`MessageHandler.on_event` sees the
      current snapshot; the handler decides who receives the event.
    - Cleanup: handler instance attributes, per-connection state,
      and socket handles are released on disconnect or on registry
      ``clear``.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, MessageHandler] = {}
        # path -> set of connection_id -> Connection
        self._connections_by_path: Dict[str, Dict[str, Connection]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, path: str, handler_cls: Type[MessageHandler]) -> MessageHandler:
        """Register a handler class against a URL path.

        The class is instantiated immediately (with no arguments). A
        handler's ``__init__`` is therefore not a place for per-request
        work; it runs once at registration time.

        Raises:
            ValueError: if ``path`` is already registered or is not a
                valid WebSocket path (must start with ``/``).
            TypeError: if ``handler_cls`` is not a subclass of
                :class:`MessageHandler`.
        """
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError(
                f"websocket path must be a string starting with '/' "
                f"(got {type(path).__name__}={path!r})"
            )
        if path in self._handlers:
            raise ValueError(
                f"websocket path {path!r} is already registered "
                f"(handler={type(self._handlers[path]).__name__})"
            )
        if not (
            isinstance(handler_cls, type) and issubclass(handler_cls, MessageHandler)
        ):
            raise TypeError(
                f"handler must be a subclass of MessageHandler "
                f"(got {handler_cls!r})"
            )

        handler = handler_cls()
        handler._registry = self
        handler._path = path
        self._handlers[path] = handler
        self._connections_by_path[path] = {}
        logger.info(
            "ws.handler.registered",
            extra={"path": path, "handler": handler_cls.__name__},
        )
        return handler

    def get(self, path: str) -> Optional[MessageHandler]:
        """Return the handler registered at ``path``, or ``None``."""
        return self._handlers.get(path)

    @property
    def paths(self) -> Set[str]:
        """Set of currently-registered paths."""
        return set(self._handlers)

    def clear(self) -> None:
        """Drop all handlers and close their connections.

        Used by :class:`Nexus` on stop and by tests for isolation.
        """
        for path, conns in list(self._connections_by_path.items()):
            for conn in list(conns.values()):
                conn._alive = False
        self._handlers.clear()
        self._connections_by_path.clear()

    # ------------------------------------------------------------------
    # Connection dispatch (called from WebSocketTransport)
    # ------------------------------------------------------------------

    async def handle_connection(self, ws: Any, path: str) -> bool:
        """Run the full lifecycle of a WebSocket connection.

        Called by :class:`WebSocketTransport` when a client connects
        on a path that matches a registered handler. Runs
        ``on_connect``, the receive loop, and ``on_disconnect``;
        returns ``True`` if the connection was handled by a
        registered handler (even if it errored), ``False`` if no
        handler was registered for the path.

        State isolation invariant: each call creates a fresh
        :class:`Connection`, so ``conn.state`` is always a new
        :class:`types.SimpleNamespace`.

        Lifecycle invariant: ``on_disconnect`` is called for every
        ``on_connect`` that returned normally, even if the receive
        loop raises or the socket closes abnormally.
        """
        handler = self._handlers.get(path)
        if handler is None:
            return False

        connection_id = uuid.uuid4().hex
        conn = Connection(ws, connection_id, path)
        self._connections_by_path[path][connection_id] = conn

        connect_ok = False
        try:
            try:
                await handler.on_connect(conn)
                connect_ok = True
            except Exception:  # noqa: BLE001
                logger.exception(
                    "ws.handler.on_connect_error",
                    extra={"path": path, "connection_id": connection_id},
                )
                await conn.close(4500, "handler on_connect failed")
                return True

            await self._receive_loop(handler, conn)
        except Exception:  # noqa: BLE001
            # websockets raises ConnectionClosed variants on client
            # disconnect; log anything unexpected at DEBUG so on_disconnect
            # still fires below.
            logger.debug(
                "ws.handler.receive_loop_ended",
                extra={"path": path, "connection_id": connection_id},
                exc_info=True,
            )
        finally:
            conn._alive = False
            # Remove from registry BEFORE on_disconnect so handler sees
            # the post-disconnect snapshot (lifecycle invariant).
            # clear() may have already removed the per-path dict, so the
            # .get() guard is load-bearing — a KeyError here would skip
            # on_disconnect and break the lifecycle invariant.
            path_conns = self._connections_by_path.get(path)
            if path_conns is not None:
                path_conns.pop(connection_id, None)
            if connect_ok:
                try:
                    await handler.on_disconnect(conn)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "ws.handler.on_disconnect_error",
                        extra={"path": path, "connection_id": connection_id},
                    )

        return True

    async def _receive_loop(self, handler: MessageHandler, conn: Connection) -> None:
        """Read frames from the socket and dispatch to the handler."""
        async for raw in conn.ws:
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except UnicodeDecodeError:
                    logger.debug(
                        "ws.handler.invalid_utf8",
                        extra={
                            "path": conn.path,
                            "connection_id": conn.connection_id,
                        },
                    )
                    continue

            # Try JSON first; fall back to on_text for non-JSON frames.
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                await self._safe_on_text(handler, conn, raw)
                continue

            if isinstance(msg, dict):
                await self._safe_on_message(handler, conn, msg)
            else:
                # JSON that isn't a dict (array, scalar) — pass to on_text
                # rather than silently dropping, so protocols that send
                # JSON arrays can still handle them.
                await self._safe_on_text(handler, conn, raw)

    @staticmethod
    async def _safe_on_message(
        handler: MessageHandler, conn: Connection, msg: Dict[str, Any]
    ) -> None:
        try:
            reply = await handler.on_message(conn, msg)
        except Exception:  # noqa: BLE001
            logger.exception(
                "ws.handler.on_message_error",
                extra={
                    "path": conn.path,
                    "connection_id": conn.connection_id,
                },
            )
            return
        await MessageHandlerRegistry._deliver_reply(conn, reply)

    @staticmethod
    async def _safe_on_text(
        handler: MessageHandler, conn: Connection, text: str
    ) -> None:
        try:
            reply = await handler.on_text(conn, text)
        except Exception:  # noqa: BLE001
            logger.exception(
                "ws.handler.on_text_error",
                extra={
                    "path": conn.path,
                    "connection_id": conn.connection_id,
                },
            )
            return
        await MessageHandlerRegistry._deliver_reply(conn, reply)

    # ------------------------------------------------------------------
    # on_message return-value delivery (issue #618 + cross-SDK kailash-rs#589)
    # ------------------------------------------------------------------

    @staticmethod
    async def _deliver_reply(conn: Connection, reply: Any) -> None:
        """Deliver a non-None ``on_message`` / ``on_text`` return value.

        Tenant-safe by construction: dispatch is scoped to ``conn`` —
        the same socket the client sent the request on. No broadcast
        leakage; the reply CAN ONLY reach the originating client.

        Type contract:
        - ``None``  → no-op (handler did its own send, or doesn't reply)
        - ``dict`` / ``list`` → JSON via ``send_json``
        - ``str`` → raw text via ``send_text``
        - ``bytes`` → UTF-8 decoded then ``send_text``; on
          ``UnicodeDecodeError`` log WARN and drop
        - any other type → ``send_json`` (best-effort
          ``json.dumps(default=str)``); ``TypeError`` logged at WARN.
        """
        if reply is None:
            return
        if isinstance(reply, (dict, list)):
            await conn.send_json(reply)
            return
        if isinstance(reply, str):
            await conn.send_text(reply)
            return
        if isinstance(reply, (bytes, bytearray)):
            try:
                text = bytes(reply).decode("utf-8")
            except UnicodeDecodeError as exc:
                logger.warning(
                    "ws.handler.reply_bytes_not_utf8",
                    extra={
                        "path": conn.path,
                        "connection_id": conn.connection_id,
                        "error": str(exc),
                    },
                )
                return
            await conn.send_text(text)
            return
        # Fallback for arbitrary serializable objects (numbers, bools,
        # custom dataclasses with default=str). Same shape as send_json
        # so handlers that return a typed object behave like dict.
        try:
            await conn.send_json(reply)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "ws.handler.reply_unserializable",
                extra={
                    "path": conn.path,
                    "connection_id": conn.connection_id,
                    "type": type(reply).__name__,
                    "error": str(exc),
                },
            )

    # ------------------------------------------------------------------
    # Broadcast entry points (called from user code / Nexus)
    # ------------------------------------------------------------------

    async def broadcast_event(self, path: str, event: Any) -> None:
        """Fire :meth:`MessageHandler.on_event` on the handler at ``path``.

        Raises KeyError if no handler is registered.
        """
        handler = self._handlers.get(path)
        if handler is None:
            raise KeyError(f"no websocket handler registered at {path!r}")
        await handler.broadcast_event(event)

    async def send_to(self, path: str, connection_id: str, payload: Any) -> bool:
        """Send ``payload`` to a single tracked connection (issue #618).

        External-publisher unicast: scoped to the exact connection
        identified by (``path``, ``connection_id``). Tenant-safe by
        construction — the dispatch reaches ONLY the named socket;
        every other connection on the same path is unaffected.

        Args:
            path: URL path the connection was registered on (e.g.
                ``"/events"``). MUST match a registered handler.
            connection_id: The :attr:`Connection.connection_id`
                returned by ``on_connect`` for the target client.
            payload: JSON-serializable value (sent via
                :meth:`Connection.send_json`), :class:`str` (sent via
                :meth:`Connection.send_text`), or :class:`bytes`
                (UTF-8 decoded then sent as text frame).

        Returns:
            ``True`` if the frame was successfully handed to the
            socket; ``False`` if the path has no registered handler,
            the connection_id is unknown, the connection is already
            closed, or the send raised. The registry prunes dead
            connections on the next receive cycle in either case.
        """
        path_conns = self._connections_by_path.get(path)
        if path_conns is None:
            logger.debug(
                "ws.send_to.unknown_path",
                extra={"path": path, "connection_id": connection_id},
            )
            return False
        conn = path_conns.get(connection_id)
        if conn is None:
            logger.debug(
                "ws.send_to.unknown_connection_id",
                extra={"path": path, "connection_id": connection_id},
            )
            return False
        if not conn.alive:
            return False
        # Reuse the shared delivery contract so external send_to and
        # on_message return-value reply produce identical wire frames.
        if isinstance(payload, str):
            return await conn.send_text(payload)
        if isinstance(payload, (bytes, bytearray)):
            try:
                text = bytes(payload).decode("utf-8")
            except UnicodeDecodeError as exc:
                logger.warning(
                    "ws.send_to.bytes_not_utf8",
                    extra={
                        "path": path,
                        "connection_id": connection_id,
                        "error": str(exc),
                    },
                )
                return False
            return await conn.send_text(text)
        return await conn.send_json(payload)

    # ------------------------------------------------------------------
    # Internals used by MessageHandler
    # ------------------------------------------------------------------

    def _snapshot_connections(self, path: Optional[str]) -> List[Connection]:
        if path is None:
            return []
        return list(self._connections_by_path.get(path, {}).values())

    def _count_connections(self, path: Optional[str]) -> int:
        if path is None:
            return 0
        return len(self._connections_by_path.get(path, {}))
