# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Server-Sent Events (SSE) streaming endpoint for the Nexus EventBus.

Registers ``GET /events/stream`` on the HTTP transport, streaming
:class:`~nexus.events.NexusEvent` objects to clients as SSE.

Usage::

    from nexus import Nexus
    from nexus.sse import register_sse_endpoint

    app = Nexus()
    register_sse_endpoint(app)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nexus.core import Nexus

logger = logging.getLogger(__name__)

__all__ = ["register_sse_endpoint"]

_KEEPALIVE_INTERVAL = 15  # seconds


async def _sse_generator(
    nexus: Nexus,
    event_type: Optional[str] = None,
) -> None:
    """Async generator that yields SSE-formatted strings.

    Args:
        nexus: The Nexus instance (provides EventBus).
        event_type: Optional filter — only events whose
            ``event_type.value`` matches are forwarded.

    Yields:
        SSE-formatted strings (``data: {...}\\n\\n`` or ``: keepalive\\n\\n``).
    """
    bus = nexus._event_bus

    if event_type:
        predicate = lambda evt: evt.event_type.value == event_type  # noqa: E731
        queue = bus.subscribe_filtered(predicate)
    else:
        queue = bus.subscribe()

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL)
                data = json.dumps(event.to_dict())
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive comment to prevent proxy/client timeouts
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        # Clean up subscription
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


def register_sse_endpoint(nexus: Nexus) -> None:
    """Register ``GET /events/stream`` on the Nexus HTTP transport.

    Query parameters:
        event_type: Optional filter (e.g. ``?event_type=handler.called``).

    Headers returned:
        Content-Type: text/event-stream
        Cache-Control: no-cache
        Connection: keep-alive

    Args:
        nexus: A :class:`~nexus.core.Nexus` instance.
    """
    from starlette.requests import Request
    from starlette.responses import StreamingResponse

    async def sse_handler(request: Request):
        """SSE streaming handler for EventBus events."""
        event_type = request.query_params.get("event_type")

        return StreamingResponse(
            _sse_generator(nexus, event_type=event_type),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    http = getattr(nexus, "_http_transport", None)
    if http is not None:
        http.register_endpoint("/events/stream", ["GET"], sse_handler)
        logger.info("Registered /events/stream SSE endpoint")
    else:
        logger.warning(
            "No HTTP transport found on Nexus instance — "
            "/events/stream endpoint not registered"
        )
