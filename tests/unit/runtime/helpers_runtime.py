"""Test helpers for runtime unit tests.

This module provides utilities for creating test workflows, nodes,
and other runtime-related test fixtures.
"""

from typing import Any, Dict, List, Optional

from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


def create_minimal_workflow() -> Workflow:
    """Create a minimal valid workflow with one node.

    Returns:
        Valid workflow with single PythonCodeNode
    """
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "test_node", {"code": "result = 'test'"})
    return builder.build()


def create_valid_workflow() -> Workflow:
    """Create a valid workflow for testing.

    Returns:
        Valid workflow with multiple connected nodes
    """
    builder = WorkflowBuilder()

    # Add first node
    builder.add_node(
        "PythonCodeNode", "node1", {"code": "result = {'data': [1, 2, 3], 'count': 3}"}
    )

    # Add second node
    builder.add_node(
        "PythonCodeNode", "node2", {"code": "output = f'Received {len(data)} items'"}
    )

    # Connect them
    builder.add_connection("node1", "result", "node2", "data")

    return builder.build()


def create_workflow_with_switch() -> Workflow:
    """Create workflow with SwitchNode for conditional execution tests.

    Returns:
        Workflow with SwitchNode and branching paths
    """
    builder = WorkflowBuilder()

    # Add input node
    builder.add_node(
        "PythonCodeNode", "input", {"code": "result = {'value': 10, 'condition': True}"}
    )

    # Add switch node
    builder.add_node("SwitchNode", "switch", {"condition_field": "condition"})

    # Add true branch
    builder.add_node(
        "PythonCodeNode", "true_branch", {"code": "result = 'True path taken'"}
    )

    # Add false branch
    builder.add_node(
        "PythonCodeNode", "false_branch", {"code": "result = 'False path taken'"}
    )

    # Connect workflow
    builder.add_connection("input", "result", "switch", "input_data")
    builder.add_connection("switch", "true_output", "true_branch", "data")
    builder.add_connection("switch", "false_output", "false_branch", "data")

    return builder.build()


def create_workflow_with_cycles() -> Workflow:
    """Create workflow with cyclic dependencies.

    Returns:
        Workflow with cycle (node1 -> node2 -> node1)
    """
    builder = WorkflowBuilder()

    # Create cycle: node1 -> node2 -> node1
    builder.add_node(
        "PythonCodeNode",
        "node1",
        {
            "code": "result = {'iteration': iteration + 1 if 'iteration' in locals() else 1}"
        },
    )

    builder.add_node(
        "PythonCodeNode",
        "node2",
        {"code": "result = {'continue': iteration < 3, 'value': iteration}"},
    )

    # Create cycle
    builder.add_connection("node1", "result", "node2", "data")
    builder.add_connection("node2", "result", "node1", "feedback")

    return builder.build()


def create_workflow_with_disconnected_node() -> Workflow:
    """Create workflow with disconnected node (validation warning).

    Returns:
        Workflow with one disconnected node
    """
    builder = WorkflowBuilder()

    # Connected nodes
    builder.add_node("PythonCodeNode", "node1", {"code": "result = 'connected'"})

    builder.add_node("PythonCodeNode", "node2", {"code": "output = data"})

    builder.add_connection("node1", "result", "node2", "data")

    # Disconnected node
    builder.add_node("PythonCodeNode", "disconnected", {"code": "result = 'isolated'"})

    return builder.build()


def create_large_workflow(node_count: int = 150) -> Workflow:
    """Create large workflow for performance testing.

    Args:
        node_count: Number of nodes to create (default 150)

    Returns:
        Workflow with specified number of nodes
    """
    builder = WorkflowBuilder()

    # Create chain of nodes
    for i in range(node_count):
        builder.add_node("PythonCodeNode", f"node_{i}", {"code": f"result = {i}"})

        # Connect to previous node
        if i > 0:
            builder.add_connection(f"node_{i-1}", "result", f"node_{i}", "input")

    return builder.build()


def create_workflow_with_missing_params() -> Workflow:
    """Create workflow with missing required parameters.

    Returns:
        Workflow with node missing required parameter
    """
    from kailash.nodes.code import PythonCodeNode
    from kailash.workflow import Workflow

    workflow = Workflow(workflow_id="test", name="Test")

    # Create node with required parameter but don't provide it
    node = PythonCodeNode(name="missing_param_node")
    # Note: Not setting required 'code' parameter
    workflow.add_node("missing_param_node", node)

    return workflow


def create_empty_workflow() -> Workflow:
    """Create empty workflow (no nodes).

    Returns:
        Empty workflow
    """
    return Workflow(workflow_id="empty", name="Empty Workflow")


def create_workflow_with_contracts() -> Workflow:
    """Create workflow with connection contracts for validation.

    Returns:
        Workflow with connection contracts defined
    """
    builder = WorkflowBuilder()

    builder.add_node(
        "PythonCodeNode",
        "source",
        {"code": "result = {'data': [1, 2, 3], 'type': 'numbers'}"},
    )

    builder.add_node("PythonCodeNode", "target", {"code": "output = data"})

    builder.add_connection("source", "result", "target", "data")

    workflow = builder.build()

    # Add connection contract to metadata
    workflow.metadata["connection_contracts"] = {
        "source.result → target.data": {
            "name": "data_transfer",
            "source_output": "result",
            "target_input": "data",
            "required": True,
            "type": "dict",
        }
    }

    return workflow


def create_node_outputs(
    node_id: str, outputs: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Create mock node outputs for testing.

    Args:
        node_id: Node identifier
        outputs: Output values

    Returns:
        Dictionary mapping node ID to outputs
    """
    return {node_id: outputs}


def create_multiple_node_outputs(*nodes: tuple) -> Dict[str, Dict[str, Any]]:
    """Create mock outputs for multiple nodes.

    Args:
        *nodes: Tuples of (node_id, outputs_dict)

    Returns:
        Dictionary mapping node IDs to outputs

    Example:
        >>> create_multiple_node_outputs(
        ...     ("node1", {"result": [1, 2, 3]}),
        ...     ("node2", {"output": "processed"})
        ... )
        {"node1": {"result": [1, 2, 3]}, "node2": {"output": "processed"}}
    """
    return {node_id: outputs for node_id, outputs in nodes}


def create_switch_results(
    switch_id: str,
    true_output: Optional[Any] = None,
    false_output: Optional[Any] = None,
    failed: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Create mock switch node results.

    Args:
        switch_id: Switch node identifier
        true_output: Output for true branch
        false_output: Output for false branch
        failed: Whether switch execution failed

    Returns:
        Dictionary with switch results
    """
    result = {}

    if failed:
        result["failed"] = True
        result["error"] = "Switch execution failed"
    else:
        if true_output is not None:
            result["true_output"] = true_output
        if false_output is not None:
            result["false_output"] = false_output

    return {switch_id: result}


__all__ = [
    "create_minimal_workflow",
    "create_valid_workflow",
    "create_workflow_with_switch",
    "create_workflow_with_cycles",
    "create_workflow_with_disconnected_node",
    "create_large_workflow",
    "create_workflow_with_missing_params",
    "create_empty_workflow",
    "create_workflow_with_contracts",
    "create_node_outputs",
    "create_multiple_node_outputs",
    "create_switch_results",
]
