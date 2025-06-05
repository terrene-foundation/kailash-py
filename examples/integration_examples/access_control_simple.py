#!/usr/bin/env python3
"""
Simple Access Control Example for Kailash SDK

Demonstrates a practical use case of access control with a data processing
workflow that has different access levels for different user roles.
Shows how to implement role-based permissions in a real-world scenario.

Design Purpose:
    Provides a straightforward example of implementing access control
    in a typical data processing workflow. Shows how different user roles
    interact with the same workflow with varying permissions.

Upstream Dependencies:
    - Sample customer data (CSV format with sensitive fields)
    - Access control manager configuration
    - User role definitions (admin, analyst, viewer)
    - Permission rule configuration

Downstream Consumers:
    - Data analysts learning secure workflow patterns
    - Developers implementing role-based data access
    - Security teams validating access control models
    - Training materials for access control concepts

Usage Patterns:
    - Run as educational demonstration
    - Used as template for simple access control implementation
    - Referenced in security training materials
    - Integrated into workflow security testing

Implementation Details:
    Creates a data processing workflow where admin users see all data,
    analysts can process but not export, and viewers can only see summaries.
    Demonstrates progressive permission restriction by role.

Example:
    Run the simple access control demo:

    $ python access_control_simple.py
    Created sample data file: customers.csv
    ✓ Access control configured

    === Admin User (Full Access) ===
    Processing all customer data...
    Export permitted

    === Analyst User (Process Only) ===
    Processing customer data...
    Export denied - insufficient permissions

    === Viewer User (Summary Only) ===
    Viewing customer summary...
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
from kailash.workflow import Workflow


def create_sample_data():
    """Create sample customers data file"""
    import os

    # Create data directory if it doesn't exist
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    # Create data in proper directory
    csv_path = os.path.join(data_dir, "customers.csv")
    if not os.path.exists(csv_path):
        with open(csv_path, "w") as f:
            f.write("name,email,phone,ssn,balance\n")
            f.write("John Doe,john@example.com,555-0123,123-45-6789,1500\n")
            f.write("Jane Smith,jane@example.com,555-0124,987-65-4321,2500\n")
            f.write("Bob Johnson,bob@example.com,555-0125,456-78-9012,800\n")
            f.write("Alice Brown,alice@example.com,555-0126,789-01-2345,3200\n")
        print(f"Created sample data file: {csv_path}")


def setup_access_rules():
    """Set up access control rules for our workflow"""
    acm = get_access_control_manager()

    # Rules for the workflow itself - add one rule per role
    for role in ["admin", "analyst", "viewer"]:
        acm.add_rule(
            PermissionRule(
                id=f"workflow_execute_{role}",
                resource_type="workflow",
                resource_id="customer_analysis",
                permission=WorkflowPermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role=role,
            )
        )

    # Rules for data processing node - admin and analyst only
    for role in ["admin", "analyst"]:
        acm.add_rule(
            PermissionRule(
                id=f"process_data_{role}",
                resource_type="node",
                resource_id="process_data",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role=role,
            )
        )

    # Rules for export node - admin only
    acm.add_rule(
        PermissionRule(
            id="export_data_admin",
            resource_type="node",
            resource_id="export_data",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )
    )

    # Rules for summary node - everyone
    for role in ["admin", "analyst", "viewer"]:
        acm.add_rule(
            PermissionRule(
                id=f"create_summary_{role}",
                resource_type="node",
                resource_id="create_summary",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role=role,
            )
        )

    # Output masking for non-admin users
    acm.add_rule(
        PermissionRule(
            id="process_data_analyst_masked",
            resource_type="node",
            resource_id="process_data",
            permission=NodePermission.READ_OUTPUT,
            effect=PermissionEffect.ALLOW,
            role="analyst",
            conditions={"mask_fields": ["ssn", "phone"]},
        )
    )


def create_workflow():
    """Create a customer analysis workflow with access control"""
    workflow = Workflow(
        workflow_id="customer_analysis", name="Customer Analysis Workflow"
    )

    # 1. Read customer data (everyone can read)
    reader = CSVReaderNode(name="csv_reader", file_path="data/customers.csv")

    # 2. Process sensitive data (admin and analyst only)
    processor = add_access_control(
        PythonCodeNode(
            name="data_processor",
            code="""
import pandas as pd

# Convert to dataframe if needed
if isinstance(data, list):
    df = pd.DataFrame(data)
else:
    df = data

# Convert balance to numeric
df['balance'] = pd.to_numeric(df['balance'])

# Calculate customer segments
df['segment'] = pd.cut(
    df['balance'], 
    bins=[0, 1000, 2000, float('inf')],
    labels=['bronze', 'silver', 'gold']
)

# Add risk score (sensitive calculation)
df['risk_score'] = (df['balance'] < 1000).astype(int)

# Keep all fields for now
result = df.to_dict('records')
            """,
            inputs={"data": "dataframe"},
        ),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="process_data",
        mask_output_fields=["ssn", "phone"],  # Mask for non-admin
    )

    # 3. Create summary (everyone can see)
    summarizer = add_access_control(
        PythonCodeNode(
            name="summarizer",
            code="""
import pandas as pd

# Convert to dataframe if needed
if isinstance(data, list):
    df = pd.DataFrame(data)
else:
    df = data

# Create summary without sensitive data
summary = pd.DataFrame({
    'total_customers': [len(df)],
    'average_balance': [df['balance'].mean()],
    'bronze_count': [len(df[df['segment'] == 'bronze'])],
    'silver_count': [len(df[df['segment'] == 'silver'])],
    'gold_count': [len(df[df['segment'] == 'gold'])]
})

result = summary.to_dict('records')
            """,
            inputs={"data": "dataframe"},
        ),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="create_summary",
    )

    # 4. Export detailed data (admin only)
    os.makedirs("outputs", exist_ok=True)
    exporter = add_access_control(
        CSVWriterNode(name="data_exporter", file_path="outputs/customer_analysis.csv"),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="export_data",
    )

    # 5. Export summary (everyone)
    summary_exporter = CSVWriterNode(
        name="summary_exporter", file_path="outputs/customer_summary.csv"
    )

    # Build workflow
    workflow.add_node("reader", reader)
    workflow.add_node("processor", processor)
    workflow.add_node("summarizer", summarizer)
    workflow.add_node("exporter", exporter)
    workflow.add_node("summary_exporter", summary_exporter)

    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})
    workflow.connect("processor", "summarizer", {"result": "data"})
    workflow.connect("processor", "exporter", {"result": "data"})
    workflow.connect("summarizer", "summary_exporter", {"result": "data"})

    return workflow


def run_as_user(workflow, user_role: str, user_email: str):
    """Run workflow as a specific user role"""
    print(f"\n{'='*50}")
    print(f"Running as {user_role.upper()} ({user_email})")
    print("=" * 50)

    # Create user context
    user = UserContext(
        user_id=f"{user_role}-001",
        tenant_id="tenant-001",
        email=user_email,
        roles=[user_role],
    )

    # Create access-controlled runtime
    runtime = AccessControlledRuntime(user)

    try:
        # Execute workflow
        result, output_node = runtime.execute(workflow)
        print("✓ Workflow executed successfully!")
        print(f"✓ Output node: {output_node}")

        # Access control is transparent - no need to check skipped nodes

    except PermissionError as e:
        print(f"✗ Execution failed: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    """Main function to demonstrate access control"""
    print("Kailash SDK - Simple Access Control Example")
    print("==========================================")

    # Create sample data
    create_sample_data()

    # Set up access rules
    print("\nSetting up access control rules...")
    setup_access_rules()
    print("✓ Access rules configured")

    # Create workflow
    print("\nCreating customer analysis workflow...")
    workflow = create_workflow()
    print("✓ Workflow created with 5 nodes")

    # Output files will be created in outputs directory

    # Run as different users
    users = [
        ("admin", "admin@company.com"),
        ("analyst", "analyst@company.com"),
        ("viewer", "viewer@company.com"),
    ]

    for role, email in users:
        run_as_user(workflow, role, email)

    print("\n" + "=" * 50)
    print("Summary of Access Levels:")
    print("=" * 50)
    print("ADMIN:   Can read, process, and export all data")
    print("ANALYST: Can read and process, but SSN/phone are masked")
    print("VIEWER:  Can only see summary statistics")

    # Check outputs
    print("\nCheck the outputs directory for:")
    print("- outputs/customer_analysis.csv (created by admin only)")
    print("- outputs/customer_summary.csv (created by all users)")


if __name__ == "__main__":
    main()
