"""Kailash Python SDK - A framework for building workflow-based applications.

The Kailash SDK provides a comprehensive framework for creating nodes and workflows
that align with container-node architecture while allowing rapid prototyping.
"""

# Import key components for easier access
from kailash.workflow.graph import Workflow, NodeInstance, Connection
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.visualization import WorkflowVisualizer
from kailash.nodes.base import Node, NodeParameter, NodeMetadata
from kailash.runtime.local import LocalRuntime

# For backward compatibility
WorkflowGraph = Workflow

__version__ = "0.1.0"

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