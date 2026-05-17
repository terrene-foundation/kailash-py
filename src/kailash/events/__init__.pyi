# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Type stub for the kailash.events public surface (issue #1054)."""

from datetime import datetime
from typing import Any, Awaitable, Callable, ClassVar, Optional, Union

__all__ = [
    "EventBus",
    "Subscription",
    "DomainEvent",
    "EventBackend",
    "InMemoryEventBackend",
    "RedisStreamsEventBackend",
    "create_backend",
]

class DomainEvent:
    event_type: str
    payload: dict[str, Any]
    correlation_id: str
    timestamp: datetime
    actor: Optional[str]
    schema_version: str
    _SUPPORTED_SCHEMA_VERSIONS: ClassVar[frozenset]
    def __init__(
        self,
        event_type: str,
        payload: dict[str, Any] = ...,
        correlation_id: str = ...,
        timestamp: datetime = ...,
        actor: Optional[str] = ...,
        schema_version: str = ...,
    ) -> None: ...
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainEvent: ...

class EventBackend:
    def register(
        self, event_type: str, handler: Callable[[DomainEvent], Awaitable[None]]
    ) -> str: ...
    async def unregister(self, subscription_id: str) -> None: ...
    async def publish(self, event: DomainEvent) -> None: ...
    async def close(self) -> None: ...

class InMemoryEventBackend(EventBackend):
    def __init__(self, max_subscribers: int = ...) -> None: ...

class RedisStreamsEventBackend(EventBackend):
    def __init__(
        self,
        url: Optional[str] = ...,
        *,
        max_subscribers: int = ...,
        block_ms: int = ...,
    ) -> None: ...

def create_backend(
    backend: Optional[str] = ...,
    *,
    redis_url: Optional[str] = ...,
    max_subscribers: int = ...,
) -> EventBackend: ...

class Subscription:
    subscription_id: str
    event_type: str
    def __init__(
        self, bus: EventBus, subscription_id: str, event_type: str
    ) -> None: ...
    @property
    def active(self) -> bool: ...
    async def unsubscribe(self) -> None: ...

class EventBus:
    def __init__(
        self,
        backend: Optional[Union[str, EventBackend]] = ...,
        *,
        redis_url: Optional[str] = ...,
        max_subscribers: int = ...,
    ) -> None: ...
    @property
    def backend_name(self) -> str: ...
    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: Optional[str] = ...,
        actor: Optional[str] = ...,
    ) -> None: ...
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> Subscription: ...
    def subscribe_events(
        self,
        event_type: str,
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> Subscription: ...
    async def close(self) -> None: ...
