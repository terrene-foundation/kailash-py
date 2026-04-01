# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

__all__ = ["BackgroundService"]


class BackgroundService(ABC):
    """Abstract base class for Nexus background services.

    Background services are non-transport lifecycle components that run
    alongside the Nexus platform. Unlike transports (which handle network
    protocols), background services handle internal tasks: scheduled jobs,
    event-driven handlers, webhook delivery, etc.

    Lifecycle contract:
        1. Service is instantiated and configured
        2. Service is registered with Nexus via app.add_background_service()
        3. Nexus.start() calls service.start() for all registered services
        4. Service runs until Nexus.stop() calls service.stop()
        5. is_healthy() is polled during health checks

    Concrete implementations:
        - SchedulerBackgroundService (TSG-222): runs @app.scheduled() handlers
        - WebhookDeliveryService (TSG-226): delivers outbound webhooks
        - BackgroundTaskManager (TSG-227): manages one-shot async tasks
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this background service."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the background service.

        Called by Nexus.start() after the event loop is running.
        Must be idempotent (safe to call multiple times).
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background service gracefully.

        Called by Nexus.stop() during shutdown. Must complete within
        a reasonable timeout (default 30s). Must be idempotent.
        """
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the service is functioning correctly.

        Called during health checks. Should be fast (no I/O).
        """
        ...
