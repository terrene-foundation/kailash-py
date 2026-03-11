"""
Demo: Inspector Parameter Tracing Methods

This example demonstrates all 5 parameter tracing methods:
1. trace_parameter() - Trace parameter back to source (DFS)
2. parameter_flow() - Trace parameter forward through workflow (BFS)
3. find_parameter_source() - Quick source lookup
4. parameter_dependencies() - All dependencies for a node
5. parameter_consumers() - All consumers of an output parameter

Example Workflow:
    fetch_user (user_id) → user_data → transform (data.email) → email → create_record
                                     └→ send_email (user_email)
"""

from dataflow.platform.inspector import Inspector

from kailash.workflow.builder import WorkflowBuilder


def build_example_workflow():
    """Build example workflow with multiple parameter flows."""
    workflow = WorkflowBuilder()

    # Simulate workflow structure (we're just using connections for demo)
    # In real usage, you'd add actual nodes here
    workflow.connections = [
        # fetch_user outputs user_data
        {
            "source_node": "fetch_user",
            "source_parameter": "user_data",
            "target_node": "transform",
            "target_parameter": "input_data",
        },
        # transform uses dot notation to extract email
        {
            "source_node": "transform",
            "source_parameter": "data.email",
            "target_node": "create_record",
            "target_parameter": "email",
        },
        # transform also sends to email service with different name
        {
            "source_node": "transform",
            "source_parameter": "data.email",
            "target_node": "send_email",
            "target_parameter": "user_email",
        },
        # create_record outputs record_id
        {
            "source_node": "create_record",
            "source_parameter": "record_id",
            "target_node": "log_activity",
            "target_parameter": "id",
        },
    ]

    return workflow


def demo_trace_parameter():
    """Demo: Trace parameter back to source."""
    print("=" * 80)
    print("1. trace_parameter() - Trace parameter back to source (DFS)")
    print("=" * 80)

    workflow = build_example_workflow()
    inspector = Inspector(None, workflow)

    # Trace 'email' parameter in create_record node
    trace = inspector.trace_parameter("create_record", "email")

    print("\n📍 Tracing: create_record.email")
    print(trace.show(color=True))
    print()


def demo_parameter_flow():
    """Demo: Trace parameter forward through workflow."""
    print("=" * 80)
    print("2. parameter_flow() - Trace parameter forward (BFS)")
    print("=" * 80)

    workflow = build_example_workflow()
    inspector = Inspector(None, workflow)

    # Trace how 'data.email' flows from transform node
    traces = inspector.parameter_flow("transform", "data.email")

    print("\n📍 Flowing: transform.data.email")
    print(f"Found {len(traces)} downstream paths:\n")

    for i, trace in enumerate(traces, 1):
        print(f"Path {i}:")
        print(
            f"  → {trace.parameter_name} (transformations: {len(trace.transformations)})"
        )
        if trace.transformations:
            for transform in trace.transformations:
                print(f"    • {transform['type']}: {transform['details']}")
    print()


def demo_find_parameter_source():
    """Demo: Quick source lookup."""
    print("=" * 80)
    print("3. find_parameter_source() - Quick source lookup")
    print("=" * 80)

    workflow = build_example_workflow()
    inspector = Inspector(None, workflow)

    # Find sources for multiple parameters
    test_cases = [
        ("create_record", "email"),
        ("send_email", "user_email"),
        ("fetch_user", "user_id"),  # No source (workflow input)
    ]

    print()
    for node_id, param in test_cases:
        source = inspector.find_parameter_source(node_id, param)
        if source:
            print(f"✓ {node_id}.{param} ← {source}")
        else:
            print(f"⊗ {node_id}.{param} ← (workflow input)")
    print()


def demo_parameter_dependencies():
    """Demo: List all dependencies for a node."""
    print("=" * 80)
    print("4. parameter_dependencies() - All dependencies for a node")
    print("=" * 80)

    workflow = build_example_workflow()
    inspector = Inspector(None, workflow)

    # Get all dependencies for create_record node
    deps = inspector.parameter_dependencies("create_record")

    print("\n📍 Dependencies for: create_record")
    print(f"Found {len(deps)} parameter dependencies:\n")

    for param_name, trace in deps.items():
        print(f"  • {param_name}")
        print(f"    Source: {trace.source_node}.{trace.source_parameter}")
        if trace.transformations:
            print(f"    Transformations: {len(trace.transformations)}")
            for transform in trace.transformations:
                print(f"      - {transform['type']}: {transform['details']}")
    print()


def demo_parameter_consumers():
    """Demo: List all consumers of an output parameter."""
    print("=" * 80)
    print("5. parameter_consumers() - All consumers of an output parameter")
    print("=" * 80)

    workflow = build_example_workflow()
    inspector = Inspector(None, workflow)

    # Find all consumers of transform.data.email
    consumers = inspector.parameter_consumers("transform", "data.email")

    print("\n📍 Consumers of: transform.data.email")
    print(f"Found {len(consumers)} consumers:\n")

    for consumer in consumers:
        print(f"  → {consumer}")
    print()


def demo_complete_workflow_analysis():
    """Demo: Complete workflow parameter analysis."""
    print("=" * 80)
    print("COMPLETE WORKFLOW PARAMETER ANALYSIS")
    print("=" * 80)

    workflow = build_example_workflow()
    inspector = Inspector(None, workflow)

    print("\nWorkflow Structure:")
    print("  fetch_user → transform → create_record → log_activity")
    print("                        └→ send_email")
    print()

    # Analyze each node
    nodes = ["fetch_user", "transform", "create_record", "send_email", "log_activity"]

    for node in nodes:
        print(f"\n{'─' * 40}")
        print(f"Node: {node}")
        print(f"{'─' * 40}")

        # Dependencies
        deps = inspector.parameter_dependencies(node)
        if deps:
            print(f"  Dependencies ({len(deps)}):")
            for param_name, trace in deps.items():
                source_info = (
                    f"{trace.source_node}.{trace.source_parameter}"
                    if trace.source_node
                    else "(workflow input)"
                )
                print(f"    • {param_name} ← {source_info}")
        else:
            print("  Dependencies: (none - entry point)")

        # Consumers (check common output parameter)
        # In real scenario, we'd query node metadata for actual output parameters
        # For demo, we'll check known parameters
        test_outputs = [
            ("fetch_user", "user_data"),
            ("transform", "data.email"),
            ("create_record", "record_id"),
        ]

        for node_id, param in test_outputs:
            if node_id == node:
                consumers = inspector.parameter_consumers(node, param)
                if consumers:
                    print(f"  Consumers of '{param}' ({len(consumers)}):")
                    for consumer in consumers:
                        print(f"    → {consumer}")

    print()


def main():
    """Run all demos."""
    print("\n" + "=" * 80)
    print("INSPECTOR PARAMETER TRACING DEMO")
    print("=" * 80)
    print()

    # Run individual demos
    demo_trace_parameter()
    demo_parameter_flow()
    demo_find_parameter_source()
    demo_parameter_dependencies()
    demo_parameter_consumers()

    # Complete analysis
    demo_complete_workflow_analysis()

    print("=" * 80)
    print("Demo Complete!")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
