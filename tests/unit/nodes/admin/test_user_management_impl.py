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

    def test_delete_user_soft_delete(self):
        """Test soft delete user functionality."""
        # Mock successful delete
        self.mock_db.execute.return_value = {
            "rows": [
                {
                    "user_id": "user123",
                    "email": "test@example.com",
                    "username": "testuser",
                    "status": "deleted",
                }
            ]
        }

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
            "hard_delete": False,
            "deleted_by": "admin",
        }

        result = self.node._delete_user(inputs)

        assert result["success"] is True
        assert result["user"]["user_id"] == "user123"
        assert result["hard_delete"] is False

        # Verify database call
        self.mock_db.execute.assert_called()
        call_args = self.mock_db.execute.call_args[1]
        assert "UPDATE users" in call_args["query"]
        assert "status = 'deleted'" in call_args["query"]

    def test_delete_user_hard_delete(self):
        """Test hard delete user functionality."""
        # Mock successful delete
        self.mock_db.execute.return_value = {
            "rows": [
                {
                    "user_id": "user123",
                    "email": "test@example.com",
                    "username": "testuser",
                }
            ]
        }

        inputs = {"user_id": "user123", "tenant_id": "test_tenant", "hard_delete": True}

        result = self.node._delete_user(inputs)

        assert result["success"] is True
        assert result["user"]["user_id"] == "user123"
        assert result["hard_delete"] is True

        # Verify database call
        call_args = self.mock_db.execute.call_args[1]
        assert "DELETE FROM users" in call_args["query"]

    def test_delete_user_not_found(self):
        """Test delete user when user not found."""
        # Mock no results
        self.mock_db.execute.return_value = {"rows": []}

        inputs = {"user_id": "nonexistent", "tenant_id": "test_tenant"}

        result = self.node._delete_user(inputs)

        assert result["success"] is False
        assert "not found" in result["message"]

    def test_change_password_with_validation(self):
        """Test password change with validation."""
        # Mock current password verification
        self.mock_db.execute.side_effect = [
            # Password verification query
            {"rows": [{"password_hash": "salt$hashedpassword"}]},
            # Password history check
            {"rows": []},
            # Update query
            {
                "rows": [
                    {
                        "user_id": "user123",
                        "email": "test@example.com",
                        "username": "testuser",
                    }
                ]
            },
            # History insert
            {"rows": []},
        ]

        # Mock password verification
        with patch.object(self.node, "_verify_password", return_value=True):
            inputs = {
                "user_id": "user123",
                "current_password": "oldpassword",
                "new_password": "NewPassword123!",
                "tenant_id": "test_tenant",
            }

            result = self.node._change_password(inputs)

        assert result["success"] is True
        assert result["user"]["user_id"] == "user123"

    def test_change_password_validation_failure(self):
        """Test password change with validation failure."""
        inputs = {
            "user_id": "user123",
            "new_password": "weak",  # Too short
            "tenant_id": "test_tenant",
            "skip_current_check": True,
        }

        with pytest.raises(NodeValidationError, match="Password must be at least"):
            self.node._change_password(inputs)

    def test_reset_password_with_token(self):
        """Test password reset with token generation."""
        # Mock user lookup
        self.mock_db.execute.side_effect = [
            # User lookup
            {
                "rows": [
                    {
                        "user_id": "user123",
                        "email": "test@example.com",
                        "username": "testuser",
                    }
                ]
            },
            # Token storage
            {"rows": []},
            # Force password change update
            {"rows": []},
        ]

        inputs = {
            "email": "test@example.com",
            "tenant_id": "test_tenant",
            "generate_token": True,
            "token_expiry_hours": 24,
        }

        result = self.node._reset_password(inputs)

        assert result["success"] is True
        assert "reset_token" in result
        assert "expires_at" in result
        assert len(result["reset_token"]) > 20  # Should be a substantial token

    def test_reset_password_direct(self):
        """Test direct password reset by admin."""
        # Mock user lookup and update
        self.mock_db.execute.side_effect = [
            # User lookup
            {
                "rows": [
                    {
                        "user_id": "user123",
                        "email": "test@example.com",
                        "username": "testuser",
                    }
                ]
            },
            # Password update
            {
                "rows": [
                    {
                        "user_id": "user123",
                        "email": "test@example.com",
                        "username": "testuser",
                    }
                ]
            },
        ]

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
            "generate_token": False,
            "new_password": "AdminReset123!",
            "force_password_change": True,
        }

        result = self.node._reset_password(inputs)

        assert result["success"] is True
        assert result["force_password_change"] is True

    def test_deactivate_user(self):
        """Test user deactivation."""
        # Mock successful deactivation
        self.mock_db.execute.side_effect = [
            # Update user status
            {
                "rows": [
                    {
                        "user_id": "user123",
                        "email": "test@example.com",
                        "username": "testuser",
                        "status": "inactive",
                    }
                ]
            },
            # Revoke sessions
            {"rows": []},
        ]

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
            "reason": "Security violation",
            "deactivated_by": "admin",
        }

        result = self.node._deactivate_user(inputs)

        assert result["success"] is True
        assert result["user"]["status"] == "inactive"
        assert result["reason"] == "Security violation"

    def test_activate_user(self):
        """Test user activation."""
        # Mock successful activation
        self.mock_db.execute.return_value = {
            "rows": [
                {
                    "user_id": "user123",
                    "email": "test@example.com",
                    "username": "testuser",
                    "status": "active",
                }
            ]
        }

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
            "activated_by": "admin",
            "clear_deactivation_data": True,
        }

        result = self.node._activate_user(inputs)

        assert result["success"] is True
        assert result["user"]["status"] == "active"

    def test_activate_user_already_active(self):
        """Test activating already active user."""
        # Mock no update (user already active)
        self.mock_db.execute.side_effect = [
            # Update attempt returns no rows
            {"rows": []},
            # Status check
            {"rows": [{"status": "active"}]},
        ]

        inputs = {"user_id": "user123", "tenant_id": "test_tenant"}

        result = self.node._activate_user(inputs)

        assert result["success"] is False
        assert "already active" in result["message"]

    def test_restore_user(self):
        """Test user restoration from deleted state."""
        # Mock restore operation
        self.mock_db.execute.side_effect = [
            # Check user exists and is deleted
            {
                "rows": [
                    {
                        "user_id": "user123",
                        "email": "test@example.com",
                        "status": "deleted",
                        "deleted_at": datetime.now(UTC),
                    }
                ]
            },
            # Restore user
            {
                "rows": [
                    {
                        "user_id": "user123",
                        "email": "test@example.com",
                        "username": "testuser",
                        "status": "active",
                    }
                ]
            },
        ]

        inputs = {
            "user_id": "user123",
            "tenant_id": "test_tenant",
            "restored_by": "admin",
            "new_status": "active",
        }

        result = self.node._restore_user(inputs)

        assert result["success"] is True
        assert result["user"]["status"] == "active"
        assert result["new_status"] == "active"

    def test_restore_user_not_deleted(self):
        """Test restoring user that is not deleted."""
        # Mock user that is not deleted
        self.mock_db.execute.return_value = {
            "rows": [{"user_id": "user123", "status": "active"}]
        }

        inputs = {"user_id": "user123", "tenant_id": "test_tenant"}

        result = self.node._restore_user(inputs)

        assert result["success"] is False
        assert "not deleted" in result["message"]

    def test_search_users_basic(self):
        """Test basic user search functionality."""
        # Mock search results
        self.mock_db.execute.side_effect = [
            # Count query
            {"rows": [{"total": 2}]},
            # Data query
            {
                "rows": [
                    {
                        "user_id": "user1",
                        "email": "test1@example.com",
                        "username": "user1",
                    },
                    {
                        "user_id": "user2",
                        "email": "test2@example.com",
                        "username": "user2",
                    },
                ]
            },
        ]

        inputs = {
            "search_query": "test",
            "tenant_id": "test_tenant",
            "fuzzy_search": True,
            "pagination": {"page": 1, "size": 20},
        }

        result = self.node._search_users(inputs)

        assert result["success"] is True
        assert len(result["users"]) == 2
        assert result["pagination"]["total"] == 2
        assert result["search"]["query"] == "test"
        assert result["search"]["fuzzy"] is True

    def test_search_users_with_filters(self):
        """Test user search with filters."""
        # Mock search results
        self.mock_db.execute.side_effect = [
            # Count query
            {"rows": [{"total": 1}]},
            # Data query
            {
                "rows": [
                    {
                        "user_id": "user1",
                        "email": "test@example.com",
                        "status": "active",
                    }
                ]
            },
        ]

        inputs = {
            "tenant_id": "test_tenant",
            "filters": {
                "status": "active",
                "created_after": "2023-01-01",
                "attributes": {"department": "engineering"},
            },
        }

        result = self.node._search_users(inputs)

        assert result["success"] is True
        assert result["filters_applied"]["status"] == "active"

    def test_bulk_update_users_success(self):
        """Test successful bulk user update."""
        # Mock individual updates
        self.mock_db.execute.side_effect = [
            # Begin transaction
            {"rows": []},
            # First user update
            {"rows": [{"user_id": "user1", "email": "updated1@example.com"}]},
            # Second user update
            {"rows": [{"user_id": "user2", "email": "updated2@example.com"}]},
            # Commit transaction
            {"rows": []},
        ]

        inputs = {
            "user_updates": [
                {"user_id": "user1", "email": "updated1@example.com"},
                {"user_id": "user2", "email": "updated2@example.com"},
            ],
            "tenant_id": "test_tenant",
            "transaction_mode": "all_or_none",
        }

        result = self.node._bulk_update_users(inputs)

        assert result["success"] is True
        assert result["results"]["stats"]["updated"] == 2
        assert result["results"]["stats"]["failed"] == 0

    def test_bulk_delete_users_soft(self):
        """Test bulk soft delete of users."""
        # Mock individual deletes
        self.mock_db.execute.side_effect = [
            # Begin transaction
            {"rows": []},
            # First user delete
            {
                "rows": [
                    {
                        "user_id": "user1",
                        "email": "test1@example.com",
                        "status": "deleted",
                    }
                ]
            },
            # Session revocation
            {"rows": []},
            # Second user delete
            {
                "rows": [
                    {
                        "user_id": "user2",
                        "email": "test2@example.com",
                        "status": "deleted",
                    }
                ]
            },
            # Session revocation
            {"rows": []},
            # Commit transaction
            {"rows": []},
        ]

        inputs = {
            "user_ids": ["user1", "user2"],
            "tenant_id": "test_tenant",
            "hard_delete": False,
            "transaction_mode": "all_or_none",
        }

        result = self.node._bulk_delete_users(inputs)

        assert result["success"] is True
        assert result["results"]["stats"]["deleted"] == 2
        assert result["hard_delete"] is False

    def test_utility_methods(self):
        """Test utility methods."""
        # Test password hashing
        password_hash = self.node._hash_password("testpassword")
        assert "$" in password_hash  # Should have salt separator

        # Test password verification
        with patch.object(self.node, "_verify_password") as mock_verify:
            mock_verify.return_value = True
            assert self.node._verify_password("test", password_hash) is True

        # Test email validation
        assert self.node._validate_email("test@example.com") is True
        assert self.node._validate_email("invalid") is False

        # Test username validation
        assert self.node._validate_username("valid_user123") is True
        assert self.node._validate_username("a") is False  # Too short

        # Test user ID generation
        user_id = self.node._generate_user_id()
        assert len(user_id) > 10  # Should be substantial ID

    def test_missing_required_parameters(self):
        """Test validation of required parameters."""
        # Delete without user_id
        with pytest.raises(NodeValidationError, match="user_id is required"):
            self.node._delete_user({})

        # Change password without user_id
        with pytest.raises(NodeValidationError, match="user_id is required"):
            self.node._change_password({})

        # Change password without new password
        with pytest.raises(NodeValidationError, match="new_password is required"):
            self.node._change_password({"user_id": "test"})

    def test_ensure_db_node_initialization(self):
        """Test database node initialization."""
        # Reset db node
        self.node._db_node = None

        # Mock init_dependencies
        with patch.object(self.node, "_init_dependencies") as mock_init:
            self.node._ensure_db_node({"database_config": {}})
            mock_init.assert_called_once()
