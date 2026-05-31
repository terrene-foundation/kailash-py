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
from types import MappingProxyType, SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Set, Type

from nexus.websocket_origin import (
    fingerprint_origin,
    origin_matches_allowlist,
    validate_origin_allowlist,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Connection",
    "MessageHandler",
    "MessageHandlerRegistry",
]


# Empty case-insensitive headers fallback: an immutable Mapping returned
# when a connection arrives without parsable handshake headers (e.g. a
# test using a bare mock socket). Letting handlers see ``conn.headers``
# as ``None`` would force every site to ``if conn.headers is not None``;
# returning an empty Mapping keeps the read-only API surface stable.
_EMPTY_HEADERS: Mapping[str, str] = MappingProxyType({})


class _CaseInsensitiveHeaders(Mapping[str, str]):
    """Read-only case-insensitive mapping over a snapshot of HTTP headers.

    Used when the underlying handshake headers come back as a plain
    ``dict`` (test fixtures, future transports). When the websockets
    library passes its own ``Headers`` object (which is already
    case-insensitive), :func:`_freeze_headers` returns it wrapped in
    ``MappingProxyType`` directly so case-insensitive lookups still
    work at zero copy cost.
    """

    __slots__ = ("_lower",)

    def __init__(self, source: Mapping[str, str]) -> None:
        # Snapshot at construction so later mutation of the source
        # does NOT mutate the headers handlers see.
        self._lower: Dict[str, str] = {}
        for k, v in source.items():
            self._lower[k.lower()] = v

    def __getitem__(self, key: str) -> str:
        return self._lower[key.lower()]

    def __iter__(self):
        return iter(self._lower)

    def __len__(self) -> int:
        return len(self._lower)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key.lower() in self._lower


def _freeze_headers(source: Any) -> Mapping[str, str]:
    """Return an immutable case-insensitive view of ``source``.

    - ``None`` → empty mapping.
    - ``dict`` (or any mutable Mapping) → fresh
      :class:`_CaseInsensitiveHeaders` snapshot wrapped in
      :class:`types.MappingProxyType` semantics (mutation refused).
    - ``websockets.datastructures.Headers`` (or any other Mapping
      subclass that already implements case-insensitive lookup) →
      wrapped in a thin proxy that forbids mutation.

    The returned object MUST raise on any mutation attempt so
    handlers cannot mutate the source headers via ``conn.headers``
    (operators MUST not be able to falsify the captured handshake
    headers from inside ``on_connect``).
    """
    if source is None:
        return _EMPTY_HEADERS
    if isinstance(source, Mapping):
        # Even though ``websockets.Headers`` is already case-insensitive,
        # snapshotting via _CaseInsensitiveHeaders normalizes the
        # underlying type so handlers see one consistent surface.
        return _CaseInsensitiveHeaders(source)
    # Best effort: try to coerce iterable-of-pairs to a Mapping.
    try:
        coerced = dict(source)
    except (TypeError, ValueError):
        return _EMPTY_HEADERS
    return _CaseInsensitiveHeaders(coerced)


def _extract_handshake_headers(ws: Any) -> Mapping[str, str]:
    """Return the handshake headers from the underlying ``websockets`` socket.

    websockets 16+ exposes the parsed handshake at
    ``ws.request.headers`` (a
    :class:`websockets.datastructures.Headers` instance). Other
    transports may set ``ws.request_headers`` directly. Test fixtures
    can pass a bare object; in all of those cases we fall through to
    the empty mapping rather than raising.
    """
    request = getattr(ws, "request", None)
    if request is not None:
        headers = getattr(request, "headers", None)
        if headers is not None:
            return _freeze_headers(headers)
    # Older / alternate code paths may attach headers directly.
    direct = getattr(ws, "request_headers", None)
    if direct is not None:
        return _freeze_headers(direct)
    return _EMPTY_HEADERS


def _validate_subprotocols(subprotocols: Optional[List[str]]) -> List[str]:
    """Validate the ``subprotocols`` allowlist at registration time.

    Returns a fresh ``list[str]`` (empty when ``None`` — the default-reject
    posture). Raises ``ValueError`` on a non-list or a non-string / empty
    entry so a malformed allowlist never silently registers (issue #1174
    AC 6 MUST 2).
    """
    if subprotocols is None:
        return []
    if isinstance(subprotocols, str):
        raise ValueError(
            "subprotocols must be a list of strings, not a single string "
            '(did you mean subprotocols=["chat.v1"]?)'
        )
    validated: List[str] = []
    for raw in subprotocols:
        if not isinstance(raw, str):
            raise ValueError(
                f"subprotocols entries must be str; got {type(raw).__name__}"
            )
        entry = raw.strip()
        if not entry:
            raise ValueError("subprotocols entries must be non-empty strings")
        validated.append(entry)
    return validated


def _offered_subprotocols(ws: Any) -> List[str]:
    """Return the client's offered ``Sec-WebSocket-Protocol`` values.

    Parses the comma-separated header per RFC 6455 §11.3.4. Returns an empty
    list when the client offered none.
    """
    headers = _extract_handshake_headers(ws)
    raw = headers.get("sec-websocket-protocol")
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


async def _resolve_ws_dependencies(dependencies: List[Any], ws: Any) -> None:
    """Resolve handshake-auth ``Depends`` immediately post-upgrade, pre-on_connect.

    Routes through the Shard-1 resolver chain (``nexus.extractors.resolver``)
    so WS handshake auth is byte-identical to the HTTP path. The ``Depends``
    callables resolve against a synthetic Starlette-style request built from
    the handshake headers (the WebSocket has no Starlette ``Request``); the
    callables typically read ``request.headers`` for a bearer token.

    Timing note: ``websockets.serve()`` performs the Upgrade BEFORE the
    transport's connection handler runs, so this resolution executes against an
    already-upgraded socket — NOT before the upgrade. The security boundary
    still holds: a raising dependency is rejected here, BEFORE ``on_connect``
    or any application message, and the socket is closed with WS close code
    1008 (policy violation). A clean HTTP 401/403 response body cannot be
    emitted after the upgrade completes; WS-1008 is the correct WS-native
    rejection. (issue #1174 AC 6 MUST 4. True pre-upgrade ``process_request``
    rejection — which CAN emit an HTTP 401/403 — is a separate follow-up.)
    """
    if not dependencies:
        return
    from nexus.context import _current_request, set_current_request
    from nexus.extractors import Depends
    from nexus.extractors.resolver import ResolverChain

    request = _HandshakeRequest(_extract_handshake_headers(ws))
    token = set_current_request(request)
    try:
        chain = ResolverChain(lambda: None, [])
        cache: Dict[Callable, Any] = {}
        for dep in dependencies:
            if not isinstance(dep, Depends):
                raise TypeError(
                    "register_websocket dependencies must be Depends(...) "
                    f"markers; got {type(dep).__name__}"
                )
            await chain._resolve_dependency(dep, request, cache, None)
    finally:
        _current_request.reset(token)


class _HandshakeRequest:
    """Minimal Starlette-``Request``-shaped view over WS handshake headers.

    The WebSocket handshake has no Starlette ``Request`` object, but handshake
    ``Depends`` callables that read ``request.headers`` for a bearer token need
    a header surface. This adapter exposes the captured handshake headers (a
    read-only case-insensitive Mapping) as ``.headers`` so a ``Depends`` that
    inspects ``request.headers.get("authorization")`` works unchanged. It is
    NOT a full Request — it carries handshake auth context only.
    """

    __slots__ = ("headers",)

    def __init__(self, headers: Mapping[str, str]) -> None:
        self.headers = headers


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
    - ``headers``: read-only :class:`~typing.Mapping` of HTTP
      handshake headers (Origin, Host, User-Agent, Sec-WebSocket-*,
      cookies, custom auth headers). Captured AT HANDSHAKE; NOT
      refreshed during the connection lifetime. Lookups are
      case-insensitive (``conn.headers["origin"]`` and
      ``conn.headers["Origin"]`` return the same value). The mapping
      is structurally immutable — attempts to assign or delete keys
      raise ``TypeError``. Operators MUST NOT be able to falsify
      captured headers from inside ``on_connect`` (issue #673).

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
        "_headers",
    )

    def __init__(
        self,
        ws: Any,
        connection_id: str,
        path: str,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.ws = ws
        self.connection_id = connection_id
        self.path = path
        # state is a plain namespace — handler owns it entirely
        self.state: SimpleNamespace = SimpleNamespace()
        self.connected_at: float = time.monotonic()
        self._alive: bool = True
        # Headers captured at handshake. Frozen via _freeze_headers so
        # any mutation attempt raises TypeError. Defaults to the empty
        # mapping when the caller (test fixture, alternate transport)
        # does not supply headers.
        self._headers: Mapping[str, str] = _freeze_headers(headers)

    @property
    def headers(self) -> Mapping[str, str]:
        """HTTP handshake headers (Origin, Host, User-Agent, Sec-WebSocket-*).

        Read-only case-insensitive Mapping. Captured AT HANDSHAKE;
        NOT refreshed during the connection lifetime. Mutation
        attempts (``conn.headers["X"] = "Y"`` /
        ``del conn.headers["X"]``) raise ``TypeError``.

        Issue #673: surfaces the request headers to ``on_connect`` so
        consumers needing custom enforcement (signed-token check,
        per-tenant auth header validation) beyond the SDK's built-in
        ``allowed_origins`` allowlist have a structural way in. The
        SDK-level allowlist (see :meth:`Nexus.register_websocket`'s
        ``allowed_origins`` parameter) is the recommended default;
        ``conn.headers`` is the escape hatch.
        """
        return self._headers

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
        # path -> validated allowed_origins list (None == SDK does
        # not enforce; handler must use conn.headers itself).
        self._allowed_origins_by_path: Dict[str, Optional[List[str]]] = {}
        # path -> subprotocol allowlist (issue #1174 AC 6 MUST 2). Empty list
        # (the default) means default-reject ANY client-offered subprotocol.
        self._subprotocols_by_path: Dict[str, List[str]] = {}
        # path -> max inbound message size in bytes (issue #1174 AC 6 MUST 3).
        # None == inherit the transport's max_size (no per-path override).
        self._max_message_bytes_by_path: Dict[str, Optional[int]] = {}
        # path -> handshake-auth Depends list (issue #1174 AC 6 MUST 4).
        self._dependencies_by_path: Dict[str, List[Any]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        path: str,
        handler_cls: Type[MessageHandler],
        *,
        allowed_origins: Optional[List[str]] = None,
        subprotocols: Optional[List[str]] = None,
        dependencies: Optional[List[Any]] = None,
        max_message_bytes: Optional[int] = None,
    ) -> MessageHandler:
        """Register a handler class against a URL path.

        The class is instantiated immediately (with no arguments). A
        handler's ``__init__`` is therefore not a place for per-request
        work; it runs once at registration time.

        Args:
            path: URL path (must start with ``/``).
            handler_cls: subclass of :class:`MessageHandler`.
            allowed_origins: optional list of HTTP ``Origin`` header
                values allowed to upgrade to this WebSocket path.
                When set, the registry rejects every handshake whose
                ``Origin`` does NOT match an entry BEFORE invoking
                ``on_connect``. See :func:`validate_origin_allowlist`
                for the entry shape (exact origins, ``https://*.x.com``
                wildcards, fail-closed ``"*"``). When ``None``, the
                SDK does NOT enforce — operators MUST either use
                ``conn.headers`` from inside ``on_connect`` for custom
                enforcement OR explicitly accept that the endpoint is
                Origin-unfiltered. Issue #673.
            subprotocols: optional allowlist of ``Sec-WebSocket-Protocol``
                values (issue #1174 AC 6 MUST 2). Negotiation is
                REJECT-ONLY: the allowlist is VALIDATED against the client's
                offered subprotocols but the accepted value is NOT echoed back
                to the client (no ``Sec-WebSocket-Protocol`` on the accept).
                The default (``None`` / ``[]``) DEFAULT-REJECTS any
                client-offered subprotocol: a handshake offering a subprotocol
                when the list is empty closes with code 1002 (protocol error).
                A non-empty list admits the connection when at least one offered
                value is present in the list, and closes with 1002 otherwise.
                (Echoing the accepted subprotocol per RFC 6455 §4.2.2 via
                ``select_subprotocol`` is a separate follow-up — it shares the
                ``serve()``-rewiring root with the pre-upgrade ``Depends``
                follow-up.)
            dependencies: optional list of ``Depends(...)`` markers
                resolved immediately POST-upgrade and BEFORE ``on_connect``
                / any application message (issue #1174 AC 6 MUST 4). A raising
                dependency closes the socket with WS close code 1008 (the typed
                HTTP status rides in the close reason); the handler lifecycle
                never starts. ``websockets.serve()`` upgrades before this runs,
                so a clean pre-upgrade HTTP 401/403 body is not emittable —
                WS-1008 is the WS-native rejection (true pre-upgrade
                ``process_request`` rejection is a separate follow-up).
            max_message_bytes: optional per-path inbound message-size cap
                (issue #1174 AC 6 MUST 3). A frame exceeding the cap
                closes the connection with code 1009 (message too big).
                ``None`` inherits the transport-level ``max_size``.

        Raises:
            ValueError: if ``path`` is already registered, is not a
                valid WebSocket path (must start with ``/``), or
                ``allowed_origins`` fails validation.
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

        # Validate allowed_origins at registration time (typed
        # ValueError on failure; raises BEFORE the handler is
        # instantiated so a bad allowlist never silently registers).
        validated_origins = validate_origin_allowlist(allowed_origins)
        validated_subprotocols = _validate_subprotocols(subprotocols)

        handler = handler_cls()
        handler._registry = self
        handler._path = path
        self._handlers[path] = handler
        self._connections_by_path[path] = {}
        self._allowed_origins_by_path[path] = validated_origins
        self._subprotocols_by_path[path] = validated_subprotocols
        self._dependencies_by_path[path] = list(dependencies or [])
        self._max_message_bytes_by_path[path] = max_message_bytes
        logger.info(
            "ws.handler.registered",
            extra={
                "path": path,
                "handler": handler_cls.__name__,
                "origin_enforcement": (
                    "sdk" if validated_origins is not None else "none"
                ),
            },
        )
        if validated_origins is None:
            # One-time WARN at registration so operators see the gap
            # without per-request log spam. Per rules/observability.md
            # Rule 3: WARN means "succeeded but used a degraded
            # path" — accepting the registration without SDK Origin
            # enforcement IS the degraded path.
            logger.warning(
                "ws.handler.origin_enforcement_disabled",
                extra={
                    "path": path,
                    "handler": handler_cls.__name__,
                    "remediation": (
                        "pass allowed_origins=[...] to register_websocket "
                        "OR enforce manually via conn.headers in on_connect"
                    ),
                },
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
        self._allowed_origins_by_path.clear()
        self._subprotocols_by_path.clear()
        self._dependencies_by_path.clear()
        self._max_message_bytes_by_path.clear()

    def get_allowed_origins(self, path: str) -> Optional[List[str]]:
        """Return the validated allowed_origins list for ``path``.

        Returns ``None`` if no SDK enforcement is active (or no
        handler is registered). Test-only inspection helper —
        production code should NOT need to read this.
        """
        return self._allowed_origins_by_path.get(path)

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

        Issue #673 — Origin enforcement: BEFORE invoking
        ``on_connect``, if the path's ``allowed_origins`` list is
        non-``None``, the request's ``Origin`` header is checked
        against the allowlist. Mismatches close the WebSocket with
        code 1008 (per RFC 6455 — policy violation) and a
        fingerprinted reason; ``on_connect`` and ``on_disconnect``
        do NOT fire (the connection never reached the handler's
        lifecycle).

        State isolation invariant: each call creates a fresh
        :class:`Connection`, so ``conn.state`` is always a new
        :class:`types.SimpleNamespace`.

        Lifecycle invariant: ``on_disconnect`` is called for every
        ``on_connect`` that returned normally, even if the receive
        loop raises or the socket closes abnormally. Origin-rejected
        connections are NOT subject to this invariant — they never
        invoke ``on_connect``.
        """
        handler = self._handlers.get(path)
        if handler is None:
            return False

        # Extract handshake headers BEFORE constructing Connection so
        # the headers are available to on_connect from the first
        # millisecond of the handler's lifecycle.
        headers = _extract_handshake_headers(ws)

        # Issue #673 — Origin allowlist enforcement (pre-on_connect).
        allowed_origins = self._allowed_origins_by_path.get(path)
        if allowed_origins is not None:
            origin = headers.get("origin")
            if not origin_matches_allowlist(origin, allowed_origins):
                # Fingerprint per rules/observability.md Rule 6 + 8:
                # never echo the raw Origin to log aggregators.
                fingerprint = fingerprint_origin(origin)
                logger.warning(
                    "ws.handler.origin_rejected",
                    extra={
                        "path": path,
                        "handler": type(handler).__name__,
                        "origin_fingerprint": fingerprint,
                        "reason": (
                            "missing_origin_header"
                            if origin is None
                            else "origin_not_in_allowlist"
                        ),
                    },
                )
                # Generic close reason — never echo the rejected
                # Origin back to the client (would let an attacker
                # confirm a probe). Code 1008 = "policy violation"
                # per RFC 6455 §7.4.1.
                try:
                    await ws.close(1008, f"origin rejected ({fingerprint})")
                except Exception as exc:  # noqa: BLE001 — best-effort
                    logger.debug(
                        "ws.handler.origin_close_failed",
                        extra={
                            "path": path,
                            "origin_fingerprint": fingerprint,
                            "error": str(exc),
                        },
                    )
                # Returning True signals the transport that the
                # connection was handled (rejected by policy is a
                # form of handling); without it the transport falls
                # through to the legacy single-path guard.
                return True

        # Issue #1174 AC 6 MUST 2 — subprotocol allowlist (default-reject,
        # REJECT-ONLY). An empty allowlist (the default) rejects ANY offered
        # subprotocol with code 1002 (protocol error); a non-empty list admits
        # the connection when at least one offered value is present in the list.
        # The accepted subprotocol is NOT echoed to the client (no
        # Sec-WebSocket-Protocol on the accept) — echoing per RFC 6455 §4.2.2
        # requires select_subprotocol on serve(), a separate follow-up sharing
        # the serve()-rewiring root. Enforced immediately post-upgrade and
        # BEFORE on_connect so a disallowed subprotocol never reaches the
        # handler lifecycle.
        allowed_subprotocols = self._subprotocols_by_path.get(path, [])
        offered = _offered_subprotocols(ws)
        if offered:
            if not allowed_subprotocols or not any(
                p in allowed_subprotocols for p in offered
            ):
                logger.warning(
                    "ws.handler.subprotocol_rejected",
                    extra={
                        "path": path,
                        "handler": type(handler).__name__,
                        "offered_count": len(offered),
                    },
                )
                try:
                    await ws.close(1002, "subprotocol not allowed")
                except Exception as exc:  # noqa: BLE001 — best-effort
                    logger.debug(
                        "ws.handler.subprotocol_close_failed",
                        extra={"path": path, "error": str(exc)},
                    )
                return True

        # Issue #1174 AC 6 MUST 4 — handshake auth via Depends, resolved
        # immediately POST-upgrade and BEFORE on_connect / any application
        # message (websockets.serve() upgrades before this handler runs, so a
        # clean pre-upgrade HTTP 401/403 body is not emittable here — WS-1008
        # is the correct WS-native rejection). A raising dependency closes the
        # socket with WS close code 1008, carrying the typed HTTP status in the
        # close reason for triage; on_connect / on_disconnect do NOT fire
        # (connection never reached the handler lifecycle).
        ws_dependencies = self._dependencies_by_path.get(path, [])
        if ws_dependencies:
            try:
                await _resolve_ws_dependencies(ws_dependencies, ws)
            except Exception as exc:  # noqa: BLE001
                from nexus.extractors import NexusHandlerError

                status = exc.status_code if isinstance(exc, NexusHandlerError) else 401
                logger.warning(
                    "ws.handler.handshake_auth_rejected",
                    extra={
                        "path": path,
                        "handler": type(handler).__name__,
                        "status": status,
                        "exc_type": type(exc).__name__,
                    },
                )
                # RFC 6455 §7.4.1: 1008 (policy violation) is the WS-native
                # close for an authz failure; the typed HTTP status is in the
                # reason for operator triage (never echoed credential bytes).
                try:
                    await ws.close(1008, f"unauthorized ({status})")
                except Exception as close_exc:  # noqa: BLE001 — best-effort
                    logger.debug(
                        "ws.handler.handshake_auth_close_failed",
                        extra={"path": path, "error": str(close_exc)},
                    )
                return True

        connection_id = uuid.uuid4().hex
        conn = Connection(ws, connection_id, path, headers=headers)
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
        # Issue #1174 AC 6 MUST 3 — per-path max inbound message size. A frame
        # exceeding the cap closes the connection with code 1009 (message too
        # big). None inherits the transport-level max_size (the websockets
        # library rejects oversized frames at the protocol layer in that case).
        max_message_bytes = self._max_message_bytes_by_path.get(conn.path)
        async for raw in conn.ws:
            if max_message_bytes is not None:
                frame_len = (
                    len(raw)
                    if isinstance(raw, (bytes, bytearray))
                    else len(raw.encode("utf-8"))
                )
                if frame_len > max_message_bytes:
                    logger.warning(
                        "ws.handler.message_too_big",
                        extra={
                            "path": conn.path,
                            "connection_id": conn.connection_id,
                            "size": frame_len,
                            "cap": max_message_bytes,
                        },
                    )
                    await conn.close(1009, "message too big")
                    return
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
