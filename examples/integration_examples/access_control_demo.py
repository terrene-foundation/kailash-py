#!/usr/bin/env python3
"""
Simplified Access Control Demo for Kailash SDK

Demonstrates the key access control features including role-based access control,
permission-based execution, data masking, and backward compatibility. This example
shows how to secure workflows without breaking existing code.

Design Purpose:
    Provides a working demonstration of Kailash's access control system,
    showing how different user roles see different data and have different
    execution permissions. Serves as a template for implementing security.

Upstream Dependencies:
    - Sample customer data (CSV format)
    - Access control manager configuration
    - User context definitions with roles
    - Permission rule definitions

Downstream Consumers:
    - Developers learning access control implementation
    - Security teams validating permission models
    - System administrators configuring user roles
    - Integration teams testing secure workflows

Usage Patterns:
    - Run as standalone demo script
    - Used as template for secure workflow creation
    - Referenced in access control documentation
    - Integrated into testing frameworks

Implementation Details:
    Creates sample data, configures permission rules for three roles
    (admin, analyst, viewer), and demonstrates execution with different
    user contexts. Shows data masking and permission-based filtering.

Example:
    Run the demo script to see access control in action:

    $ python access_control_demo.py
    ✓ Created sample data
    ✓ Configured access control

    === Admin User (Full Access) ===
    Processing 4 customer records...

    === Analyst User (Masked Data) ===
    Processing 4 customer records (SSNs masked)...

    === Viewer User (Read Only) ===
    Viewing 4 customer records...
"""

import os

from kailash.access_control import (
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
    get_access_control_manager,
)
from kailash.nodes.base_with_acl import add_access_control
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def setup_sample_data():
    """Create sample customer data"""
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    data = """name,email,ssn,balance,status
John Doe,john@example.com,123-45-6789,1500,active
Jane Smith,jane@example.com,987-65-4321,2500,active
Bob Johnson,bob@example.com,456-78-9012,800,inactive
Alice Brown,alice@example.com,789-01-2345,3200,active"""

    with open("data/customers.csv", "w") as f:
        f.write(data)
    print("✓ Created sample data")


def setup_access_rules():
    """Configure access control rules"""
    acm = get_access_control_manager()

    # Workflow permissions
    for role in ["admin", "analyst", "viewer"]:
        acm.add_rule(
            PermissionRule(
                id=f"workflow_{role}",
                resource_type="workflow",
                resource_id="customer_pipeline",
                permission=WorkflowPermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role=role,
            )
        )

    # Node permissions
    # Everyone can read data
    for role in ["admin", "analyst", "viewer"]:
        acm.add_rule(
            PermissionRule(
                id=f"read_{role}",
                resource_type="node",
                resource_id="reader",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role=role,
            )
        )

    # Only admin and analyst can process data
    for role in ["admin", "analyst"]:
        acm.add_rule(
            PermissionRule(
                id=f"process_{role}",
                resource_type="node",
                resource_id="processor",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role=role,
            )
        )

    # Only admin can export full data
    acm.add_rule(
        PermissionRule(
            id="export_admin",
            resource_type="node",
            resource_id="exporter",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )
    )

    # Everyone can see summary
    for role in ["admin", "analyst", "viewer"]:
        acm.add_rule(
            PermissionRule(
                id=f"summary_{role}",
                resource_type="node",
                resource_id="summarizer",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role=role,
            )
        )

    print("✓ Access rules configured")


def create_workflow():
    """Create a workflow with access-controlled nodes"""
    workflow = Workflow(workflow_id="customer_pipeline", name="Customer Pipeline")

    # 1. Read data (everyone)
    reader = add_access_control(
        CSVReaderNode(name="reader", file_path="data/customers.csv"),
        enable_access_control=True,
        node_id="reader",
    )

    # 2. Process data (admin/analyst only)
    processor = add_access_control(
        PythonCodeNode(
            name="processor",
            code="""
# Simple processing
data_list = data if isinstance(data, list) else [data]
for record in data_list:
    # Add risk flag
    balance = float(record.get('balance', 0))
    record['risk'] = 'high' if balance < 1000 else 'low'
    
result = data_list
            """,
            inputs={"data": "any"},
        ),
        enable_access_control=True,
        node_id="processor",
        mask_output_fields=["ssn"],  # Mask SSN for non-admin
    )

    # 3. Export full data (admin only)
    os.makedirs("outputs", exist_ok=True)
    exporter = add_access_control(
        CSVWriterNode(name="exporter", file_path="outputs/processed_data.csv"),
        enable_access_control=True,
        node_id="exporter",
    )

    # 4. Create summary (everyone)
    summarizer = add_access_control(
        PythonCodeNode(
            name="summarizer",
            code="""
# Create summary
data_list = data if isinstance(data, list) else [data]
total = len(data_list)
high_risk = sum(1 for r in data_list if r.get('risk') == 'high')
low_risk = total - high_risk

result = [{
    'total_customers': total,
    'high_risk_count': high_risk,
    'low_risk_count': low_risk
}]
            """,
            inputs={"data": "any"},
        ),
        enable_access_control=True,
        node_id="summarizer",
    )

    # Build workflow
    workflow.add_node("reader", reader)
    workflow.add_node("processor", processor)
    workflow.add_node("exporter", exporter)
    workflow.add_node("summarizer", summarizer)

    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})
    workflow.connect("processor", "exporter", {"result": "data"})
    workflow.connect("processor", "summarizer", {"result": "data"})

    return workflow


def test_user_access(workflow, user_email: str, role: str):
    """Test workflow execution for a specific user"""
    print(f"\n### Testing as {role.upper()} ({user_email}):")

    # Create user context
    user = UserContext(
        user_id=f"user_{role}", tenant_id="tenant-001", email=user_email, roles=[role]
    )

    # Execute with access control
    runtime = AccessControlledRuntime(user)

    try:
        result, output_node = runtime.execute(workflow)
        print("✓ Workflow completed successfully")

        # Check outputs
        if "exporter" in result:
            print("✓ Full data exported (admin privilege)")
        if "summarizer" in result:
            summary = result["summarizer"]["result"][0]
            print(
                f"✓ Summary: {summary['total_customers']} customers, "
                f"{summary['high_risk_count']} high risk"
            )

        # Check if data was masked
        if "processor" in result and result["processor"]["result"]:
            first_record = result["processor"]["result"][0]
            if "ssn" in first_record and "***" in str(first_record["ssn"]):
                print("✓ Sensitive data masked")

    except PermissionError as e:
        print(f"✗ Access denied: {e}")
    except Exception as e:
        print(f"✗ Error: {str(e)[:100]}...")


def test_backward_compatibility():
    """Show that existing workflows work without changes"""
    print("\n### Testing Backward Compatibility:")

    # Create a simple workflow without access control
    workflow = Workflow(workflow_id="simple", name="Simple Workflow")

    reader = CSVReaderNode(name="reader", file_path="data/customers.csv")
    processor = PythonCodeNode(
        name="processor", code="result = {'count': len(data)}", inputs={"data": "any"}
    )

    workflow.add_node("reader", reader)
    workflow.add_node("processor", processor)
    workflow.connect("reader", "processor", {"data": "data"})

    # Run with standard runtime
    runtime = LocalRuntime()
    result, _ = runtime.execute(workflow)
    print(f"✓ Standard runtime: {result['processor']['result']}")

    # Run with access-controlled runtime (as admin)
    user = UserContext(
        user_id="admin",
        tenant_id="tenant-001",
        email="admin@example.com",
        roles=["admin"],
    )
    ac_runtime = AccessControlledRuntime(user)

    # Need to add permission for this workflow
    acm = get_access_control_manager()
    acm.add_rule(
        PermissionRule(
            id="simple_admin",
            resource_type="workflow",
            resource_id="simple",
            permission=WorkflowPermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )
    )

    result2, _ = ac_runtime.execute(workflow)
    print(f"✓ AC runtime: {result2['processor']['result']}")
    print("✓ Access control is transparent to existing code")


def main():
    """Run the demo"""
    print("Kailash SDK - Access Control Demo")
    print("=" * 50)

    # Setup
    setup_sample_data()
    setup_access_rules()

    # Create workflow
    workflow = create_workflow()
    print("✓ Created workflow with 4 nodes")

    # Test different users
    users = [
        ("admin@example.com", "admin"),
        ("analyst@example.com", "analyst"),
        ("viewer@example.com", "viewer"),
    ]

    for email, role in users:
        test_user_access(workflow, email, role)

    # Test backward compatibility
    test_backward_compatibility()

    # Summary
    print("\n" + "=" * 50)
    print("Summary:")
    print("• Admin: Can read, process, export, and see all data")
    print("• Analyst: Can read and process, but SSN is masked")
    print("• Viewer: Can only read and see summaries")
    print("• Access control is optional and backward compatible")

    # Cleanup
    for f in ["data/customers.csv", "outputs/processed_data.csv"]:
        if os.path.exists(f):
            os.remove(f)


if __name__ == "__main__":
    main()
