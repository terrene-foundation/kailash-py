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

# For backward compatibility
WorkflowGraph = Workflow

__version__ = "0.1.1"

__all__ = [
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
