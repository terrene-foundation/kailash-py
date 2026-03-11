"""
Unit Tests for Planning Tools (Tier 1)

Tests EnterPlanModeTool and ExitPlanModeTool for autonomous agents.
Part of TODO-207 ClaudeCodeAgent Full Tool Parity.
"""

import asyncio
from typing import List

import pytest

from kaizen.tools.native.planning_tool import (
    AllowedPrompt,
    EnterPlanModeTool,
    ExitPlanModeTool,
    PlanMode,
    PlanModeManager,
    PlanState,
)
from kaizen.tools.types import DangerLevel, ToolCategory


class TestPlanMode:
    """Tests for PlanMode enum."""

    def test_plan_mode_values(self):
        """Test all plan mode values exist."""
        assert PlanMode.INACTIVE.value == "inactive"
        assert PlanMode.ACTIVE.value == "active"
        assert PlanMode.READY_FOR_APPROVAL.value == "ready_for_approval"
        assert PlanMode.APPROVED.value == "approved"

    def test_plan_mode_from_string(self):
        """Test creating plan mode from string."""
        assert PlanMode("inactive") == PlanMode.INACTIVE
        assert PlanMode("active") == PlanMode.ACTIVE
        assert PlanMode("ready_for_approval") == PlanMode.READY_FOR_APPROVAL
        assert PlanMode("approved") == PlanMode.APPROVED

    def test_invalid_plan_mode_raises(self):
        """Test invalid plan mode raises ValueError."""
        with pytest.raises(ValueError):
            PlanMode("invalid")


class TestAllowedPrompt:
    """Tests for AllowedPrompt dataclass."""

    def test_create_prompt(self):
        """Test creating allowed prompt."""
        prompt = AllowedPrompt(tool="Bash", prompt="run tests")
        assert prompt.tool == "Bash"
        assert prompt.prompt == "run tests"

    def test_to_dict(self):
        """Test converting to dictionary."""
        prompt = AllowedPrompt(tool="Bash", prompt="install deps")
        d = prompt.to_dict()
        assert d == {"tool": "Bash", "prompt": "install deps"}

    def test_from_dict(self):
        """Test creating from dictionary."""
        prompt = AllowedPrompt.from_dict(
            {
                "tool": "Bash",
                "prompt": "run build",
            }
        )
        assert prompt.tool == "Bash"
        assert prompt.prompt == "run build"


class TestPlanState:
    """Tests for PlanState dataclass."""

    def test_default_state(self):
        """Test default plan state."""
        state = PlanState()
        assert state.mode == PlanMode.INACTIVE
        assert state.entered_at is None
        assert state.plan_file is None
        assert state.allowed_prompts == []

    def test_state_with_values(self):
        """Test plan state with values."""
        prompts = [AllowedPrompt("Bash", "test")]
        state = PlanState(
            mode=PlanMode.ACTIVE,
            entered_at="2025-01-01T00:00:00Z",
            plan_file="/tmp/plan.md",
            allowed_prompts=prompts,
        )
        assert state.mode == PlanMode.ACTIVE
        assert state.entered_at == "2025-01-01T00:00:00Z"
        assert state.plan_file == "/tmp/plan.md"
        assert len(state.allowed_prompts) == 1

    def test_to_dict(self):
        """Test converting state to dictionary."""
        state = PlanState(
            mode=PlanMode.ACTIVE,
            entered_at="2025-01-01T00:00:00Z",
            allowed_prompts=[AllowedPrompt("Bash", "test")],
        )
        d = state.to_dict()
        assert d["mode"] == "active"
        assert d["entered_at"] == "2025-01-01T00:00:00Z"
        assert len(d["allowed_prompts"]) == 1


class TestEnterPlanModeTool:
    """Tests for EnterPlanModeTool class."""

    def test_tool_attributes(self):
        """Test tool has required attributes."""
        tool = EnterPlanModeTool()
        assert tool.name == "enter_plan_mode"
        assert tool.description != ""
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.CUSTOM

    def test_get_schema(self):
        """Test schema generation."""
        tool = EnterPlanModeTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert schema["properties"] == {}

    def test_get_full_schema(self):
        """Test full schema for LLM."""
        tool = EnterPlanModeTool()
        schema = tool.get_full_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "enter_plan_mode"

    @pytest.mark.asyncio
    async def test_execute_enters_plan_mode(self):
        """Test executing enters plan mode."""
        tool = EnterPlanModeTool()
        result = await tool.execute()

        assert result.success is True
        assert "plan mode" in result.output.lower()
        assert tool.state.mode == PlanMode.ACTIVE
        assert tool.state.entered_at is not None

    @pytest.mark.asyncio
    async def test_execute_already_in_plan_mode(self):
        """Test executing when already in plan mode."""
        tool = EnterPlanModeTool()

        # Enter first time
        await tool.execute()
        entered_at = tool.state.entered_at

        # Try to enter again
        result = await tool.execute()

        assert result.success is True
        assert "already" in result.output.lower()
        assert tool.state.entered_at == entered_at  # Unchanged

    @pytest.mark.asyncio
    async def test_execute_with_sync_callback(self):
        """Test executing with synchronous callback."""
        callback_called = []

        def callback(state: PlanState):
            callback_called.append(state.mode)

        tool = EnterPlanModeTool(on_enter=callback)
        await tool.execute()

        assert len(callback_called) == 1
        assert callback_called[0] == PlanMode.ACTIVE

    @pytest.mark.asyncio
    async def test_execute_with_async_callback(self):
        """Test executing with asynchronous callback."""
        callback_called = []

        async def callback(state: PlanState):
            await asyncio.sleep(0.001)
            callback_called.append(state.mode)

        tool = EnterPlanModeTool(on_enter=callback)
        await tool.execute()

        assert len(callback_called) == 1
        assert callback_called[0] == PlanMode.ACTIVE

    def test_state_property(self):
        """Test state property."""
        tool = EnterPlanModeTool()
        assert tool.state.mode == PlanMode.INACTIVE

    def test_set_state(self):
        """Test setting shared state."""
        state = PlanState(mode=PlanMode.ACTIVE)
        tool = EnterPlanModeTool()
        tool.set_state(state)
        assert tool.state.mode == PlanMode.ACTIVE


class TestExitPlanModeTool:
    """Tests for ExitPlanModeTool class."""

    def test_tool_attributes(self):
        """Test tool has required attributes."""
        tool = ExitPlanModeTool()
        assert tool.name == "exit_plan_mode"
        assert tool.description != ""
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.CUSTOM

    def test_get_schema(self):
        """Test schema generation."""
        tool = ExitPlanModeTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "allowedPrompts" in schema["properties"]

    def test_get_full_schema(self):
        """Test full schema for LLM."""
        tool = ExitPlanModeTool()
        schema = tool.get_full_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "exit_plan_mode"

    @pytest.mark.asyncio
    async def test_execute_not_in_plan_mode(self):
        """Test executing when not in plan mode."""
        tool = ExitPlanModeTool()
        result = await tool.execute()

        assert result.success is False
        assert "not in plan mode" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_exits_plan_mode(self):
        """Test executing exits plan mode."""
        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool(state=state)

        result = await tool.execute()

        assert result.success is True
        assert "approval" in result.output.lower()
        assert tool.state.mode == PlanMode.READY_FOR_APPROVAL

    @pytest.mark.asyncio
    async def test_execute_with_allowed_prompts(self):
        """Test executing with allowed prompts."""
        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool(state=state)

        result = await tool.execute(
            allowedPrompts=[
                {"tool": "Bash", "prompt": "run tests"},
                {"tool": "Bash", "prompt": "install deps"},
            ]
        )

        assert result.success is True
        assert len(tool.state.allowed_prompts) == 2
        assert tool.state.allowed_prompts[0].prompt == "run tests"

    @pytest.mark.asyncio
    async def test_execute_missing_tool_field(self):
        """Test error when tool field is missing."""
        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool(state=state)

        result = await tool.execute(allowedPrompts=[{"prompt": "run tests"}])

        assert result.success is False
        assert "tool" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_prompt_field(self):
        """Test error when prompt field is missing."""
        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool(state=state)

        result = await tool.execute(allowedPrompts=[{"tool": "Bash"}])

        assert result.success is False
        assert "prompt" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_remote_options(self):
        """Test executing with remote session options."""
        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool(state=state)

        result = await tool.execute(
            pushToRemote=True,
            remoteSessionId="session-123",
            remoteSessionTitle="My Plan",
            remoteSessionUrl="https://example.com/session/123",
        )

        assert result.success is True
        assert result.metadata["push_to_remote"] is True
        assert result.metadata["remote_session_id"] == "session-123"

    @pytest.mark.asyncio
    async def test_execute_with_sync_callback(self):
        """Test executing with synchronous callback."""
        callback_called = []

        def callback(state: PlanState):
            callback_called.append(state.mode)

        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool(on_exit=callback, state=state)
        await tool.execute()

        assert len(callback_called) == 1
        assert callback_called[0] == PlanMode.READY_FOR_APPROVAL

    @pytest.mark.asyncio
    async def test_execute_with_async_callback(self):
        """Test executing with asynchronous callback."""
        callback_called = []

        async def callback(state: PlanState):
            await asyncio.sleep(0.001)
            callback_called.append(state.mode)

        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool(on_exit=callback, state=state)
        await tool.execute()

        assert len(callback_called) == 1
        assert callback_called[0] == PlanMode.READY_FOR_APPROVAL

    def test_state_property(self):
        """Test state property."""
        tool = ExitPlanModeTool()
        assert tool.state.mode == PlanMode.INACTIVE

    def test_set_state(self):
        """Test setting shared state."""
        state = PlanState(mode=PlanMode.ACTIVE)
        tool = ExitPlanModeTool()
        tool.set_state(state)
        assert tool.state.mode == PlanMode.ACTIVE


class TestPlanModeManager:
    """Tests for PlanModeManager class."""

    def test_create_manager(self):
        """Test creating plan mode manager."""
        manager = PlanModeManager()
        assert manager.state.mode == PlanMode.INACTIVE
        assert not manager.is_active
        assert not manager.is_ready_for_approval

    def test_create_enter_tool(self):
        """Test creating enter tool with shared state."""
        manager = PlanModeManager()
        tool = manager.create_enter_tool()
        assert tool.state is manager.state

    def test_create_exit_tool(self):
        """Test creating exit tool with shared state."""
        manager = PlanModeManager()
        tool = manager.create_exit_tool()
        assert tool.state is manager.state

    @pytest.mark.asyncio
    async def test_tools_share_state(self):
        """Test tools share state through manager."""
        manager = PlanModeManager()
        enter_tool = manager.create_enter_tool()
        exit_tool = manager.create_exit_tool()

        # Enter plan mode
        await enter_tool.execute()
        assert manager.is_active
        assert exit_tool.state.mode == PlanMode.ACTIVE

        # Exit plan mode
        await exit_tool.execute()
        assert manager.is_ready_for_approval
        assert enter_tool.state.mode == PlanMode.READY_FOR_APPROVAL

    def test_approve(self):
        """Test approving plan."""
        manager = PlanModeManager()
        manager.state.mode = PlanMode.READY_FOR_APPROVAL
        manager.approve()
        assert manager.state.mode == PlanMode.APPROVED

    def test_approve_not_ready(self):
        """Test approve does nothing if not ready."""
        manager = PlanModeManager()
        manager.approve()
        assert manager.state.mode == PlanMode.INACTIVE  # Unchanged

    def test_reset(self):
        """Test resetting plan mode."""
        manager = PlanModeManager()
        manager.state.mode = PlanMode.ACTIVE
        manager.state.entered_at = "2025-01-01T00:00:00Z"
        manager.reset()
        assert manager.state.mode == PlanMode.INACTIVE
        assert manager.state.entered_at is None

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete plan mode workflow."""
        enter_called = []
        exit_called = []

        def on_enter(state: PlanState):
            enter_called.append(state.mode)

        def on_exit(state: PlanState):
            exit_called.append(state.mode)

        manager = PlanModeManager(on_enter=on_enter, on_exit=on_exit)
        enter_tool = manager.create_enter_tool()
        exit_tool = manager.create_exit_tool()

        # Initial state
        assert manager.state.mode == PlanMode.INACTIVE

        # Enter plan mode
        result = await enter_tool.execute()
        assert result.success
        assert manager.is_active
        assert len(enter_called) == 1

        # Exit plan mode with permissions
        result = await exit_tool.execute(
            allowedPrompts=[{"tool": "Bash", "prompt": "run tests"}]
        )
        assert result.success
        assert manager.is_ready_for_approval
        assert len(exit_called) == 1
        assert len(manager.state.allowed_prompts) == 1

        # Approve
        manager.approve()
        assert manager.state.mode == PlanMode.APPROVED

        # Reset for next planning session
        manager.reset()
        assert manager.state.mode == PlanMode.INACTIVE

    def test_is_safe(self):
        """Test both tools are marked as safe."""
        manager = PlanModeManager()
        enter_tool = manager.create_enter_tool()
        exit_tool = manager.create_exit_tool()
        assert enter_tool.is_safe
        assert exit_tool.is_safe
