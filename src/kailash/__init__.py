# pyright: reportUnsupportedDunderAll=false
"""Kailash Python SDK - A framework for building workflow-based applications.

The Kailash SDK provides a comprehensive framework for creating nodes and workflows
that align with container-node architecture while allowing rapid prototyping.

Note: ``__all__`` lists names resolved via ``__getattr__`` (lazy imports for
optional server extras). Pyright's ``reportUnsupportedDunderAll`` check is
disabled because it does not follow ``__getattr__`` fallbacks.
"""

import warnings

from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import key components for easier access
from kailash.workflow.graph import Connection, NodeInstance, Workflow


def __getattr__(name):
    """Lazy imports for optional dependencies and deprecation warnings."""
    if name == "WorkflowVisualizer":
        from kailash.workflow.visualization import WorkflowVisualizer

        return WorkflowVisualizer
    if name == "WorkflowGraph":
        warnings.warn(
            "WorkflowGraph is deprecated and will be removed in v3.0.0. "
            "Use Workflow instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return Workflow
    if name in (
        "AgentUIMiddleware",
        "APIGateway",
        "RealtimeMiddleware",
    ):
        warnings.warn(
            f"{name} is no longer exported from kailash top-level. "
            f"Import from kailash.middleware instead: from kailash.middleware import {name}",
            DeprecationWarning,
            stacklevel=2,
        )
        from kailash import middleware

        return getattr(middleware, name)
    # Lazy server imports (require server extras)
    _server_names = {
        "WorkflowServer",
        "DurableWorkflowServer",
        "EnterpriseWorkflowServer",
        "create_gateway",
        "create_enterprise_gateway",
        "create_durable_gateway",
        "create_basic_gateway",
    }
    if name in _server_names:
        try:
            if name in (
                "WorkflowServer",
                "DurableWorkflowServer",
                "EnterpriseWorkflowServer",
            ):
                from kailash import servers

                return getattr(servers, name)
            else:
                from kailash.servers import gateway

                return getattr(gateway, name)
        except ImportError:
            raise ImportError(
                f"{name} requires server dependencies. "
                f"Install with: pip install kailash"
            ) from None
    raise AttributeError(f"module 'kailash' has no attribute {name!r}")


__version__ = "2.8.7"

__all__ = [
    # Core workflow components
    "Workflow",
    "NodeInstance",
    "Connection",
    "WorkflowBuilder",
    "WorkflowVisualizer",
    "Node",
    "NodeParameter",
    "NodeMetadata",
    "LocalRuntime",
    # Server classes (lazy, require kailash[server])
    "WorkflowServer",
    "DurableWorkflowServer",
    "EnterpriseWorkflowServer",
    "create_gateway",
    "create_enterprise_gateway",
    "create_durable_gateway",
    "create_basic_gateway",
]
