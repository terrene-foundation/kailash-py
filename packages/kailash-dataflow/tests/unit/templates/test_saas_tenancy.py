"""
SaaS Starter Template - Multi-Tenant Isolation Tests

Test-first development (TDD) for multi-tenant isolation.

Tests (10 total):
1. test_get_user_organization - Get user's organization
2. test_filter_by_organization - Add organization filter to queries
3. test_list_organization_users - List users in organization
4. test_check_user_belongs_to_org_success - Verify user belongs to org
5. test_check_user_belongs_to_org_failure - Verify user doesn't belong to org
6. test_switch_user_organization_success - Move user to different org
7. test_switch_user_organization_invalid_org - Switch to non-existent org fails
8. test_tenant_isolation_enforcement - Ensure tenant isolation is enforced
9. test_cross_tenant_access_blocked - Block cross-tenant data access
10. test_organization_data_segregation - Verify organization data segregation

CRITICAL: These tests are written BEFORE implementation (RED phase).
Tests define the API contract and expected behavior for multi-tenant isolation.
"""

import os

# Add templates directory to Python path for imports
import sys
from datetime import datetime
from typing import Dict, List, Optional

import pytest

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../../../templates")
if TEMPLATES_DIR not in sys.path:
    sys.path.insert(0, TEMPLATES_DIR)


@pytest.mark.unit
class TestMultiTenantIsolation:
    """
    Test multi-tenant isolation functions (no complex workflows).

    Tests 1-10: Direct function tests with mocked DataFlow for speed.

    Real database integration tests are in tests/integration/templates/
    """

    def test_get_user_organization(self, monkeypatch):
        """
        Test getting user's organization.

        Expected Behavior:
        - Input: db instance, user_id
        - Output: organization dict with all fields
        - Uses DataFlow UserReadNode + OrganizationReadNode

        RED Phase: This test will fail because get_user_organization() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import get_user_organization

        mock_db = MagicMock()
        user_id = "user_123"

        user_data = {
            "id": user_id,
            "organization_id": "org_456",
            "email": "alice@example.com",
            "role": "member",
            "status": "active",
        }

        org_data = {
            "id": "org_456",
            "name": "Acme Corp",
            "slug": "acme-corp",
            "plan_id": "plan_pro",
            "status": "active",
            "settings": {},
        }

        # Mock workflow execution for both user lookup and org lookup
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()

        # First call returns user, second call returns org
        mock_runtime.execute.side_effect = [
            ({"read_user": user_data}, "run_id_1"),
            ({"read_org": org_data}, "run_id_2"),
        ]

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = get_user_organization(mock_db, user_id)

            # Verify organization returned
            assert result is not None, "Should return organization"
            assert result["id"] == "org_456", "Should return correct org ID"
            assert result["name"] == "Acme Corp", "Should return org name"
            assert result["slug"] == "acme-corp", "Should return org slug"

    def test_filter_by_organization(self):
        """
        Test adding organization filter to query filters.

        Expected Behavior:
        - Input: existing filters dict, organization_id
        - Output: filters dict with organization_id added
        - Pure function (no database access)

        RED Phase: This test will fail because filter_by_organization() doesn't exist yet.
        """
        from saas_starter.tenancy.isolation import filter_by_organization

        # Test adding org filter to empty filters
        filters = {}
        org_id = "org_789"
        result = filter_by_organization(filters, org_id)

        assert "organization_id" in result, "Should add organization_id filter"
        assert result["organization_id"] == org_id, "Should have correct org ID"

        # Test adding org filter to existing filters
        existing_filters = {"status": "active", "role": "member"}
        result2 = filter_by_organization(existing_filters, org_id)

        assert "organization_id" in result2, "Should add organization_id filter"
        assert result2["organization_id"] == org_id, "Should have correct org ID"
        assert result2["status"] == "active", "Should preserve existing filters"
        assert result2["role"] == "member", "Should preserve existing filters"

    def test_list_organization_users(self, monkeypatch):
        """
        Test listing users in an organization.

        Expected Behavior:
        - Input: db instance, organization_id
        - Output: list of user dicts
        - Uses DataFlow UserListNode with organization_id filter

        RED Phase: This test will fail because list_organization_users() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import list_organization_users

        mock_db = MagicMock()
        org_id = "org_456"

        users_data = [
            {
                "id": "user_1",
                "organization_id": org_id,
                "email": "alice@example.com",
                "role": "owner",
                "status": "active",
            },
            {
                "id": "user_2",
                "organization_id": org_id,
                "email": "bob@example.com",
                "role": "member",
                "status": "active",
            },
        ]

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"list_users": users_data}, "run_id_123")

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = list_organization_users(mock_db, org_id)

            # Verify users returned
            assert isinstance(result, list), "Should return list of users"
            assert len(result) == 2, "Should return 2 users"
            assert (
                result[0]["organization_id"] == org_id
            ), "All users should belong to org"
            assert (
                result[1]["organization_id"] == org_id
            ), "All users should belong to org"

    def test_check_user_belongs_to_org_success(self, monkeypatch):
        """
        Test checking if user belongs to organization (success case).

        Expected Behavior:
        - Input: db instance, user_id, organization_id
        - Output: True if user belongs to organization
        - Uses DataFlow UserReadNode to verify organization_id

        RED Phase: This test will fail because check_user_belongs_to_org() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import check_user_belongs_to_org

        mock_db = MagicMock()
        user_id = "user_123"
        org_id = "org_456"

        user_data = {
            "id": user_id,
            "organization_id": org_id,
            "email": "alice@example.com",
            "role": "member",
            "status": "active",
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"read_user": user_data}, "run_id_123")

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = check_user_belongs_to_org(mock_db, user_id, org_id)

            # Verify user belongs to org
            assert result is True, "User should belong to organization"

    def test_check_user_belongs_to_org_failure(self, monkeypatch):
        """
        Test checking if user belongs to organization (failure case).

        Expected Behavior:
        - Input: db instance, user_id, wrong organization_id
        - Output: False if user doesn't belong to organization

        RED Phase: This test will fail because check_user_belongs_to_org() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import check_user_belongs_to_org

        mock_db = MagicMock()
        user_id = "user_123"
        wrong_org_id = "org_999"

        user_data = {
            "id": user_id,
            "organization_id": "org_456",  # Different org
            "email": "alice@example.com",
            "role": "member",
            "status": "active",
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"read_user": user_data}, "run_id_123")

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = check_user_belongs_to_org(mock_db, user_id, wrong_org_id)

            # Verify user doesn't belong to wrong org
            assert result is False, "User should not belong to wrong organization"

    def test_switch_user_organization_success(self, monkeypatch):
        """
        Test switching user to different organization (success case).

        Expected Behavior:
        - Input: db instance, user_id, new_organization_id
        - Output: updated user dict
        - Uses DataFlow UserUpdateNode to change organization_id

        RED Phase: This test will fail because switch_user_organization() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import switch_user_organization

        mock_db = MagicMock()
        user_id = "user_123"
        new_org_id = "org_789"

        org_data = {
            "id": new_org_id,
            "name": "New Org",
            "slug": "new-org",
            "status": "active",
        }

        updated_user = {
            "id": user_id,
            "organization_id": new_org_id,
            "email": "alice@example.com",
            "role": "member",
            "status": "active",
        }

        # Mock workflow execution - first call returns org, second call returns updated user
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.side_effect = [
            ({"read_org": org_data}, "run_id_1"),
            ({"update_user": updated_user}, "run_id_2"),
        ]

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = switch_user_organization(mock_db, user_id, new_org_id)

            # Verify user switched organizations
            assert result is not None, "Should return updated user"
            assert result["organization_id"] == new_org_id, "Should have new org ID"

    def test_switch_user_organization_invalid_org(self, monkeypatch):
        """
        Test switching user to non-existent organization (failure case).

        Expected Behavior:
        - Input: db instance, user_id, non-existent organization_id
        - Output: None or error indicator
        - Should validate organization exists first

        RED Phase: This test will fail because switch_user_organization() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import switch_user_organization

        mock_db = MagicMock()
        user_id = "user_123"
        invalid_org_id = "org_nonexistent"

        # Mock workflow execution - org lookup returns None
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"read_org": None}, "run_id_123")

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = switch_user_organization(mock_db, user_id, invalid_org_id)

            # Verify operation failed
            assert result is None, "Should return None for invalid org"

    def test_tenant_isolation_enforcement(self, monkeypatch):
        """
        Test that tenant isolation is properly enforced.

        Expected Behavior:
        - Queries must include organization_id filter
        - Cross-tenant data access should be prevented
        - Validates filter_by_organization() usage

        RED Phase: This test will fail because filter_by_organization() doesn't exist yet.
        """
        from saas_starter.tenancy.isolation import filter_by_organization

        org_id_1 = "org_111"
        org_id_2 = "org_222"

        # Test that each organization gets its own filter
        filters_1 = filter_by_organization({}, org_id_1)
        filters_2 = filter_by_organization({}, org_id_2)

        assert filters_1["organization_id"] == org_id_1, "Should isolate to org 1"
        assert filters_2["organization_id"] == org_id_2, "Should isolate to org 2"
        assert (
            filters_1["organization_id"] != filters_2["organization_id"]
        ), "Should enforce separation"

    def test_cross_tenant_access_blocked(self, monkeypatch):
        """
        Test that cross-tenant data access is blocked.

        Expected Behavior:
        - User from org A cannot access org B's data
        - check_user_belongs_to_org() returns False for cross-tenant access

        RED Phase: This test will fail because check_user_belongs_to_org() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import check_user_belongs_to_org

        mock_db = MagicMock()

        # User belongs to org A
        user_id = "user_org_a"
        user_org_id = "org_a"
        target_org_id = "org_b"  # Trying to access org B

        user_data = {
            "id": user_id,
            "organization_id": user_org_id,
            "email": "user@orga.com",
            "role": "member",
            "status": "active",
        }

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"read_user": user_data}, "run_id_123")

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            # Try to verify user belongs to different org
            result = check_user_belongs_to_org(mock_db, user_id, target_org_id)

            # Verify cross-tenant access is blocked
            assert result is False, "Cross-tenant access should be blocked"

    def test_organization_data_segregation(self, monkeypatch):
        """
        Test organization data segregation.

        Expected Behavior:
        - list_organization_users() only returns users from specified org
        - No data leakage between organizations

        RED Phase: This test will fail because list_organization_users() doesn't exist yet.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.tenancy.isolation import list_organization_users

        mock_db = MagicMock()
        org_a_id = "org_a"

        # Only org A users should be returned
        org_a_users = [
            {
                "id": "user_a1",
                "organization_id": org_a_id,
                "email": "user1@orga.com",
                "role": "owner",
                "status": "active",
            },
            {
                "id": "user_a2",
                "organization_id": org_a_id,
                "email": "user2@orga.com",
                "role": "member",
                "status": "active",
            },
        ]

        # Mock workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"list_users": org_a_users}, "run_id_123")

        import saas_starter.tenancy.isolation

        with (
            patch.object(
                saas_starter.tenancy.isolation,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.tenancy.isolation,
                "LocalRuntime",
                return_value=mock_runtime,
            ),
        ):
            result = list_organization_users(mock_db, org_a_id)

            # Verify only org A users returned
            assert len(result) == 2, "Should return only org A users"
            assert all(
                u["organization_id"] == org_a_id for u in result
            ), "All users should belong to org A"
            # Verify no org B users leaked in
            org_b_emails = ["user@orgb.com"]
            assert not any(
                u["email"] in org_b_emails for u in result
            ), "No org B users should leak"
