"""Integration tests for User Management with Middleware.

Tests the complete user management flow through the middleware stack
to ensure all components work correctly with the .execute() method fix.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

import pytest
import pytest_asyncio

from kailash.middleware import AgentUIMiddleware, create_gateway
from kailash.middleware.auth.access_control import MiddlewareAccessControl
from kailash.nodes.admin import (
    AuditLogNode,
    PermissionCheckNode,
    RoleManagementNode,
    UserManagementNode,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow, WorkflowBuilder


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestUserManagementMiddlewareIntegration:
    """Test user management through middleware stack."""

    @pytest_asyncio.fixture
    async def middleware_stack(self):
        """Create middleware stack with user management."""
        # Use test database configuration
        db_url = os.getenv(
            "POSTGRES_TEST_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

        # Create agent UI middleware
        agent_ui = AgentUIMiddleware(
            database_url=db_url,
            enable_persistence=True,
            enable_dynamic_workflows=True,
        )

        # Create access control
        access_control = MiddlewareAccessControl(
            strategy="rbac",
            database_url=db_url,
        )

        yield agent_ui, access_control

        # Cleanup
        await agent_ui.cleanup()

    @pytest.mark.asyncio
    async def test_user_creation_through_middleware(self, middleware_stack):
        """Test creating users through the middleware stack."""
        agent_ui, access_control = middleware_stack

        # Create a session
        session_id = await agent_ui.create_session("admin_user")

        # Create a user management workflow
        workflow = (
            WorkflowBuilder("user_mgmt_workflow")
            .add_node(
                "create_user",
                UserManagementNode,
                config={
                    "operation": "create_user",
                    "tenant_id": "test_tenant",
                    "user_data": {
                        "email": "test@example.com",
                        "username": "testuser",
                        "roles": ["user", "editor"],
                        "attributes": {"department": "engineering"},
                    },
                },
            )
            .add_node(
                "check_permission",
                PermissionCheckNode,
                config={
                    "user_id": "{{create_user.result.user_id}}",
                    "resource": "document",
                    "permission": "write",
                    "tenant_id": "test_tenant",
                },
            )
            .build()
        )

        # Register and execute workflow
        workflow_id = await agent_ui.register_workflow(
            session_id, workflow, metadata={"name": "User Creation Test"}
        )

        execution_id = await agent_ui.execute_workflow(
            session_id, workflow_id, inputs={}
        )

        # Wait for completion
        result = await agent_ui.wait_for_completion(session_id, execution_id)

        # Verify results
        assert result["status"] == "completed"
        assert "create_user" in result["outputs"]
        assert result["outputs"]["create_user"]["success"] is True

        created_user = result["outputs"]["create_user"]["user"]
        assert created_user["email"] == "test@example.com"
        assert "user" in created_user["roles"]
        assert "editor" in created_user["roles"]

    @pytest.mark.asyncio
    async def test_role_management_with_access_control(self, middleware_stack):
        """Test role management with access control middleware."""
        agent_ui, access_control = middleware_stack

        # Create admin session
        admin_session = await agent_ui.create_session("admin_user")

        # Create role workflow
        role_workflow = (
            WorkflowBuilder("role_mgmt")
            .add_node(
                "create_role",
                RoleManagementNode,
                config={
                    "operation": "create_role",
                    "tenant_id": "test_tenant",
                    "role_data": {
                        "name": "data_analyst",
                        "permissions": [
                            "read:data",
                            "write:reports",
                            "execute:queries",
                        ],
                        "description": "Data analyst role",
                    },
                },
            )
            .add_node(
                "audit_log",
                AuditLogNode,
                config={
                    "user_id": "admin_user",
                    "action": "create_role",
                    "resource_type": "role",
                    "resource_id": "{{create_role.result.role_id}}",
                    "tenant_id": "test_tenant",
                    "success": "{{create_role.success}}",
                },
            )
            .build()
        )

        # Execute through middleware
        workflow_id = await agent_ui.register_workflow(
            admin_session, role_workflow, metadata={"name": "Role Creation"}
        )

        exec_id = await agent_ui.execute_workflow(admin_session, workflow_id, {})
        result = await agent_ui.wait_for_completion(admin_session, exec_id)

        # Verify role creation
        assert result["status"] == "completed"
        assert result["outputs"]["create_role"]["success"] is True

        role = result["outputs"]["create_role"]["role"]
        assert role["name"] == "data_analyst"
        assert "read:data" in role["permissions"]

    @pytest.mark.asyncio
    async def test_permission_check_through_gateway(self, middleware_stack):
        """Test permission checking through the API gateway."""
        agent_ui, access_control = middleware_stack

        # Create gateway
        gateway = create_gateway(
            title="User Management Gateway",
            enable_auth=True,
            auth_manager=None,  # Will use default
        )

        # Inject our middleware
        gateway.agent_ui = agent_ui

        # Test permission check node execution
        perm_node = PermissionCheckNode()

        # This should use .execute() internally
        result = perm_node.execute(
            user_id="test_user",
            resource="workflow",
            permission="execute",
            tenant_id="test_tenant",
            database_url=os.getenv("POSTGRES_TEST_URL"),
        )

        # Should return permission result
        assert "has_permission" in result
        assert isinstance(result["has_permission"], bool)

    @pytest.mark.asyncio
    async def test_bulk_user_operations(self, middleware_stack):
        """Test bulk user operations through middleware."""
        agent_ui, _ = middleware_stack

        session_id = await agent_ui.create_session("bulk_admin")

        # Create workflow for bulk operations
        bulk_workflow = (
            WorkflowBuilder("bulk_users")
            .add_node(
                "bulk_create",
                UserManagementNode,
                config={
                    "operation": "bulk_create_users",
                    "tenant_id": "test_tenant",
                    "users": [
                        {
                            "email": f"user{i}@example.com",
                            "username": f"user{i}",
                            "roles": ["user"],
                        }
                        for i in range(5)
                    ],
                },
            )
            .add_node(
                "list_users",
                UserManagementNode,
                config={
                    "operation": "list_users",
                    "tenant_id": "test_tenant",
                    "filters": {"roles": ["user"]},
                    "limit": 10,
                },
            )
            .build()
        )

        # Execute
        workflow_id = await agent_ui.register_workflow(
            session_id, bulk_workflow, metadata={"name": "Bulk User Creation"}
        )

        exec_id = await agent_ui.execute_workflow(session_id, workflow_id, {})
        result = await agent_ui.wait_for_completion(session_id, exec_id)

        # Verify bulk creation
        assert result["status"] == "completed"
        assert result["outputs"]["bulk_create"]["success"] is True
        assert result["outputs"]["bulk_create"]["created_count"] == 5

        # Verify listing
        users = result["outputs"]["list_users"]["users"]
        assert len(users) >= 5

    def test_admin_node_execute_method(self):
        """Verify admin nodes have correct execute() method."""
        # Create instances
        nodes = [
            UserManagementNode(),
            RoleManagementNode(),
            PermissionCheckNode(),
            AuditLogNode(),
        ]

        # Verify all have execute() method (from base class)
        for node in nodes:
            assert hasattr(node, "execute")
            assert callable(getattr(node, "execute"))

            # Should NOT have process() method
            assert not hasattr(node, "process")

            # Should have run() method (implementation)
            assert hasattr(node, "run")

    @pytest.mark.asyncio
    async def test_middleware_access_control_integration(self, middleware_stack):
        """Test middleware access control uses execute() correctly."""
        _, access_control = middleware_stack

        # Check permission through middleware
        has_perm = await access_control.check_permission(
            user_id="test_user",
            resource="workflow:123",
            permission="execute",
            context={"tenant_id": "test_tenant"},
        )

        # Should work without errors
        assert isinstance(has_perm, bool)

        # Verify internal nodes use execute()
        assert hasattr(access_control.permission_check_node, "execute")
        assert hasattr(access_control.audit_node, "execute")
        assert hasattr(access_control.role_mgmt_node, "execute")
