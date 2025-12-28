"""
Workflow Debugging Example

This example demonstrates how to use Inspector to debug workflow connections
and trace parameter flow.

Run this example:
    python sdk-users/apps/dataflow/examples/inspector/02_workflow_debugging.py
"""

from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from dataflow.platform.inspector import Inspector


def main():
    print("=" * 60)
    print("Inspector Example 2: Workflow Debugging")
    print("=" * 60)
    print()

    # Create in-memory DataFlow instance
    db = DataFlow(":memory:")

    # Define model
    @db.model
    class User:
        id: str
        name: str
        email: str

    # Create workflow with parameter flow
    workflow = WorkflowBuilder()

    # Node 1: Create user
    workflow.add_node(
        "UserCreateNode",
        "create",
        {"id": "user-123", "name": "Alice Smith", "email": "alice@example.com"},
    )

    # Node 2: Read user (connected to create)
    workflow.add_node("UserReadNode", "read", {"id": "$param:user_id"})

    # Node 3: Update user (connected to read)
    workflow.add_node(
        "UserUpdateNode",
        "update",
        {
            "filter": {"id": "$param:updated_user_id"},
            "fields": {"name": "Alice Johnson"},
        },
    )

    # Add connections
    workflow.add_connection("create", "id", "read", "user_id")
    workflow.add_connection("read", "id", "update", "updated_user_id")

    # Create Inspector
    inspector = Inspector(workflow)

    # 1. List all connections
    print("1. Workflow Connections")
    print("-" * 60)
    connections = inspector.connections()
    print(f"Found {len(connections)} connections:\n")
    for conn in connections:
        print(
            f"  - {conn.source_node}.{conn.source_parameter} → {conn.target_node}.{conn.target_parameter}"
        )
    print()

    # 2. Trace parameter flow
    print("2. Parameter Trace: update.updated_user_id")
    print("-" * 60)
    trace = inspector.trace_parameter("update", "updated_user_id")
    print(trace.show())
    print()

    # 3. Validate connections
    print("3. Connection Validation")
    print("-" * 60)
    validation = inspector.validate_connections()
    if validation["is_valid"]:
        print("✓ All connections are valid")
    else:
        print(f"⚠ Found {len(validation['errors'])} validation errors:")
        for error in validation["errors"]:
            print(f"  - {error}")
    print()

    # 4. Workflow summary
    print("4. Workflow Summary")
    print("-" * 60)
    summary = inspector.workflow_summary()
    print(summary.show())
    print()

    # 5. Find broken connections (should be none)
    print("5. Broken Connection Check")
    print("-" * 60)
    broken = inspector.find_broken_connections()
    if not broken:
        print("✓ No broken connections found")
    else:
        print(f"⚠ Found {len(broken)} broken connections:")
        for issue in broken:
            print(issue.show())
    print()

    print("=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
