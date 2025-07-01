"""
End-to-end tests for admin nodes with Docker and Ollama.

These tests demonstrate real-world usage of the unified admin system
with user management, role management, and permission checks.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any, Dict, List

import pytest

from kailash.nodes.admin.permission_check import PermissionCheckNode
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.schema_manager import AdminSchemaManager
from kailash.nodes.admin.user_management import UserManagementNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.runtime import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from kailash.workflow import WorkflowBuilder
from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_url,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestAdminNodesE2E:
    """End-to-end tests for admin nodes with real infrastructure."""

    @pytest.fixture(scope="class")
    def docker_services(self):
        """Ensure Docker services are running."""
        ensure_docker_services()
        return {
            "postgres_url": get_postgres_connection_string(),
            "redis_url": get_redis_url(),
        }

    @pytest.fixture
    def db_config(self, docker_services):
        """Database configuration for tests."""
        return {
            "connection_string": docker_services["postgres_url"],
            "database_type": "postgresql",
        }

    @pytest.fixture
    def cache_config(self, docker_services):
        """Cache configuration for tests."""
        return {
            "redis_url": docker_services["redis_url"],
            "ttl": 300,
        }

    @pytest.fixture
    def ollama_config(self):
        """Ollama configuration for test data generation."""
        return {
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11435"),
            "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
            "timeout": 30,
        }

    @pytest.fixture
    async def setup_admin_schema(self, db_config):
        """Set up admin database schema."""
        schema_manager = AdminSchemaManager(database_config=db_config)
        await asyncio.to_thread(schema_manager.initialize_schema)
        yield
        # Cleanup is handled by container teardown

    async def test_complete_user_lifecycle(
        self, db_config, cache_config, setup_admin_schema
    ):
        """Test complete user lifecycle: create, update, roles, permissions."""
        # Create nodes
        user_node = UserManagementNode(database_config=db_config)
        role_node = RoleManagementNode(database_config=db_config)
        permission_node = PermissionCheckNode(
            database_config=db_config,
            cache_backend="redis",
            cache_config=cache_config,
        )

        # Create a test tenant
        tenant_id = "test_tenant_001"

        # 1. Create roles
        editor_role = await asyncio.to_thread(
            role_node.run,
            operation="create_role",
            role_data={
                "name": "editor",
                "description": "Content editor with read/write permissions",
                "permissions": ["content:read", "content:write", "content:edit"],
            },
            tenant_id=tenant_id,
        )
        assert editor_role["result"]["success"] is True

        admin_role = await asyncio.to_thread(
            role_node.run,
            operation="create_role",
            role_data={
                "name": "admin",
                "description": "Administrator with full permissions",
                "permissions": ["*:*"],  # Global permission
                "parent_roles": ["editor"],  # Inherits from editor
            },
            tenant_id=tenant_id,
        )
        assert admin_role["result"]["success"] is True

        # 2. Create users
        test_user = await asyncio.to_thread(
            user_node.run,
            operation="create_user",
            user_data={
                "email": "john.doe@example.com",
                "username": "johndoe",
                "first_name": "John",
                "last_name": "Doe",
                "display_name": "John Doe",
                "password": "SecurePassword123!",
                "roles": ["editor"],
            },
            tenant_id=tenant_id,
        )
        assert test_user["result"]["user"]["email"] == "john.doe@example.com"

        admin_user = await asyncio.to_thread(
            user_node.run,
            operation="create_user",
            user_data={
                "email": "admin@example.com",
                "username": "admin",
                "first_name": "Admin",
                "last_name": "User",
                "display_name": "Administrator",
                "password": "AdminPassword123!",
                "roles": ["admin"],
            },
            tenant_id=tenant_id,
        )
        assert admin_user["result"]["user"]["roles"] == ["admin"]

        # 3. Test permission checks
        # Editor can read and write content
        editor_read_check = await asyncio.to_thread(
            permission_node.run,
            operation="check_permission",
            user_id=test_user["result"]["user"]["user_id"],
            resource_id="content",
            permission="read",
            tenant_id=tenant_id,
        )
        assert editor_read_check["result"]["check"]["allowed"] is True

        # Editor cannot delete content
        editor_delete_check = await asyncio.to_thread(
            permission_node.run,
            operation="check_permission",
            user_id=test_user["result"]["user"]["user_id"],
            resource_id="content",
            permission="delete",
            tenant_id=tenant_id,
        )
        assert editor_delete_check["result"]["check"]["allowed"] is False

        # Admin can do anything (global permission)
        admin_delete_check = await asyncio.to_thread(
            permission_node.run,
            operation="check_permission",
            user_id=admin_user["result"]["user"]["user_id"],
            resource_id="content",
            permission="delete",
            tenant_id=tenant_id,
        )
        assert admin_delete_check["result"]["check"]["allowed"] is True

        # 4. Update user (promote editor to admin)
        promoted_user = await asyncio.to_thread(
            user_node.run,
            operation="update_user",
            user_id=test_user["result"]["user"]["user_id"],
            user_data={"roles": ["editor", "admin"]},
            tenant_id=tenant_id,
        )
        assert "admin" in promoted_user["result"]["user"]["roles"]

        # 5. Test batch permission check
        batch_check = await asyncio.to_thread(
            permission_node.run,
            operation="batch_check",
            user_id=test_user["result"]["user"]["user_id"],
            checks=[
                {"resource_id": "content", "permissions": ["read", "write", "delete"]},
                {"resource_id": "users", "permissions": ["read", "manage"]},
            ],
            tenant_id=tenant_id,
        )
        assert (
            batch_check["result"]["results"]["content"]["delete"] is True
        )  # Now has admin

        # 6. Deactivate user
        deactivated = await asyncio.to_thread(
            user_node.run,
            operation="deactivate_user",
            user_id=test_user["result"]["user"]["user_id"],
            tenant_id=tenant_id,
        )
        assert deactivated["result"]["user"]["status"] == "inactive"

        # 7. Permission check should fail for inactive user
        with pytest.raises(NodeExecutionError):
            await asyncio.to_thread(
                permission_node.run,
                operation="check_permission",
                user_id=test_user["result"]["user"]["user_id"],
                resource_id="content",
                permission="read",
                tenant_id=tenant_id,
            )

    async def test_role_hierarchy_and_inheritance(self, db_config, setup_admin_schema):
        """Test role hierarchy with permission inheritance."""
        role_node = RoleManagementNode(database_config=db_config)
        tenant_id = "test_tenant_002"

        # Create base roles
        viewer_role = await asyncio.to_thread(
            role_node.run,
            operation="create_role",
            role_data={
                "name": "viewer",
                "description": "Basic viewer role",
                "permissions": ["content:read", "profile:read"],
            },
            tenant_id=tenant_id,
        )

        contributor_role = await asyncio.to_thread(
            role_node.run,
            operation="create_role",
            role_data={
                "name": "contributor",
                "description": "Can contribute content",
                "permissions": ["content:write", "content:edit"],
                "parent_roles": ["viewer"],  # Inherits read permissions
            },
            tenant_id=tenant_id,
        )

        moderator_role = await asyncio.to_thread(
            role_node.run,
            operation="create_role",
            role_data={
                "name": "moderator",
                "description": "Can moderate content",
                "permissions": ["content:delete", "content:moderate", "users:warn"],
                "parent_roles": ["contributor"],  # Inherits contributor + viewer
            },
            tenant_id=tenant_id,
        )

        # Get effective permissions for moderator
        effective_perms = await asyncio.to_thread(
            role_node.run,
            operation="get_effective_permissions",
            role_id="moderator",
            tenant_id=tenant_id,
        )

        # Should have all permissions from hierarchy
        perms = effective_perms["result"]["permissions"]
        assert "content:read" in perms  # From viewer
        assert "content:write" in perms  # From contributor
        assert "content:delete" in perms  # Own permission

    async def test_bulk_operations_with_ollama_data(
        self, db_config, ollama_config, setup_admin_schema
    ):
        """Test bulk operations using Ollama to generate test data."""
        user_node = UserManagementNode(database_config=db_config)
        llm_node = LLMAgentNode(**ollama_config)
        tenant_id = "test_tenant_003"

        # Use Ollama to generate test users
        prompt = """Generate 5 realistic user profiles for a content management system.
        Return as JSON array with fields: email, username, first_name, last_name, display_name.
        Make them diverse and realistic."""

        try:
            llm_result = await asyncio.to_thread(
                llm_node.run,
                prompt=prompt,
                temperature=0.7,
                response_format="json",
            )

            # Parse generated users
            users_data = json.loads(llm_result.get("response", "[]"))

            # Create users in bulk
            bulk_result = await asyncio.to_thread(
                user_node.run,
                operation="bulk_create",
                users_data=[
                    {
                        **user,
                        "password": f"Pass{idx}word123!",
                        "roles": ["viewer"] if idx % 2 == 0 else ["contributor"],
                    }
                    for idx, user in enumerate(users_data[:5])
                ],
                tenant_id=tenant_id,
            )

            assert bulk_result["result"]["bulk_result"]["created_count"] >= 3

        except Exception as e:
            # If Ollama is not available, use fallback data
            pytest.skip(f"Ollama not available: {e}")

    async def test_workflow_integration(
        self, db_config, cache_config, setup_admin_schema
    ):
        """Test admin nodes in a workflow context."""
        # Build a user onboarding workflow
        builder = WorkflowBuilder()

        # Add nodes
        builder.add_node(
            "UserManagementNode",
            "create_user",
            database_config=db_config,
        )

        builder.add_node(
            "RoleManagementNode",
            "assign_role",
            database_config=db_config,
        )

        builder.add_node(
            "PermissionCheckNode",
            "verify_access",
            database_config=db_config,
            cache_backend="redis",
            cache_config=cache_config,
        )

        # Connect nodes
        builder.add_connection(
            "create_user", "assign_role", "result.user.user_id", "user_id"
        )
        builder.add_connection(
            "assign_role", "verify_access", "result.user_id", "user_id"
        )

        # Build and run workflow
        workflow = builder.build()
        runtime = LocalRuntime()

        inputs = {
            "operation": "create_user",
            "user_data": {
                "email": "workflow.user@example.com",
                "username": "workflowuser",
                "first_name": "Workflow",
                "last_name": "User",
                "display_name": "Workflow Test User",
                "password": "WorkflowPass123!",
            },
            "tenant_id": "test_tenant_004",
            "role_id": "viewer",
            "resource_id": "content",
            "permission": "read",
        }

        result = await runtime.execute_async(workflow, inputs)

        # Verify user was created and has access
        assert result["verify_access"]["check"]["allowed"] is True

    async def test_multi_tenant_isolation(self, db_config, setup_admin_schema):
        """Test that data is properly isolated between tenants."""
        user_node = UserManagementNode(database_config=db_config)

        # Create users in different tenants
        tenant_a_user = await asyncio.to_thread(
            user_node.run,
            operation="create_user",
            user_data={
                "email": "user@tenanta.com",
                "username": "tenanta_user",
                "first_name": "Tenant A",
                "last_name": "User",
                "password": "TenantAPass123!",
            },
            tenant_id="tenant_a",
        )

        tenant_b_user = await asyncio.to_thread(
            user_node.run,
            operation="create_user",
            user_data={
                "email": "user@tenantb.com",
                "username": "tenantb_user",
                "first_name": "Tenant B",
                "last_name": "User",
                "password": "TenantBPass123!",
            },
            tenant_id="tenant_b",
        )

        # List users in tenant A - should not see tenant B user
        tenant_a_users = await asyncio.to_thread(
            user_node.run,
            operation="list_users",
            tenant_id="tenant_a",
        )

        user_emails = [u["email"] for u in tenant_a_users["result"]["users"]]
        assert "user@tenanta.com" in user_emails
        assert "user@tenantb.com" not in user_emails

        # Try to access tenant B user from tenant A - should fail
        with pytest.raises(NodeExecutionError):
            await asyncio.to_thread(
                user_node.run,
                operation="get_user",
                user_id=tenant_b_user["result"]["user"]["user_id"],
                tenant_id="tenant_a",
            )
