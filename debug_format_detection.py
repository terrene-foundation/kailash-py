#!/usr/bin/env python3
"""Debug the parameter format detection logic."""

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def debug_format_detection():
    """Debug the _is_node_specific_format detection logic."""

    print("=" * 60)
    print("DEBUGGING PARAMETER FORMAT DETECTION")
    print("=" * 60)

    # Create workflow
    def test_processor(data, **kwargs):
        return {"data": data, "kwargs": kwargs}

    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "processor", {"function": test_processor})
    workflow = builder.build()

    runtime = LocalRuntime()

    print(f"Workflow nodes: {list(workflow.graph.nodes())}")

    # Test different parameter formats
    test_cases = [
        {
            "name": "Pure workflow-level",
            "params": {"tenant_id": "test_tenant", "security_level": "high"},
        },
        {
            "name": "Mixed with node data",
            "params": {
                "processor": {"data": [1, 2, 3]},
                "tenant_id": "test_tenant",
                "security_level": "high",
            },
        },
        {
            "name": "Pure node-specific",
            "params": {"processor": {"data": [1, 2, 3], "tenant_id": "test_tenant"}},
        },
    ]

    for test_case in test_cases:
        params = test_case["params"]
        is_node_specific = runtime._is_node_specific_format(params, workflow)

        print(f"\n{test_case['name']}:")
        print(f"  Parameters: {params}")
        print(f"  Detected as node-specific: {is_node_specific}")

        # Show the logic step by step
        node_ids = set(workflow.graph.nodes())
        print(f"  Node IDs: {node_ids}")

        # Check first condition: key is node ID and value is dict
        first_condition = False
        for key, value in params.items():
            if key in node_ids and isinstance(value, dict):
                print(f"  Found node ID '{key}' with dict value -> node-specific")
                first_condition = True
                break

        if not first_condition:
            # Check second condition
            all_dict_values = all(isinstance(v, dict) for v in params.values())
            keys_look_like_ids = any(
                "_" in k or k.startswith("node") or k in node_ids for k in params.keys()
            )
            print(f"  All dict values: {all_dict_values}")
            print(f"  Keys look like IDs: {keys_look_like_ids}")
            print(
                f"  Second condition result: {all_dict_values and keys_look_like_ids}"
            )


if __name__ == "__main__":
    debug_format_detection()
