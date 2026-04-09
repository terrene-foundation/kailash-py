"""
Communication Layer for Kailash Middleware

Handles all external communication including REST APIs, WebSockets,
events, and domain event buses with pluggable backends.
"""

from .api_gateway import APIGateway, create_gateway
from .backends import InMemoryEventBus
from .domain_event import DomainEvent
from .event_bus import EventBus, EventBusError, PublishError, SubscriptionError
from .events import (
    EventPriority,
    EventStream,
    EventType,
    NodeEvent,
    UIEvent,
    WorkflowEvent,
)
from .realtime import RealtimeMiddleware

__all__ = [
    # Event system
    "EventStream",
    "EventType",
    "EventPriority",
    "WorkflowEvent",
    "NodeEvent",
    "UIEvent",
    # EventBus (pluggable backends)
    "EventBus",
    "DomainEvent",
    "InMemoryEventBus",
    "EventBusError",
    "PublishError",
    "SubscriptionError",
    # Real-time communication
    "RealtimeMiddleware",
    # API Gateway
    "APIGateway",
    "create_gateway",
]
