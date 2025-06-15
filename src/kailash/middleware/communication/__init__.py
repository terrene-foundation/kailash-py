"""
Communication Layer for Kailash Middleware

Handles all external communication including REST APIs, WebSockets,
events, and AI chat interfaces.
"""

from .ai_chat import AIChatMiddleware, ChatMessage, WorkflowGenerator
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
    # AI Chat
    "AIChatMiddleware",
    "ChatMessage",
    "WorkflowGenerator",
]
