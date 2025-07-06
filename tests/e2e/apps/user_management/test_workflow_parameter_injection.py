"""Test workflow parameter injection with user management workflows.

This test demonstrates the recommended approach using workflows with
the new parameter injection feature instead of direct node calls.
"""

import asyncio
import os
from datetime import datetime

import pytest
import pytest_asyncio

from kailash import Workflow, WorkflowBuilder
from kailash.nodes.admin import RoleManagementNode, UserManagementNode
from kailash.nodes.code import PythonCodeNode

# ValidationNode is implemented using PythonCodeNode.from_function() in the test
from kailash.runtime.local import LocalRuntime


class TestWorkflowParameterInjection:
    """Test the new workflow parameter injection with real user management."""

    @pytest_asyncio.fixture
    async def setup_app(self):
        """Setup test application with database."""
        from apps.user_management.main import UserManagementApp

        app = UserManagementApp()
        await app.setup_database()

        yield app

        # Cleanup would go here

    @pytest.mark.asyncio
    async def test_registration_workflow_with_parameter_injection(self, setup_app):
        """Test user registration workflow using parameter injection."""
        app = setup_app
        runtime = LocalRuntime(debug=True)

        # Build registration workflow
        builder = WorkflowBuilder()

        # Add validation node
        def validate_registration(email: str, password: str) -> dict:
            errors = []
            if "@" not in email:
                errors.append("Invalid email format")
            if len(password) < 8:
                errors.append("Password must be at least 8 characters")

            # Create properly structured user_data for UserManagementNode
            user_data = {
                "email": email,
                "password": password,
                "first_name": "Test",
                "last_name": "User",
                "status": "active",
            }

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "user_data": user_data,  # Return structured user_data dict
                "email": email,
                "password": password,
            }

        builder.add_node(
            PythonCodeNode.from_function(validate_registration), "validator"
        )

        # Add user creation node
        builder.add_node(
            UserManagementNode(
                operation="create_user",
                tenant_id="default",
                database_config={
                    "connection_string": app.config.DATABASE_URL,
                    "database_type": "postgresql",
                },
            ),
            "creator",
        )

        # Connect nodes
        builder.connect(
            "validator",
            "creator",
            {"result.user_data": "user_data"},  # Pass the structured user_data dict
        )

        # Define workflow-level parameter mappings
        builder.add_workflow_inputs(
            "validator", {"email": "email", "password": "password"}
        )

        # Special handling for user_data structure
        workflow = builder.build("registration")

        # Execute with simple parameters
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        test_email = f"test_user_{timestamp}@example.com"

        results, _ = runtime.execute(
            workflow,
            parameters={"email": test_email, "password": "secure_password_123"},
        )

        # Verify results
        assert results["validator"]["result"]["valid"] is True
        assert "user" in results["creator"]["result"]
        assert "user" in results["creator"]["result"]
        assert "user_id" in results["creator"]["result"]["user"]
        assert results["creator"]["result"]["user"]["email"] == test_email

    @pytest.mark.asyncio
    async def test_complex_workflow_with_auto_mapping(self, setup_app):
        """Test complex workflow with automatic parameter mapping."""
        app = setup_app

        # Create workflow with multiple nodes
        workflow = Workflow("complex_user_mgmt", "Complex user management")

        # Role creation node
        role_node = RoleManagementNode(
            operation="create_role",
            tenant_id="default",
            database_config={
                "connection_string": app.config.DATABASE_URL,
                "database_type": "postgresql",
            },
        )
        workflow.add_node("role_creator", role_node)

        # Validation node with auto-mapping
        def validate_complex_data(email: str, password: str, role: str) -> dict:
            errors = []

            # Email validation
            if not email or "@" not in email:
                errors.append("Invalid email format")

            # Password validation
            if not password or len(password) < 8:
                errors.append("Password must be at least 8 characters")

            # Role validation
            if not role:
                errors.append("Role is required")

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "validated_data": {"email": email, "password": password, "role": role},
            }

        validation_node = PythonCodeNode.from_function(validate_complex_data)
        workflow.add_node("validator", validation_node)

        # User creation node
        user_node = UserManagementNode(
            operation="create_user",
            tenant_id="default",
            database_config={
                "connection_string": app.config.DATABASE_URL,
                "database_type": "postgresql",
            },
        )
        workflow.add_node("user_creator", user_node)

        # Set up parameter mappings via metadata
        workflow.metadata["_workflow_inputs"] = {
            "role_creator": {"role_name": "role_data"},
            "validator": {"user_data": "data"},  # ValidationNode expects "data"
            "user_creator": {"user_email": "user_data", "user_password": "password"},
        }

        # Execute workflow with mixed parameters
        runtime = LocalRuntime()

        # Execute with parameters that match what the nodes expect
        results, _ = runtime.execute(
            workflow,
            parameters={
                "email": "complex_test@example.com",
                "password": "secure_password_123",
                "role": "test_role",
                "role_name": {"name": "test_role", "description": "Test role"},
                "permissions": ["read", "write"],
            },
        )

        # Then create user with validation
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        user_results, _ = runtime.execute(
            workflow,
            parameters={
                "user_data": {
                    "email": f"validated_user_{timestamp}@example.com",
                    "password": "validated_pass_123",
                    "role": "test_role",
                },
                "user_email": f"validated_user_{timestamp}@example.com",
                "user_password": "validated_pass_123",
            },
        )

        # Verify validation from first execution worked
        assert results.get("validator", {}).get("result", {}).get("valid") is True

        # This test verifies parameter injection works with complex workflows
        print("Complex workflow with auto mapping passed")

    @pytest.mark.asyncio
    async def test_backward_compatibility(self, setup_app):
        """Test that node-specific parameters still work."""
        app = setup_app
        runtime = LocalRuntime()

        # Simple workflow
        workflow = Workflow("backward_compat", "Test backward compatibility")

        user_node = UserManagementNode(
            operation="create_user",
            tenant_id="default",
            database_config={
                "connection_string": app.config.DATABASE_URL,
                "database_type": "postgresql",
            },
        )
        workflow.add_node("creator", user_node)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")

        # Old style: node-specific parameters
        results, _ = runtime.execute(
            workflow,
            parameters={
                "creator": {
                    "user_data": {"email": f"old_style_{timestamp}@example.com"},
                    "password": "old_style_pass",
                }
            },
        )

        assert "user" in results["creator"]["result"]
        assert "user_id" in results["creator"]["result"]["user"]

        # New style: workflow-level parameters (with metadata)
        workflow.metadata["_workflow_inputs"] = {
            "creator": {"email": "user_data", "password": "password"}
        }

        results2, _ = runtime.execute(
            workflow,
            parameters={
                "email": {"email": f"new_style_{timestamp}@example.com"},
                "password": "new_style_pass",
            },
        )

        assert "user" in results2["creator"]["result"]
        assert "user_id" in results2["creator"]["result"]["user"]

        # Mixed style: both types
        results3, _ = runtime.execute(
            workflow,
            parameters={
                "email": {
                    "email": f"ignored_{timestamp}@example.com"
                },  # Will be overridden
                "creator": {
                    "user_data": {"email": f"mixed_style_{timestamp}@example.com"},
                    "password": "mixed_style_pass",
                },
            },
        )

        # Node-specific should win
        assert (
            results3["creator"]["result"]["user"]["email"]
            == f"mixed_style_{timestamp}@example.com"
        )
