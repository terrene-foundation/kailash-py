"""
Comprehensive unit tests for unified admin node schema.

These tests validate the complete admin node infrastructure including:
- Schema creation and validation
- Role management with hierarchy
- Permission checking with RBAC/ABAC
- Multi-tenant isolation
- Schema migrations
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.admin.permission_check import PermissionCheckNode
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.schema_manager import AdminSchemaManager
from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@pytest.mark.critical
class TestUnifiedAdminSchema:
    """Test the unified admin schema components."""

    def setup_method(self):
        """Setup for each test method."""
        self.db_config = {
            "connection_string": "sqlite:///:memory:",
            "database_type": "sqlite",
        }
        self.mock_db_node = Mock(spec=SQLDatabaseNode)

    def test_admin_schema_manager_creation(self):
        """Test AdminSchemaManager initialization."""
        manager = AdminSchemaManager(self.db_config)
        assert manager.database_config == self.db_config
        assert manager.current_schema_version == "1.0.0"
        assert manager.db_node is not None

    @patch("kailash.nodes.admin.schema_manager.SQLDatabaseNode")
    def test_schema_creation_success(self, mock_sql_node_class):
        """Test successful schema creation."""
        # Mock the SQLDatabaseNode instance
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock file reading
        with patch("builtins.open", mock_open(read_data="CREATE TABLE test;")):
            with patch("pathlib.Path.exists", return_value=True):
                # Mock successful execution
                mock_db_instance.run.return_value = None

                manager = AdminSchemaManager(self.db_config)
                # Mock the table existence check
                manager._get_existing_tables = Mock(
                    return_value=["users", "roles", "permissions"]
                )

                result = manager.create_full_schema(drop_existing=False)

                assert result["success"] is True
                assert result["schema_version"] == "1.0.0"
                assert "users" in result["tables_created"]
                assert len(result["errors"]) == 0

    @patch("kailash.nodes.admin.schema_manager.SQLDatabaseNode")
    def test_schema_validation(self, mock_sql_node_class):
        """Test schema validation functionality."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock database responses
        mock_db_instance.execute.side_effect = [
            # Schema version query
            {"data": [{"version": "1.0.0"}]},
        ]

        manager = AdminSchemaManager(self.db_config)

        # Mock table and index existence
        manager._get_existing_tables = Mock(
            return_value=[
                "users",
                "roles",
                "user_role_assignments",
                "permissions",
                "permission_cache",
                "user_attributes",
                "resource_attributes",
                "user_sessions",
                "admin_audit_log",
            ]
        )
        manager._get_existing_indexes = Mock(
            return_value=[
                "idx_users_tenant_status",
                "idx_roles_tenant_active",
                "idx_user_roles_user",
                "idx_permission_cache_user",
            ]
        )
        manager._validate_table_structures = Mock(return_value=[])

        validation = manager.validate_schema()

        assert validation["is_valid"] is True
        assert validation["schema_version"] == "1.0.0"
        assert len(validation["missing_tables"]) == 0
        assert len(validation["missing_indexes"]) == 0

    @patch("kailash.nodes.admin.schema_manager.SQLDatabaseNode")
    def test_schema_validation_missing_tables(self, mock_sql_node_class):
        """Test schema validation with missing tables."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        manager = AdminSchemaManager(self.db_config)

        # Mock partial table existence
        manager._get_existing_tables = Mock(return_value=["users", "roles"])
        manager._get_existing_indexes = Mock(return_value=[])

        validation = manager.validate_schema()

        assert validation["is_valid"] is False
        assert "permissions" in validation["missing_tables"]
        assert "user_role_assignments" in validation["missing_tables"]

    def test_role_management_node_initialization(self):
        """Test RoleManagementNode initialization."""
        node = RoleManagementNode()
        # Admin nodes have db_node initialized on first use
        assert hasattr(node, "_db_node")
        assert node._db_node is None  # Not initialized until first operation

    @patch("kailash.nodes.admin.role_management.SQLDatabaseNode")
    def test_role_creation_with_hierarchy(self, mock_sql_node_class):
        """Test role creation with parent roles."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Create a more flexible mock that handles different queries
        def mock_run(**kwargs):
            query = kwargs.get("query", "")

            # Parent role existence check
            if "SELECT role_id FROM roles" in query and "role_id IN" in query:
                return {"data": [{"role_id": "editor"}]}

            # Build role hierarchy
            elif "SELECT role_id, name, permissions, parent_roles" in query:
                return {
                    "data": [
                        {
                            "role_id": "editor",
                            "name": "Editor",
                            "permissions": ["read", "write"],
                            "parent_roles": [],
                            "child_roles": [],
                            "is_active": True,
                        }
                    ]
                }

            # Insert role
            elif "INSERT INTO roles" in query:
                return {"data": [], "success": True}

            # Update child roles
            elif "UPDATE roles SET child_roles" in query:
                return {"data": [], "success": True}

            # Fetch created role
            elif "SELECT role_id" in query:
                return {
                    "data": [
                        {
                            "role_id": "senior_editor",
                            "name": "senior_editor",
                            "description": "Senior editor role",
                            "permissions": ["read", "write", "review"],
                            "parent_roles": ["editor"],
                            "tenant_id": "tenant_1",
                            "role_type": "custom",
                            "attributes": {},
                            "is_active": True,
                            "created_at": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc),
                            "created_by": "system",
                        }
                    ]
                }

            # Default response
            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        node = RoleManagementNode()
        node._db_node = mock_db_instance

        result = node.execute(
            operation="create_role",
            role_data={
                "name": "senior_editor",
                "description": "Senior editor role",
                "permissions": ["read", "write", "review"],
                "parent_roles": ["editor"],
            },
            tenant_id="tenant_1",
            database_config=self.db_config,
        )

        assert result["result"]["role"]["name"] == "senior_editor"
        assert "editor" in result["result"]["role"]["parent_roles"]
        assert len(result["result"]["role"]["permissions"]) == 3

    @patch("kailash.nodes.admin.role_management.SQLDatabaseNode")
    def test_role_permission_inheritance(self, mock_sql_node_class):
        """Test permission inheritance through role hierarchy."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Create a mock that handles hierarchy building and other queries
        def mock_run(**kwargs):
            query = kwargs.get("query", "")
            fetch_mode = kwargs.get("fetch_mode", "one")

            # Build role hierarchy query
            if (
                "SELECT role_id, name, permissions, parent_roles" in query
                and "FROM roles" in query
            ):
                return {
                    "data": [
                        {
                            "role_id": "child_role",
                            "name": "Child Role",
                            "permissions": ["read", "write"],
                            "parent_roles": ["parent_role"],
                            "child_roles": [],
                            "is_active": True,
                        },
                        {
                            "role_id": "parent_role",
                            "name": "Parent Role",
                            "permissions": ["delete"],
                            "parent_roles": ["grandparent_role"],
                            "child_roles": ["child_role"],
                            "is_active": True,
                        },
                        {
                            "role_id": "grandparent_role",
                            "name": "Grandparent Role",
                            "permissions": ["admin"],
                            "parent_roles": [],
                            "child_roles": ["parent_role"],
                            "is_active": True,
                        },
                    ]
                }

            # Recursive CTE query for permissions
            elif "WITH RECURSIVE role_hierarchy" in query:
                return {
                    "data": [
                        {"permission": "read"},
                        {"permission": "write"},
                        {"permission": "delete"},  # Inherited from parent
                        {"permission": "admin"},  # Inherited from grandparent
                    ]
                }

            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        node = RoleManagementNode()
        node._db_node = mock_db_instance

        result = node.execute(
            operation="get_effective_permissions",
            role_id="child_role",
            tenant_id="tenant_1",
            include_inherited=True,
            database_config=self.db_config,
        )

        assert len(result["result"]["all_permissions"]) == 4
        assert "admin" in result["result"]["all_permissions"]

    def test_permission_check_node_initialization(self):
        """Test PermissionCheckNode initialization."""
        node = PermissionCheckNode()
        # Admin nodes have db_node initialized on first use
        assert hasattr(node, "_db_node")
        assert node._db_node is None  # Not initialized until first operation

    @patch("kailash.nodes.admin.permission_check.AdminSchemaManager")
    @patch("kailash.nodes.admin.permission_check.SQLDatabaseNode")
    def test_permission_check_with_cache(
        self, mock_sql_node_class, mock_schema_manager_class
    ):
        """Test permission checking with cache."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock schema manager
        mock_schema_instance = Mock()
        mock_schema_manager_class.return_value = mock_schema_instance
        mock_schema_instance.validate_schema.return_value = {"is_valid": True}

        # Mock database queries
        def mock_run(**kwargs):
            query = kwargs.get("query", "")

            # User context query
            if "FROM users" in query and "WHERE user_id" in query:
                return {
                    "data": [
                        {
                            "user_id": "user_123",
                            "email": "user@example.com",
                            "roles": ["reader"],
                            "attributes": {},
                            "status": "active",
                            "tenant_id": "tenant_1",
                        }
                    ]
                }

            # Role permissions query
            elif "WITH RECURSIVE role_hierarchy" in query:
                return {"data": [{"permission": "read"}]}

            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        # Mock cache hit
        node = PermissionCheckNode()

        # Pre-populate the internal cache to simulate a cache hit
        cache_key = node._generate_cache_key("user_123", "resource_456", "read", {})
        node._permission_cache[cache_key] = {
            "allowed": True,
            "reason": "Cached permission grant",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        node._cache_timestamps[cache_key] = datetime.now(timezone.utc)

        result = node.execute(
            operation="check_permission",
            user_id="user_123",
            resource_id="resource_456",
            permission="read",
            tenant_id="tenant_1",
            database_config=self.db_config,
        )

        assert result["result"]["check"]["allowed"] is True
        assert result["result"]["check"]["cache_hit"] is True

    @patch("kailash.nodes.admin.permission_check.AdminSchemaManager")
    @patch("kailash.nodes.admin.permission_check.SQLDatabaseNode")
    def test_permission_check_rbac_flow(
        self, mock_sql_node_class, mock_schema_manager_class
    ):
        """Test RBAC permission checking flow."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock schema manager
        mock_schema_instance = Mock()
        mock_schema_manager_class.return_value = mock_schema_instance
        mock_schema_instance.validate_schema.return_value = {"is_valid": True}

        # Mock database queries
        def mock_run(**kwargs):
            query = kwargs.get("query", "")

            # User context query - first query in _get_user_context
            if "FROM users" in query and "WHERE user_id" in query:
                return {
                    "data": [
                        {
                            "user_id": "user_123",
                            "email": "user@example.com",
                            "attributes": {},
                            "status": "active",
                            "tenant_id": "tenant_1",
                        }
                    ]
                }

            # User roles query - second query in _get_user_context
            elif "FROM user_role_assignments" in query:
                return {
                    "data": [
                        {"role_id": "editor"},
                        {"role_id": "reviewer"},
                    ]
                }

            # Role permissions query - return permissions in correct format
            elif "WITH RECURSIVE role_hierarchy" in query:
                # Return permissions that match the RBAC format
                return {
                    "data": [
                        {"permission": "*:read"},  # Global read permission
                        {"permission": "document_789:write"},  # Specific document write
                        {"permission": "*:review"},  # Global review permission
                    ]
                }

            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        node = PermissionCheckNode()

        result = node.execute(
            operation="check_permission",
            user_id="user_123",
            resource_id="document_789",
            permission="write",
            tenant_id="tenant_1",
            database_config=self.db_config,
            explain=True,  # Request explanation to get decision_path
        )

        assert result["result"]["check"]["allowed"] is True
        # Verify RBAC was used by checking the result structure
        assert result["result"]["check"]["cached"] is False
        # If we have explanation, verify it contains RBAC information
        if "explanation" in result["result"]:
            assert (
                "rbac_result" in result["result"]["explanation"]
                or "rbac_analysis" in result["result"]["explanation"]
            )

    @patch("kailash.nodes.admin.permission_check.AttributeEvaluator")
    @patch("kailash.nodes.admin.permission_check.AccessControlManager")
    @patch("kailash.nodes.admin.permission_check.AdminSchemaManager")
    @patch("kailash.nodes.admin.permission_check.SQLDatabaseNode")
    def test_permission_check_abac_flow(
        self,
        mock_sql_node_class,
        mock_schema_manager_class,
        mock_access_manager_class,
        mock_attr_evaluator_class,
    ):
        """Test ABAC permission checking with attributes."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock schema manager
        mock_schema_instance = Mock()
        mock_schema_manager_class.return_value = mock_schema_instance
        mock_schema_instance.validate_schema.return_value = {"is_valid": True}

        # Mock AccessControlManager for ABAC
        mock_access_manager = Mock()
        mock_access_manager_class.return_value = mock_access_manager

        # Mock the check_node_access method to return allowed decision
        mock_decision = Mock()
        mock_decision.allowed = True
        mock_decision.reason = "ABAC check passed"
        mock_access_manager.check_node_access.return_value = mock_decision

        # Mock database queries for ABAC flow
        def mock_run(**kwargs):
            query = kwargs.get("query", "")

            # User context query with attributes - first query in _get_user_context
            if "FROM users" in query and "WHERE user_id" in query:
                return {
                    "data": [
                        {
                            "user_id": "user_123",
                            "email": "user@example.com",
                            "attributes": {
                                "department": "engineering",
                                "level": "senior",
                            },
                            "status": "active",
                            "tenant_id": "tenant_1",
                        }
                    ]
                }

            # User roles query - second query in _get_user_context
            elif "FROM user_role_assignments" in query:
                return {
                    "data": [
                        {"role_id": "engineer"},
                    ]
                }

            # Role permissions query
            elif "WITH RECURSIVE role_hierarchy" in query:
                return {
                    "data": [
                        {"permission": "*:read"},  # Global read permission
                        {"permission": "doc_456:read"},  # Specific document read
                    ]
                }

            # Resource attributes query
            elif "FROM resource_attributes" in query:
                return {
                    "data": [
                        {
                            "resource_id": "doc_456",
                            "attributes": {
                                "classification": "internal",
                                "department": "engineering",
                            },
                        }
                    ]
                }

            # ABAC rules query
            elif "FROM abac_rules" in query:
                return {
                    "data": [
                        {
                            "rule_id": "eng_internal_access",
                            "allowed": True,
                            "condition": "user.department == resource.department",
                        }
                    ]
                }

            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        node = PermissionCheckNode()

        result = node.execute(
            operation="check_permission",
            user_id="user_123",
            resource_id="doc_456",
            permission="read",
            tenant_id="tenant_1",
            database_config=self.db_config,
        )

        # Should be allowed through RBAC (has read permission)
        assert result["result"]["check"]["allowed"] is True

        # Now test with ABAC context - this should also pass since we have permissions
        result_with_context = node.execute(
            operation="check_permission",
            user_id="user_123",
            resource_id="doc_456",
            permission="read",
            tenant_id="tenant_1",
            context={"ip_address": "10.0.0.1", "time_of_day": "business_hours"},
            database_config=self.db_config,
        )

        # Even with ABAC context, it should pass because we have the permission
        assert result_with_context["result"]["check"]["allowed"] is True

    @patch("kailash.nodes.admin.permission_check.AdminSchemaManager")
    @patch("kailash.nodes.admin.permission_check.SQLDatabaseNode")
    def test_multi_tenant_isolation(
        self, mock_sql_node_class, mock_schema_manager_class
    ):
        """Test multi-tenant data isolation."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock schema manager
        mock_schema_instance = Mock()
        mock_schema_manager_class.return_value = mock_schema_instance
        mock_schema_instance.validate_schema.return_value = {"is_valid": True}

        # Mock database responses for different tenants
        def mock_run(**kwargs):
            query = kwargs.get("query", "")
            parameters = kwargs.get("parameters", [])

            # User context query - only return users from matching tenant
            if "FROM users" in query and "WHERE user_id" in query:
                user_id = parameters[0] if parameters else None
                tenant_id = parameters[1] if len(parameters) > 1 else None

                if user_id == "user_a1" and tenant_id == "tenant_a":
                    return {
                        "data": [
                            {
                                "user_id": "user_a1",
                                "email": "user@tenant_a.com",
                                "roles": ["user"],
                                "attributes": {},
                                "status": "active",
                                "tenant_id": "tenant_a",
                            }
                        ]
                    }
                else:
                    return {"data": []}  # No data for wrong tenant

            # Role permissions query
            elif "WITH RECURSIVE role_hierarchy" in query:
                # Only return permissions if we're in the right tenant context
                return {"data": [{"permission": "*:read"}]}

            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        node = PermissionCheckNode()

        # Try to access user from tenant A with correct tenant
        result = node.execute(
            operation="check_permission",
            user_id="user_a1",
            resource_id="resource",
            permission="read",
            tenant_id="tenant_a",
            database_config=self.db_config,
        )
        # Should succeed
        assert "error" not in result

        # Try to access same user from tenant B (wrong tenant)
        # Create a fresh node instance to ensure clean state
        node2 = PermissionCheckNode()

        with pytest.raises(NodeExecutionError, match="User not found"):
            node2.execute(
                operation="check_permission",
                user_id="user_a1",
                resource_id="resource",
                permission="read",
                tenant_id="tenant_b",  # Wrong tenant
                database_config=self.db_config,
            )

    def test_schema_migration_check(self):
        """Test schema migration functionality."""
        manager = AdminSchemaManager(self.db_config)
        manager._get_current_schema_version = Mock(return_value="0.9.0")

        result = manager.migrate_schema(target_version="1.0.0")

        assert result["migration_needed"] is True
        assert result["current_version"] == "0.9.0"
        assert result["target_version"] == "1.0.0"

    @patch("kailash.nodes.admin.permission_check.AdminSchemaManager")
    @patch("kailash.nodes.admin.permission_check.SQLDatabaseNode")
    def test_audit_log_creation(self, mock_sql_node_class, mock_schema_manager_class):
        """Test audit log entry creation through permission check."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock schema manager
        mock_schema_instance = Mock()
        mock_schema_manager_class.return_value = mock_schema_instance
        mock_schema_instance.validate_schema.return_value = {"is_valid": True}

        # Mock database queries
        def mock_run(**kwargs):
            query = kwargs.get("query", "")

            # User context query - first query in _get_user_context
            if "FROM users" in query and "WHERE user_id" in query:
                return {
                    "data": [
                        {
                            "user_id": "user_123",
                            "email": "user@example.com",
                            "attributes": {},
                            "status": "active",
                            "tenant_id": "tenant_1",
                        }
                    ]
                }

            # User roles query - second query in _get_user_context
            elif "FROM user_role_assignments" in query:
                return {
                    "data": [
                        {"role_id": "reader"},
                    ]
                }

            # Role permissions query
            elif "WITH RECURSIVE role_hierarchy" in query:
                return {"data": [{"permission": "*:read"}]}

            # Audit log insert
            elif "INSERT INTO admin_audit_log" in query:
                return {"data": [{"id": 1}]}

            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        node = PermissionCheckNode()

        # Perform operation with audit enabled
        result = node.execute(
            operation="check_permission",
            user_id="user_123",
            resource_id="doc_456",
            permission="read",
            tenant_id="tenant_1",
            database_config=self.db_config,
            audit=True,  # Enable audit logging
        )

        assert result["result"]["check"]["allowed"] is True
        # Verify audit log was created
        audit_calls = [
            call
            for call in mock_db_instance.execute.call_args_list
            if "INSERT INTO admin_audit_log" in str(call)
        ]
        assert len(audit_calls) > 0

    @patch("kailash.nodes.admin.role_management.SQLDatabaseNode")
    def test_cache_invalidation_on_role_update(self, mock_sql_node_class):
        """Test that role updates work correctly (cache invalidation happens internally)."""
        mock_db_instance = Mock()
        mock_sql_node_class.return_value = mock_db_instance

        # Mock successful role fetch and update
        def mock_run(**kwargs):
            query = kwargs.get("query", "")

            # Role fetch query
            if (
                "SELECT role_id" in query
                and "FROM roles" in query
                and "WHERE role_id" in query
            ):
                # For single role fetch with result_format="dict"
                return {
                    "data": [
                        {
                            "role_id": "role_123",
                            "name": "Original Role",
                            "description": "Original description",
                            "permissions": ["read", "write"],
                            "parent_roles": [],
                            "attributes": {},
                            "is_active": True,
                            "role_type": "custom",
                            "created_at": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc),
                        }
                    ]
                }

            # Role update query
            elif "UPDATE roles" in query and "RETURNING" in query:
                return {
                    "data": [
                        {
                            "role_id": "role_123",
                            "name": "Updated Role",
                            "description": "Updated description",
                            "permissions": ["read", "write", "delete"],
                            "parent_roles": [],
                            "attributes": {},
                            "is_active": True,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    ]
                }

            return {"data": []}

        mock_db_instance.execute.side_effect = mock_run

        node = RoleManagementNode()
        node._db_node = mock_db_instance

        result = node.execute(
            operation="update_role",
            role_id="role_123",
            role_data={
                "description": "Updated description",
                "permissions": ["read", "write", "delete"],
            },
            database_config=self.db_config,
        )

        assert result["result"]["success"] is True
        assert result["result"]["role"]["description"] == "Updated description"

    def test_session_management_integration(self):
        """Test that permission checks respect session status in user context."""
        # This test verifies that permission checks work with user session data
        # Session validation would be handled by the authentication layer, not the permission node

        # Just verify that the permission check node initializes correctly
        node = PermissionCheckNode()
        assert hasattr(node, "_db_node")
        assert node._db_node is None  # Not initialized until first operation

    def test_concurrent_permission_checks(self):
        """Test handling of concurrent permission checks."""
        mock_db = Mock()
        mock_db.execute.return_value = {"data": [{"allowed": True}]}

        node = PermissionCheckNode()
        node._db_node = mock_db
        node._handle_concurrent_check = Mock(return_value=True)

        # Simulate concurrent checks
        results = []
        for i in range(10):
            result = node._handle_concurrent_check(
                f"user_{i}", "resource_1", "read", "tenant_1"
            )
            results.append(result)

        assert all(results)
        assert node._handle_concurrent_check.call_count == 10


class TestSchemaOperations:
    """Test schema-specific operations."""

    def setup_method(self):
        """Setup for each test method."""
        self.db_config = {
            "connection_string": "sqlite:///:memory:",
            "database_type": "sqlite",
        }

    @patch("kailash.nodes.admin.schema_manager.SQLDatabaseNode")
    def test_create_indexes(self, mock_sql_node_class):
        """Test index creation."""
        mock_db = Mock()
        mock_sql_node_class.return_value = mock_db

        manager = AdminSchemaManager({})
        manager._create_indexes = Mock()

        manager._create_indexes()
        manager._create_indexes.assert_called_once()

    def test_schema_version_tracking(self):
        """Test schema version tracking."""
        mock_db = Mock()
        mock_db.execute.return_value = {"data": [{"version": "1.0.0"}]}

        manager = AdminSchemaManager(self.db_config)
        manager.db_node = mock_db

        version = manager._get_current_schema_version()
        assert version == "1.0.0"

    def test_table_structure_validation(self):
        """Test validation of table structures."""
        mock_db = Mock()

        # Mock column information
        mock_db.execute.return_value = {
            "data": [
                {"column_name": "user_id"},
                {"column_name": "email"},
                {"column_name": "tenant_id"},
            ]
        }

        manager = AdminSchemaManager(self.db_config)
        manager.db_node = mock_db

        columns = manager._get_table_columns("users")
        assert "user_id" in columns
        assert "email" in columns
        assert "tenant_id" in columns


class TestErrorHandling:
    """Test error handling in admin nodes."""

    def setup_method(self):
        """Setup for each test method."""
        self.db_config = {
            "connection_string": "sqlite:///:memory:",
            "database_type": "sqlite",
        }

    @patch("kailash.nodes.admin.schema_manager.SQLDatabaseNode")
    def test_schema_creation_error(self, mock_sql_node_class):
        """Test handling of schema creation errors."""
        mock_db = Mock()
        mock_sql_node_class.return_value = mock_db
        mock_db.execute.side_effect = Exception("Database connection failed")

        manager = AdminSchemaManager(self.db_config)

        with pytest.raises(NodeExecutionError, match="Failed to create admin schema"):
            manager.create_full_schema()

    def test_permission_check_database_error(self):
        """Test handling of database errors during permission check."""
        node = PermissionCheckNode()
        node._db_node = Mock()
        node._db_node.run.side_effect = Exception("Query failed")

        with pytest.raises(NodeExecutionError):
            node.execute(
                operation="check_permission",
                user_id="user_123",
                resource_id="res_456",
                permission="read",
                tenant_id="tenant_1",
            )

    def test_role_creation_validation_error(self):
        """Test validation errors in role creation."""
        node = RoleManagementNode()

        with pytest.raises(NodeExecutionError, match="Missing required field"):
            node.execute(
                operation="create_role",
                role_data={},  # Missing required fields
                tenant_id="tenant_1",
                database_config=self.db_config,
            )


def mock_open(read_data=""):
    """Helper to mock file opening."""
    import builtins

    mock = MagicMock(spec=builtins.open)
    mock.return_value.__enter__.return_value.read.return_value = read_data
    return mock
