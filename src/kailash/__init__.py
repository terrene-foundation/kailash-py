"""Kailash Python SDK - A framework for building workflow-based applications.

The Kailash SDK provides a comprehensive framework for creating nodes and workflows
that align with container-node architecture while allowing rapid prototyping.

New in v0.9.23: CRITICAL FIX - Resolved P0 variable persistence bug in PythonCodeNode and workflow parameter caching.
Fixed two-layer data leakage issue preventing variable/parameter persistence across workflow executions in Nexus deployments.
Previous v0.9.17: AsyncSQL per-pool locking eliminates lock contention bottleneck.
Achieves 100% success at 300+ concurrent operations (was 50% failure). 85% performance improvement with per-pool locks.
Previous v0.9.13: Fixed WorkflowBuilder parameter validation false positives (Bug 010).
Enhanced validation.py to recognize auto_map_from parameters, eliminating spurious warnings.
Previous v0.9.12: SQLite Compatibility & Code Quality improvements.
Previous v0.9.2: WebSocket Transport Support with Enterprise Connection Pooling.
Fixed "Unsupported transport: websocket" error. Added 73% performance improvement with connection pooling.
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

__version__ = "0.9.23"

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
