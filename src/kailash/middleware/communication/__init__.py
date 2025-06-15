"""
Communication Layer for Kailash Middleware

Handles all external communication including REST APIs, WebSockets,
events, and AI chat interfaces.
"""

from .events import EventStream, EventType, EventPriority, WorkflowEvent, NodeEvent, UIEvent
from .realtime import RealtimeMiddleware
from .api_gateway import APIGateway, create_gateway
from .ai_chat import AIChatMiddleware, ChatMessage, WorkflowGenerator

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