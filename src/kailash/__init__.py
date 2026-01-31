"""Kailash Python SDK - A framework for building workflow-based applications.

The Kailash SDK provides a comprehensive framework for creating nodes and workflows
that align with container-node architecture while allowing rapid prototyping.
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
    )

    # Import new server classes (v0.6.7+)
    from kailash.servers import (
        DurableWorkflowServer,
        EnterpriseWorkflowServer,
        WorkflowServer,
    )

    # Import updated create_gateway function with enterprise defaults
    from kailash.servers.gateway import (
        create_basic_gateway,
        create_durable_gateway,
        create_enterprise_gateway,
        create_gateway,
    )

    _MIDDLEWARE_AVAILABLE = True
except ImportError:
    _MIDDLEWARE_AVAILABLE = False
    # Middleware dependencies not available

# For backward compatibility
WorkflowGraph = Workflow

__version__ = "0.10.16"

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

# Add middleware and servers to exports if available
if _MIDDLEWARE_AVAILABLE:
    __all__.extend(
        [
            # Legacy middleware
            "AgentUIMiddleware",
            "RealtimeMiddleware",
            "APIGateway",
            "AIChatMiddleware",
            # New server classes
            "WorkflowServer",
            "DurableWorkflowServer",
            "EnterpriseWorkflowServer",
            # Gateway creation functions
            "create_gateway",
            "create_enterprise_gateway",
            "create_durable_gateway",
            "create_basic_gateway",
        ]
    )
