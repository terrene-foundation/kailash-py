"""
Integration tests for ToolApprovalManager with real Control Protocol.

Tests end-to-end approval flow with real infrastructure (NO MOCKING).

Test Structure:
- Test 1: End-to-end approval flow with Control Protocol
- Test 2: Integration with PermissionPolicy (ASK decisions)
- Test 3: Integration with BudgetEnforcer (budget warnings in prompts)
- Test 4: Complete permission check → approval → execution flow

CRITICAL: These tests use REAL Control Protocol infrastructure.
They should FAIL until ToolApprovalManager is implemented.
"""

import asyncio

import anyio
import pytest
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports.memory import InMemoryTransport
from kaizen.core.autonomy.control.types import ControlResponse
from kaizen.core.autonomy.permissions.budget_enforcer import BudgetEnforcer
from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.policy import PermissionPolicy
from kaizen.core.autonomy.permissions.types import (
    PermissionMode,
    PermissionRule,
    PermissionType,
)

# ──────────────────────────────────────────────────────────
# TEST 1: End-to-End Approval Flow with Control Protocol
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_approval_flow_with_memory_transport():
    """Test end-to-end approval flow with real InMemoryTransport."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup real transport
    transport = InMemoryTransport()
    await transport.connect()

    protocol = ControlProtocol(transport=transport)

    # Start protocol
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        # Create approval manager
        manager = ToolApprovalManager(protocol)

        # Create context
        context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=10.0)
        context.budget_used = 3.0

        # Simulate user approval in background
        async def simulate_user_approval():
            """Simulate user approving the request."""
            await asyncio.sleep(0.1)  # Wait for request to be sent

            # Read request from transport
            messages = []
            async for msg in transport.read_messages():
                messages.append(msg)
                if len(messages) >= 1:
                    break

            # Parse request
            import json

            request_data = json.loads(messages[0])
            request_id = request_data["request_id"]

            # Send approval response
            response = ControlResponse(
                request_id=request_id, data={"approved": True, "action": "once"}
            )
            await transport.write(response.to_json())

        # Launch background approval
        tg.start_soon(simulate_user_approval)

        # Request approval (should succeed)
        approved = await manager.request_approval(
            tool_name="Bash", tool_input={"command": "ls"}, context=context
        )

        # Assertions
        assert approved is True

        # Stop protocol
        await protocol.stop()


# ──────────────────────────────────────────────────────────
# TEST 2: Integration with PermissionPolicy (ASK Decisions)
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_integration_with_permission_policy():
    """Test ToolApprovalManager integration with PermissionPolicy."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup context with ASK rule
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        rules=[
            PermissionRule(
                pattern="Write",
                permission_type=PermissionType.ASK,
                reason="File modifications require approval",
                priority=100,
            )
        ],
    )

    # Create policy
    policy = PermissionPolicy(context)

    # Check permission (should return None, None for ASK)
    decision, reason = policy.check_permission("Write", {"file_path": "/test.txt"}, 0.0)

    assert decision is None
    assert reason is None

    # Now test with real approval manager
    transport = InMemoryTransport()
    await transport.connect()

    protocol = ControlProtocol(transport=transport)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        manager = ToolApprovalManager(protocol)

        # Simulate user approval
        async def simulate_approval():
            await asyncio.sleep(0.1)

            messages = []
            async for msg in transport.read_messages():
                messages.append(msg)
                if len(messages) >= 1:
                    break

            import json

            request_data = json.loads(messages[0])
            request_id = request_data["request_id"]

            response = ControlResponse(
                request_id=request_id, data={"approved": True, "action": "once"}
            )
            await transport.write(response.to_json())

        tg.start_soon(simulate_approval)

        # Request approval (should succeed)
        approved = await manager.request_approval(
            "Write", {"file_path": "/test.txt"}, context
        )

        assert approved is True

        await protocol.stop()


# ──────────────────────────────────────────────────────────
# TEST 3: Integration with BudgetEnforcer (Budget Warnings)
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_integration_with_budget_enforcer():
    """Test that approval prompts include budget warnings from BudgetEnforcer."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup context with budget nearly exhausted
    context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=10.0)
    context.budget_used = 9.5  # 95% used - should trigger warning

    # Estimate cost
    estimated_cost = BudgetEnforcer.estimate_cost("Write", {"file_path": "/test.txt"})

    # Check budget
    has_budget = BudgetEnforcer.has_budget(context, estimated_cost)
    assert has_budget is True  # Still has budget

    # Setup transport
    transport = InMemoryTransport()
    await transport.connect()

    protocol = ControlProtocol(transport=transport)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        manager = ToolApprovalManager(protocol)

        # Capture request
        captured_request = None

        async def capture_request():
            nonlocal captured_request

            await asyncio.sleep(0.1)

            messages = []
            async for msg in transport.read_messages():
                messages.append(msg)
                if len(messages) >= 1:
                    break

            import json

            captured_request = json.loads(messages[0])

            # Send approval
            response = ControlResponse(
                request_id=captured_request["request_id"],
                data={"approved": True, "action": "once"},
            )
            await transport.write(response.to_json())

        tg.start_soon(capture_request)

        # Request approval
        await manager.request_approval("Write", {"file_path": "/test.txt"}, context)

        # Wait for capture
        await asyncio.sleep(0.2)

        # Verify budget info in prompt
        assert captured_request is not None
        prompt = captured_request["data"]["prompt"]

        # Should contain budget usage (9.5) and limit (10.0)
        assert "9.5" in prompt or "9" in prompt
        assert "10.0" in prompt or "10" in prompt

        await protocol.stop()


# ──────────────────────────────────────────────────────────
# TEST 4: Complete Permission Check → Approval → Execution Flow
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_permission_approval_flow():
    """Test complete flow: permission check → approval request → execution."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup context
    context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=20.0)

    # Create policy
    policy = PermissionPolicy(context)

    # Setup transport
    transport = InMemoryTransport()
    await transport.connect()

    protocol = ControlProtocol(transport=transport)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        manager = ToolApprovalManager(protocol)

        # STEP 1: Check permission (should ask for risky tool)
        tool_name = "Bash"
        tool_input = {"command": "echo test"}
        estimated_cost = BudgetEnforcer.estimate_cost(tool_name, tool_input)

        decision, reason = policy.check_permission(
            tool_name, tool_input, estimated_cost
        )

        # Should return (None, None) for ASK
        assert decision is None
        assert reason is None

        # STEP 2: Request approval
        async def simulate_approval():
            await asyncio.sleep(0.1)

            messages = []
            async for msg in transport.read_messages():
                messages.append(msg)
                if len(messages) >= 1:
                    break

            import json

            request_data = json.loads(messages[0])
            request_id = request_data["request_id"]

            # User approves
            response = ControlResponse(
                request_id=request_id, data={"approved": True, "action": "once"}
            )
            await transport.write(response.to_json())

        tg.start_soon(simulate_approval)

        approved = await manager.request_approval(tool_name, tool_input, context)

        # Should be approved
        assert approved is True

        # STEP 3: Record usage
        actual_cost = 0.01  # Bash command cost
        BudgetEnforcer.record_usage(context, tool_name, actual_cost)

        # Verify usage recorded
        assert context.budget_used == actual_cost
        assert context.tool_usage_count[tool_name] == 1

        await protocol.stop()
