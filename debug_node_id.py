#!/usr/bin/env python3
"""
Debug script to see the actual node ID.
"""

from kailash.nodes.code.python import PythonCodeNode
from kailash.workflow.builder import WorkflowBuilder


def process_with_kwargs(data: str, **kwargs):
    return {"processed_data": data.upper()}


# Create workflow
workflow = WorkflowBuilder()
node = PythonCodeNode.from_function(process_with_kwargs, name="processor")
workflow.add_node_instance(node)

# Build workflow and print node info
built_workflow = workflow.build()
print("Nodes in workflow:")
for node_id, node_obj in built_workflow.graph.nodes(data=True):
    print(f"  Node ID: {node_id}, Name: {node_obj.get('name', 'N/A')}")
    if hasattr(node_obj, "name"):
        print(f"  Node object name: {node_obj.name}")

print("\nWorkflow graph nodes:", list(built_workflow.graph.nodes()))
