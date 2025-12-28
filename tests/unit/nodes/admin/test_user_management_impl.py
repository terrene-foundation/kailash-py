"""Test UserManagementNode implementations."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.admin.user_management import (
    UserManagementNode,
    UserOperation,
    UserStatus,
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestUserManagementImplementations:
    """Test the implemented methods in UserManagementNode."""

    def setup_method(self):
        """Setup for each test method."""
        self.node = UserManagementNode()
        # Mock the database node
        self.mock_db = Mock()
        self.node._db_node = self.mock_db

        # Set up default user response for most tests
        self.default_user = {
            "user_id": "user123",
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "display_name": "Test User",
            "status": "active",
            "roles": [],
            "attributes": {},
            "metadata": {},
            "tenant_id": "test_tenant",
            "external_auth_id": None,
            "auth_provider": "local",
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            "updated_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            "last_login_at": None,
        }
        # Default to returning a user for get operations
        self.mock_db.execute.return_value = {"data": [self.default_user]}

    def test_delete_user_soft_delete(self):
        """Test soft delete user functionality."""
        # Default mock already returns a user

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
            "hard_delete": False,
            "deleted_by": "admin",
        }

        result = self.node._delete_user(inputs)

        assert "result" in result
        assert result["result"]["deleted_user"]["user_id"] == "user123"
        assert result["result"]["hard_delete"] is False

        # Verify database calls
        assert self.mock_db.execute.call_count >= 2  # At least get user and update
        # Check that UPDATE was called
        update_call = None
        for call in self.mock_db.execute.call_args_list:
            if "UPDATE users" in str(call):
                update_call = call
                break
        assert update_call is not None

    def test_delete_user_hard_delete(self):
        """Test hard delete user functionality."""
        # Mock successful delete - use the same complete user data as default
        self.mock_db.execute.return_value = {"data": [self.default_user]}

        inputs = {"user_id": "user123", "tenant_id": "test_tenant", "hard_delete": True}

        result = self.node._delete_user(inputs)

        assert "result" in result
        assert result["result"]["deleted_user"]["user_id"] == "user123"
        assert result["result"]["hard_delete"] is True

        # Verify database calls
        assert self.mock_db.execute.call_count >= 2  # At least get user and delete

    def test_delete_user_not_found(self):
        """Test delete user when user not found."""
        # Mock no results
        self.mock_db.execute.return_value = {"data": []}

        inputs = {"user_id": "nonexistent", "tenant_id": "test_tenant"}

        from kailash.sdk_exceptions import NodeValidationError

        with pytest.raises(NodeValidationError, match="User not found"):
            self.node._delete_user(inputs)

    def test_set_password(self):
        """Test setting user password."""
        inputs = {
            "user_id": "user123",
            "password_hash": "hashed_password_value",
            "tenant_id": "test_tenant",
        }

        result = self.node._set_password(inputs)

        assert "result" in result
        assert result["result"]["user_id"] == "user123"
        assert result["result"]["password_updated"] is True
        assert result["result"]["operation"] == "set_password"

    def test_deactivate_user(self):
        """Test user deactivation."""
        # Mock successful deactivation
        self.mock_db.execute.side_effect = [
            # Update user status
            {"data": []},
            # Get updated user
            {"data": [{**self.default_user, "status": "inactive"}]},
        ]

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
        }

        result = self.node._deactivate_user(inputs)

        assert "result" in result
        assert result["result"]["user"]["status"] == "inactive"
        assert result["result"]["operation"] == "deactivate_user"

    def test_activate_user(self):
        """Test user activation."""
        # Mock successful activation
        self.mock_db.execute.side_effect = [
            # Update user status
            {"data": []},
            # Get updated user
            {"data": [self.default_user]},
        ]

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
        }

        result = self.node._activate_user(inputs)

        assert "result" in result
        assert result["result"]["user"]["status"] == "active"
        assert result["result"]["operation"] == "activate_user"

    def test_get_user_roles(self):
        """Test getting user roles."""
        # Mock user with roles
        user_with_roles = {**self.default_user, "roles": ["admin", "editor"]}

        # First mock is for _get_user_by_id, second is for role details
        self.mock_db.execute.side_effect = [
            # Get user by id
            {"data": [user_with_roles]},
            # Get role details
            {
                "data": [
                    {
                        "role_id": "admin",
                        "name": "Administrator",
                        "description": "Admin role",
                    },
                    {
                        "role_id": "editor",
                        "name": "Editor",
                        "description": "Editor role",
                    },
                ]
            },
        ]

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
        }

        result = self.node._get_user_roles(inputs)

        assert "result" in result
        assert result["result"]["user_id"] == "user123"
        assert result["result"]["operation"] == "get_user_roles"
        # The roles come from the user data, and role_details from the query
        assert "roles" in result["result"]
        assert "role_details" in result["result"]

    def test_update_profile(self):
        """Test update profile (uses update_user internally)."""
        # Mock getting existing user
        self.mock_db.execute.side_effect = [
            # Get existing user
            {"data": [self.default_user]},
            # Update query
            {"data": []},
            # Get updated user
            {
                "data": [
                    {**self.default_user, "first_name": "Updated", "last_name": "Name"}
                ]
            },
        ]

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
            "user_data": {
                "first_name": "Updated",
                "last_name": "Name",
            },
        }

        result = self.node._update_profile(inputs)

        assert "result" in result
        assert result["result"]["user"]["first_name"] == "Updated"
        assert result["result"]["user"]["last_name"] == "Name"
        assert result["result"]["operation"] == "update_profile"

    def test_get_user_permissions(self):
        """Test getting user permissions."""
        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
        }

        result = self.node._get_user_permissions(inputs)

        assert "result" in result
        assert result["result"]["user_id"] == "user123"
        assert result["result"]["operation"] == "get_user_permissions"
        assert "roles" in result["result"]
        assert "attributes" in result["result"]
        # This method returns a note about using PermissionCheckNode
        assert "note" in result["result"]

    def test_bulk_update(self):
        """Test bulk user update."""
        # Mock bulk update results
        inputs = {
            "users_data": [
                {"user_id": "user1", "email": "updated1@example.com"},
                {"user_id": "user2", "email": "updated2@example.com"},
            ],
            "tenant_id": "test_tenant",
            "database_config": {},  # Provided to match expected inputs
        }

        # Mock individual update calls
        with patch.object(self.node, "_update_user") as mock_update:
            mock_update.side_effect = [
                {"result": {"user": {"user_id": "user1"}, "operation": "update_user"}},
                {"result": {"user": {"user_id": "user2"}, "operation": "update_user"}},
            ]

            result = self.node._bulk_update(inputs)

        assert "result" in result
        assert result["result"]["bulk_result"]["updated_count"] == 2
        assert result["result"]["bulk_result"]["failed_count"] == 0

    def test_bulk_delete(self):
        """Test bulk delete of users."""
        # Mock bulk delete
        inputs = {
            "user_ids": ["user1", "user2"],
            "tenant_id": "test_tenant",
            "hard_delete": False,
            "database_config": {},  # Provided to match expected inputs
        }

        # Mock individual delete calls
        with patch.object(self.node, "_delete_user") as mock_delete:
            mock_delete.side_effect = [
                {
                    "result": {
                        "deleted_user": {"user_id": "user1"},
                        "hard_delete": False,
                    }
                },
                {
                    "result": {
                        "deleted_user": {"user_id": "user2"},
                        "hard_delete": False,
                    }
                },
            ]

            result = self.node._bulk_delete(inputs)

        assert "result" in result
        assert result["result"]["bulk_result"]["deleted_count"] == 2
        assert result["result"]["bulk_result"]["failed_count"] == 0

    def test_bulk_create(self):
        """Test bulk user creation."""
        inputs = {
            "users_data": [
                {
                    "email": "user1@example.com",
                    "username": "user1",
                    "first_name": "User",
                    "last_name": "One",
                },
                {
                    "email": "user2@example.com",
                    "username": "user2",
                    "first_name": "User",
                    "last_name": "Two",
                },
            ],
            "tenant_id": "test_tenant",
            "database_config": {},  # Provided to match expected inputs
        }

        # Mock individual create calls
        with patch.object(self.node, "_create_user") as mock_create:
            mock_create.side_effect = [
                {
                    "result": {
                        "user": {"user_id": "new_user1", "email": "user1@example.com"}
                    }
                },
                {
                    "result": {
                        "user": {"user_id": "new_user2", "email": "user2@example.com"}
                    }
                },
            ]

            result = self.node._bulk_create(inputs)

        assert "result" in result
        assert result["result"]["bulk_result"]["created_count"] == 2
        assert result["result"]["bulk_result"]["failed_count"] == 0

    def test_missing_required_parameters(self):
        """Test validation of required parameters."""
        # Delete without user_id
        with pytest.raises(KeyError):
            self.node._delete_user({})

        # Set password without user_id
        with pytest.raises(KeyError):
            self.node._set_password({})
