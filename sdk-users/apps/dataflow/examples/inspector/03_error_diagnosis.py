"""
Error Diagnosis Example

This example demonstrates how to use Inspector to diagnose DataFlow errors
and get actionable suggestions.

Run this example:
    python sdk-users/apps/dataflow/examples/inspector/03_error_diagnosis.py
"""

from dataflow import DataFlow
from dataflow.exceptions import EnhancedDataFlowError, ErrorSolution
from dataflow.platform.inspector import Inspector


def main():
    print("=" * 60)
    print("Inspector Example 3: Error Diagnosis")
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

    # Create Inspector
    inspector = Inspector(db)

    # Example 1: Parameter Error
    print("1. Parameter Error Diagnosis")
    print("-" * 60)
    parameter_error = EnhancedDataFlowError(
        error_code="DF-PARAM-001",
        message="Missing required parameter 'data'",
        context={"node_id": "user_create", "parameter_name": "data"},
        causes=["Parameter not provided in node definition"],
        solutions=[
            ErrorSolution(
                priority=1,
                description="Add missing parameter to node",
                code_template="workflow.add_node('UserCreateNode', 'create', {'id': '...', 'name': '...', 'email': '...'})",
            )
        ],
    )

    diagnosis1 = inspector.diagnose_error(parameter_error)
    print(diagnosis1.show(color=False))
    print()

    # Example 2: Connection Error
    print("2. Connection Error Diagnosis")
    print("-" * 60)
    connection_error = EnhancedDataFlowError(
        error_code="DF-CONN-001",
        message="Broken connection detected",
        context={
            "node_id": "user_read",
            "source_node": "user_create",
            "target_parameter": "id",
        },
        causes=["Source parameter does not exist", "Target parameter type mismatch"],
        solutions=[
            ErrorSolution(
                priority=1,
                description="Verify source parameter exists",
                code_template="inspector.node('user_create')",
            ),
            ErrorSolution(
                priority=2,
                description="Check parameter types match",
                code_template="inspector.trace_parameter('user_read', 'id')",
            ),
        ],
    )

    diagnosis2 = inspector.diagnose_error(connection_error)
    print(diagnosis2.show(color=False))
    print()

    # Example 3: Model Error
    print("3. Model Error Diagnosis")
    print("-" * 60)
    model_error = EnhancedDataFlowError(
        error_code="DF-MODEL-001",
        message="Model schema mismatch",
        context={"model_name": "User", "field_name": "email"},
        causes=["Field type changed", "Field removed from model"],
        solutions=[
            ErrorSolution(
                priority=1,
                description="Check model schema",
                code_template="inspector.model('User')",
            ),
            ErrorSolution(
                priority=2,
                description="Verify migration status",
                code_template="inspector.model_migration_status('User')",
            ),
        ],
    )

    diagnosis3 = inspector.diagnose_error(model_error)
    print(diagnosis3.show(color=False))
    print()

    # Example 4: Standard Python Exception
    print("4. Standard Exception Diagnosis")
    print("-" * 60)
    standard_error = KeyError("user_id")

    diagnosis4 = inspector.diagnose_error(standard_error)
    print(diagnosis4.show(color=False))
    print()

    print("=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
