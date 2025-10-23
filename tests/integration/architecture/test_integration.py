"""Integration tests for refactored architecture components.

This module tests that our refactored components work correctly
and that the existing ABAC functionality is preserved.
"""

import pytest
from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
)

from tests.utils import FunctionalTestMixin


class TestAccessControlIntegration(FunctionalTestMixin):
    """Test integration of access control components."""

    def test_enhanced_access_control_basic(self):
        """Test basic access control functionality with RBAC strategy."""
        # Create manager with RBAC strategy
        manager = AccessControlManager(strategy="rbac")

        # Add basic RBAC rule
        rule = PermissionRule(
            id="admin_access",
            resource_type="node",
            resource_id="test_resource",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )
        manager.add_rule(rule)

        # Test admin access
        admin_user = UserContext(
            user_id="admin1",
            tenant_id="test_tenant",
            email="admin@test.com",
            roles=["admin"],
            attributes={},
        )

        decision = manager.check_node_access(
            admin_user, "test_resource", NodePermission.EXECUTE
        )
        assert decision.allowed

        # Test non-admin user denial
        regular_user = UserContext(
            user_id="user1",
            tenant_id="test_tenant",
            email="user@test.com",
            roles=["user"],
            attributes={},
        )

        decision = manager.check_node_access(
            regular_user, "test_resource", NodePermission.EXECUTE
        )
        assert not decision.allowed

    def test_abac_functionality_preserved(self):
        """Test that ABAC functionality works correctly."""
        # Create manager with ABAC strategy
        manager = AccessControlManager(strategy="abac")

        # Add ABAC rule with attribute conditions (the one that was failing before)
        rule = PermissionRule(
            id="finance_department_access",
            resource_type="node",
            resource_id="financial_data",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
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
        manager.add_rule(rule)

        # Test Finance user access (this was failing before our fix)
        finance_user = UserContext(
            user_id="finance1",
            tenant_id="test_tenant",
            email="finance@test.com",
            roles=["analyst"],
            attributes={"department": "Finance"},
        )

        decision = manager.check_node_access(
            finance_user, "financial_data", NodePermission.EXECUTE
        )
        assert decision.allowed, f"Finance user should have access: {decision.reason}"

        # Test non-Finance user denial
        it_user = UserContext(
            user_id="it1",
            tenant_id="test_tenant",
            email="it@test.com",
            roles=["analyst"],
            attributes={"department": "IT"},
        )

        decision = manager.check_node_access(
            it_user, "financial_data", NodePermission.EXECUTE
        )
        assert not decision.allowed, "IT user should not have access to financial data"


class TestTestUtilities(FunctionalTestMixin):
    """Test that our new test utilities work correctly."""

    def test_functional_test_mixin(self):
        """Test functional test mixin works."""
        # Test basic functionality assertion
        result = {"status": "success", "data": [1, 2, 3]}
        expected = {"status": "success", "data": [1, 2, 3]}
        self.assert_functionality_only(result, expected)

        # Test context creation
        context = self.create_minimal_context(timeout=2.0, debug_mode=False)
        assert context["timeout"] == 2.0
        assert context["debug_mode"] is False
        assert context["retry_count"] == 0  # Default

    def test_database_test_utils(self):
        """Test database test utilities."""
        from tests.utils import DatabaseTestUtils

        # Test mock query result creation
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = DatabaseTestUtils.create_mock_query_result(data)

        assert result["row_count"] == 2
        assert result["data"] == data
        assert result["columns"] == ["id", "name"]
        assert result["execution_time"] > 0

        # Test user context creation
        user = DatabaseTestUtils.create_test_user_context(
            user_id="test123",
            roles=["admin", "user"],
            attributes={"department": "Engineering"},
        )

        assert user.user_id == "test123"
        assert "admin" in user.roles
        assert user.attributes["department"] == "Engineering"

    def test_existing_abac_tests_still_pass(self):
        """Verify that our refactoring didn't break existing ABAC tests."""
        # This test ensures the functionality we just fixed still works
        # Since the original test file was deleted during reorganization,
        # we'll test the core ABAC functionality directly

        # Test that ABAC access control still works with complex conditions
        manager = AccessControlManager(strategy="abac")

        # Add a complex ABAC rule similar to what was tested before
        rule = PermissionRule(
            id="complex_finance_access",
            resource_type="node",
            resource_id="financial_data",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            conditions={
                "type": "attribute_expression",
                "value": {
                    "operator": "and",
                    "conditions": [
                        {
                            "attribute_path": "user.attributes.department",
                            "operator": "equals",
                            "value": "Finance",
                        },
                        {
                            "attribute_path": "user.attributes.clearance_level",
                            "operator": "greater_than",
                            "value": 3,
                        },
                    ],
                },
            },
        )
        manager.add_rule(rule)

        # Test user with matching attributes
        qualified_user = UserContext(
            user_id="finance_lead",
            tenant_id="test_tenant",
            email="lead@finance.com",
            roles=["analyst"],
            attributes={"department": "Finance", "clearance_level": 5},
        )

        decision = manager.check_node_access(
            qualified_user, "financial_data", NodePermission.EXECUTE
        )
        assert decision.allowed, "User with matching attributes should have access"

        # Test user missing clearance level
        unqualified_user = UserContext(
            user_id="finance_intern",
            tenant_id="test_tenant",
            email="intern@finance.com",
            roles=["analyst"],
            attributes={"department": "Finance", "clearance_level": 2},
        )

        decision = manager.check_node_access(
            unqualified_user, "financial_data", NodePermission.EXECUTE
        )
        assert (
            not decision.allowed
        ), "User without sufficient clearance should be denied"


# Export test classes
__all__ = [
    "TestAccessControlIntegration",
    "TestTestUtilities",
]
