"""Kailash Python SDK - A framework for building workflow-based applications.

The Kailash SDK provides a comprehensive framework for creating nodes and workflows
that align with container-node architecture while allowing rapid prototyping.

New in v0.4.1: Production-ready Alert Nodes with Discord integration and
AI Provider Vision Support. Rich Discord alerts with embeds, rate limiting,
and universal vision capabilities across OpenAI, Anthropic, and Ollama providers.
"""

from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import key components for easier access
from kailash.workflow.graph import Connection, NodeInstance, Workflow
from kailash.workflow.visualization import WorkflowVisualizer

# Import middleware components (enhanced in v0.4.0)
try:
    from kailash.middleware import (
        AgentUIMiddleware,
        AIChatMiddleware,
        APIGateway,
        RealtimeMiddleware,
        create_gateway,
    )

    _MIDDLEWARE_AVAILABLE = True
except ImportError:
    _MIDDLEWARE_AVAILABLE = False
    # Middleware dependencies not available

# For backward compatibility
WorkflowGraph = Workflow

__version__ = "0.4.1"

__all__ = [
    # Core workflow components
    "Workflow",
    "WorkflowGraph",  # Backward compatibility
    "NodeInstance",
    "Connection",
    "WorkflowBuilder",
    "WorkflowVisualizer",
    "Node",
    "NodeParameter",
    "NodeMetadata",
    "LocalRuntime",
]

# Add middleware to exports if available
if _MIDDLEWARE_AVAILABLE:
    __all__.extend(
        [
            "AgentUIMiddleware",
            "RealtimeMiddleware",
            "APIGateway",
            "AIChatMiddleware",
            "create_gateway",
        ]
    )
