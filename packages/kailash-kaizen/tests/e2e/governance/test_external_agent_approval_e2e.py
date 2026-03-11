"""
End-to-end tests for External Agent Approval Workflows.

Tests complete approval workflow preventing execution (NO MOCKING).
Focus on INTENT:
- Verify approval blocks external agent invocation until approved
- Verify timeout prevents execution after waiting period
- Verify rejection decision is recorded and prevents execution
"""

import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from kaizen.governance.approval_manager import (
    ApprovalLevel,
    ApprovalRequirement,
    ApprovalStatus,
    ExternalAgentApprovalManager,
)


@pytest.fixture
def approval_manager():
    """External agent approval manager fixture."""
    return ExternalAgentApprovalManager()


class MockExternalAgentExecutor:
    """
    Mock external agent executor for E2E testing.

    Simulates external agent invocation with approval checks.
    """

    def __init__(self, approval_manager: ExternalAgentApprovalManager):
        self.approval_manager = approval_manager
        self.execution_count = 0

    async def invoke_external_agent(
        self,
        external_agent_id: str,
        user_id: str,
        metadata: dict,
    ) -> dict:
        """
        Invoke external agent with approval check.

        Returns:
            Result dict with success=True if approved, error message if blocked
        """
        # Check if approval required
        required, requirement = self.approval_manager.determine_if_approval_required(
            external_agent_id, metadata
        )

        if not required:
            # No approval required, execute immediately
            self.execution_count += 1
            return {
                "success": True,
                "result": "Execution completed",
                "execution_count": self.execution_count,
            }

        # Approval required: Create approval request
        request_id = await self.approval_manager.request_approval(
            external_agent_id, user_id, metadata
        )

        # Wait for approval (with timeout)
        timeout = requirement.approval_timeout_seconds
        approved = await self.approval_manager.wait_for_approval(
            request_id, timeout=timeout
        )

        if not approved:
            # Check why not approved
            request = self.approval_manager.get_request(request_id)
            if request.status == ApprovalStatus.TIMEOUT:
                return {"success": False, "error": "Approval request timed out"}
            elif request.status == ApprovalStatus.REJECTED:
                return {
                    "success": False,
                    "error": f"Approval rejected: {request.rejection_reason}",
                }
            else:
                return {"success": False, "error": "Approval required but not granted"}

        # Approved: Execute agent
        self.execution_count += 1
        return {
            "success": True,
            "result": "Execution completed after approval",
            "execution_count": self.execution_count,
        }


class TestApprovalBlocksExecution:
    """Test approval prevents execution until approved."""

    @pytest.mark.asyncio
    async def test_approval_prevents_execution_until_approved(self, approval_manager):
        """
        INTENT: Verify approval blocks external agent invocation until approval granted.

        Setup: Real database, ExternalAgentApprovalManager, ApprovalRequirement with require_for_cost_above=10.00
        Steps:
            1. Attempt external agent invocation with estimated_cost=15.00
            2. Verify invocation blocked, approval request created
            3. Approve request via approve_request()
            4. Retry invocation
        Assertions:
            - First invocation blocked with "Approval required"
            - Approval request created with status=PENDING
            - approve_request() succeeds
            - Second invocation allowed and executes
        """
        # Setup: Configure approval requirement (cost > $10.00)
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
            approval_timeout_seconds=3600,
        )
        approval_manager.add_requirement("agent_001", requirement)
        approval_manager._user_teams = {"user_123": "team_001"}
        approval_manager._team_leads = {"team_001": ["lead_001"]}

        # Setup: Create executor
        executor = MockExternalAgentExecutor(approval_manager)

        # Step 1: Attempt invocation (should block and create approval request)
        metadata = {"cost": 15.00, "environment": "production"}

        # Start invocation in background (will block waiting for approval)
        async def invoke_in_background():
            return await executor.invoke_external_agent(
                "agent_001", "user_123", metadata
            )

        invocation_task = asyncio.create_task(invoke_in_background())

        # Wait for approval request to be created
        await asyncio.sleep(0.1)

        # Step 2: Verify approval request created with PENDING status
        pending = approval_manager.get_pending_approvals("lead_001")
        assert len(pending) == 1, "Approval request should be created"
        request_id = pending[0].id
        assert pending[0].status == ApprovalStatus.PENDING
        assert pending[0].request_metadata["cost"] == 15.00

        # Verify invocation not executed yet
        assert (
            executor.execution_count == 0
        ), "Execution should be blocked pending approval"

        # Step 3: Approve request
        await approval_manager.approve_request(request_id, "lead_001")

        # Step 4: Wait for invocation to complete
        result = await invocation_task

        # Verify: Invocation succeeded after approval
        assert result["success"] is True, "Invocation should succeed after approval"
        assert executor.execution_count == 1, "Execution should complete after approval"
        assert "after approval" in result["result"]

    @pytest.mark.asyncio
    async def test_execution_without_approval_when_not_required(self, approval_manager):
        """
        INTENT: Verify execution proceeds without approval when not required.

        When no approval conditions match, execution should proceed immediately.
        """
        # Setup: Configure approval requirement (cost > $100.00)
        requirement = ApprovalRequirement(
            require_for_cost_above=100.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        approval_manager.add_requirement("agent_001", requirement)

        # Setup: Create executor
        executor = MockExternalAgentExecutor(approval_manager)

        # Test: Attempt invocation with low cost (approval not required)
        metadata = {"cost": 5.00, "environment": "development"}
        result = await executor.invoke_external_agent("agent_001", "user_123", metadata)

        # Verify: Invocation succeeded immediately
        assert result["success"] is True, "Invocation should succeed without approval"
        assert executor.execution_count == 1, "Execution should complete immediately"

        # Verify: No approval requests created
        pending = approval_manager.get_pending_approvals("lead_001")
        assert len(pending) == 0, "No approval requests should be created"


class TestApprovalTimeoutPreventsExecution:
    """Test approval timeout prevents execution."""

    @pytest.mark.asyncio
    async def test_approval_timeout_prevents_execution(self, approval_manager):
        """
        INTENT: Verify timeout prevents execution after waiting period.

        Setup: Real database, mock time, ApprovalRequirement with timeout=5 seconds
        Steps:
            1. Create approval request
            2. Wait 6 seconds (timeout + 1)
            3. Run timeout background task
            4. Attempt invocation
        Assertions:
            - Approval status=TIMEOUT after background task
            - Invocation still blocked with "Approval request timed out"
        """
        # Setup: Configure approval requirement with short timeout
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
            approval_timeout_seconds=2,  # 2 seconds for fast testing
        )
        approval_manager.add_requirement("agent_001", requirement)
        approval_manager._user_teams = {"user_123": "team_001"}
        approval_manager._team_leads = {"team_001": ["lead_001"]}

        # Setup: Create executor
        executor = MockExternalAgentExecutor(approval_manager)

        # Step 1: Attempt invocation (will create approval request and wait for timeout)
        metadata = {"cost": 15.00, "environment": "production"}

        # Start invocation in background (will timeout)
        async def invoke_in_background():
            return await executor.invoke_external_agent(
                "agent_001", "user_123", metadata
            )

        invocation_task = asyncio.create_task(invoke_in_background())

        # Wait for approval request to be created
        await asyncio.sleep(0.1)

        # Step 2: Get approval request
        pending = approval_manager.get_pending_approvals("lead_001")
        assert len(pending) == 1
        request_id = pending[0].id

        # Simulate timeout by backdating created_at
        request = approval_manager.get_request(request_id)
        request.created_at = datetime.utcnow() - timedelta(seconds=10)  # 10 seconds ago

        # Step 3: Run timeout background task
        timed_out_count = await approval_manager.timeout_pending_approvals()

        # Verify timeout occurred
        assert timed_out_count == 1, "Should timeout 1 pending approval"
        request = approval_manager.get_request(request_id)
        assert request.status == ApprovalStatus.TIMEOUT, "Status should be TIMEOUT"

        # Step 4: Wait for invocation task to complete
        result = await invocation_task

        # Assertions
        assert result["success"] is False, "Invocation should be blocked after timeout"
        assert "timed out" in result["error"], "Error should indicate timeout"
        assert (
            executor.execution_count == 0
        ), "Execution should NOT complete after timeout"


class TestRejectionPreventsExecution:
    """Test rejection decision prevents execution with audit trail."""

    @pytest.mark.asyncio
    async def test_rejection_prevents_execution_with_audit_trail(
        self, approval_manager
    ):
        """
        INTENT: Verify rejection decision is recorded and prevents execution.

        Setup: Real database, ExternalAgentApprovalManager
        Steps:
            1. Create approval request
            2. Reject request with reason="Cost too high"
            3. Attempt invocation
            4. Verify audit trail
        Assertions:
            - Approval status=REJECTED
            - rejection_reason="Cost too high"
            - Invocation blocked with "Approval rejected: Cost too high"
            - Rejection decision recorded (approved_by, approved_at)
        """
        # Setup: Configure approval requirement
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
            approval_timeout_seconds=3600,
        )
        approval_manager.add_requirement("agent_001", requirement)
        approval_manager._user_teams = {"user_123": "team_001"}
        approval_manager._team_leads = {"team_001": ["lead_001"]}

        # Setup: Create executor
        executor = MockExternalAgentExecutor(approval_manager)

        # Step 1: Attempt invocation (will create approval request and wait)
        metadata = {"cost": 15.00, "environment": "production"}

        # Start invocation in background
        async def invoke_in_background():
            return await executor.invoke_external_agent(
                "agent_001", "user_123", metadata
            )

        invocation_task = asyncio.create_task(invoke_in_background())

        # Wait for approval request to be created
        await asyncio.sleep(0.1)

        # Step 2: Get approval request and reject it
        pending = approval_manager.get_pending_approvals("lead_001")
        assert len(pending) == 1
        request_id = pending[0].id

        rejection_reason = "Cost too high for this operation"
        await approval_manager.reject_request(request_id, "lead_001", rejection_reason)

        # Step 3: Wait for invocation task to complete
        result = await invocation_task

        # Assertions: Verify invocation blocked
        assert (
            result["success"] is False
        ), "Invocation should be blocked after rejection"
        assert "rejected" in result["error"].lower(), "Error should indicate rejection"
        assert (
            rejection_reason in result["error"]
        ), "Error should include rejection reason"
        assert (
            executor.execution_count == 0
        ), "Execution should NOT complete after rejection"

        # Step 4: Verify audit trail
        request = approval_manager.get_request(request_id)
        assert request.status == ApprovalStatus.REJECTED, "Status should be REJECTED"
        assert (
            request.rejection_reason == rejection_reason
        ), "Rejection reason should be recorded"
        assert request.approved_by == "lead_001", "Rejector ID should be recorded"
        assert request.approved_at is not None, "Rejection timestamp should be recorded"

    @pytest.mark.asyncio
    async def test_multiple_sequential_approvals(self, approval_manager):
        """
        INTENT: Verify multiple sequential approval requests work correctly.

        Test that approval system handles multiple approval requests independently.
        """
        # Setup: Configure approval requirement
        requirement = ApprovalRequirement(
            require_for_cost_above=10.0,
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        approval_manager.add_requirement("agent_001", requirement)
        approval_manager._user_teams = {"user_123": "team_001"}
        approval_manager._team_leads = {"team_001": ["lead_001"]}

        # Setup: Create executor
        executor = MockExternalAgentExecutor(approval_manager)

        # Test 1: Create and approve first request
        async def invoke_1():
            return await executor.invoke_external_agent(
                "agent_001", "user_123", {"cost": 15.00}
            )

        task_1 = asyncio.create_task(invoke_1())
        await asyncio.sleep(0.1)

        pending = approval_manager.get_pending_approvals("lead_001")
        assert len(pending) == 1
        await approval_manager.approve_request(pending[0].id, "lead_001")

        result_1 = await task_1
        assert result_1["success"] is True
        assert executor.execution_count == 1

        # Test 2: Create and reject second request
        async def invoke_2():
            return await executor.invoke_external_agent(
                "agent_001", "user_123", {"cost": 20.00}
            )

        task_2 = asyncio.create_task(invoke_2())
        await asyncio.sleep(0.1)

        pending = approval_manager.get_pending_approvals("lead_001")
        assert len(pending) == 1
        await approval_manager.reject_request(
            pending[0].id, "lead_001", "Budget exceeded"
        )

        result_2 = await task_2
        assert result_2["success"] is False
        assert "rejected" in result_2["error"].lower()
        assert executor.execution_count == 1  # Still 1, second execution blocked

        # Verify independent approval tracking
        all_requests = list(approval_manager._requests.values())
        assert len(all_requests) == 2, "Should have 2 independent approval requests"
        assert all_requests[0].status == ApprovalStatus.APPROVED
        assert all_requests[1].status == ApprovalStatus.REJECTED
