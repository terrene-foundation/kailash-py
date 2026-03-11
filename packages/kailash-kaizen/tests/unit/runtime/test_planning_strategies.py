"""
Unit Tests for LocalKaizenAdapter Planning Strategies (Tier 1)

Tests the planning strategy implementations:
- ReAct: Reason-Act-Observe pattern (simple step-by-step)
- PEV: Plan-Execute-Verify pattern (explicit planning phase)

Coverage:
- Strategy selection based on config
- ReAct reasoning in prompts
- PEV plan creation and tracking
- Plan progress through execution
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter
from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    ExecutionState,
    PlanningStrategy,
)
from kaizen.runtime.context import ExecutionContext, ExecutionStatus


class TestReActStrategy:
    """Test ReAct (Reason + Act) strategy."""

    def test_react_is_default_strategy(self):
        """Test ReAct is the default planning strategy."""
        adapter = LocalKaizenAdapter()
        assert adapter.config.planning_strategy == PlanningStrategy.REACT

    def test_react_prompt_includes_reasoning(self):
        """Test ReAct system prompt includes reasoning instructions."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.REACT)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        # ReAct should mention thinking/reasoning and action
        assert "reason" in prompt.lower() or "think" in prompt.lower()
        assert "action" in prompt.lower() or "act" in prompt.lower()

    def test_react_no_explicit_plan(self):
        """Test ReAct doesn't create explicit plan upfront."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.REACT)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        # ReAct should not have a pre-defined plan
        assert len(state.plan) == 0

    @pytest.mark.asyncio
    async def test_react_execution_flow(self):
        """Test ReAct follows reason-act-observe pattern."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.REACT)
        llm_provider = MagicMock()

        responses = [
            {
                "content": "I need to list files first",
                "tool_calls": [{"name": "list_files", "arguments": {"path": "/"}}],
                "usage": {"total_tokens": 50},
            },
            {
                "content": "Now I can see the files",
                "tool_calls": None,
                "usage": {"total_tokens": 30},
            },
        ]
        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            response = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return response

        llm_provider.chat_async = mock_chat

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = []
        tool_registry.execute = AsyncMock(return_value="file1.txt\nfile2.txt")

        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="List files in root", session_id="react-test")
        result = await adapter.execute(context)

        assert result.status == ExecutionStatus.COMPLETE
        assert call_count == 2  # Two LLM calls: reason+act, then observe


class TestPEVStrategy:
    """Test PEV (Plan-Execute-Verify) strategy."""

    def test_pev_strategy_selection(self):
        """Test PEV can be selected via config."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)

        assert adapter.config.planning_strategy == PlanningStrategy.PEV

    def test_pev_prompt_includes_plan_execute_verify(self):
        """Test PEV system prompt includes plan-execute-verify instructions."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        assert "plan" in prompt.lower()
        assert "execute" in prompt.lower() or "action" in prompt.lower()
        assert "verify" in prompt.lower() or "check" in prompt.lower()

    def test_pev_prompt_shows_plan_status(self):
        """Test PEV prompt shows plan progress."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")
        state.plan = ["Step 1: Analyze", "Step 2: Implement", "Step 3: Verify"]
        state.plan_index = 1  # Currently on step 2

        prompt = adapter._build_system_prompt(state)

        # Should show plan progress
        assert "Step 2" in prompt or "current" in prompt.lower()

    def test_has_create_plan_method(self):
        """Test adapter has method to create plan."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_create_plan")
        assert callable(adapter._create_plan)

    def test_has_advance_plan_method(self):
        """Test adapter has method to advance plan."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_advance_plan")
        assert callable(adapter._advance_plan)

    @pytest.mark.asyncio
    async def test_create_plan_generates_steps(self):
        """Test _create_plan generates plan steps from task."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        llm_provider = MagicMock()
        llm_provider.chat_async = AsyncMock(
            return_value={
                "content": """Here's my plan:
1. First, analyze the codebase
2. Then, implement the feature
3. Finally, test the changes""",
                "tool_calls": None,
                "usage": {"total_tokens": 50},
            }
        )

        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm_provider,
        )

        state = ExecutionState(task="Implement new feature")
        await adapter._create_plan(state)

        # Plan should be populated
        assert len(state.plan) >= 1

    def test_advance_plan_increments_index(self):
        """Test _advance_plan increments plan index."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.plan = ["Step 1", "Step 2", "Step 3"]
        state.plan_index = 0

        adapter._advance_plan(state)

        assert state.plan_index == 1

    def test_advance_plan_respects_bounds(self):
        """Test _advance_plan doesn't exceed plan length."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.plan = ["Step 1", "Step 2"]
        state.plan_index = 2  # Already past end

        adapter._advance_plan(state)

        # Should not increase past plan length
        assert state.plan_index == 2

    def test_has_is_plan_complete_method(self):
        """Test adapter has method to check plan completion."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_is_plan_complete")
        assert callable(adapter._is_plan_complete)

    def test_is_plan_complete_returns_true_when_done(self):
        """Test _is_plan_complete returns True when all steps done."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.plan = ["Step 1", "Step 2"]
        state.plan_index = 2  # All steps done

        assert adapter._is_plan_complete(state) is True

    def test_is_plan_complete_returns_false_when_in_progress(self):
        """Test _is_plan_complete returns False when steps remain."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.plan = ["Step 1", "Step 2"]
        state.plan_index = 1  # One step remaining

        assert adapter._is_plan_complete(state) is False

    def test_get_current_plan_step(self):
        """Test getting current plan step."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_get_current_plan_step")

        state = ExecutionState(task="Test task")
        state.plan = ["Step 1", "Step 2", "Step 3"]
        state.plan_index = 1

        current_step = adapter._get_current_plan_step(state)

        assert current_step == "Step 2"

    def test_get_current_plan_step_empty_plan(self):
        """Test getting current step with empty plan."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.plan = []
        state.plan_index = 0

        current_step = adapter._get_current_plan_step(state)

        assert current_step is None

    @pytest.mark.asyncio
    async def test_pev_creates_plan_before_execution(self):
        """Test PEV creates plan at start of execution."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        llm_provider = MagicMock()

        call_count = 0
        responses = [
            # Planning call
            {
                "content": "Plan:\n1. Step one\n2. Step two",
                "tool_calls": None,
                "usage": {"total_tokens": 50},
            },
            # Execution calls
            {
                "content": "Executing step",
                "tool_calls": [{"name": "tool", "arguments": {}}],
                "usage": {"total_tokens": 50},
            },
            {"content": "Done", "tool_calls": None, "usage": {"total_tokens": 30}},
        ]

        async def mock_chat(**kwargs):
            nonlocal call_count
            response = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return response

        llm_provider.chat_async = mock_chat

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = []
        tool_registry.execute = AsyncMock(return_value="ok")

        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Test task", session_id="pev-test")
        result = await adapter.execute(context)

        # Verify planning phase was invoked
        assert call_count >= 2  # At least planning + execution


class TestTreeOfThoughtsStrategy:
    """Test Tree-of-Thoughts strategy basics."""

    def test_tree_of_thoughts_selection(self):
        """Test Tree-of-Thoughts can be selected."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.TREE_OF_THOUGHTS)
        adapter = LocalKaizenAdapter(config=config)

        assert adapter.config.planning_strategy == PlanningStrategy.TREE_OF_THOUGHTS

    def test_tree_of_thoughts_prompt(self):
        """Test Tree-of-Thoughts system prompt includes multi-path exploration."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.TREE_OF_THOUGHTS)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        # Should mention exploring multiple paths/options
        assert (
            "explore" in prompt.lower()
            or "multiple" in prompt.lower()
            or "path" in prompt.lower()
        )


class TestPlanParsing:
    """Test plan parsing from LLM responses."""

    def test_has_parse_plan_method(self):
        """Test adapter has method to parse plan from LLM response."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_parse_plan_from_response")
        assert callable(adapter._parse_plan_from_response)

    def test_parse_numbered_plan(self):
        """Test parsing numbered plan format."""
        adapter = LocalKaizenAdapter()
        response = """Here's my plan:
1. Analyze the codebase
2. Identify the module to modify
3. Implement the changes
4. Test the implementation"""

        steps = adapter._parse_plan_from_response(response)

        assert len(steps) == 4
        assert "Analyze" in steps[0]
        assert "Test" in steps[3]

    def test_parse_bulleted_plan(self):
        """Test parsing bulleted plan format."""
        adapter = LocalKaizenAdapter()
        response = """My plan:
- First, read the file
- Then, modify the content
- Finally, write it back"""

        steps = adapter._parse_plan_from_response(response)

        assert len(steps) >= 3

    def test_parse_step_prefix_plan(self):
        """Test parsing 'Step X:' format."""
        adapter = LocalKaizenAdapter()
        response = """
Step 1: Read the configuration
Step 2: Validate the settings
Step 3: Apply changes"""

        steps = adapter._parse_plan_from_response(response)

        assert len(steps) == 3

    def test_parse_empty_response(self):
        """Test parsing empty response returns empty list."""
        adapter = LocalKaizenAdapter()
        response = ""

        steps = adapter._parse_plan_from_response(response)

        assert steps == []

    def test_parse_response_without_plan(self):
        """Test parsing response without clear plan format."""
        adapter = LocalKaizenAdapter()
        response = "I'll help you with that. Let me start working on it."

        steps = adapter._parse_plan_from_response(response)

        # Should return empty or single step
        assert len(steps) <= 1


class TestStrategyContextBuilding:
    """Test that context building adapts to strategy."""

    def test_context_includes_strategy_info(self):
        """Test thinking context includes strategy metadata."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        context = adapter._build_thinking_context(state)

        # System message should mention strategy
        system_msg = context["messages"][0]["content"]
        assert "plan" in system_msg.lower()

    def test_pev_context_includes_current_step(self):
        """Test PEV context includes current plan step."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")
        state.plan = ["Step A", "Step B", "Step C"]
        state.plan_index = 1

        context = adapter._build_thinking_context(state)

        # System message should reference current step
        system_msg = context["messages"][0]["content"]
        assert "Step B" in system_msg or "current" in system_msg.lower()
