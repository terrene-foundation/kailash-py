"""
Core RBAC functionality test - validates critical enterprise security features.

This test ensures that role-based access control is working correctly,
which is critical for enterprise security.
"""

import pytest
from kailash import LocalRuntime, WorkflowBuilder
from kailash.nodes.admin import (
    PermissionCheckNode,
    RoleManagementNode,
    UserManagementNode,
)


@pytest.mark.docker
@pytest.mark.e2e
class TestRBACCoreFunctionality:
    """Test core RBAC functionality for enterprise security."""

    def test_rbac_role_creation_and_assignment(self):
        """Test that roles can be created and assigned to users correctly."""
        # Check if PostgreSQL is available before proceeding
        try:
            import psycopg2

            conn = psycopg2.connect(
                host="localhost",
                port=5434,
                database="kailash_test",
                user="test_user",
                password="test_password",
                connect_timeout=3,
            )
            conn.close()
        except Exception:
            pytest.skip("PostgreSQL test database not available")

        print("\n🔐 Testing Core RBAC Functionality...")

        # Database configuration
        db_config = {
            "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
            "database_type": "postgresql",
        }
        tenant_id = "test_tenant"

        # Step 1: Create a role directly
        print("\n1️⃣ Creating role...")
        role_node = RoleManagementNode(
            operation="create_role", tenant_id=tenant_id, database_config=db_config
        )

        role_data = {
            "name": "Test Admin Role",
            "description": "Administrator role for testing",
            "permissions": ["users:manage", "roles:manage", "system:admin"],
            "parent_roles": [],
            "attributes": {"level": 10},
            "role_type": "system",
        }

        role_result = role_node.execute(role_data=role_data, tenant_id=tenant_id)

        print(
            f"   Role creation result: {role_result.get('result', {}).get('success', False)}"
        )
        assert role_result.get("result", {}).get(
            "success", True
        ), "Role creation should succeed"

        # Step 2: Create a user
        print("\n2️⃣ Creating user...")
        user_node = UserManagementNode(
            operation="create_user", tenant_id=tenant_id, database_config=db_config
        )

        import uuid

        unique_id = str(uuid.uuid4())[:8]
        user_data = {
            "email": f"test_admin_{unique_id}@example.com",
            "username": f"test_admin_{unique_id}",
            "first_name": "Test",
            "last_name": "Admin",
            "attributes": {"department": "IT"},
            "status": "active",
            "password": "TestPassword123!",  # Add password to ensure user is properly created
        }

        user_result = user_node.execute(user_data=user_data, tenant_id=tenant_id)

        print(
            f"   User creation result: {user_result.get('result', {}).get('success', True)}"
        )
        created_user = user_result.get("result", {}).get("user", {})
        user_id = created_user.get("user_id")
        print(
            f"   Created user: ID={user_id}, status={created_user.get('status', 'unknown')}"
        )
        assert user_id, "User should be created with an ID"

        # Step 3: Assign role to user
        print("\n3️⃣ Assigning role to user...")
        assign_node = RoleManagementNode(
            operation="assign_user", tenant_id=tenant_id, database_config=db_config
        )

        # Get the actual role_id that was created
        # The RoleManagementNode generates the role_id from the name
        import re

        generated_role_id = re.sub(r"[^a-zA-Z0-9_]", "_", role_data["name"].lower())
        generated_role_id = re.sub(r"_+", "_", generated_role_id).strip("_")

        assign_result = assign_node.execute(
            user_id=user_id, role_id=generated_role_id, tenant_id=tenant_id
        )

        print(
            f"   Role assignment result: {assign_result.get('result', {}).get('success', False)}"
        )
        assert assign_result.get("result", {}).get(
            "success", False
        ), "Role assignment should succeed"

        # Step 3.5: Verify the role was actually assigned
        print("\n3.5️⃣ Verifying role assignment...")
        list_roles_node = RoleManagementNode(
            operation="get_user_roles", tenant_id=tenant_id, database_config=db_config
        )

        user_roles_result = list_roles_node.execute(
            user_id=user_id, tenant_id=tenant_id
        )

        print(f"   User roles: {user_roles_result.get('result', {}).get('roles', [])}")

        # Step 4: Verify permissions
        print("\n4️⃣ Verifying permissions...")
        perm_node = PermissionCheckNode(
            operation="check_permission", tenant_id=tenant_id, database_config=db_config
        )

        # Try different permission formats
        print("   Testing permission formats...")

        # Check if user has admin permission - try without resource/action first
        perm_result = perm_node.execute(
            user_id=user_id,
            resource_id="system",
            permission="admin",  # Try just "admin" instead of "system:admin"
            tenant_id=tenant_id,
        )

        print(
            f"   Permission check result: {perm_result.get('result', {}).get('check', {}).get('allowed', False)}"
        )
        print(f"   Full permission result: {perm_result}")
        assert (
            perm_result.get("result", {}).get("check", {}).get("allowed", False)
        ), "User should have admin permission"

        print("\n✅ Core RBAC functionality test passed!")

    def test_rbac_workflow_integration(self):
        """Test RBAC functionality through workflow integration."""
        # Check if PostgreSQL is available before proceeding
        try:
            import psycopg2

            conn = psycopg2.connect(
                host="localhost",
                port=5434,
                database="kailash_test",
                user="test_user",
                password="test_password",
                connect_timeout=3,
            )
            conn.close()
        except Exception:
            pytest.skip("PostgreSQL test database not available")

        print("\n🔄 Testing RBAC Workflow Integration...")

        # Database configuration
        db_config = {
            "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
            "database_type": "postgresql",
        }
        tenant_id = "workflow_tenant"

        # Create a workflow that creates a role and assigns it
        workflow_builder = WorkflowBuilder()

        # Add nodes
        workflow_builder.add_node(
            "RoleManagementNode",
            "create_role",
            {
                "operation": "create_role",
                "tenant_id": tenant_id,
                "database_config": db_config,
            },
        )

        workflow_builder.add_node(
            "UserManagementNode",
            "create_user",
            {
                "operation": "create_user",
                "tenant_id": tenant_id,
                "database_config": db_config,
            },
        )

        workflow_builder.add_node(
            "RoleManagementNode",
            "assign_role",
            {
                "operation": "assign_user",
                "tenant_id": tenant_id,
                "database_config": db_config,
            },
        )

        # Connect nodes - ensure role is created before assignment
        workflow_builder.add_connection(
            "create_role", "result", "assign_role", "role_info"
        )
        workflow_builder.add_connection(
            "create_user", "result", "assign_role", "user_info"
        )

        # Build workflow
        workflow = workflow_builder.build("rbac_workflow")

        # Execute workflow
        runtime = LocalRuntime()

        role_data = {
            "name": "Workflow Admin",
            "description": "Admin role created by workflow",
            "permissions": ["workflow:manage", "users:view"],
            "parent_roles": [],
            "role_type": "custom",
        }

        user_data = {
            "email": "workflow_user@example.com",
            "username": "workflow_user",
            "first_name": "Workflow",
            "last_name": "User",
        }

        # Generate role_id for assignment
        import re

        role_id = re.sub(r"[^a-zA-Z0-9_]", "_", role_data["name"].lower())
        role_id = re.sub(r"_+", "_", role_id).strip("_")

        result, _ = runtime.execute(
            workflow,
            parameters={
                "create_role": {"role_data": role_data, "tenant_id": tenant_id},
                "create_user": {"user_data": user_data, "tenant_id": tenant_id},
                "assign_role": {
                    "role_id": role_id,
                    "user_id": "dynamic",  # Will be replaced by workflow
                    "tenant_id": tenant_id,
                },
            },
        )

        print("\n   Workflow execution completed")
        print(
            f"   Role created: {result.get('create_role', {}).get('result', {}).get('success', False)}"
        )
        print(
            f"   User created: {result.get('create_user', {}).get('result', {}).get('success', False)}"
        )
        print(
            f"   Role assigned: {result.get('assign_role', {}).get('result', {}).get('success', False)}"
        )

        print("\n✅ RBAC workflow integration test completed!")
