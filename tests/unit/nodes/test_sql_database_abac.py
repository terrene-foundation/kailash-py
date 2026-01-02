"""Test SQL Database Node with ABAC integration."""

import os
import sqlite3
import tempfile

import pytest
from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
)
from kailash.access_control_abac import (
    AttributeCondition,
    AttributeExpression,
    AttributeMaskingRule,
    AttributeOperator,
    LogicalOperator,
)
from kailash.nodes.data import SQLDatabaseNode


class TestSQLDatabaseNodeABAC:
    """Test SQL Database Node with ABAC features."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database with test data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
            db_path = f.name

        # Create test data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create users table
        cursor.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                department TEXT,
                salary REAL
            )
        """
        )

        # Insert test data
        users = [
            (1, "Alice Johnson", "alice@company.com", "IT", 95000),
            (2, "Bob Smith", "bob@company.com", "Finance", 85000),
            (3, "Charlie Brown", "charlie@company.com", "HR", 75000),
            (4, "Diana Prince", "diana@company.com", "IT", 98000),
        ]
        cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", users)

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_sql_node_with_abac_masking(self, temp_db):
        """Test SQL node with ABAC data masking."""
        # Create access control manager
        access_manager = AccessControlManager(strategy="abac")

        # Add permission rule to allow execution
        access_manager.add_rule(
            PermissionRule(
                id="allow_query_execution",
                resource_type="node",
                resource_id="secure_sql_query",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
            )
        )

        # Define masking rule for salary - mask for non-Finance users
        access_manager.add_masking_rule(
            "secure_sql_query",
            AttributeMaskingRule(
                field_path="salary",
                mask_type="redact",
                condition=AttributeExpression(
                    operator=LogicalOperator.AND,
                    conditions=[
                        AttributeCondition(
                            attribute_path="user.attributes.department",
                            operator=AttributeOperator.NOT_EQUALS,
                            value="Finance",
                        )
                    ],
                ),
            ),
        )

        # Define masking rule for email - partial mask for non-IT users
        access_manager.add_masking_rule(
            "secure_sql_query",
            AttributeMaskingRule(
                field_path="email",
                mask_type="partial",
                condition=AttributeExpression(
                    operator=LogicalOperator.AND,
                    conditions=[
                        AttributeCondition(
                            attribute_path="user.attributes.department",
                            operator=AttributeOperator.NOT_EQUALS,
                            value="IT",
                        )
                    ],
                ),
            ),
        )

        # Create SQL node with access control
        node = SQLDatabaseNode(
            name="secure_sql_query",
            connection_string=f"sqlite:///{temp_db}",
            access_control_manager=access_manager,
        )

        # Test with Finance user (sees salaries but masked emails)
        finance_context = UserContext(
            user_id="fin_user",
            tenant_id="test_tenant",
            email="finance@company.com",
            roles=["analyst"],
            attributes={"department": "Finance"},
        )

        result = node.execute(
            query="SELECT * FROM users ORDER BY id", user_context=finance_context
        )

        assert result["row_count"] == 4
        # Finance users see full salary
        assert result["data"][0]["salary"] == 95000
        # But emails are masked (except IT emails)
        assert (
            "***" in result["data"][0]["email"]
        )  # Alice is IT, but finance sees masked
        assert "***" in result["data"][1]["email"]  # Bob is Finance, but still masked

        # Test with IT user (sees emails but not salaries)
        it_context = UserContext(
            user_id="it_user",
            tenant_id="test_tenant",
            email="it@company.com",
            roles=["developer"],
            attributes={"department": "IT"},
        )

        result = node.execute(
            query="SELECT * FROM users ORDER BY id", user_context=it_context
        )

        # IT users see full emails
        assert "@" in result["data"][0]["email"]
        assert "alice@company.com" == result["data"][0]["email"]
        # But salaries are redacted
        assert result["data"][0]["salary"] == "[REDACTED]"
        assert result["data"][1]["salary"] == "[REDACTED]"

        # Test with HR user (both fields masked)
        hr_context = UserContext(
            user_id="hr_user",
            tenant_id="test_tenant",
            email="hr@company.com",
            roles=["hr_manager"],
            attributes={"department": "HR"},
        )

        result = node.execute(
            query="SELECT * FROM users ORDER BY id", user_context=hr_context
        )

        # HR users see masked emails
        assert "***" in result["data"][0]["email"]
        # And redacted salaries
        assert result["data"][0]["salary"] == "[REDACTED]"

    def test_sql_node_access_denied(self, temp_db):
        """Test SQL node access control denial."""
        # Create access control manager with restrictive rule
        access_manager = AccessControlManager(strategy="abac")

        # Add a general deny rule with lower priority
        access_manager.add_rule(
            PermissionRule(
                id="deny_all",
                resource_type="node",
                resource_id="restricted_query",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.DENY,
                priority=0,  # Lower priority
            )
        )

        # Then allow only Finance department to execute queries using ABAC
        access_manager.add_rule(
            PermissionRule(
                id="finance_only",
                resource_type="node",
                resource_id="restricted_query",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                priority=10,  # Higher priority
                conditions={
                    "type": "attribute_expression",
                    "value": {
                        "operator": "and",
                        "conditions": [
                            {
                                "attribute_path": "user.attributes.department",
                                "operator": "equals",
                                "value": "Finance",
                            }
                        ],
                    },
                },
            )
        )

        # Create SQL node
        node = SQLDatabaseNode(
            name="restricted_query",
            connection_string=f"sqlite:///{temp_db}",
            access_control_manager=access_manager,
        )

        # Test with IT user - should be denied
        it_context = UserContext(
            user_id="it_user",
            tenant_id="test_tenant",
            email="it@company.com",
            roles=["developer"],
            attributes={"department": "IT"},
        )

        with pytest.raises(Exception) as exc_info:
            node.execute(query="SELECT * FROM users", user_context=it_context)

        assert "Access denied" in str(exc_info.value)

        # Test with Finance user - should succeed
        finance_context = UserContext(
            user_id="fin_user",
            tenant_id="test_tenant",
            email="finance@company.com",
            roles=["analyst"],
            attributes={"department": "Finance"},
        )

        result = node.execute(
            query="SELECT COUNT(*) as total FROM users", user_context=finance_context
        )

        assert result["data"][0]["total"] == 4

    def test_sql_node_without_access_control(self, temp_db):
        """Test that SQL node works normally without access control."""
        # Create node without access control
        node = SQLDatabaseNode(
            name="basic_query",
            connection_string=f"sqlite:///{temp_db}",
        )

        # Execute query without user context
        result = node.execute(
            query="SELECT * FROM users WHERE department = ?", parameters=["IT"]
        )

        assert result["row_count"] == 2
        assert len(result["data"]) == 2
        # All data visible without masking
        assert result["data"][0]["email"] == "alice@company.com"
        assert result["data"][0]["salary"] == 95000
