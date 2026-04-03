# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric SSE endpoint — real-time push for product updates and source health.

GET /fabric/_events streams Server-Sent Events over HTTP/2. Clients use
the browser ``EventSource`` API for auto-reconnection.

Event types:
- ``product_updated``: cache swapped after pipeline completes
- ``source_health``: source health status changed
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

__all__ = ["SSEManager"]


class SSEManager:
    """Manages SSE connections and event broadcasting."""

    _MAX_CLIENTS = 1000

    def __init__(self) -> None:
        self._clients: List[asyncio.Queue[str]] = []
        self._lock = asyncio.Lock()

    async def add_client(self) -> asyncio.Queue[str]:
        """Register a new SSE client. Returns a queue that receives events.

        Rejects connections beyond _MAX_CLIENTS to prevent resource exhaustion.
        """
        if len(self._clients) >= self._MAX_CLIENTS:
            raise ConnectionError(f"Maximum SSE clients ({self._MAX_CLIENTS}) reached")
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._clients.append(queue)
        logger.debug("SSE client connected (total=%d)", len(self._clients))
        return queue

    async def remove_client(self, queue: asyncio.Queue[str]) -> None:
        """Unregister an SSE client."""
        async with self._lock:
            try:
                self._clients.remove(queue)
            except ValueError:
                pass
        logger.debug("SSE client disconnected (total=%d)", len(self._clients))

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast an event to all connected clients.

        Args:
            event_type: SSE event name (e.g., "product_updated")
            data: JSON-serializable event data
        """
        message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        async with self._lock:
            disconnected: List[asyncio.Queue[str]] = []
            for queue in self._clients:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    disconnected.append(queue)
                    logger.debug("SSE client queue full — dropping")

            for q in disconnected:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass

    async def broadcast_product_updated(
        self, product_name: str, cached_at: Optional[str] = None
    ) -> None:
        """Broadcast a product_updated event."""
        await self.broadcast(
            "product_updated",
            {
                "product": product_name,
                "cached_at": cached_at or datetime.now(timezone.utc).isoformat(),
            },
        )

    async def broadcast_source_health(
        self, source_name: str, healthy: bool, state: str
    ) -> None:
        """Broadcast a source_health event."""
        await self.broadcast(
            "source_health",
            {
                "source": source_name,
                "healthy": healthy,
                "state": state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def get_sse_handler(self) -> Dict[str, Any]:
        """Route definition for GET /fabric/_events."""
        manager = self

        async def handler(**kwargs: Any) -> Dict[str, Any]:
            """SSE endpoint — returns an async generator for streaming."""
            queue = await manager.add_client()

            async def event_stream():
                try:
                    while True:
                        message = await queue.get()
                        yield message
                except asyncio.CancelledError:
                    pass
                finally:
                    await manager.remove_client(queue)

            return {
                "_status": 200,
                "_headers": {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
                "_stream": event_stream(),
            }

        handler.__name__ = "fabric_events"
        return {
            "method": "GET",
            "path": "/fabric/_events",
            "handler": handler,
            "metadata": {"type": "sse"},
        }
