"""
Unit tests for ToolApprovalManager.

Tests approval prompt generation, Control Protocol integration, and approval flow.

Test Structure:
- Tests 1-3: Prompt generation for different tool types (Bash, Write, Read)
- Tests 4-6: Approval request flow with Control Protocol
- Tests 7-9: "Approve All" mode handling
- Tests 10-12: Error handling and timeouts

CRITICAL: These tests are written FIRST (TDD red phase).
They should FAIL until ToolApprovalManager is implemented.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from kaizen.core.autonomy.control.types import ControlResponse
from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.types import PermissionMode

# ──────────────────────────────────────────────────────────
# TESTS 1-3: Prompt Generation for Different Tool Types
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prompt_generation_bash():
    """Test approval prompt generation for Bash tool."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup
    mock_protocol = MagicMock()
    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Bash"
    tool_input = {"command": "rm -rf /tmp/test"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=10.0)
    context.budget_used = 2.5

    # Generate prompt
    prompt = manager._generate_approval_prompt(tool_name, tool_input, context)

    # Assertions
    assert "Bash" in prompt or "bash" in prompt
    assert "rm -rf /tmp/test" in prompt
    assert "system" in prompt.lower() or "risky" in prompt.lower()
    assert "2.5" in prompt  # Budget used
    assert "10.0" in prompt or "10" in prompt  # Budget limit


@pytest.mark.asyncio
async def test_prompt_generation_write():
    """Test approval prompt generation for Write/Edit tools."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup
    mock_protocol = MagicMock()
    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Write"
    tool_input = {"file_path": "/src/app.py", "content": "print('hello')"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=5.0)
    context.budget_used = 1.2

    # Generate prompt
    prompt = manager._generate_approval_prompt(tool_name, tool_input, context)

    # Assertions
    assert "Write" in prompt or "write" in prompt
    assert "/src/app.py" in prompt
    assert "file" in prompt.lower() or "codebase" in prompt.lower()
    assert "1.2" in prompt  # Budget used
    assert "5.0" in prompt or "5" in prompt  # Budget limit


@pytest.mark.asyncio
async def test_prompt_generation_generic():
    """Test approval prompt generation for generic tools."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup
    mock_protocol = MagicMock()
    manager = ToolApprovalManager(mock_protocol)

    tool_name = "CustomTool"
    tool_input = {"param1": "value1", "param2": "value2"}
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT, budget_limit=None  # Unlimited budget
    )

    # Generate prompt
    prompt = manager._generate_approval_prompt(tool_name, tool_input, context)

    # Assertions
    assert "CustomTool" in prompt
    assert "unlimited" in prompt.lower() or context.budget_limit is None
    assert len(prompt) > 0


# ──────────────────────────────────────────────────────────
# TESTS 4-6: Approval Request Flow with Control Protocol
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approval_request_approved():
    """Test approval request when user approves."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-123", data={"approved": True, "action": "once"}
    )
    mock_protocol.send_request = AsyncMock(return_value=mock_response)

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Bash"
    tool_input = {"command": "ls"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Request approval
    approved = await manager.request_approval(tool_name, tool_input, context)

    # Assertions
    assert approved is True
    mock_protocol.send_request.assert_called_once()

    # Verify request structure
    call_args = mock_protocol.send_request.call_args
    request = call_args[0][0]  # First positional arg
    assert request.type == "approval"
    assert request.data["tool_name"] == "Bash"


@pytest.mark.asyncio
async def test_approval_request_denied():
    """Test approval request when user denies."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-456", data={"approved": False, "action": "once"}
    )
    mock_protocol.send_request = AsyncMock(return_value=mock_response)

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Write"
    tool_input = {"file_path": "/test.txt"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Request approval
    approved = await manager.request_approval(tool_name, tool_input, context)

    # Assertions
    assert approved is False
    mock_protocol.send_request.assert_called_once()


@pytest.mark.asyncio
async def test_approval_request_with_budget_info():
    """Test that approval prompts include budget information."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-789", data={"approved": True, "action": "once"}
    )
    mock_protocol.send_request = AsyncMock(return_value=mock_response)

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Bash"
    tool_input = {"command": "echo test"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=20.0)
    context.budget_used = 15.0

    # Request approval
    await manager.request_approval(tool_name, tool_input, context)

    # Verify budget info in prompt
    call_args = mock_protocol.send_request.call_args
    request = call_args[0][0]
    prompt = request.data["prompt"]

    assert "15.0" in prompt or "15" in prompt  # Budget used
    assert "20.0" in prompt or "20" in prompt  # Budget limit


# ──────────────────────────────────────────────────────────
# TESTS 7-9: "Approve All" Mode Handling
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_all_adds_to_allowed_tools():
    """Test that 'Approve All' adds tool to allowed_tools."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-all-1", data={"approved": True, "action": "all"}
    )
    mock_protocol.send_request = AsyncMock(return_value=mock_response)

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Bash"
    tool_input = {"command": "ls"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Verify tool not in allowed_tools before
    assert "Bash" not in context.allowed_tools

    # Request approval
    approved = await manager.request_approval(tool_name, tool_input, context)

    # Assertions
    assert approved is True
    assert "Bash" in context.allowed_tools


@pytest.mark.asyncio
async def test_deny_all_adds_to_disallowed_tools():
    """Test that 'Deny All' adds tool to disallowed_tools."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-all-2", data={"approved": False, "action": "all"}
    )
    mock_protocol.send_request = AsyncMock(return_value=mock_response)

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Write"
    tool_input = {"file_path": "/test.txt"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Verify tool not in disallowed_tools before
    assert "Write" not in context.denied_tools

    # Request approval
    approved = await manager.request_approval(tool_name, tool_input, context)

    # Assertions
    assert approved is False
    assert "Write" in context.denied_tools


@pytest.mark.asyncio
async def test_approve_once_does_not_modify_context():
    """Test that 'Approve Once' does not modify allowed/disallowed tools."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-once", data={"approved": True, "action": "once"}
    )
    mock_protocol.send_request = AsyncMock(return_value=mock_response)

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Bash"
    tool_input = {"command": "pwd"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Request approval
    approved = await manager.request_approval(tool_name, tool_input, context)

    # Assertions
    assert approved is True
    assert "Bash" not in context.allowed_tools
    assert "Bash" not in context.denied_tools


# ──────────────────────────────────────────────────────────
# TESTS 10-12: Error Handling and Timeouts
# ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approval_timeout_returns_false():
    """Test that timeout during approval returns False (fail-closed)."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol that times out
    mock_protocol = AsyncMock()
    mock_protocol.send_request = AsyncMock(
        side_effect=TimeoutError("Request timed out")
    )

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Bash"
    tool_input = {"command": "sleep 100"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Request approval (should fail-closed on timeout)
    approved = await manager.request_approval(tool_name, tool_input, context)

    # Assertions
    assert approved is False


@pytest.mark.asyncio
async def test_approval_protocol_error_returns_false():
    """Test that protocol errors return False (fail-closed)."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol that raises error
    mock_protocol = AsyncMock()
    mock_protocol.send_request = AsyncMock(
        side_effect=ConnectionError("Protocol failed")
    )

    manager = ToolApprovalManager(mock_protocol)

    tool_name = "Write"
    tool_input = {"file_path": "/test.txt"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Request approval (should fail-closed on error)
    approved = await manager.request_approval(tool_name, tool_input, context)

    # Assertions
    assert approved is False


@pytest.mark.asyncio
async def test_approval_with_risk_warnings():
    """Test that dangerous operations include risk warnings in prompts."""
    from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-risk", data={"approved": True, "action": "once"}
    )
    mock_protocol.send_request = AsyncMock(return_value=mock_response)

    manager = ToolApprovalManager(mock_protocol)

    # Test with dangerous bash command
    tool_name = "Bash"
    tool_input = {"command": "rm -rf /"}
    context = ExecutionContext(mode=PermissionMode.DEFAULT)

    # Request approval
    await manager.request_approval(tool_name, tool_input, context)

    # Verify risk warning in prompt
    call_args = mock_protocol.send_request.call_args
    request = call_args[0][0]
    prompt = request.data["prompt"]

    # Should contain warning about system changes
    assert any(
        word in prompt.lower()
        for word in ["warning", "danger", "risky", "caution", "⚠️", "system"]
    )
