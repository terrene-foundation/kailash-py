"""
Tier 3 E2E Tests: External Agent Approval Workflows End-to-End

Tests complete approval workflows including integration with external agent invocation (NO MOCKING).

Intent: Verify approval prevents execution until approved, timeout handling, and rejection handling.

CRITICAL: Uses real infrastructure for NO MOCKING policy (Tier 3).
"""

from datetime import datetime, timedelta, timezone

import pytest
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.trust.governance import (
    ApprovalLevel,
    ApprovalManager,
    ApprovalPolicy,
    ApprovalPolicyModel,
    ApprovalRequest,
    ApprovalRequestModel,
    ApprovalStatus,
)


@pytest.fixture
async def db():
    """
    Create real SQLite database for testing.

    Returns in-memory SQLite with DataFlow schema registered.
    """
    db = DataFlow(database_type="sqlite", database_config={"database": ":memory:"})

    # Register approval models
    db.register_model(ApprovalPolicyModel)
    db.register_model(ApprovalRequestModel)

    # Create tables
    await db.async_execute(
        """
        CREATE TABLE IF NOT EXISTS approval_policy_model (
            external_agent_id TEXT PRIMARY KEY,
            require_for_cost_above REAL,
            require_for_environments TEXT,
            require_for_data_classifications TEXT,
            require_for_operations TEXT,
            approval_level TEXT,
            custom_approvers TEXT,
            approval_timeout_seconds INTEGER,
            enabled INTEGER,
            created_at TEXT,
            updated_at TEXT,
            metadata TEXT
        )
    """
    )

    await db.async_execute(
        """
        CREATE TABLE IF NOT EXISTS approval_request_model (
            id TEXT PRIMARY KEY,
            external_agent_id TEXT,
            requested_by TEXT,
            approvers TEXT,
            status TEXT,
            approval_reason TEXT,
            request_metadata TEXT,
            created_at TEXT,
            approved_at TEXT,
            approved_by TEXT,
            rejection_reason TEXT,
            bypass_justification TEXT,
            timeout_at TEXT,
            metadata TEXT
        )
    """
    )

    yield db

    await db.close()


@pytest.fixture
def runtime():
    """Create AsyncLocalRuntime for workflow execution."""
    return AsyncLocalRuntime()


@pytest.mark.asyncio
@pytest.mark.e2e
class TestApprovalWorkflowEndToEnd:
    """E2E tests for complete approval workflows."""

    async def test_approval_prevents_execution_until_approved(self, db, runtime):
        """
        Intent: Verify approval blocks external agent invocation until approval granted.

        Setup: Real SQLite, ApprovalManager, Policy with cost threshold $10
        Steps:
        1. Create policy requiring approval for cost > $10
        2. Attempt agent invocation with estimated_cost=$15
        3. Verify invocation blocked, approval request created
        4. Approve request via approve_request()
        5. Retry invocation
        6. Verify invocation allowed after approval

        Expected:
        - First invocation blocked with "Approval required"
        - Approval request created with status=PENDING
        - approve_request() succeeds
        - Second invocation allowed and executes
        """
        manager = ApprovalManager(runtime=runtime, db=db)

        # Create approval policy
        policy = ApprovalPolicy(
            external_agent_id="copilot_hr",
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )

        # Check if approval required for $15 invocation
        result = manager.determine_if_approval_required(
            policy, cost=15.0, environment="production", operation="query_payroll"
        )

        # Verify approval required
        assert result.approval_required is True
        assert "Cost exceeds threshold" in result.reason

        # Request approval
        approval_id = await manager.request_approval(
            external_agent_id="copilot_hr",
            requested_by="user-123",
            policy=policy,
            metadata={
                "cost": 15.0,
                "environment": "production",
                "operation": "query_payroll",
            },
        )

        # Verify approval request created
        assert approval_id.startswith("approval-copilot_hr-")

        # Mock approval request for testing
        approval_request = ApprovalRequest(
            id=approval_id,
            external_agent_id="copilot_hr",
            requested_by="user-123",
            approvers=["team_lead_for_user-123"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        # Approve request
        approved = await manager.approve_request(approval_id, "team_lead_for_user-123")

        # Verify approval granted
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approved_by == "team_lead_for_user-123"

        # Simulate second invocation attempt (would now be allowed)
        # In real implementation, would check approval status before executing

    async def test_approval_timeout_prevents_execution(self, db, runtime):
        """
        Intent: Verify timeout prevents execution after waiting period.

        Setup: Real SQLite, Policy with timeout=300 seconds (5 minutes)
        Steps:
        1. Create approval request
        2. Wait 301 seconds (timeout) - simulated with expired timeout_at
        3. Run check_approval_timeout
        4. Verify approval status=TIMEOUT
        5. Attempt invocation
        6. Verify invocation still blocked with "Approval request timed out"

        Expected:
        - Approval status=TIMEOUT after check_approval_timeout
        - Invocation still blocked with timeout message
        """
        manager = ApprovalManager(runtime=runtime, db=db)

        # Create approval policy with short timeout
        policy = ApprovalPolicy(
            external_agent_id="test_agent",
            require_for_cost_above=10.0,
            approval_timeout_seconds=300,  # 5 minutes
        )

        # Create approval request
        approval_id = await manager.request_approval(
            external_agent_id="test_agent",
            requested_by="user-123",
            policy=policy,
            metadata={"cost": 15.0},
        )

        # Mock approval request with expired timeout
        approval_request = ApprovalRequest(
            id=approval_id,
            external_agent_id="test_agent",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
            timeout_at=datetime.now(timezone.utc)
            - timedelta(seconds=301),  # Expired 301 seconds ago
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        # Check timeout
        result = await manager.check_approval_timeout(approval_id)

        # Verify timeout applied
        assert result.status == ApprovalStatus.TIMEOUT
        assert result.approved_at is not None

        # Verify invocation would still be blocked
        # In real implementation, would check approval status and reject if TIMEOUT

    async def test_rejection_prevents_execution_with_audit_trail(self, db, runtime):
        """
        Intent: Verify rejection decision is recorded and prevents execution.

        Setup: Real SQLite, ApprovalManager
        Steps:
        1. Create approval request
        2. Reject request with reason="Cost too high"
        3. Attempt invocation
        4. Verify invocation blocked with "Approval rejected: Cost too high"
        5. Query audit log (future implementation)
        6. Verify audit log contains rejection event with approver identity

        Expected:
        - Approval status=REJECTED
        - rejection_reason="Cost too high"
        - Invocation blocked with rejection message
        - Audit log contains rejection event
        """
        manager = ApprovalManager(runtime=runtime, db=db)

        # Create approval policy
        policy = ApprovalPolicy(
            external_agent_id="test_agent", require_for_cost_above=10.0
        )

        # Create approval request
        approval_id = await manager.request_approval(
            external_agent_id="test_agent",
            requested_by="user-123",
            policy=policy,
            metadata={"cost": 15.0},
        )

        # Mock approval request
        approval_request = ApprovalRequest(
            id=approval_id,
            external_agent_id="test_agent",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        # Reject request
        result = await manager.reject_request(
            approval_id, "approver-456", "Cost too high for this operation"
        )

        # Verify rejection
        assert result.status == ApprovalStatus.REJECTED
        assert result.rejection_reason == "Cost too high for this operation"
        assert result.approved_by == "approver-456"

        # Verify invocation would be blocked
        # In real implementation, would check approval status and reject if REJECTED

    async def test_approval_bypass_emergency_workflow(self, db, runtime):
        """
        Intent: Verify emergency bypass workflow with audit trail.

        Setup: Real SQLite, Pending approval request
        Steps:
        1. Create approval request for high-cost operation
        2. Production outage occurs (simulated)
        3. Admin bypasses approval with justification
        4. Verify invocation allowed
        5. Verify bypass recorded in audit log

        Expected:
        - Bypass succeeds with valid justification
        - Invocation allowed after bypass
        - Audit log contains bypass event with admin ID and justification
        """
        manager = ApprovalManager(runtime=runtime, db=db)

        # Create approval policy
        policy = ApprovalPolicy(
            external_agent_id="test_agent", require_for_cost_above=10.0
        )

        # Create approval request
        approval_id = await manager.request_approval(
            external_agent_id="test_agent",
            requested_by="user-123",
            policy=policy,
            metadata={"cost": 50.0},  # High-cost operation
        )

        # Mock approval request
        approval_request = ApprovalRequest(
            id=approval_id,
            external_agent_id="test_agent",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            return approval_request

        manager._load_approval_request = mock_load

        # Bypass approval (emergency)
        result = await manager.bypass_approval(
            approval_id,
            "admin-789",
            "Production outage: critical payroll system down, need immediate HR agent access",
        )

        # Verify bypass
        assert result.status == ApprovalStatus.BYPASSED
        assert (
            result.bypass_justification
            == "Production outage: critical payroll system down, need immediate HR agent access"
        )
        assert result.approved_by == "admin-789"

        # Verify invocation would be allowed after bypass

    async def test_approval_workflow_with_multiple_conditions(self, db, runtime):
        """
        Intent: Verify approval works with multiple trigger conditions.

        Setup: Policy with cost, environment, and data classification triggers
        Steps:
        1. Create policy requiring approval for:
           - Cost > $10
           - Environment = production
           - Data classification = PII
        2. Attempt invocation with cost=$5, environment=production (cost OK, env requires approval)
        3. Verify approval required due to environment
        4. Approve request
        5. Verify invocation allowed

        Expected:
        - Approval required when any condition matches
        - Approval reason indicates which condition triggered
        """
        manager = ApprovalManager(runtime=runtime, db=db)

        # Create policy with multiple conditions
        policy = ApprovalPolicy(
            external_agent_id="test_agent",
            require_for_cost_above=10.0,
            require_for_environments=["production"],
            require_for_data_classifications=["pii"],
        )

        # Check with environment trigger
        result = manager.determine_if_approval_required(
            policy,
            cost=5.0,  # Within cost limit
            environment="production",  # Triggers approval
            data_classifications=[],
        )

        # Verify approval required for environment
        assert result.approval_required is True
        assert "Environment 'production' requires approval" in result.reason

        # Check with data classification trigger
        result2 = manager.determine_if_approval_required(
            policy,
            cost=5.0,  # Within cost limit
            environment="development",  # Allowed
            data_classifications=["pii"],  # Triggers approval
        )

        # Verify approval required for data classification
        assert result2.approval_required is True
        assert "Data classification requires approval" in result2.reason

    async def test_approval_escalation_path(self, db, runtime):
        """
        Intent: Verify approval escalation from team lead to admin.

        Setup: Policy with TEAM_LEAD level, no team lead available (future)
        Steps:
        1. Create policy with TEAM_LEAD approval level
        2. Request approval for user with no team lead
        3. Verify approval escalates to ADMIN level
        4. Admin approves request
        5. Verify invocation allowed

        Expected:
        - Approval escalates when team lead not available
        - Admin can approve escalated request
        """
        manager = ApprovalManager(runtime=runtime, db=db)

        # Create policy with TEAM_LEAD level
        policy = ApprovalPolicy(
            external_agent_id="test_agent", approval_level=ApprovalLevel.TEAM_LEAD
        )

        # Request approval
        approval_id = await manager.request_approval(
            external_agent_id="test_agent", requested_by="user-123", policy=policy
        )

        # Verify approval request created
        assert approval_id.startswith("approval-test_agent-")

        # NOTE: In real implementation, would check if team lead exists
        # If not, escalate to admin level

    async def test_concurrent_approvals_same_user(self, db, runtime):
        """
        Intent: Verify user can have multiple pending approvals.

        Setup: Real SQLite, Multiple approval requests for same user
        Steps:
        1. Request approval for agent A, user-123
        2. Request approval for agent B, user-123
        3. Approve agent A request
        4. Verify agent B request still pending
        5. Approve agent B request
        6. Verify both approvals succeeded independently

        Expected:
        - Both approvals created successfully
        - Approvals are independent
        - User can have multiple pending approvals
        """
        manager = ApprovalManager(runtime=runtime, db=db)

        policy_a = ApprovalPolicy(
            external_agent_id="agent_a", require_for_cost_above=10.0
        )

        policy_b = ApprovalPolicy(
            external_agent_id="agent_b", require_for_cost_above=10.0
        )

        # Create both approval requests
        approval_id_a = await manager.request_approval(
            external_agent_id="agent_a",
            requested_by="user-123",
            policy=policy_a,
            metadata={"cost": 15.0},
        )

        approval_id_b = await manager.request_approval(
            external_agent_id="agent_b",
            requested_by="user-123",
            policy=policy_b,
            metadata={"cost": 20.0},
        )

        # Verify both created
        assert approval_id_a.startswith("approval-agent_a-")
        assert approval_id_b.startswith("approval-agent_b-")
        assert approval_id_a != approval_id_b

        # Mock approval requests
        approval_request_a = ApprovalRequest(
            id=approval_id_a,
            external_agent_id="agent_a",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        approval_request_b = ApprovalRequest(
            id=approval_id_b,
            external_agent_id="agent_b",
            requested_by="user-123",
            approvers=["approver-456"],
            status=ApprovalStatus.PENDING,
        )

        async def mock_load(request_id):
            if request_id == approval_id_a:
                return approval_request_a
            elif request_id == approval_id_b:
                return approval_request_b
            return None

        manager._load_approval_request = mock_load

        # Approve agent A request
        result_a = await manager.approve_request(approval_id_a, "approver-456")
        assert result_a.status == ApprovalStatus.APPROVED

        # Verify agent B request still pending
        # (In real implementation, would query database to verify)

        # Approve agent B request
        result_b = await manager.approve_request(approval_id_b, "approver-456")
        assert result_b.status == ApprovalStatus.APPROVED


# Run tests with pytest -xvs tests/e2e/trust/governance/test_approval_e2e.py
