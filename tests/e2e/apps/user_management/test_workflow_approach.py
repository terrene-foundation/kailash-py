"""
Test user management using the recommended workflow approach with parameter injection.
This complements the direct node tests by showing best practices.
"""

import asyncio
import time
from datetime import datetime

import pytest
import pytest_asyncio

from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.user_management import UserManagementNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder
from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestWorkflowApproach:
    """Test user management using workflow patterns (recommended approach)."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_environment(self):
        """Set up test environment."""
        # Ensure Docker services are running
        services_ok = await ensure_docker_services()
        if not services_ok:
            pytest.skip("Docker services not available")

        self.db_url = get_postgres_connection_string()
        self.tenant_id = "test_workflow"
        self.runtime = LocalRuntime(debug=True)

        # Setup database schema
        await self._setup_database()

    async def _setup_database(self):
        """Initialize database schema."""
        # Import the app to set up database
        import sys

        sys.path.append("apps/user_management")
        from apps.user_management.main import UserManagementApp

        app = UserManagementApp()
        app.config.DATABASE_URL = self.db_url

        print("Setting up database schema...")
        await app.setup_database()
        print("Database schema created successfully")

    def _build_user_registration_workflow(self) -> Workflow:
        """Build a user registration workflow with validation."""
        builder = WorkflowBuilder()

        # Validation node
        def validate_user(email: str, password: str, role: str = "user") -> dict:
            errors = []
            if "@" not in email:
                errors.append("Invalid email format")
            if len(password) < 8:
                errors.append("Password too short")
            if role not in ["admin", "user", "moderator"]:
                errors.append(f"Invalid role: {role}")

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "user_data": {
                    "email": email,
                    "username": email.split("@")[0],  # Extract username from email
                    "status": "active",
                },
                "role": role,
            }

        # Add nodes
        builder.add_node(PythonCodeNode.from_function(validate_user), "validator")

        builder.add_node(
            UserManagementNode(
                operation="create_user",
                tenant_id=self.tenant_id,
                database_config={
                    "connection_string": self.db_url,
                    "database_type": "postgresql",
                },
            ),
            "creator",
        )

        # Connect nodes - validator passes user_data dict to creator
        builder.connect("validator", "creator", {"result.user_data": "user_data"})

        # Define workflow input mappings
        builder.add_workflow_inputs(
            "validator", {"email": "email", "password": "password", "role": "role"}
        )

        builder.add_workflow_inputs("creator", {"password": "password"})

        return builder.build("user_registration")

    def _build_role_workflow(self) -> Workflow:
        """Build workflow for role management."""
        workflow = Workflow("role_management", "Manage roles and permissions")

        # Role creation node
        workflow.add_node(
            "role_creator",
            RoleManagementNode(
                operation="create_role",
                tenant_id=self.tenant_id,
                database_config={
                    "connection_string": self.db_url,
                    "database_type": "postgresql",
                },
            ),
        )

        # Add permission assignment node
        def assign_permissions(role_result: dict, permissions: list) -> dict:
            if role_result.get("success"):
                return {
                    "role_id": role_result["role"]["role_id"],
                    "permissions": permissions,
                    "assigned": True,
                }
            return {"assigned": False, "error": "Role creation failed"}

        workflow.add_node(
            "permission_assigner", PythonCodeNode.from_function(assign_permissions)
        )

        # Connect nodes
        workflow.connect(
            "role_creator", "permission_assigner", {"result": "role_result"}
        )

        # Set up parameter mappings
        workflow.metadata["_workflow_inputs"] = {
            "role_creator": {"role_name": "role_data", "permissions": "permissions"},
            "permission_assigner": {"permissions": "permissions"},
        }

        return workflow

    def _build_user_search_workflow(self) -> Workflow:
        """Build workflow for user search with filtering."""
        builder = WorkflowBuilder()

        # Search node
        builder.add_node(
            UserManagementNode(
                operation="search_users",
                tenant_id=self.tenant_id,
                database_config={
                    "connection_string": self.db_url,
                    "database_type": "postgresql",
                },
            ),
            "searcher",
        )

        # Filter node
        def filter_results(users: list, min_created_date: str = None) -> dict:
            if min_created_date:
                filtered = [
                    u for u in users if u.get("created_at", "") >= min_created_date
                ]
            else:
                filtered = users

            return {
                "users": filtered,
                "count": len(filtered),
                "filtered": min_created_date is not None,
            }

        builder.add_node(PythonCodeNode.from_function(filter_results), "filter")

        # Connect nodes
        builder.connect("searcher", "filter", {"result.users": "users"})

        # Parameter mappings
        builder.add_workflow_inputs(
            "searcher", {"search_query": "search_query", "filters": "filters"}
        )

        builder.add_workflow_inputs("filter", {"min_created_date": "min_created_date"})

        return builder.build("user_search")

    @pytest.mark.asyncio
    async def test_user_registration_workflow(self):
        """Test user registration using workflow approach."""
        workflow = self._build_user_registration_workflow()

        # Test valid registration
        timestamp = str(int(time.time()))
        results, _ = self.runtime.execute(
            workflow,
            parameters={
                "email": f"workflow_user_{timestamp}@example.com",
                "password": "secure_password_123",
                "role": "user",
            },
        )

        # Check validation passed
        assert results["validator"]["result"]["valid"] is True
        assert len(results["validator"]["result"]["errors"]) == 0

        # Check user created - handle both error and success cases
        if "error" in results["creator"]:
            print(f"Creator error: {results['creator']['error']}")
            assert False, f"User creation failed: {results['creator']['error']}"

        # The node returns result.user with the user data
        assert "result" in results["creator"]
        assert "user" in results["creator"]["result"]
        assert "user_id" in results["creator"]["result"]["user"]
        assert (
            results["creator"]["result"]["user"]["email"]
            == f"workflow_user_{timestamp}@example.com"
        )

        print(
            f"✓ Created user via workflow: {results['creator']['result']['user']['user_id']}"
        )

        # Test invalid registration
        results2, _ = self.runtime.execute(
            workflow,
            parameters={
                "email": "invalid-email",
                "password": "short",
                "role": "invalid_role",
            },
        )

        # Check validation failed
        assert results2["validator"]["result"]["valid"] is False
        assert len(results2["validator"]["result"]["errors"]) == 3

        print("✓ Validation correctly rejected invalid input")

    @pytest.mark.asyncio
    async def test_role_creation_workflow(self):
        """Test role creation and permission assignment workflow."""
        workflow = self._build_role_workflow()

        timestamp = str(int(time.time()))
        role_name = f"test_role_{timestamp}"

        results, _ = self.runtime.execute(
            workflow,
            parameters={
                "role_name": {
                    "name": role_name,
                    "description": "Test role created via workflow",
                },
                "permissions": ["users.read", "users.write", "reports.view"],
            },
        )

        # Check role created
        assert results["role_creator"]["result"]["success"] is True
        assert results["role_creator"]["result"]["role"]["name"] == role_name

        # Check permissions assigned
        assert results["permission_assigner"]["result"]["assigned"] is True
        assert len(results["permission_assigner"]["result"]["permissions"]) == 3

        print(f"✓ Created role with permissions: {role_name}")

    @pytest.mark.asyncio
    async def test_user_search_workflow(self):
        """Test user search with filtering workflow."""
        # First create some users
        registration_workflow = self._build_user_registration_workflow()
        base_time = str(int(time.time()))

        for i in range(5):
            self.runtime.execute(
                registration_workflow,
                parameters={
                    "email": f"search_test_{base_time}_{i}@example.com",
                    "password": "test_password_123",
                    "role": "user",
                },
            )

        # Now search for them
        search_workflow = self._build_user_search_workflow()

        results, _ = self.runtime.execute(
            search_workflow,
            parameters={
                "search_query": f"search_test_{base_time}",
                "filters": {"status": "active"},
                "min_created_date": datetime.now().strftime("%Y-%m-%d"),
            },
        )

        # Check search results
        assert results["filter"]["result"]["count"] >= 5
        assert results["filter"]["result"]["filtered"] is True

        print(
            f"✓ Found {results['filter']['result']['count']} users via workflow search"
        )

    @pytest.mark.asyncio
    async def test_complex_workflow_with_branches(self):
        """Test a complex workflow with conditional branches."""
        builder = WorkflowBuilder()

        # User validator
        def validate_admin(email: str, admin_code: str) -> dict:
            is_admin = admin_code == "ADMIN2024"
            return {
                "email": email,
                "is_admin": is_admin,
                "validation": "admin" if is_admin else "user",
            }

        builder.add_node(PythonCodeNode.from_function(validate_admin), "admin_check")

        # Admin creation path
        builder.add_node(
            UserManagementNode(
                operation="create_user",
                tenant_id=self.tenant_id,
                database_config={
                    "connection_string": self.db_url,
                    "database_type": "postgresql",
                },
            ),
            "admin_creator",
        )

        # Regular user path
        builder.add_node(
            UserManagementNode(
                operation="create_user",
                tenant_id=self.tenant_id,
                database_config={
                    "connection_string": self.db_url,
                    "database_type": "postgresql",
                },
            ),
            "user_creator",
        )

        # Conditional routing (simplified - both paths execute)
        builder.connect("admin_check", "admin_creator", {"result.email": "user_data"})

        builder.connect("admin_check", "user_creator", {"result.email": "user_data"})

        # Workflow inputs
        builder.add_workflow_inputs(
            "admin_check", {"email": "email", "admin_code": "admin_code"}
        )

        builder.add_workflow_inputs("admin_creator", {"password": "password"})

        builder.add_workflow_inputs("user_creator", {"password": "password"})

        workflow = builder.build("conditional_registration")

        # Test admin path
        timestamp = str(int(time.time()))
        results, _ = self.runtime.execute(
            workflow,
            parameters={
                "email": f"admin_{timestamp}@example.com",
                "password": "admin_password_123",
                "admin_code": "ADMIN2024",
            },
        )

        assert results["admin_check"]["result"]["is_admin"] is True

        # Both nodes execute in this simple example
        if "admin_creator" in results and "result" in results["admin_creator"]:
            print(
                f"✓ Admin user created: {results['admin_creator']['result'].get('user_id')}"
            )

    @pytest.mark.asyncio
    async def test_workflow_parameter_precedence(self):
        """Test parameter precedence in workflows."""
        workflow = self._build_user_registration_workflow()

        timestamp = str(int(time.time()))

        # Test with both workflow-level and node-specific parameters
        results, _ = self.runtime.execute(
            workflow,
            parameters={
                # Workflow-level parameters
                "email": f"precedence_test_{timestamp}@example.com",
                "password": "workflow_level_pass",
                "role": "user",
                # Node-specific override (should take precedence)
                "validator": {
                    "role": "admin"  # This should override the workflow-level "user"
                },
            },
        )

        # The validator should use the overridden role
        assert results["validator"]["result"]["role"] == "admin"

        print("✓ Parameter precedence working correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
