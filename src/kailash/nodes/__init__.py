"""Node system for the Kailash SDK."""

# Import all node modules to ensure registration
from kailash.nodes import (
    ai,
    alerts,
    api,
    auth,
    cache,
    code,
    compliance,
    data,
    enterprise,
    logic,
    mixins,
    monitoring,
    security,
    testing,
    transaction,
    transform,
)
from kailash.nodes.base import Node, NodeParameter, NodeRegistry, register_node
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code import PythonCodeNode

# Compatibility alias - AsyncNode is now just Node
AsyncNode = Node

__all__ = [
    "Node",
    "AsyncNode",  # Compatibility alias
    "CycleAwareNode",
    "NodeParameter",
    "NodeRegistry",
    "register_node",
    "PythonCodeNode",
    # Node modules
    "ai",
    "alerts",
    "api",
    "auth",
    "cache",
    "code",
    "compliance",
    "data",
    "enterprise",
    "logic",
    "mixins",
    "monitoring",
    "security",
    "testing",
    "transaction",
    "transform",
]
