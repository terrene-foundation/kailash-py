#!/usr/bin/env python3
"""
Admin Framework Quick Start Example

This example demonstrates how to quickly get started with the Kailash Admin Framework,
showing all five core admin nodes working together in a simple scenario.
"""

from datetime import datetime, UTC
from kailash.workflow import Workflow
from kailash.nodes.admin import (
    UserManagementNode, RoleManagementNode, PermissionCheckNode,
    AuditLogNode, SecurityEventNode
)
from kailash.runtime.local import LocalRuntime


def quick_admin_demo():
    """Quick demonstration of admin framework capabilities."""
    
    print("🚀 Kailash Admin Framework - Quick Start Demo")
    print("=" * 50)
    
    runtime = LocalRuntime()
    
    # Step 1: Create a new user
    print("\n1️⃣ Creating new user...")
    create_user = UserManagementNode(
        name="create_user",
        operation="create",
        user_data={
            "email": "admin.demo@company.com",
            "username": "admin.demo",
            "first_name": "Admin",
            "last_name": "Demo",
            "attributes": {
                "department": "IT",
                "clearance": "high"
            }
        },
        password="SecurePass123!",
        tenant_id="demo_company",
        database_config={
            "database_type": "postgresql",
            "host": "localhost",
            "port": 5433,  # Admin postgres port
            "database": "kailash_admin",
            "user": "admin",
            "password": "admin"
        }
    )
    
    workflow = Workflow(workflow_id="user_creation_demo", name="user_creation")
    workflow.add_node("create_user", create_user)
    result, _ = runtime.execute(workflow)
    
    user = result["create_user"]["user"]
    print(f"✅ User created: {user['email']} (ID: {user['user_id']})")
    
    # Step 2: Create and assign admin role
    print("\n2️⃣ Creating admin role with permissions...")
    create_role = RoleManagementNode(
        name="create_admin_role",
        operation="create_role",
        role_data={
            "name": "System Administrator",
            "description": "Full system access",
            "permissions": [
                "users:*",
                "roles:*", 
                "audit:read",
                "security:*",
                "system:*"
            ],
            "attributes": {
                "level": "admin",
                "scope": "global"
            }
        },
        tenant_id="demo_company"
    )
    
    assign_role = RoleManagementNode(
        name="assign_role",
        operation="assign_user",
        user_id=user["user_id"],
        role_id="system_administrator",
        tenant_id="demo_company"
    )
    
    workflow = Workflow(workflow_id="role_assignment_demo", name="role_assignment")
    workflow.add_node("create_role", create_role)
    workflow.add_node("assign_role", assign_role)
    workflow.connect("create_role", "assign_role")
    result, _ = runtime.execute(workflow)
    
    print(f"✅ Admin role created and assigned")
    
    # Step 3: Check permissions
    print("\n3️⃣ Verifying admin permissions...")
    check_permission = PermissionCheckNode(
        name="check_admin_access",
        operation="check_permission",
        user_id=user["user_id"],
        resource_id="system_settings",
        permission="write",
        explain=True,
        tenant_id="demo_company"
    )
    
    workflow = Workflow(workflow_id="permission_check_demo", name="permission_check")
    workflow.add_node("check_permission", check_permission)
    result, _ = runtime.execute(workflow)
    
    permission = result["check_admin_access"]["check"]
    print(f"✅ Permission check: {'ALLOWED' if permission['allowed'] else 'DENIED'}")
    if permission.get("explanation"):
        print(f"   Reason: {permission['reason']}")
    
    # Step 4: Log security event
    print("\n4️⃣ Creating security event...")
    security_event = SecurityEventNode(
        name="log_admin_creation",
        operation="create_event",
        event_data={
            "event_type": "privilege_escalation",
            "threat_level": "low",
            "user_id": user["user_id"],
            "source_ip": "10.0.0.100",
            "description": "New admin user created via quick start demo",
            "indicators": {
                "admin_level": "full",
                "creation_method": "api"
            },
            "detection_method": "administrative_action"
        },
        tenant_id="demo_company"
    )
    
    workflow = Workflow(workflow_id="security_logging_demo", name="security_logging")
    workflow.add_node("security_event", security_event)
    result, _ = runtime.execute(workflow)
    
    event = result["log_admin_creation"]["security_event"]
    print(f"✅ Security event logged: {event['event_id']} (Risk: {event['risk_score']})")
    
    # Step 5: Audit trail
    print("\n5️⃣ Creating audit trail...")
    audit_log = AuditLogNode(
        name="audit_admin_creation",
        operation="log_event",
        event_data={
            "event_type": "user_created",
            "severity": "high",
            "user_id": user["user_id"],
            "action": "admin_user_created",
            "description": f"Administrator account created: {user['email']}",
            "metadata": {
                "role": "system_administrator",
                "permissions_granted": 5,
                "created_by": "quick_start_demo"
            }
        },
        tenant_id="demo_company"
    )
    
    workflow = Workflow(workflow_id="audit_logging_demo", name="audit_logging")
    workflow.add_node("audit_log", audit_log)
    result, _ = runtime.execute(workflow)
    
    print(f"✅ Audit event logged for compliance")
    
    # Complete workflow demonstration
    print("\n\n🎯 Complete Admin Workflow Example")
    print("-" * 50)
    
    # Create a workflow that uses all nodes together
    complete_workflow = Workflow(workflow_id="complete_admin_flow_demo", name="complete_admin_flow")
    
    # Add all nodes
    new_user = UserManagementNode(
        name="new_employee",
        operation="create",
        user_data={
            "email": "john.smith@company.com",
            "username": "john.smith",
            "first_name": "John",
            "last_name": "Smith",
            "roles": ["employee"],
            "attributes": {"department": "sales"}
        },
        tenant_id="demo_company"
    )
    
    check_access = PermissionCheckNode(
        name="verify_access",
        operation="check_permission",
        resource_id="sales_data",
        permission="read",
        tenant_id="demo_company"
    )
    
    log_activity = AuditLogNode(
        name="log_activity",
        operation="log_event",
        event_data={
            "event_type": "data_accessed",
            "severity": "low",
            "action": "sales_data_viewed",
            "description": "Employee accessed sales data"
        },
        tenant_id="demo_company"
    )
    
    # Connect nodes
    complete_workflow.add_node("new_user", new_user)
    complete_workflow.add_node("check_access", check_access)
    complete_workflow.add_node("log_activity", log_activity)
    complete_workflow.connect("new_user", "check_access", {"result": "user_id"})
    complete_workflow.connect("check_access", "log_activity", {"result": "user_id"})
    
    # Run complete workflow
    print("Running complete workflow...")
    result, _ = runtime.execute(complete_workflow)
    
    print(f"✅ Employee created: {result['new_employee']['user']['email']}")
    print(f"✅ Access verified: {'ALLOWED' if result['verify_access']['check']['allowed'] else 'DENIED'}")
    print(f"✅ Activity logged for audit trail")
    
    # Summary
    print("\n" + "=" * 50)
    print("✨ QUICK START DEMO COMPLETE!")
    print("=" * 50)
    print("\nYou've successfully:")
    print("1. Created users with the UserManagementNode")
    print("2. Managed roles with the RoleManagementNode")
    print("3. Checked permissions with the PermissionCheckNode")
    print("4. Logged security events with the SecurityEventNode")
    print("5. Created audit trails with the AuditLogNode")
    print("\n🚀 Your admin framework is ready for enterprise use!")
    
    # Show how to query audit logs
    print("\n📊 Bonus: Querying audit logs...")
    query_logs = AuditLogNode(
        name="query_recent",
        operation="query_logs",
        query_filters={
            "event_types": ["user_created", "data_accessed"],
            "date_range": {
                "start": datetime.now(UTC).replace(hour=0, minute=0).isoformat(),
                "end": datetime.now(UTC).isoformat()
            }
        },
        pagination={"page": 1, "size": 10},
        tenant_id="demo_company"
    )
    
    workflow = Workflow(workflow_id="query_logs_demo", name="query_logs")
    workflow.add_node("query_logs", query_logs)
    result, _ = runtime.execute(workflow)
    
    logs = result["query_recent"]["logs"]
    print(f"✅ Found {len(logs)} audit events today")
    
    return {
        "demo_completed": True,
        "nodes_demonstrated": 5,
        "workflows_created": 6
    }


if __name__ == "__main__":
    result = quick_admin_demo()
    print(f"\n📄 Demo completed successfully!")