"""
Unit tests for ExternalAgentApprovalManager.

Tests approval logic in isolation with focus on INTENT:
- Verify cost-based approval triggering
- Verify environment-based approval triggering
- Verify data classification-based approval triggering
- Verify approval not required for non-sensitive operations
- Verify team lead approval routing
- Verify admin approval routing
- Verify custom approver list handling
- Verify approval decision recording
- Verify rejection decision recording
"""

from datetime import datetime, timedelta, timezone

import pytest

from kaizen.governance.approval_manager import (
    ApprovalLevel,
    ApprovalRequirement,
    ApprovalStatus,
    ExternalAgentApprovalManager,
)


class TestApprovalRequirementEvaluation:
    """Test approval requirement evaluation logic."""

    def test_cost_based_approval_triggering(self):
        """
        INTENT: Verify cost-based approval triggering.

        When estimated cost exceeds threshold, approval should be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Cost exceeds threshold
        metadata = {"cost": 15.00}
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert (
            required is True
        ), "Approval should be required when cost exceeds threshold"
        assert req is not None
        assert req.require_for_cost_above == 10.0

    def test_cost_based_approval_not_triggered(self):
        """
        INTENT: Verify cost-based approval NOT triggered when below threshold.

        When estimated cost is below threshold, approval should not be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Cost below threshold
        metadata = {"cost": 5.00}
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert (
            required is False
        ), "Approval should NOT be required when cost below threshold"
        assert req is None

    def test_environment_based_approval_triggering(self):
        """
        INTENT: Verify environment-based approval triggering.

        When executing in production environment, approval should be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_environments=["production"],
            approval_level=ApprovalLevel.ADMIN,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Production environment
        metadata = {"environment": "production"}
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert (
            required is True
        ), "Approval should be required for production environment"
        assert req is not None
        assert "production" in req.require_for_environments

    def test_environment_based_approval_not_triggered(self):
        """
        INTENT: Verify environment-based approval NOT triggered for development.

        When executing in development environment, approval should not be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_environments=["production"],
            approval_level=ApprovalLevel.ADMIN,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Development environment
        metadata = {"environment": "development"}
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert (
            required is False
        ), "Approval should NOT be required for development environment"
        assert req is None

    def test_data_classification_based_approval_triggering(self):
        """
        INTENT: Verify data classification-based approval triggering.

        When accessing restricted data, approval should be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_data_classifications=["confidential", "restricted"],
            approval_level=ApprovalLevel.OWNER,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Accessing confidential data
        metadata = {"data_classifications": ["confidential"]}
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert required is True, "Approval should be required for confidential data"
        assert req is not None
        assert "confidential" in req.require_for_data_classifications

    def test_data_classification_based_approval_not_triggered(self):
        """
        INTENT: Verify data classification-based approval NOT triggered for public data.

        When accessing public data, approval should not be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_data_classifications=["confidential", "restricted"],
            approval_level=ApprovalLevel.OWNER,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Accessing public data
        metadata = {"data_classifications": ["public"]}
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert required is False, "Approval should NOT be required for public data"
        assert req is None

    def test_operation_based_approval_triggering(self):
        """
        INTENT: Verify operation-based approval triggering.

        When performing delete operation, approval should be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_operations=["delete", "export"],
            approval_level=ApprovalLevel.ADMIN,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Delete operation
        metadata = {"operation": "delete"}
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert required is True, "Approval should be required for delete operation"
        assert req is not None
        assert "delete" in req.require_for_operations

    def test_approval_not_required_for_non_sensitive_operations(self):
        """
        INTENT: Verify approval NOT required for non-sensitive operations.

        When no approval conditions match, approval should not be required.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=100.0,
            require_for_environments=["production"],
            require_for_data_classifications=["confidential"],
            require_for_operations=["delete"],
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Non-sensitive operation (low cost, dev environment, public data, read operation)
        metadata = {
            "cost": 1.00,
            "environment": "development",
            "data_classifications": ["public"],
            "operation": "read",
        }
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert (
            required is False
        ), "Approval should NOT be required for non-sensitive operation"
        assert req is None

    def test_multiple_conditions_or_logic(self):
        """
        INTENT: Verify OR logic for multiple approval conditions.

        If ANY condition matches, approval should be required (not ALL).
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=100.0,  # Not met
            require_for_environments=["production"],  # MET
            require_for_data_classifications=["confidential"],  # Not met
            approval_level=ApprovalLevel.ADMIN,
        )
        manager.add_requirement("agent_001", requirement)

        # Test: Only environment condition met
        metadata = {
            "cost": 5.00,
            "environment": "production",
            "data_classifications": ["public"],
        }
        required, req = manager.determine_if_approval_required("agent_001", metadata)

        # Verify
        assert (
            required is True
        ), "Approval should be required when ANY condition matches (OR logic)"
        assert req is not None


class TestApprovalRouting:
    """Test approval routing to appropriate approvers."""

    def test_team_lead_approval_routing(self):
        """
        INTENT: Verify team lead approval routing.

        Approval should route to team leads of requesting user's team.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001", "lead_002"]}

        # Test
        approvers = manager._get_approvers(ApprovalLevel.TEAM_LEAD, "user_123", [])

        # Verify
        assert approvers == [
            "lead_001",
            "lead_002",
        ], "Should return team leads for user's team"

    def test_team_lead_routing_user_without_team(self):
        """
        INTENT: Verify team lead routing when user has no team.

        Should return empty list when user not assigned to any team.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        manager._user_teams = {}  # User not in any team

        # Test
        approvers = manager._get_approvers(ApprovalLevel.TEAM_LEAD, "user_123", [])

        # Verify
        assert approvers == [], "Should return empty list when user has no team"

    def test_admin_approval_routing(self):
        """
        INTENT: Verify admin approval routing.

        Approval should route to organization administrators.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        manager._org_admins = ["admin_001", "admin_002"]

        # Test
        approvers = manager._get_approvers(ApprovalLevel.ADMIN, "user_123", [])

        # Verify
        assert approvers == [
            "admin_001",
            "admin_002",
        ], "Should return organization admins"

    def test_owner_approval_routing(self):
        """
        INTENT: Verify owner approval routing.

        Approval should route to organization owner.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        manager._org_owner = "owner_001"

        # Test
        approvers = manager._get_approvers(ApprovalLevel.OWNER, "user_123", [])

        # Verify
        assert approvers == ["owner_001"], "Should return organization owner"

    def test_custom_approver_list_handling(self):
        """
        INTENT: Verify custom approver list handling.

        Approval should use custom_approvers list when level=CUSTOM.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        custom_approvers = ["custom_001", "custom_002", "custom_003"]

        # Test
        approvers = manager._get_approvers(
            ApprovalLevel.CUSTOM, "user_123", custom_approvers
        )

        # Verify
        assert approvers == custom_approvers, "Should return custom approver list"


class TestApprovalDecisions:
    """Test approval and rejection decision recording."""

    @pytest.mark.asyncio
    async def test_approve_request_updates_status_correctly(self):
        """
        INTENT: Verify approval decision recording.

        approve_request() should update status to APPROVED with approver identity and timestamp.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001"]}

        # Create approval request
        request_id = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )

        # Test: Approve request
        await manager.approve_request(request_id, "lead_001")

        # Verify
        request = manager.get_request(request_id)
        assert request is not None
        assert request.status == ApprovalStatus.APPROVED, "Status should be APPROVED"
        assert request.approved_by == "lead_001", "Approver ID should be recorded"
        assert request.approved_at is not None, "Approval timestamp should be recorded"

    @pytest.mark.asyncio
    async def test_reject_request_updates_status_with_rejection_reason(self):
        """
        INTENT: Verify rejection decision recording.

        reject_request() should update status to REJECTED with rejection reason.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001"]}

        # Create approval request
        request_id = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )

        # Test: Reject request
        rejection_reason = "Cost too high for this operation"
        await manager.reject_request(request_id, "lead_001", rejection_reason)

        # Verify
        request = manager.get_request(request_id)
        assert request is not None
        assert request.status == ApprovalStatus.REJECTED, "Status should be REJECTED"
        assert request.approved_by == "lead_001", "Rejector ID should be recorded"
        assert request.approved_at is not None, "Rejection timestamp should be recorded"
        assert (
            request.rejection_reason == rejection_reason
        ), "Rejection reason should be recorded"

    @pytest.mark.asyncio
    async def test_approve_request_requires_authorized_approver(self):
        """
        INTENT: Verify approval requires authorized approver.

        approve_request() should raise error if approver not in approvers list.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001"]}

        # Create approval request
        request_id = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )

        # Test: Unauthorized approver
        with pytest.raises(ValueError, match="not authorized"):
            await manager.approve_request(request_id, "unauthorized_user")

    @pytest.mark.asyncio
    async def test_approve_request_prevents_double_approval(self):
        """
        INTENT: Verify approval cannot be changed after decision.

        approve_request() should raise error if request already decided.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001"]}

        # Create and approve request
        request_id = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )
        await manager.approve_request(request_id, "lead_001")

        # Test: Try to approve again
        with pytest.raises(ValueError, match="already decided"):
            await manager.approve_request(request_id, "lead_001")


class TestApprovalTimeout:
    """Test approval timeout logic."""

    @pytest.mark.asyncio
    async def test_timeout_marks_pending_approvals_as_timeout(self):
        """
        INTENT: Verify timeout logic marks pending approvals as TIMEOUT.

        Pending approvals exceeding timeout should be marked as TIMEOUT.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
            approval_timeout_seconds=3600,  # 1 hour
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001"]}

        # Create approval request
        request_id = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )

        # Simulate timeout by backdating created_at
        request = manager.get_request(request_id)
        request.created_at = datetime.now(timezone.utc) - timedelta(
            seconds=7200
        )  # 2 hours ago

        # Test: Run timeout background task
        count = await manager.timeout_pending_approvals()

        # Verify
        assert count == 1, "Should timeout 1 pending approval"
        request = manager.get_request(request_id)
        assert request.status == ApprovalStatus.TIMEOUT, "Status should be TIMEOUT"

    @pytest.mark.asyncio
    async def test_timeout_does_not_affect_decided_approvals(self):
        """
        INTENT: Verify timeout does NOT affect already-decided approvals.

        APPROVED/REJECTED approvals should not be changed by timeout task.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
            approval_timeout_seconds=3600,
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001"]}

        # Create and approve request
        request_id = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )
        await manager.approve_request(request_id, "lead_001")

        # Simulate timeout by backdating created_at
        request = manager.get_request(request_id)
        request.created_at = datetime.now(timezone.utc) - timedelta(seconds=7200)

        # Test: Run timeout background task
        count = await manager.timeout_pending_approvals()

        # Verify
        assert count == 0, "Should NOT timeout any approvals (already decided)"
        request = manager.get_request(request_id)
        assert (
            request.status == ApprovalStatus.APPROVED
        ), "Status should remain APPROVED"


class TestGetPendingApprovals:
    """Test querying pending approvals."""

    @pytest.mark.asyncio
    async def test_get_pending_approvals_for_approver(self):
        """
        INTENT: Verify get_pending_approvals returns correct requests.

        Should return only pending approvals where user is an approver.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001", "user_456": "team_002"}
        manager._team_leads = {"team_001": ["lead_001"], "team_002": ["lead_002"]}

        # Create approval requests
        request_id_1 = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )
        request_id_2 = await manager.request_approval(
            "agent_001",
            "user_456",
            {"cost": 20.00},
        )

        # Test: Get pending approvals for lead_001
        pending = manager.get_pending_approvals("lead_001")

        # Verify
        assert len(pending) == 1, "Should return 1 pending approval for lead_001"
        assert pending[0].id == request_id_1
        assert pending[0].status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_pending_approvals_excludes_decided(self):
        """
        INTENT: Verify get_pending_approvals excludes decided requests.

        Should NOT return APPROVED/REJECTED/TIMEOUT approvals.
        """
        # Setup
        manager = ExternalAgentApprovalManager()
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("agent_001", requirement)
        manager._user_teams = {"user_123": "team_001"}
        manager._team_leads = {"team_001": ["lead_001"]}

        # Create and approve request
        request_id = await manager.request_approval(
            "agent_001",
            "user_123",
            {"cost": 15.00},
        )
        await manager.approve_request(request_id, "lead_001")

        # Test: Get pending approvals for lead_001
        pending = manager.get_pending_approvals("lead_001")

        # Verify
        assert len(pending) == 0, "Should NOT return decided approvals"
