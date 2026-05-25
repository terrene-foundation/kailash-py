# pyright: reportUnsupportedDunderAll=false
"""Kailash Python SDK - A framework for building workflow-based applications.

The Kailash SDK provides a comprehensive framework for creating nodes and workflows
that align with container-node architecture while allowing rapid prototyping.

Note: ``__all__`` lists names resolved via ``__getattr__`` (lazy imports for
optional server extras). Pyright's ``reportUnsupportedDunderAll`` check is
disabled because it does not follow ``__getattr__`` fallbacks.
"""

import warnings

from kailash.events import DomainEvent, EventBus, Subscription
from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import key components for easier access
from kailash.workflow.graph import Connection, NodeInstance, Workflow

# isort: split
# Eagerly register the EventBus workflow node. MUST be imported AFTER the
# runtime chain above so kailash.runtime.async_local -> kailash.nodes.base_async
# is fully loaded first. Otherwise:
#   EventPublishNode -> AsyncNode -> kailash.runtime.template_resolver
#   -> kailash.runtime.__init__ -> async_local -> AsyncNode
# triggers a partially-initialized-module ImportError on plain `import kailash`.
# The `# isort: split` directive above is load-bearing: it tells isort to treat
# this import as a separate sort block so the alphabetical-order pass does
# NOT reorder it back before `runtime.local` (which would re-introduce the
# circular import). Verified by `import kailash` + pre-commit Tier-1
# collection (issue #1054).
from kailash.nodes.events import EventPublishNode  # noqa: E402,F401


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
        except ImportError as exc:
            raise ImportError(
                f"{name} requires server dependencies (fastapi, uvicorn, "
                f"aiohttp, httpx, aiofiles). Install with: "
                f"pip install 'kailash[server]'"
            ) from exc
    raise AttributeError(f"module 'kailash' has no attribute {name!r}")


__version__ = "2.26.2"

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
    # Domain-event primitive (issue #1054)
    "EventBus",
    "Subscription",
    "DomainEvent",
    # Server classes (lazy, require kailash[server])
    "WorkflowServer",
    "DurableWorkflowServer",
    "EnterpriseWorkflowServer",
    "create_gateway",
    "create_enterprise_gateway",
    "create_durable_gateway",
    "create_basic_gateway",
]
