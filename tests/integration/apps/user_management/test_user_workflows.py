"""Integration tests for user management workflows using real Docker services."""

import asyncio
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from kailash.nodes.admin.permission_check import PermissionCheckNode
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.user_management import UserManagementNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
)


@pytest.mark.integration
@pytest.mark.requires_docker
class TestUserManagementIntegration:
    """Test user management workflows with real PostgreSQL."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_database(self):
        """Set up test database using real PostgreSQL."""
        # Ensure Docker services are running
        services_ok = await ensure_docker_services()
        if not services_ok:
            pytest.skip("Docker services not available")

        # Get real database connection - use default kailash database
        self.db_config = {
            "connection_string": get_postgres_connection_string(),
            "database_type": "postgresql",
        }

        # Initialize database schema
        db_node = AsyncSQLDatabaseNode(**self.db_config)
        runtime = LocalRuntime()

        # Use the admin schema manager to create tables
        from kailash.nodes.admin.schema_manager import AdminSchemaManager

        schema_manager = AdminSchemaManager(self.db_config)

        try:
            # Create the full admin schema
            schema_result = schema_manager.create_full_schema(drop_existing=True)
            print(f"Schema created: {schema_result['tables_created']}")
        except Exception as e:
            print(f"Schema creation warning: {e}")
            # If schema manager fails, use direct SQL as fallback
            schema_path = (
                Path(__file__).parent.parent.parent.parent.parent
                / "src/kailash/nodes/admin/schema.sql"
            )
            if schema_path.exists():
                with open(schema_path, "r") as f:
                    create_tables_sql = f.read()
                result = db_node.execute(query=create_tables_sql, operation="execute")

        yield

        # Cleanup using schema manager
        try:
            schema_manager.create_full_schema(drop_existing=True)
        except Exception:
            # Manual cleanup if schema manager fails
            cleanup_sql = """
            DROP TABLE IF EXISTS permission_cache CASCADE;
            DROP TABLE IF EXISTS audit_log CASCADE;
            DROP TABLE IF EXISTS user_role_assignments CASCADE;
            DROP TABLE IF EXISTS permissions CASCADE;
            DROP TABLE IF EXISTS roles CASCADE;
            DROP TABLE IF EXISTS users CASCADE;
            """

            cleanup_result = db_node.execute(query=cleanup_sql, operation="execute")

    @pytest.mark.asyncio
    async def test_complete_user_registration_flow(self):
        """Test complete user registration with real database."""
        runtime = LocalRuntime()

        # Initialize nodes directly
        user_mgmt = UserManagementNode()
        role_mgmt = RoleManagementNode()

        # Create default role first
        default_role = role_mgmt.execute(
            operation="create_role",
            tenant_id="test_tenant",
            database_config=self.db_config,
            role_data={"name": "user", "description": "Default user role"},
        )

        # Register new user
        user_data = {
            "email": "test@example.com",
            "username": "testuser",
            "attributes": {"first_name": "Test", "last_name": "User"},
        }

        result = user_mgmt.execute(
            operation="create_user",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_data=user_data,
            password_hash=hashlib.sha256("SecurePass123!".encode()).hexdigest(),
        )

        assert "result" in result
        assert result["result"]["user"]["email"] == user_data["email"]
        assert result["result"]["user"]["username"] == user_data["username"]
        assert "user_id" in result["result"]["user"]

        # Assign role to user
        role_result = role_mgmt.execute(
            operation="assign_user",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_id=result["result"]["user"]["user_id"],
            role_id=default_role["result"]["role"]["role_id"],
        )

        assert "result" in role_result

        # Verify user was created with role using RoleManagementNode
        user_roles = role_mgmt.execute(
            operation="get_user_roles",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_id=result["result"]["user"]["user_id"],
        )

        assert "result" in user_roles
        # Check if there are roles assigned
        if "user_roles" in user_roles["result"]:
            assert len(user_roles["result"]["user_roles"]) > 0
            assert any(r["name"] == "user" for r in user_roles["result"]["user_roles"])
        elif "roles" in user_roles["result"]:
            assert len(user_roles["result"]["roles"]) > 0
            assert any(r["name"] == "user" for r in user_roles["result"]["roles"])

    @pytest.mark.asyncio
    async def test_role_based_access_control(self):
        """Test RBAC with real database and permissions."""
        runtime = LocalRuntime()

        # Initialize nodes
        user_node = UserManagementNode()
        role_node = RoleManagementNode()
        perm_node = PermissionCheckNode()

        # Create roles
        admin_role = role_node.execute(
            operation="create_role",
            tenant_id="test_tenant",
            database_config=self.db_config,
            role_data={"name": "admin", "description": "Administrator role"},
        )

        editor_role = role_node.execute(
            operation="create_role",
            tenant_id="test_tenant",
            database_config=self.db_config,
            role_data={"name": "editor", "description": "Content editor role"},
        )

        # Define permissions
        admin_permissions = [
            "users.create",
            "users.read",
            "users.update",
            "users.delete",
            "content.create",
            "content.update",
        ]

        editor_permissions = ["content.create", "content.update"]

        # Update admin role with permissions
        role_node.execute(
            operation="update_role",
            tenant_id="test_tenant",
            database_config=self.db_config,
            role_id=admin_role["result"]["role"]["role_id"],
            role_data={"permissions": admin_permissions},
        )

        # Update editor role with permissions
        role_node.execute(
            operation="update_role",
            tenant_id="test_tenant",
            database_config=self.db_config,
            role_id=editor_role["result"]["role"]["role_id"],
            role_data={"permissions": editor_permissions},
        )

        # Create users with different roles
        admin_user = user_node.execute(
            operation="create_user",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_data={
                "email": "admin@example.com",
                "username": "admin",
                "attributes": {},
            },
            password_hash=hashlib.sha256("AdminPass123!".encode()).hexdigest(),
        )

        editor_user = user_node.execute(
            operation="create_user",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_data={
                "email": "editor@example.com",
                "username": "editor",
                "attributes": {},
            },
            password_hash=hashlib.sha256("EditorPass123!".encode()).hexdigest(),
        )

        # Assign roles
        role_node.execute(
            operation="assign_user",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_id=admin_user["result"]["user"]["user_id"],
            role_id=admin_role["result"]["role"]["role_id"],
        )

        role_node.execute(
            operation="assign_user",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_id=editor_user["result"]["user"]["user_id"],
            role_id=editor_role["result"]["role"]["role_id"],
        )

        # Check roles were assigned - get user roles
        admin_roles = role_node.execute(
            operation="get_user_roles",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_id=admin_user["result"]["user"]["user_id"],
        )

        editor_roles = role_node.execute(
            operation="get_user_roles",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_id=editor_user["result"]["user"]["user_id"],
        )

        # Admin should have the admin role with all permissions
        assert "result" in admin_roles
        assert len(admin_roles["result"]["roles"]) == 1
        admin_role_data = admin_roles["result"]["roles"][0]
        assert admin_role_data["name"] == "admin"
        assert set(admin_role_data["permissions"]) == set(admin_permissions)

        # Editor should have the editor role with content permissions only
        assert "result" in editor_roles
        assert len(editor_roles["result"]["roles"]) == 1
        editor_role_data = editor_roles["result"]["roles"][0]
        assert editor_role_data["name"] == "editor"
        assert set(editor_role_data["permissions"]) == set(editor_permissions)

    @pytest.mark.asyncio
    async def test_bulk_user_operations(self):
        """Test bulk user operations with real database."""
        runtime = LocalRuntime()
        user_node = UserManagementNode()

        # Create multiple users
        users_data = [
            {
                "email": f"user{i}@example.com",
                "username": f"user{i}",
                "password": f"Password{i}123!",
            }
            for i in range(10)
        ]

        created_users = []
        for ud in users_data:
            result = user_node.execute(
                operation="create_user",
                tenant_id="test_tenant",
                database_config=self.db_config,
                user_data={
                    "email": ud["email"],
                    "username": ud["username"],
                    "attributes": {},
                },
                password_hash=hashlib.sha256(ud["password"].encode()).hexdigest(),
            )
            created_users.append(result["result"]["user"])

        # Test bulk operations
        user_ids = [u["user_id"] for u in created_users]

        # Bulk deactivate - prepare users_data list
        users_to_deactivate = [
            {"user_id": user_id, "status": "inactive"} for user_id in user_ids[:5]
        ]

        deactivate_result = user_node.execute(
            operation="bulk_update",
            tenant_id="test_tenant",
            database_config=self.db_config,
            users_data=users_to_deactivate,
        )

        assert "result" in deactivate_result
        assert deactivate_result["result"]["bulk_result"]["updated_count"] == 5

        # Verify deactivation
        for user_id in user_ids[:5]:
            user = user_node.execute(
                operation="get_user",
                tenant_id="test_tenant",
                database_config=self.db_config,
                user_id=user_id,
            )
            # Check if user is deactivated based on status field
            assert user["result"]["user"]["status"] == "inactive"

        # Search for active users - search by status
        search_result = user_node.execute(
            operation="list_users",
            tenant_id="test_tenant",
            database_config=self.db_config,
            filters={"status": "active"},
        )

        assert "result" in search_result
        # Count only active users
        active_users = [
            u for u in search_result["result"]["users"] if u.get("status") == "active"
        ]
        assert (
            len(active_users) == 5
        ), f"Expected 5 active users, got {len(active_users)}"

        # Bulk delete
        delete_result = user_node.execute(
            operation="bulk_delete",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_ids=user_ids[5:],
        )

        assert "result" in delete_result
        assert delete_result["result"]["bulk_result"]["deleted_count"] == 5

    @pytest.mark.asyncio
    async def test_password_reset_flow(self):
        """Test password reset workflow with real services."""
        runtime = LocalRuntime()

        # Initialize nodes
        user_mgmt = UserManagementNode()

        # Create user
        user_result = user_mgmt.execute(
            operation="create_user",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_data={
                "email": "reset@example.com",
                "username": "resetuser",
                "attributes": {},
            },
            password_hash=hashlib.sha256("OldPassword123!".encode()).hexdigest(),
        )

        user_id = user_result["result"]["user"]["user_id"]

        # Generate reset token
        token_result = user_mgmt.execute(
            operation="generate_reset_token",
            tenant_id="test_tenant",
            database_config=self.db_config,
            user_id=user_id,
        )

        assert "token" in token_result
        reset_token = token_result["token"]

        # Reset password with token
        reset_result = user_mgmt.execute(
            operation="reset_password",
            tenant_id="test_tenant",
            database_config=self.db_config,
            token=reset_token,
            new_password="NewPassword123!",
        )

        assert reset_result["success"] is True

        # Verify old password doesn't work
        old_auth = user_mgmt.execute(
            operation="authenticate",
            tenant_id="test_tenant",
            database_config=self.db_config,
            username="resetuser",
            password="OldPassword123!",
        )

        assert old_auth["authenticated"] is False

        # Verify new password works
        new_auth = user_mgmt.execute(
            operation="authenticate",
            tenant_id="test_tenant",
            database_config=self.db_config,
            username="resetuser",
            password="NewPassword123!",
        )

        assert new_auth["authenticated"] is True
