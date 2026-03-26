# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Abstract EventBus with pluggable backends.

Defines the ``EventBus`` interface and the ``EventBusError`` exception
hierarchy. Concrete backends (in-memory, Redis, Kafka, etc.) implement
this interface so that application code remains transport-agnostic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

from .domain_event import DomainEvent

logger = logging.getLogger(__name__)

__all__ = [
    "EventBus",
    "EventBusError",
    "PublishError",
    "SubscriptionError",
]


# ------------------------------------------------------------------
# Exception hierarchy
# ------------------------------------------------------------------


class EventBusError(Exception):
    """Base exception for all EventBus operations.

    Attributes:
        details: Structured context about the error (agent-friendly).
    """

    def __init__(self, message: str, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: Dict[str, Any] = details or {}


class PublishError(EventBusError):
    """Raised when an event cannot be published."""


class SubscriptionError(EventBusError):
    """Raised when a subscribe / unsubscribe operation fails."""


# ------------------------------------------------------------------
# Abstract bus
# ------------------------------------------------------------------


class EventBus(ABC):
    """Abstract event bus with pluggable backends.

    Implementations **must** be thread-safe and **must** enforce a bounded
    subscriber list (``maxlen=10_000`` by default) to prevent unbounded
    memory growth in long-running processes.
    """

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all matching subscribers.

        Args:
            event: The domain event to publish.

        Raises:
            PublishError: If the event cannot be delivered.
        """

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], None]) -> str:
        """Register a handler for a given event type.

        Args:
            event_type: Dot-delimited event type to listen for
                (e.g. ``"order.created"``).
            handler: Callable invoked synchronously when a matching event
                is published.

        Returns:
            A unique subscription ID that can be passed to
            :meth:`unsubscribe`.

        Raises:
            SubscriptionError: If the subscriber limit has been reached or
                the handler is invalid.
        """

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a previously registered subscription.

        Args:
            subscription_id: The ID returned by :meth:`subscribe`.

        Raises:
            SubscriptionError: If the subscription ID is unknown.
        """
