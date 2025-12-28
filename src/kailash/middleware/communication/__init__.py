"""
Communication Layer for Kailash Middleware

Handles all external communication including REST APIs, WebSockets,
and events.

Note:
    AI chat functionality has been moved to the Kaizen framework.
    For AI-powered chat interfaces, use:
    `from kaizen.middleware.communication import AIChatMiddleware, ChatMessage, WorkflowGenerator`
"""

from .api_gateway import APIGateway, create_gateway
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
    # Real-time communication
    "RealtimeMiddleware",
    # API Gateway
    "APIGateway",
    "create_gateway",
]
