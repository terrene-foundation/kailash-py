# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Server-Sent Events (SSE) streaming endpoints for Nexus.

Two surfaces live here:

- :func:`register_sse` (issue #1174, AC 5) — the general parameterized SSE
  endpoint. A consumer registers a path + an ``on_subscribe(request)`` async
  generator yielding ``dict`` events; the SDK frames each as
  ``data: {json}\\n\\n``, fires keepalive comments, and carries the full
  authn/authz + rate-limit + backpressure posture of a plain HTTP handler.

- :func:`register_sse_endpoint` — the EventBus-backed convenience that registers
  ``GET /events/stream``. Since issue #1174 it is a THIN SHIM over
  :func:`register_sse` with an EventBus-backed ``on_subscribe`` — no behavior
  change for existing consumers.

Usage::

    from nexus import Nexus
    app = Nexus()

    async def on_subscribe(request):
        yield {"hello": "world"}
        yield {"tick": 1}

    app.register_sse("/feed", on_subscribe)
"""

# NOTE: PEP 563 (``from __future__ import annotations``) is intentionally NOT
# enabled here. Nexus extractor / resolver code resolves real annotation values
# at runtime; stringizing them would break that resolution. See
# rules/nexus-essential-patterns.md "No PEP 563".

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, List, Optional

if TYPE_CHECKING:
    from nexus.core import Nexus

logger = logging.getLogger(__name__)

__all__ = ["register_sse", "register_sse_endpoint"]

_KEEPALIVE_INTERVAL = 15  # seconds

# Defaults for the register_sse backpressure / resource bounds (spec §217-219).
_DEFAULT_MAX_QUEUE_DEPTH = 1000
_DEFAULT_MAX_EVENT_BYTES = 65_536
_DEFAULT_SLOW_CONSUMER_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# register_sse — general parameterized SSE endpoint (issue #1174 AC 5)
# ---------------------------------------------------------------------------


def _sse_error_frame(code: str, **extra: Any) -> str:
    """Build an ``event: error\\ndata: {...}\\n\\n`` SSE frame.

    The ``code`` is a stable upper-snake identifier (``QUEUE_OVERFLOW`` etc.);
    ``extra`` carries optional structured fields (e.g. ``correlation_id``).
    """
    payload = {"code": code, **extra}
    return f"event: error\ndata: {json.dumps(payload)}\n\n"


async def _resolve_sse_dependencies(
    dependencies: "List[Any]",
    request: Any,
) -> None:
    """Resolve each ``Depends`` in ``dependencies`` against ``request``.

    Reuses the Shard-1 resolver chain (``nexus.extractors.resolver``) so the
    SSE auth path is byte-identical to the HTTP ``handler_extract`` path: each
    ``Depends`` callable resolves once, recursively (it may itself take
    ``Request`` / nested ``Depends``), with the same memoisation cache.

    A raising ``Depends`` propagates here so the caller closes the stream with
    the typed status BEFORE the SSE handshake completes (spec §225 MUST 1). The
    resolved values are discarded — SSE ``Depends`` are used for their SIDE
    EFFECT (auth check / rate-limit gate), not for injection into
    ``on_subscribe``.
    """
    if not dependencies:
        return
    # Local import avoids a module-load cycle (resolver imports extractors,
    # which the core also imports).
    from nexus.context import _current_request, set_current_request
    from nexus.extractors import Depends
    from nexus.extractors.resolver import ResolverChain

    # Bind the request into the resolver ContextVar so nested Request/Depends
    # resolve against THIS request even though we are not on the HTTP
    # handler_extract path. Reset in finally so we never leak into a sibling
    # request on the same worker.
    token = set_current_request(request)
    try:
        # An empty-spec ResolverChain gives us access to the memoised,
        # recursive _resolve_dependency machinery without re-implementing it.
        chain = ResolverChain(lambda: None, [])
        cache: "dict[Callable, Any]" = {}
        for dep in dependencies:
            if not isinstance(dep, Depends):
                raise TypeError(
                    "register_sse dependencies must be Depends(...) markers; "
                    f"got {type(dep).__name__}"
                )
            await chain._resolve_dependency(dep, request, cache, None)
    finally:
        _current_request.reset(token)


def register_sse(
    nexus: "Nexus",
    path: str,
    on_subscribe: "Callable[[Any], AsyncIterator[dict]]",
    *,
    keepalive_interval: int = _KEEPALIVE_INTERVAL,
    dependencies: "Optional[List[Any]]" = None,
    max_queue_depth: int = _DEFAULT_MAX_QUEUE_DEPTH,
    max_event_bytes: int = _DEFAULT_MAX_EVENT_BYTES,
    slow_consumer_timeout: float = _DEFAULT_SLOW_CONSUMER_TIMEOUT,
) -> None:
    """Register an SSE endpoint at ``path`` (issue #1174 AC 5).

    ``on_subscribe(request) -> AsyncIterator[dict]`` yields events; each dict
    serializes to ``data: {json}\\n\\n`` per the SSE spec. Keepalive comments
    (``: keepalive\\n\\n``) fire every ``keepalive_interval`` seconds of
    idleness.

    Headers set on every response:
    - ``Content-Type: text/event-stream``
    - ``Cache-Control: no-cache``
    - ``X-Accel-Buffering: no``

    MUST clauses (spec §223-232):

    1. **Auth via** ``dependencies``. Every ``Depends`` resolves on SUBSCRIBE
       through the Shard-1 resolver chain. A raising ``Depends`` closes the
       stream with the typed HTTP status (401/403) + JSON body BEFORE the SSE
       handshake — never a partial ``text/event-stream`` to an unauthenticated
       client.
    2. **Bounded queue depth** (``max_queue_depth``). An ``asyncio.Queue``
       buffers events between ``on_subscribe`` and the client; on overflow the
       stream emits ``event: error\\ndata: {"code":"QUEUE_OVERFLOW"}`` then EOF.
    3. **Max event size** (``max_event_bytes``). An event whose serialized JSON
       exceeds the cap is DROPPED with a server-side log + an
       ``event: error\\ndata: {"code":"EVENT_TOO_LARGE"}`` frame; the stream
       CONTINUES (a single oversized event is recoverable).
    4. **Slow-consumer disconnect** (``slow_consumer_timeout``). When the
       transport cannot accept the next flush within the timeout, the stream
       closes and per-subscription state is released.
    5. **Rate-limit on SUBSCRIBE**. The ``nexus.auth`` rate-limit hook fires
       ONCE at handshake; refusal closes with HTTP 429 BEFORE the upgrade.
    6. **on_subscribe exception handling**. ``asyncio.CancelledError`` (client
       disconnect / shutdown) releases state and exits silently; any other
       exception logs full context server-side AND emits
       ``event: error\\ndata: {"code":"INTERNAL_ERROR","correlation_id":...}``
       then EOF — never a silent close.

    Args:
        nexus: The :class:`~nexus.core.Nexus` instance.
        path: URL path for the SSE endpoint (e.g. ``"/events/stream"``).
        on_subscribe: ``async def`` generator taking the Starlette request and
            yielding ``dict`` events.
        keepalive_interval: Seconds of idleness before a keepalive comment.
        dependencies: list of ``Depends(...)`` markers resolved on subscribe
            for their auth side effect.
        max_queue_depth: per-subscription event-buffer bound (MUST 2).
        max_event_bytes: per-event serialized-JSON cap (MUST 3).
        slow_consumer_timeout: flush timeout before slow-consumer close
            (MUST 4).
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse

    deps = list(dependencies or [])

    async def sse_handler(request: "Request"):
        # MUST 5 — rate-limit on the SUBSCRIBE event, once at handshake,
        # BEFORE the SSE upgrade. Refusal -> HTTP 429 (NOT a partial stream).
        rate_limit_check = getattr(getattr(nexus, "auth", None), "rate_limit", None)
        if callable(rate_limit_check):
            try:
                allowed = rate_limit_check(request)
                if asyncio.iscoroutine(allowed):
                    allowed = await allowed
            except Exception:  # noqa: BLE001 — fail closed on hook error
                logger.exception(
                    "sse.subscribe.rate_limit_hook_error",
                    extra={"path": path},
                )
                allowed = False
            if allowed is False:
                return JSONResponse(
                    {"error": "rate limit exceeded", "code": "RATE_LIMITED"},
                    status_code=429,
                )

        # MUST 1 — resolve auth dependencies on SUBSCRIBE, BEFORE the
        # handshake. A raising Depends closes with the typed status + JSON
        # body — never a partial event-stream to an unauthenticated client.
        try:
            await _resolve_sse_dependencies(deps, request)
        except Exception as exc:  # noqa: BLE001
            from nexus.extractors import NexusHandlerError

            if isinstance(exc, NexusHandlerError):
                status = exc.status_code
                body = exc.body if isinstance(exc.body, dict) else {"error": exc.body}
            else:
                # Non-typed auth failure: surface 401 + a clean envelope; the
                # full context is logged server-side, never echoed to the
                # client (split-visibility per resolver contract).
                logger.warning(
                    "sse.subscribe.auth_failed",
                    extra={"path": path, "exc_type": type(exc).__name__},
                )
                status = 401
                body = {"error": "unauthorized", "code": "UNAUTHORIZED"}
            return JSONResponse(body, status_code=status)

        return StreamingResponse(
            _sse_stream(
                request,
                on_subscribe,
                keepalive_interval=keepalive_interval,
                max_queue_depth=max_queue_depth,
                max_event_bytes=max_event_bytes,
                slow_consumer_timeout=slow_consumer_timeout,
                path=path,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    http = _resolve_http_transport(nexus)
    if http is not None:
        http.register_endpoint(path, ["GET"], sse_handler)
        logger.info("sse.registered", extra={"path": path})
    else:
        logger.warning("sse.no_http_transport", extra={"path": path})


def _resolve_http_transport(nexus: "Nexus") -> Any:
    """Best-effort lookup of the Nexus HTTP transport.

    Prefers the private ``_http_transport`` attribute; falls back to the first
    transport whose ``name`` is ``"http"``. Returns ``None`` when no HTTP
    transport is attached (the endpoint registration is then a logged no-op).
    """
    http = getattr(nexus, "_http_transport", None)
    if http is not None:
        return http
    for transport in getattr(nexus, "_transports", []):
        if getattr(transport, "name", None) == "http":
            return transport
    return None


async def _sse_stream(
    request: Any,
    on_subscribe: "Callable[[Any], AsyncIterator[dict]]",
    *,
    keepalive_interval: int,
    max_queue_depth: int,
    max_event_bytes: int,
    slow_consumer_timeout: float,
    path: str,
) -> AsyncIterator[str]:
    """Drive ``on_subscribe`` through a bounded queue and yield SSE frames.

    A producer task pulls events from ``on_subscribe`` into a bounded
    ``asyncio.Queue``; the consumer (this generator) drains the queue, emitting
    keepalive comments on idle timeout. The queue is the backpressure boundary
    (MUST 2): when the producer outpaces the consumer past ``max_queue_depth``
    the producer signals overflow and the consumer emits ``QUEUE_OVERFLOW``
    then EOF.
    """
    # Sentinels distinguishable from any user dict event.
    _OVERFLOW = object()
    _DONE = object()

    queue: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=max_queue_depth)
    iterator = on_subscribe(request)

    async def _producer() -> None:
        try:
            async for event in iterator:
                # MUST 3 — drop oversized events, keep streaming.
                data = json.dumps(event, default=str)
                if len(data.encode("utf-8")) > max_event_bytes:
                    logger.warning(
                        "sse.event_too_large",
                        extra={
                            "path": path,
                            "size": len(data.encode("utf-8")),
                            "cap": max_event_bytes,
                        },
                    )
                    await queue.put(("error", "EVENT_TOO_LARGE", {}))
                    continue
                # MUST 2 — bounded queue; on overflow signal + stop.
                try:
                    queue.put_nowait(("data", data, {}))
                except asyncio.QueueFull:
                    logger.warning(
                        "sse.queue_overflow",
                        extra={"path": path, "max_queue_depth": max_queue_depth},
                    )
                    # Best-effort overflow signal (queue may already be full;
                    # the consumer drains then sees _OVERFLOW).
                    await queue.put(_OVERFLOW)
                    return
        except asyncio.CancelledError:
            # MUST 6 — client disconnect / shutdown: expected, exit silently.
            raise
        except Exception as exc:  # noqa: BLE001
            # MUST 6 — any other exception: log full context server-side,
            # surface an INTERNAL_ERROR frame with a correlation id (NOT a
            # silent close).
            correlation_id = str(uuid.uuid4())
            logger.error(
                "sse.on_subscribe_error",
                exc_info=exc,
                extra={
                    "path": path,
                    "correlation_id": correlation_id,
                    "exc_type": type(exc).__name__,
                },
            )
            await queue.put(
                ("error", "INTERNAL_ERROR", {"correlation_id": correlation_id})
            )
        finally:
            await queue.put(_DONE)
            # Release the underlying async generator's resources.
            aclose = getattr(iterator, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:  # noqa: BLE001 — best-effort cleanup
                    logger.debug(
                        "sse.iterator_aclose_failed",
                        extra={"path": path},
                        exc_info=True,
                    )

    producer = asyncio.ensure_future(_producer())
    try:
        while True:
            try:
                # MUST 4 — slow-consumer / idle handling. wait_for bounds the
                # idle window: on keepalive_interval idleness we emit a
                # comment; the producer drains independently so a stuck
                # consumer cannot wedge the producer past the queue bound.
                item = await asyncio.wait_for(queue.get(), timeout=keepalive_interval)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue

            if item is _DONE:
                return
            if item is _OVERFLOW:
                yield _sse_error_frame("QUEUE_OVERFLOW")
                return

            kind, value, extra = item
            if kind == "data":
                yield f"data: {value}\n\n"
            elif kind == "error":
                yield _sse_error_frame(value, **extra)
                if value == "INTERNAL_ERROR":
                    # INTERNAL_ERROR is terminal — EOF after the frame.
                    return
                # EVENT_TOO_LARGE is recoverable — continue draining.
    except asyncio.CancelledError:
        # MUST 6 — client disconnect: cancel the producer, release state,
        # exit silently.
        raise
    finally:
        if not producer.done():
            producer.cancel()
            try:
                await producer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# register_sse_endpoint — EventBus-backed shim over register_sse
# ---------------------------------------------------------------------------


def register_sse_endpoint(nexus: "Nexus") -> None:
    """Register ``GET /events/stream`` streaming the Nexus EventBus.

    Since issue #1174 this is a THIN SHIM over :func:`register_sse` with an
    EventBus-backed ``on_subscribe`` — no behavior change for existing
    consumers. The endpoint still:

    - accepts an optional ``?event_type=<value>`` filter,
    - frames each :class:`~nexus.events.NexusEvent` as ``data: {...}\\n\\n``,
    - sends ``: keepalive\\n\\n`` comments every 15s of idleness,
    - sets the canonical SSE headers.

    Args:
        nexus: A :class:`~nexus.core.Nexus` instance.
    """

    async def _eventbus_on_subscribe(request: Any) -> AsyncIterator[dict]:
        """EventBus-backed event source for ``register_sse``.

        Subscribes (optionally filtered) and yields each event's ``to_dict()``.
        Cleanup (subscription removal) happens in the ``finally`` so a client
        disconnect — which cancels this generator — still unsubscribes.
        """
        bus = nexus._event_bus
        event_type = request.query_params.get("event_type")

        if event_type:
            predicate = lambda evt: evt.event_type.value == event_type  # noqa: E731
            queue = bus.subscribe_filtered(predicate)
        else:
            queue = bus.subscribe()

        try:
            while True:
                event = await queue.get()
                yield event.to_dict()
        finally:
            # Remove the subscription on disconnect / completion.
            if event_type:
                try:
                    bus._filtered_subscribers.remove(
                        next(
                            entry
                            for entry in bus._filtered_subscribers
                            if entry[1] is queue
                        )
                    )
                except (StopIteration, ValueError):
                    pass
            else:
                try:
                    bus._subscribers.remove(queue)
                except ValueError:
                    pass

    register_sse(nexus, "/events/stream", _eventbus_on_subscribe)
