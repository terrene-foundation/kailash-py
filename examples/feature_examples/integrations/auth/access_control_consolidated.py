#!/usr/bin/env python3
"""
Consolidated Access Control and RBAC Example for Kailash SDK

Comprehensive demonstration of Kailash's access control system including
role-based access control, multi-tenant isolation, JWT authentication
simulation, and advanced security features.

Design Purpose:
    Showcases the complete access control capabilities of Kailash SDK,
    providing a production-ready example of secure workflow execution
    with multiple user roles, tenant isolation, and data protection.

Upstream Dependencies:
    - Sample customer and HR data (CSV format)
    - SimpleJWTAuth for authentication simulation
    - Access control manager configuration
    - Multi-tenant permission rule definitions

Downstream Consumers:
    - Enterprise developers implementing secure workflows
    - Security architects validating access control models
    - DevOps teams deploying multi-tenant systems
    - Compliance teams auditing data access patterns

Usage Patterns:
    - Run as comprehensive demonstration script
    - Used as reference implementation for enterprise security
    - Template for multi-tenant workflow architectures
    - Integration testing for access control features

Implementation Details:
    Simulates JWT authentication, creates tenant-isolated data,
    demonstrates role-based permissions (Admin, Analyst, Viewer),
    shows data masking, conditional routing, and backward compatibility.
    Includes multi-tenant customer analytics and HR workflows.

Example:
    Run the consolidated demo to see all features:

    $ python access_control_consolidated.py
    ✓ Sample data created
    ✓ JWT authentication configured
    ✓ Access control rules applied

    === Testing Customer Analytics Workflow ===
    🔐 Admin user: Full access to sensitive data
    🔐 Analyst user: Masked sensitive fields
    🔐 Viewer user: Limited read-only access

    === Testing HR Workflow ===
    🔐 Multi-tenant isolation verified
"""

import hashlib
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from examples.utils.data_paths import (
    ensure_output_dir_exists,
    get_input_data_path,
    get_output_data_path,
)
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

# Kailash imports
from kailash.workflow import Workflow


def risk_calculator(data=None):
    """Auto-converted from PythonCodeNode string code."""
    import pandas as pd

    # Convert to dataframe
    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data

    # Advanced risk calculations
    df["risk_category"] = df.apply(
        lambda row: (
            "critical"
            if row["risk_score"] == "high" and row["balance"] > 20000
            else row["risk_score"]
        ),
        axis=1,
    )

    # Flag accounts for review
    df["needs_review"] = (df["risk_category"] == "critical") | (
        df["utilization"] > 0.95
    )

    # Convert to JSON-serializable format
    result = df.to_dict("records")

    return result


def summarizer(data=None):
    """Auto-converted from PythonCodeNode string code."""
    import pandas as pd

    # Convert to dataframe
    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data

    # Create summary without sensitive data
    summary = pd.DataFrame(
        {
            "total_customers": [len(df)],
            "average_balance": [df["balance"].mean()],
            "high_risk_count": [len(df[df["risk_score"] == "high"])],
            "medium_risk_count": [len(df[df["risk_score"] == "medium"])],
            "low_risk_count": [len(df[df["risk_score"] == "low"])],
            "accounts_needing_review": [df["needs_review"].sum()],
        }
    )

    result = summary.to_dict("records")

    return result


def comp_calculator(data=None):
    """Auto-converted from PythonCodeNode string code."""
    import pandas as pd

    # Convert to dataframe
    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data

    # Convert numeric columns
    df["salary"] = pd.to_numeric(df["salary"])
    df["performance_rating"] = pd.to_numeric(df["performance_rating"])

    # Calculate bonus based on performance
    df["bonus"] = df.apply(
        lambda row: (
            row["salary"] * 0.15
            if row["performance_rating"] >= 4.5
            else (
                row["salary"] * 0.10
                if row["performance_rating"] >= 4.0
                else row["salary"] * 0.05
            )
        ),
        axis=1,
    )

    # Mask SSN for security
    df["ssn"] = df["ssn"].apply(lambda x: f"***-**-{x[-4:]}")

    # Department statistics
    dept_stats = (
        df.groupby("department")
        .agg({"salary": ["mean", "min", "max"], "performance_rating": "mean"})
        .round(2)
    )

    # Convert to JSON-serializable format
    result = {"employees": df.to_dict("records"), "dept_stats": dept_stats.to_dict()}

    return result


def hr_exporter(data=None):
    """Auto-converted from PythonCodeNode string code."""
    import json
    import os

    # Ensure outputs directory exists
    from examples.utils.data_paths import (
        ensure_output_dir_exists,
        get_input_data_path,
        get_output_data_path,
    )

    ensure_output_dir_exists()

    # Save employee data
    hr_report_path = str(get_output_data_path("access_control/hr_report.json"))
    with open(hr_report_path, "w") as f:
        json.dump(data["employees"], f, indent=2)

    # Save department stats
    dept_stats_path = str(get_output_data_path("access_control/dept_stats.json"))
    with open(dept_stats_path, "w") as f:
        json.dump(data["dept_stats"], f, indent=2)

    result = {
        "status": "exported",
        "files": [hr_report_path, dept_stats_path],
    }

    return result


def processor(data=None):
    """Auto-converted from PythonCodeNode string code."""
    import pandas as pd

    # Simple data processing
    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data

    # Just count records
    result = {"total_records": len(df)}

    return result


def create_sample_data():
    """Create sample data files for the examples"""
    # Customer data with sensitive information
    customers_data = """customer_id,name,email,phone,ssn,balance,credit_limit,join_date
1001,John Smith,john@example.com,555-0101,123-45-6789,15000,20000,2020-01-15
1002,Jane Doe,jane@example.com,555-0102,987-65-4321,8500,10000,2021-03-22
1003,Bob Johnson,bob@example.com,555-0103,456-78-9012,22000,25000,2019-11-08
1004,Alice Brown,alice@example.com,555-0104,789-01-2345,3200,5000,2022-07-14
1005,Charlie Wilson,charlie@example.com,555-0105,234-56-7890,18500,20000,2021-09-30"""

    customer_path = get_input_data_path("customers.csv", subdirectory="csv")
    with open(customer_path, "w") as f:
        f.write(customers_data)

    # Employee data for HR example
    employees_data = """employee_id,name,department,salary,ssn,performance_rating
2001,Sarah Connor,Engineering,125000,111-22-3333,4.5
2002,John Connor,Sales,95000,222-33-4444,3.8
2003,Kyle Reese,HR,85000,333-44-5555,4.2
2004,Miles Dyson,Engineering,135000,444-55-6666,4.7
2005,Marcus Wright,Marketing,78000,555-66-7777,3.5"""

    employee_path = get_input_data_path("employees.csv", subdirectory="csv")
    with open(employee_path, "w") as f:
        f.write(employees_data)

    print("✓ Created sample data files")


def setup_comprehensive_access_rules():
    """Set up comprehensive access control rules"""
    acm = get_access_control_manager()
    # acm.clear_rules()  # Start fresh - not available in this version

    # Define workflows and their permissions
    workflows = {
        "customer_analytics": ["admin", "analyst", "viewer"],
        "hr_processing": ["admin", "hr_manager"],
        "financial_reporting": ["admin", "finance_team", "auditor"],
        "legacy_workflow": ["admin"],  # Allow admin to run legacy workflow
    }

    for workflow_id, allowed_roles in workflows.items():
        for role in allowed_roles:
            acm.add_rule(
                PermissionRule(
                    id=f"{workflow_id}_execute_{role}",
                    resource_type="workflow",
                    resource_id=workflow_id,
                    permission=WorkflowPermission.EXECUTE,
                    effect=PermissionEffect.ALLOW,
                    role=role,
                )
            )

    # Node-level permissions for customer analytics
    nodes_config = [
        ("read_customers", ["admin", "analyst", "viewer"], NodePermission.EXECUTE),
        ("process_sensitive", ["admin", "analyst"], NodePermission.EXECUTE),
        ("calculate_risk", ["admin", "analyst"], NodePermission.EXECUTE),
        ("export_full", ["admin"], NodePermission.EXECUTE),
        ("create_summary", ["admin", "analyst", "viewer"], NodePermission.EXECUTE),
        ("export_summary", ["admin", "analyst", "viewer"], NodePermission.EXECUTE),
    ]

    for node_id, roles, permission in nodes_config:
        for role in roles:
            acm.add_rule(
                PermissionRule(
                    id=f"{node_id}_{permission.value}_{role}",
                    resource_type="node",
                    resource_id=node_id,
                    permission=permission,
                    effect=PermissionEffect.ALLOW,
                    role=role,
                )
            )

    # Data masking rules for analysts
    acm.add_rule(
        PermissionRule(
            id="mask_sensitive_analyst",
            resource_type="node",
            resource_id="process_sensitive",
            permission=NodePermission.READ_OUTPUT,
            effect=PermissionEffect.ALLOW,
            role="analyst",
            conditions={"mask_fields": ["ssn", "phone"]},
        )
    )

    # HR workflow permissions
    hr_nodes = [
        ("read_employees", ["admin", "hr_manager"], NodePermission.EXECUTE),
        ("calculate_compensation", ["admin", "hr_manager"], NodePermission.EXECUTE),
        ("export_hr_report", ["admin", "hr_manager"], NodePermission.EXECUTE),
    ]

    for node_id, roles, permission in hr_nodes:
        for role in roles:
            acm.add_rule(
                PermissionRule(
                    id=f"{node_id}_{permission.value}_{role}",
                    resource_type="node",
                    resource_id=node_id,
                    permission=permission,
                    effect=PermissionEffect.ALLOW,
                    role=role,
                )
            )

    print("✓ Configured comprehensive access rules")


class SimpleJWTAuth:
    """Simple JWT-style authentication simulation (no external dependencies)"""

    def __init__(self, secret_key: str = "your-secret-key"):
        self.secret_key = secret_key
        self.users_db = {}
        self.tokens = {}

    def register_user(
        self, email: str, password: str, roles: List[str], tenant_id: str
    ) -> Dict[str, Any]:
        """Register a new user"""
        user_id = f"user_{len(self.users_db) + 1}"
        password_hash = hashlib.sha256(
            f"{password}{self.secret_key}".encode()
        ).hexdigest()

        user = {
            "user_id": user_id,
            "email": email,
            "password_hash": password_hash,
            "roles": roles,
            "tenant_id": tenant_id,
            "created_at": datetime.now().isoformat(),
        }

        self.users_db[email] = user
        return {"user_id": user_id, "email": email, "tenant_id": tenant_id}

    def login(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user and generate token"""
        user = self.users_db.get(email)
        if not user:
            return None

        password_hash = hashlib.sha256(
            f"{password}{self.secret_key}".encode()
        ).hexdigest()
        if password_hash != user["password_hash"]:
            return None

        # Generate simple token
        token = hashlib.sha256(
            f"{email}{time.time()}{self.secret_key}".encode()
        ).hexdigest()

        token_data = {
            "token": token,
            "user_id": user["user_id"],
            "email": user["email"],
            "roles": user["roles"],
            "tenant_id": user["tenant_id"],
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
        }

        self.tokens[token] = token_data
        return token_data

    def verify_token(self, token: str) -> Optional[UserContext]:
        """Verify token and return user context"""
        token_data = self.tokens.get(token)
        if not token_data:
            return None

        # Check expiration
        if datetime.fromisoformat(token_data["expires_at"]) < datetime.now():
            del self.tokens[token]
            return None

        return UserContext(
            user_id=token_data["user_id"],
            tenant_id=token_data["tenant_id"],
            email=token_data["email"],
            roles=token_data["roles"],
        )


def create_customer_analytics_workflow():
    """Create a customer analytics workflow with access control"""
    workflow = Workflow(
        workflow_id="customer_analytics", name="Customer Analytics Pipeline"
    )

    # 1. Read customer data (everyone can read)
    reader = add_access_control(
        CSVReaderNode(
            name="csv_reader",
            file_path=str(get_input_data_path("customers.csv", subdirectory="csv")),
        ),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="read_customers",
    )

    # Define sensitive data processor function (better IDE support)
    def process_sensitive_data(data):
        """Process sensitive customer data with risk calculations."""
        import pandas as pd

        # Convert to dataframe
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data

        # Convert numeric columns
        df["balance"] = pd.to_numeric(df["balance"])
        df["credit_limit"] = pd.to_numeric(df["credit_limit"])

        # Calculate risk metrics
        df["utilization"] = df["balance"] / df["credit_limit"]
        df["risk_score"] = df["utilization"].apply(
            lambda x: "high" if x > 0.8 else ("medium" if x > 0.5 else "low")
        )

        # Add account age
        df["join_date"] = pd.to_datetime(df["join_date"])
        df["account_age_days"] = (pd.Timestamp.now() - df["join_date"]).dt.days

        # Convert to JSON-serializable format
        return df.to_dict("records")

    # 2. Process sensitive data (admin and analyst only)
    processor = add_access_control(
        PythonCodeNode.from_function(
            func=process_sensitive_data,
            name="sensitive_processor",
            description="Process sensitive customer data with risk calculations",
        ),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="process_sensitive",
        mask_output_fields=["ssn", "phone"],  # Mask for non-admin users
    )

    # 3. Calculate advanced risk metrics (admin and analyst only)
    risk_calc_node = add_access_control(
        PythonCodeNode.from_function(func=risk_calculator, name="risk_calculator"),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="calculate_risk",
    )

    # 4. Create summary report (everyone can execute)
    summarizer_node = add_access_control(
        PythonCodeNode.from_function(func=summarizer, name="summarizer"),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="create_summary",
    )

    # 5. Export full data (admin only)
    ensure_output_dir_exists()
    full_exporter = add_access_control(
        CSVWriterNode(
            name="full_exporter",
            file_path=str(
                get_output_data_path("access_control/customer_analysis_full.csv")
            ),
        ),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="export_full",
    )

    # 6. Export summary (everyone)
    summary_exporter = add_access_control(
        CSVWriterNode(
            name="summary_exporter",
            file_path=str(
                get_output_data_path("access_control/customer_analysis_summary.csv")
            ),
        ),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="export_summary",
    )

    # Build workflow
    workflow.add_node("reader", reader)
    workflow.add_node("processor", processor)
    workflow.add_node("risk_calculator", risk_calc_node)
    workflow.add_node("summarizer", summarizer_node)
    workflow.add_node("full_exporter", full_exporter)
    workflow.add_node("summary_exporter", summary_exporter)

    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})
    workflow.connect("processor", "risk_calculator", {"result": "data"})
    workflow.connect("risk_calculator", "summarizer", {"result": "data"})
    workflow.connect("risk_calculator", "full_exporter", {"result": "data"})
    workflow.connect("summarizer", "summary_exporter", {"result": "data"})

    return workflow


def create_hr_workflow():
    """Create an HR workflow with strict access control"""
    workflow = Workflow(workflow_id="hr_processing", name="HR Data Processing")

    # Read employee data
    reader = add_access_control(
        CSVReaderNode(
            name="hr_reader",
            file_path=str(get_input_data_path("employees.csv", subdirectory="csv")),
        ),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="read_employees",
    )

    # Calculate compensation metrics
    calculator = add_access_control(
        PythonCodeNode.from_function(func=comp_calculator, name="comp_calculator"),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="calculate_compensation",
    )

    # Export HR report
    exporter = add_access_control(
        PythonCodeNode.from_function(func=hr_exporter, name="hr_exporter"),
        enable_access_control=True,
        required_permission=NodePermission.EXECUTE,
        node_id="export_hr_report",
    )

    # Build workflow
    workflow.add_node("reader", reader)
    workflow.add_node("calculator", calculator)
    workflow.add_node("exporter", exporter)

    # Connect nodes
    workflow.connect("reader", "calculator", {"data": "data"})
    workflow.connect("calculator", "exporter", {"result": "data"})

    return workflow


def demonstrate_jwt_auth():
    """Demonstrate JWT-style authentication"""
    print("\n" + "=" * 60)
    print("JWT-Style Authentication Demo")
    print("=" * 60)

    auth = SimpleJWTAuth()

    # Register users
    users = [
        ("admin@company.com", "admin123", ["admin"], "tenant-001"),
        ("analyst@company.com", "analyst123", ["analyst"], "tenant-001"),
        ("viewer@company.com", "viewer123", ["viewer"], "tenant-001"),
        ("hr@company.com", "hr123", ["hr_manager"], "tenant-001"),
        ("external@partner.com", "external123", ["viewer"], "tenant-002"),
    ]

    print("\n1. Registering users:")
    for email, password, roles, tenant in users:
        auth.register_user(email, password, roles, tenant)
        print(f"   ✓ Registered {email} with roles {roles} in {tenant}")

    # Test authentication
    print("\n2. Testing authentication:")

    # Successful login
    token_data = auth.login("admin@company.com", "admin123")
    if token_data:
        print(f"   ✓ Admin login successful - Token: {token_data['token'][:16]}...")
        admin_context = auth.verify_token(token_data["token"])
        print(
            f"   ✓ Token verified - User: {admin_context.email}, Roles: {admin_context.roles}"
        )

    # Failed login
    failed = auth.login("admin@company.com", "wrongpassword")
    if not failed:
        print("   ✓ Invalid password correctly rejected")

    # Test token expiration simulation
    print("\n3. Testing tenant isolation:")
    analyst_token = auth.login("analyst@company.com", "analyst123")
    external_token = auth.login("external@partner.com", "external123")

    analyst_ctx = auth.verify_token(analyst_token["token"])
    external_ctx = auth.verify_token(external_token["token"])

    print(f"   • Analyst tenant: {analyst_ctx.tenant_id}")
    print(f"   • External tenant: {external_ctx.tenant_id}")
    print("   ✓ Users are isolated in different tenants")

    return auth, token_data["token"]


def demonstrate_access_control(auth: SimpleJWTAuth, admin_token: str):
    """Demonstrate comprehensive access control"""
    print("\n" + "=" * 60)
    print("Access Control Demonstration")
    print("=" * 60)

    # Create workflows
    customer_workflow = create_customer_analytics_workflow()
    hr_workflow = create_hr_workflow()

    # Test different user scenarios
    test_users = [
        ("admin@company.com", "admin123", "Admin User"),
        ("analyst@company.com", "analyst123", "Analyst User"),
        ("viewer@company.com", "viewer123", "Viewer User"),
        ("hr@company.com", "hr123", "HR Manager"),
    ]

    for email, password, description in test_users:
        print(f"\n### Testing as {description} ({email}):")

        # Login
        token_data = auth.login(email, password)
        user_context = auth.verify_token(token_data["token"])

        # Create runtime with user context
        runtime = AccessControlledRuntime(user_context)

        # Try customer analytics workflow
        print("\n• Customer Analytics Workflow:")
        try:
            result, output_node = runtime.execute(customer_workflow)
            print("  ✓ Workflow executed successfully")
            print(f"  ✓ Completed at node: {output_node}")

            # Check what files were created
            files_created = []
            full_path = str(
                get_output_data_path("access_control/customer_analysis_full.csv")
            )
            summary_path = str(
                get_output_data_path("access_control/customer_analysis_summary.csv")
            )
            if os.path.exists(full_path):
                files_created.append(full_path)
            if os.path.exists(summary_path):
                files_created.append(summary_path)

            if files_created:
                print(f"  ✓ Files created: {', '.join(files_created)}")

        except PermissionError as e:
            print(f"  ✗ Access denied: {e}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

        # Try HR workflow
        print("\n• HR Processing Workflow:")
        try:
            result, output_node = runtime.execute(hr_workflow)
            print("  ✓ Workflow executed successfully")

            # Check HR files
            hr_files = []
            hr_report_path = str(get_output_data_path("access_control/hr_report.json"))
            dept_stats_path = str(
                get_output_data_path("access_control/dept_stats.json")
            )
            if os.path.exists(hr_report_path):
                hr_files.append(hr_report_path)
            if os.path.exists(dept_stats_path):
                hr_files.append(dept_stats_path)

            if hr_files:
                print(f"  ✓ Files created: {', '.join(hr_files)}")

        except PermissionError as e:
            print(f"  ✗ Access denied: {e}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

        # Clean up files for next user
        for f in [
            "outputs/customer_analysis_full.csv",
            "outputs/customer_analysis_summary.csv",
            "outputs/hr_report.json",
            "outputs/dept_stats.json",
        ]:
            if os.path.exists(f):
                os.remove(f)


def demonstrate_backward_compatibility():
    """Show that access control doesn't affect existing code"""
    print("\n" + "=" * 60)
    print("Backward Compatibility Demo")
    print("=" * 60)

    # Create a simple workflow without any access control
    workflow = Workflow(workflow_id="legacy_workflow", name="Legacy Workflow")

    # Standard nodes - no access control
    reader = CSVReaderNode(
        name="reader",
        file_path=str(get_input_data_path("customers.csv", subdirectory="csv")),
    )

    processor_node = PythonCodeNode.from_function(func=processor, name="processor")

    # Build workflow
    workflow.add_node("reader", reader)
    workflow.add_node("processor", processor_node)
    workflow.connect("reader", "processor", {"data": "data"})

    print("\n1. Running with standard LocalRuntime (no access control):")
    runtime = LocalRuntime()
    result, output = runtime.execute(workflow)
    print("   ✓ Workflow executed successfully")
    print(f"   ✓ Result: {result}")

    print("\n2. Same workflow with AccessControlledRuntime:")
    # Create a user context
    user = UserContext(
        user_id="legacy_user",
        tenant_id="tenant-001",
        email="legacy@example.com",
        roles=["admin"],
    )

    ac_runtime = AccessControlledRuntime(user)
    result2, output2 = ac_runtime.execute(workflow)
    print("   ✓ Workflow executed successfully")
    print(f"   ✓ Result: {result2}")
    print("   ✓ Access control is transparent to existing workflows")


def main():
    """Run all demonstrations"""
    print("Kailash SDK - Consolidated Access Control & RBAC Demo")
    print("=" * 60)

    # Create sample data
    create_sample_data()

    # Set up access rules
    setup_comprehensive_access_rules()

    # Demonstrate JWT authentication
    auth, admin_token = demonstrate_jwt_auth()

    # Demonstrate access control
    demonstrate_access_control(auth, admin_token)

    # Show backward compatibility
    demonstrate_backward_compatibility()

    # Clean up
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("• Access control is completely optional and backward compatible")
    print("• Different users have different permissions based on roles")
    print("• Sensitive data can be masked for non-privileged users")
    print("• Workflows can be shared across tenants with proper isolation")
    print("• JWT-style authentication can be integrated easily")

    # Clean up sample files
    for f in [
        "data/customers.csv",
        "data/employees.csv",
        str(get_output_data_path("access_control/customer_analysis_full.csv")),
        str(get_output_data_path("access_control/customer_analysis_summary.csv")),
        str(get_output_data_path("access_control/hr_report.json")),
        str(get_output_data_path("access_control/dept_stats.json")),
    ]:
        if os.path.exists(f):
            os.remove(f)


if __name__ == "__main__":
    main()
