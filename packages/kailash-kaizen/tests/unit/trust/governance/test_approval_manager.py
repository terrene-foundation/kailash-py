"""
Tier 1 Unit Tests: ApprovalManager

Tests approval workflow logic in isolation (no database persistence).

Intent: Verify approval determination, routing, and decision tracking.
"""

from datetime import datetime, timedelta, timezone

import pytest
from kailash.runtime import AsyncLocalRuntime

from kaizen.trust.governance import (
    ApprovalLevel,
    ApprovalManager,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
)


class TestApprovalPolicy:
    """Test ApprovalPolicy dataclass."""

    def test_approval_policy_creation_with_defaults(self):
        """
        Intent: Verify policy can be created with sensible defaults.

        Expected: All required fields set, optional fields have defaults.
        """
        policy = ApprovalPolicy(external_agent_id="test_agent")

        assert policy.external_agent_id == "test_agent"
        assert policy.require_for_cost_above is None
        assert policy.require_for_environments == []
        assert policy.require_for_data_classifications == []
        assert policy.require_for_operations == []
        assert policy.approval_level == ApprovalLevel.TEAM_LEAD
        assert policy.custom_approvers == []
        assert policy.approval_timeout_seconds == 3600  # 1 hour
        assert policy.enabled is True

    def test_approval_policy_creation_with_cost_threshold(self):
        """
        Intent: Verify cost threshold can be configured.

        Expected: Cost threshold set correctly.
        """
        policy = ApprovalPolicy(
            external_agent_id="test_agent", require_for_cost_above=10.0
        )

        assert policy.require_for_cost_above == 10.0

    def test_approval_policy_creation_with_environment_restrictions(self):
        """
        Intent: Verify environment restrictions can be configured.

        Expected: Environment list set correctly.
        """
        policy = ApprovalPolicy(
            external_agent_id="test_agent",
            require_for_environments=["production", "staging"],
        )

        assert "production" in policy.require_for_environments
        assert "staging" in policy.require_for_environments

    def test_approval_policy_creation_with_custom_approvers(self):
        """
        Intent: Verify custom approver list can be configured.

        Expected: Custom approvers and CUSTOM approval level set.
        """
        policy = ApprovalPolicy(
            external_agent_id="test_agent",
            approval_level=ApprovalLevel.CUSTOM,
            custom_approvers=["user-1", "user-2"],
        )

        assert policy.approval_level == ApprovalLevel.CUSTOM
        assert policy.custom_approvers == ["user-1", "user-2"]


class TestApprovalResult:
    """Test ApprovalResult dataclass."""

    def test_approval_result_required(self):
        """
        Intent: Verify approval required result has correct structure.

        Expected: approval_required=True, policy populated, reason provided.
        """
        policy = ApprovalPolicy(external_agent_id="test", require_for_cost_above=10.0)

        result = ApprovalResult(
            approval_required=True,
            policy=policy,
            reason="Cost exceeds threshold",
            estimated_cost=15.0,
        )

        assert result.approval_required is True
        assert result.policy == policy
        assert result.reason == "Cost exceeds threshold"
        assert result.estimated_cost == 15.0

    def test_approval_result_not_required(self):
        """
        Intent: Verify approval not required result.

        Expected: approval_required=False, no policy needed.
        """
        result = ApprovalResult(
            approval_required=False, reason="No approval conditions matched"
        )

        assert result.approval_required is False
        assert result.policy is None
        assert result.reason == "No approval conditions matched"


class TestApprovalManager:
    """Test approval manager logic."""

    def test_determine_if_approval_required_cost_exceeds_threshold(self):
        """
        Intent: Verify approval required when cost exceeds threshold.

        Setup: Policy with cost threshold $10, invocation cost $15
        Expected: Approval required, reason indicates cost threshold
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(external_agent_id="test", require_for_cost_above=10.0)

        result = manager.determine_if_approval_required(policy, cost=15.0)

        assert result.approval_required is True
        assert result.policy == policy
        assert "Cost exceeds threshold" in result.reason
        assert "$15.00" in result.reason
        assert "$10.00" in result.reason
        assert result.estimated_cost == 15.0

    def test_determine_if_approval_required_cost_within_threshold(self):
        """
        Intent: Verify no approval required when cost is within threshold.

        Setup: Policy with cost threshold $10, invocation cost $5
        Expected: Approval not required
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(external_agent_id="test", require_for_cost_above=10.0)

        result = manager.determine_if_approval_required(policy, cost=5.0)

        assert result.approval_required is False

    def test_determine_if_approval_required_environment_matches(self):
        """
        Intent: Verify approval required when environment is restricted.

        Setup: Policy requires approval for production, environment is production
        Expected: Approval required, reason indicates environment
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test", require_for_environments=["production"]
        )

        result = manager.determine_if_approval_required(
            policy, environment="production"
        )

        assert result.approval_required is True
        assert "Environment 'production' requires approval" in result.reason
        assert result.environment == "production"

    def test_determine_if_approval_required_environment_not_restricted(self):
        """
        Intent: Verify no approval required for unrestricted environments.

        Setup: Policy requires approval for production, environment is development
        Expected: Approval not required
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test", require_for_environments=["production"]
        )

        result = manager.determine_if_approval_required(
            policy, environment="development"
        )

        assert result.approval_required is False

    def test_determine_if_approval_required_data_classification_matches(self):
        """
        Intent: Verify approval required when data classification is restricted.

        Setup: Policy requires approval for PII, data includes PII
        Expected: Approval required, reason indicates data classification
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test",
            require_for_data_classifications=["pii", "confidential"],
        )

        result = manager.determine_if_approval_required(
            policy, data_classifications=["pii"]
        )

        assert result.approval_required is True
        assert "Data classification requires approval" in result.reason
        assert "pii" in result.reason
        assert result.data_classifications == ["pii"]

    def test_determine_if_approval_required_data_classification_multiple_match(self):
        """
        Intent: Verify approval required when multiple data classifications match.

        Setup: Policy requires approval for PII and confidential, data includes both
        Expected: Approval required, reason shows matching classifications
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test",
            require_for_data_classifications=["pii", "confidential"],
        )

        result = manager.determine_if_approval_required(
            policy, data_classifications=["pii", "confidential", "public"]
        )

        assert result.approval_required is True
        assert "Data classification requires approval" in result.reason

    def test_determine_if_approval_required_operation_matches(self):
        """
        Intent: Verify approval required when operation is restricted.

        Setup: Policy requires approval for delete operations, operation is delete_user
        Expected: Approval required, reason indicates operation
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test",
            require_for_operations=["delete_user", "update_payroll"],
        )

        result = manager.determine_if_approval_required(policy, operation="delete_user")

        assert result.approval_required is True
        assert "Operation 'delete_user' requires approval" in result.reason
        assert result.operation == "delete_user"

    def test_determine_if_approval_required_operation_not_restricted(self):
        """
        Intent: Verify no approval required for unrestricted operations.

        Setup: Policy requires approval for delete operations, operation is query_user
        Expected: Approval not required
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test",
            require_for_operations=["delete_user", "update_payroll"],
        )

        result = manager.determine_if_approval_required(policy, operation="query_user")

        assert result.approval_required is False

    def test_determine_if_approval_required_policy_disabled(self):
        """
        Intent: Verify disabled policy does not trigger approval.

        Setup: Policy disabled, all conditions would match
        Expected: Approval not required, reason indicates policy disabled
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test", require_for_cost_above=10.0, enabled=False
        )

        result = manager.determine_if_approval_required(policy, cost=15.0)

        assert result.approval_required is False
        assert "Policy is disabled" in result.reason

    def test_determine_if_approval_required_multiple_conditions_first_match_wins(self):
        """
        Intent: Verify first matching condition triggers approval.

        Setup: Policy with cost and environment conditions, cost matches first
        Expected: Approval required with cost-based reason
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test",
            require_for_cost_above=10.0,
            require_for_environments=["production"],
        )

        result = manager.determine_if_approval_required(
            policy, cost=15.0, environment="production"
        )

        assert result.approval_required is True
        assert "Cost exceeds threshold" in result.reason  # Cost checked first

    def test_determine_if_approval_required_no_conditions_match(self):
        """
        Intent: Verify no approval required when no conditions match.

        Setup: Policy with cost threshold, cost is within limit
        Expected: Approval not required
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(external_agent_id="test", require_for_cost_above=10.0)

        result = manager.determine_if_approval_required(policy, cost=5.0)

        assert result.approval_required is False
        assert result.policy == policy  # Policy still included for reference

    @pytest.mark.asyncio
    async def test_request_approval_creates_request_with_team_lead_approvers(self):
        """
        Intent: Verify approval request creation routes to team lead.

        Setup: Policy with TEAM_LEAD approval level
        Expected: Approval request created with team lead as approver
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test_agent", approval_level=ApprovalLevel.TEAM_LEAD
        )

        approval_id = await manager.request_approval(
            external_agent_id="test_agent",
            requested_by="user-123",
            policy=policy,
            metadata={"cost": 15.0, "environment": "production"},
        )

        assert approval_id.startswith("approval-test_agent-")

    @pytest.mark.asyncio
    async def test_request_approval_creates_request_with_admin_approvers(self):
        """
        Intent: Verify approval request creation routes to admins.

        Setup: Policy with ADMIN approval level
        Expected: Approval request created with admins as approvers
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test_agent", approval_level=ApprovalLevel.ADMIN
        )

        approval_id = await manager.request_approval(
            external_agent_id="test_agent", requested_by="user-123", policy=policy
        )

        assert approval_id.startswith("approval-test_agent-")

    @pytest.mark.asyncio
    async def test_request_approval_creates_request_with_custom_approvers(self):
        """
        Intent: Verify approval request creation uses custom approver list.

        Setup: Policy with CUSTOM approval level and custom approvers
        Expected: Approval request created with custom approvers
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        policy = ApprovalPolicy(
            external_agent_id="test_agent",
            approval_level=ApprovalLevel.CUSTOM,
            custom_approvers=["approver-1", "approver-2"],
        )

        approval_id = await manager.request_approval(
            external_agent_id="test_agent", requested_by="user-123", policy=policy
        )

        assert approval_id.startswith("approval-test_agent-")

    @pytest.mark.asyncio
    async def test_approve_request_updates_status_to_approved(self):
        """
        Intent: Verify approve_request updates status correctly.

        Setup: Pending approval request
        Expected: Status updated to APPROVED, approver recorded, timestamp set
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        # Create mock approval request (in real implementation, would come from DB)
        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        # Mock _load_approval_request to return our test request
        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        result = await manager.approve_request("approval-123", "approver-456")

        assert result.status == ApprovalStatus.APPROVED
        assert result.approved_by == "approver-456"
        assert result.approved_at is not None

    @pytest.mark.asyncio
    async def test_approve_request_rejects_unauthorized_approver(self):
        """
        Intent: Verify only authorized approvers can approve.

        Setup: Pending approval request with specific approver
        Expected: ValueError raised when unauthorized user tries to approve
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        with pytest.raises(ValueError) as exc_info:
            await manager.approve_request("approval-123", "unauthorized-999")

        assert "not authorized to approve" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_approve_request_rejects_non_pending_request(self):
        """
        Intent: Verify only pending requests can be approved.

        Setup: Already approved request
        Expected: ValueError raised
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.APPROVED,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        with pytest.raises(ValueError) as exc_info:
            await manager.approve_request("approval-123", "approver-456")

        assert "not pending" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reject_request_updates_status_to_rejected(self):
        """
        Intent: Verify reject_request updates status correctly.

        Setup: Pending approval request
        Expected: Status updated to REJECTED, reason recorded
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        result = await manager.reject_request(
            "approval-123", "approver-456", "Cost too high for this operation"
        )

        assert result.status == ApprovalStatus.REJECTED
        assert result.approved_by == "approver-456"  # Records who rejected
        assert result.rejection_reason == "Cost too high for this operation"
        assert result.approved_at is not None

    @pytest.mark.asyncio
    async def test_bypass_approval_requires_justification(self):
        """
        Intent: Verify bypass requires justification.

        Setup: Pending approval request, short justification
        Expected: ValueError raised for insufficient justification
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        with pytest.raises(ValueError) as exc_info:
            await manager.bypass_approval("approval-123", "admin-789", "short")

        assert "Bypass justification required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bypass_approval_updates_status_to_bypassed(self):
        """
        Intent: Verify bypass updates status and records justification.

        Setup: Pending approval request, valid justification
        Expected: Status updated to BYPASSED, justification recorded
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        result = await manager.bypass_approval(
            "approval-123",
            "admin-789",
            "Production outage requires immediate agent invocation",
        )

        assert result.status == ApprovalStatus.BYPASSED
        assert result.approved_by == "admin-789"
        assert (
            result.bypass_justification
            == "Production outage requires immediate agent invocation"
        )
        assert result.approved_at is not None

    @pytest.mark.asyncio
    async def test_check_approval_timeout_updates_status_when_expired(self):
        """
        Intent: Verify timeout check updates status when timeout passed.

        Setup: Pending request with timeout 1 hour ago
        Expected: Status updated to TIMEOUT
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
            timeout_at=datetime.now(timezone.utc)
            - timedelta(hours=1),  # Expired 1 hour ago
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        result = await manager.check_approval_timeout("approval-123")

        assert result.status == ApprovalStatus.TIMEOUT
        assert result.approved_at is not None

    @pytest.mark.asyncio
    async def test_check_approval_timeout_no_update_when_not_expired(self):
        """
        Intent: Verify timeout check doesn't update status when not expired.

        Setup: Pending request with timeout 1 hour in future
        Expected: Status remains PENDING
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
            timeout_at=datetime.now(timezone.utc)
            + timedelta(hours=1),  # Expires in 1 hour
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        result = await manager.check_approval_timeout("approval-123")

        assert result.status == ApprovalStatus.PENDING
        assert result.approved_at is None

    @pytest.mark.asyncio
    async def test_check_approval_timeout_ignores_non_pending_requests(self):
        """
        Intent: Verify timeout check only applies to pending requests.

        Setup: Already approved request
        Expected: Status remains APPROVED, no timeout applied
        """
        manager = ApprovalManager(runtime=AsyncLocalRuntime())

        approval_request = ApprovalRequest(
            id="approval-123",
            external_agent_id="test",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.APPROVED,
            timeout_at=datetime.now(timezone.utc)
            - timedelta(hours=1),  # Would be expired if pending
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        result = await manager.check_approval_timeout("approval-123")

        assert result.status == ApprovalStatus.APPROVED  # Still approved


# Run tests with pytest -xvs tests/unit/trust/governance/test_approval_manager.py
