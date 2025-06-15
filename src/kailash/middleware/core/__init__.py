"""
Core Middleware Components for Kailash

Central orchestration and management components that form the foundation
of the middleware layer.
"""

from .agent_ui import AgentUIMiddleware
from .schema import DynamicSchemaRegistry, NodeSchemaGenerator
from .workflows import MiddlewareWorkflows, WorkflowBasedMiddleware

__all__ = [
    # Core orchestration
    "AgentUIMiddleware",
    # Workflow patterns
    "MiddlewareWorkflows",
    "WorkflowBasedMiddleware",
    # Schema management
    "NodeSchemaGenerator",
    "DynamicSchemaRegistry",
]
