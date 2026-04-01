# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.registry import HandlerDef, HandlerRegistry

logger = logging.getLogger(__name__)

__all__ = ["Transport"]


class Transport(ABC):
    """Abstract base class for Nexus transports.

    A transport maps registered handlers to a specific protocol or channel.
    HTTPTransport creates FastAPI routes. MCPTransport registers FastMCP tools.
    WebSocketTransport handles WS connections. Each transport reads from
    HandlerRegistry and builds its own dispatch layer.

    Lifecycle:
        1. Transport is instantiated with protocol-specific config
        2. Transport is registered with Nexus via app.add_transport()
        3. Nexus.start() calls transport.start(registry)
        4. As handlers are registered, on_handler_registered() is called
        5. Nexus.stop() calls transport.stop()

    The Transport protocol mirrors kailash-rs Nexus transport architecture.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique transport name (e.g., 'http', 'mcp', 'websocket')."""
        ...

    @abstractmethod
    async def start(self, registry: HandlerRegistry) -> None:
        """Start the transport, reading handlers from the registry.

        Called by Nexus.start(). The transport should read all currently
        registered handlers from the registry and set up its dispatch layer.

        Args:
            registry: The HandlerRegistry containing all registered handlers.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the transport gracefully.

        Called by Nexus.stop(). Must release all resources (sockets, threads,
        etc.) and return promptly. Must be idempotent.
        """
        ...

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Return True if the transport is currently running."""
        ...

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        """Called when a new handler is registered after start().

        Default implementation is a no-op. Transports that support hot-reload
        (adding handlers while running) should override this.

        Args:
            handler_def: The newly registered handler definition.
        """
        pass
