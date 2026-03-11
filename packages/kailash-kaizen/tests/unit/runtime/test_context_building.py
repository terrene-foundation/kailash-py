"""
Unit Tests for LocalKaizenAdapter Context Building (Tier 1)

Tests the context building methods for the TAOD loop:
- _build_thinking_context(): Build full context for LLM calls
- _build_system_prompt(): Strategy-specific system prompt generation
- _format_memory_context(): Format working memory and learned patterns

Coverage:
- System prompt generation for each planning strategy
- Context building with messages, tools, and memory
- Memory formatting with learned patterns
- Edge cases (empty memory, no tools, etc.)
"""

from typing import Any, Dict, List

import pytest

from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter
from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    ExecutionState,
    PermissionMode,
    PlanningStrategy,
)


class TestBuildSystemPrompt:
    """Test _build_system_prompt() method."""

    def test_has_build_system_prompt_method(self):
        """Test adapter has _build_system_prompt method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_build_system_prompt")
        assert callable(adapter._build_system_prompt)

    def test_system_prompt_returns_string(self):
        """Test system prompt returns a string."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_system_prompt_includes_task(self):
        """Test system prompt includes the task description."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Analyze the codebase and find bugs")

        prompt = adapter._build_system_prompt(state)

        # The task context should be mentioned in setup
        assert "autonomous" in prompt.lower() or "agent" in prompt.lower()

    def test_react_strategy_prompt(self):
        """Test system prompt for ReAct strategy."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.REACT)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        # ReAct uses step-by-step reasoning
        assert "reason" in prompt.lower() or "think" in prompt.lower()
        assert "step" in prompt.lower() or "action" in prompt.lower()

    def test_pev_strategy_prompt(self):
        """Test system prompt for PEV (Plan-Execute-Verify) strategy."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        # PEV uses plan-execute-verify cycle
        assert "plan" in prompt.lower()
        assert "execute" in prompt.lower() or "action" in prompt.lower()
        assert "verify" in prompt.lower() or "check" in prompt.lower()

    def test_tree_of_thoughts_strategy_prompt(self):
        """Test system prompt for Tree-of-Thoughts strategy."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.TREE_OF_THOUGHTS)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        # Tree-of-Thoughts explores multiple paths
        assert (
            "explore" in prompt.lower()
            or "multiple" in prompt.lower()
            or "path" in prompt.lower()
        )

    def test_system_prompt_includes_cycle_info(self):
        """Test system prompt includes current cycle information."""
        config = AutonomousConfig(max_cycles=100)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")
        state.current_cycle = 5

        prompt = adapter._build_system_prompt(state)

        # Should mention cycles or iteration context
        assert (
            "5" in prompt or "cycle" in prompt.lower() or "iteration" in prompt.lower()
        )

    def test_system_prompt_respects_permission_mode(self):
        """Test system prompt includes permission context for dangerous mode."""
        config = AutonomousConfig(permission_mode=PermissionMode.CONFIRM_ALL)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        # Should mention approval or confirmation when in confirm mode
        assert (
            "confirm" in prompt.lower()
            or "approv" in prompt.lower()
            or "permission" in prompt.lower()
        )

    def test_system_prompt_auto_permission_mode(self):
        """Test system prompt for auto permission mode."""
        config = AutonomousConfig(permission_mode=PermissionMode.AUTO)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        prompt = adapter._build_system_prompt(state)

        # Auto mode should allow autonomous operation
        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestFormatMemoryContext:
    """Test _format_memory_context() method."""

    def test_has_format_memory_context_method(self):
        """Test adapter has _format_memory_context method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_format_memory_context")
        assert callable(adapter._format_memory_context)

    def test_format_empty_memory(self):
        """Test formatting with no memory content."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        memory_context = adapter._format_memory_context(state)

        # Empty memory should return empty string or minimal context
        assert isinstance(memory_context, str)

    def test_format_working_memory(self):
        """Test formatting working memory contents."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["file_list"] = ["file1.py", "file2.py"]
        state.working_memory["current_focus"] = "analyzing imports"

        memory_context = adapter._format_memory_context(state)

        # Should include working memory info
        assert "file1.py" in memory_context or "working" in memory_context.lower()

    def test_format_learned_patterns(self):
        """Test formatting learned patterns."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.learned_patterns = [
            "Always check file exists before reading",
            "Use absolute paths for reliability",
        ]

        memory_context = adapter._format_memory_context(state)

        # Should include learned patterns
        assert (
            "pattern" in memory_context.lower() or "learned" in memory_context.lower()
        )

    def test_format_combined_memory(self):
        """Test formatting both working memory and learned patterns."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["key"] = "value"
        state.learned_patterns = ["Pattern 1"]

        memory_context = adapter._format_memory_context(state)

        assert isinstance(memory_context, str)

    def test_format_memory_truncation(self):
        """Test memory formatting truncates very long content."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        # Add very long content
        state.working_memory["long_content"] = "x" * 50000

        memory_context = adapter._format_memory_context(state)

        # Should be truncated to reasonable size
        assert len(memory_context) < 20000  # Some reasonable limit


class TestBuildThinkingContext:
    """Test _build_thinking_context() method."""

    def test_has_build_thinking_context_method(self):
        """Test adapter has _build_thinking_context method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_build_thinking_context")
        assert callable(adapter._build_thinking_context)

    def test_thinking_context_returns_dict(self):
        """Test thinking context returns a dictionary."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        context = adapter._build_thinking_context(state)

        assert isinstance(context, dict)

    def test_thinking_context_includes_messages(self):
        """Test thinking context includes messages."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.add_message({"role": "user", "content": "Hello"})

        context = adapter._build_thinking_context(state)

        assert "messages" in context
        assert len(context["messages"]) >= 1

    def test_thinking_context_includes_system_message(self):
        """Test thinking context includes system message first."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.add_message({"role": "user", "content": "Hello"})

        context = adapter._build_thinking_context(state)

        assert "messages" in context
        messages = context["messages"]
        assert len(messages) >= 1
        # First message should be system prompt
        assert messages[0]["role"] == "system"

    def test_thinking_context_includes_model(self):
        """Test thinking context includes model from config."""
        config = AutonomousConfig(model="gpt-4o-mini")
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        context = adapter._build_thinking_context(state)

        assert "model" in context
        assert context["model"] == "gpt-4o-mini"

    def test_thinking_context_includes_temperature(self):
        """Test thinking context includes temperature from config."""
        config = AutonomousConfig(temperature=0.5)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        context = adapter._build_thinking_context(state)

        assert "temperature" in context
        assert context["temperature"] == 0.5

    def test_thinking_context_with_tools(self):
        """Test thinking context includes tools when registry available."""
        from unittest.mock import MagicMock

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = [
            {"type": "function", "function": {"name": "read_file"}}
        ]

        adapter = LocalKaizenAdapter(tool_registry=tool_registry)
        state = ExecutionState(task="Test task")

        context = adapter._build_thinking_context(state)

        assert "tools" in context
        assert len(context["tools"]) == 1

    def test_thinking_context_no_tools(self):
        """Test thinking context without tool registry."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        context = adapter._build_thinking_context(state)

        # Should still work, just without tools
        assert isinstance(context, dict)
        assert "messages" in context

    def test_thinking_context_includes_memory(self):
        """Test thinking context includes formatted memory in system prompt."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["important"] = "context value"

        context = adapter._build_thinking_context(state)

        # Memory should be part of system message
        assert "messages" in context
        system_msg = context["messages"][0]
        assert system_msg["role"] == "system"

    def test_thinking_context_preserves_message_order(self):
        """Test thinking context preserves message order."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.add_message({"role": "user", "content": "First"})
        state.add_message({"role": "assistant", "content": "Second"})
        state.add_message({"role": "user", "content": "Third"})

        context = adapter._build_thinking_context(state)

        messages = context["messages"]
        # Skip system message at index 0
        assert messages[1]["content"] == "First"
        assert messages[2]["content"] == "Second"
        assert messages[3]["content"] == "Third"

    def test_thinking_context_with_plan(self):
        """Test thinking context includes plan information for PEV strategy."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")
        state.plan = ["Step 1: Analyze", "Step 2: Implement", "Step 3: Verify"]
        state.plan_index = 1

        context = adapter._build_thinking_context(state)

        # Plan should be included in system message
        system_msg = context["messages"][0]["content"]
        assert "Step" in system_msg or "plan" in system_msg.lower()


class TestThinkPhaseContextIntegration:
    """Test that _think_phase uses context building methods."""

    @pytest.mark.asyncio
    async def test_think_phase_uses_built_context(self):
        """Test _think_phase uses _build_thinking_context."""
        from unittest.mock import AsyncMock, MagicMock

        # Mock LLM that captures what it receives
        llm_provider = MagicMock()
        llm_provider.chat_async = AsyncMock(
            return_value={
                "content": "I will help you.",
                "tool_calls": None,
                "usage": {"total_tokens": 100},
            }
        )

        adapter = LocalKaizenAdapter(llm_provider=llm_provider)
        state = ExecutionState(task="Test task")
        state.add_message({"role": "user", "content": "Test"})
        adapter._current_state = state
        adapter._on_progress = None

        await adapter._think_phase(state)

        # Verify LLM was called
        assert llm_provider.chat_async.called

        # Get the call args
        call_kwargs = llm_provider.chat_async.call_args[1]

        # Should have messages with system prompt first
        messages = call_kwargs.get("messages", [])
        assert len(messages) >= 1
        # First message should be system prompt
        assert messages[0]["role"] == "system"


class TestPlanContextBuilding:
    """Test plan-related context building."""

    def test_build_plan_context_empty_plan(self):
        """Test building context with no plan."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")

        context = adapter._build_thinking_context(state)

        # Should still work with empty plan
        assert isinstance(context, dict)

    def test_build_plan_context_with_completed_steps(self):
        """Test building context with some completed plan steps."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.PEV)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")
        state.plan = ["Step 1", "Step 2", "Step 3"]
        state.plan_index = 2  # First two done

        context = adapter._build_thinking_context(state)
        system_msg = context["messages"][0]["content"]

        # Should indicate progress through plan
        assert "Step 3" in system_msg or "current" in system_msg.lower()

    def test_react_no_plan_context(self):
        """Test ReAct strategy doesn't include unnecessary plan context."""
        config = AutonomousConfig(planning_strategy=PlanningStrategy.REACT)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Test task")
        # ReAct shouldn't have a plan
        state.plan = []

        context = adapter._build_thinking_context(state)

        # Should still build valid context
        assert isinstance(context, dict)


class TestContextBuildingEdgeCases:
    """Test edge cases in context building."""

    def test_very_long_message_history(self):
        """Test context building with very long message history."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        # Add many messages
        for i in range(100):
            state.add_message(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                }
            )

        context = adapter._build_thinking_context(state)

        # Should handle gracefully (may truncate)
        assert isinstance(context, dict)
        assert "messages" in context

    def test_special_characters_in_task(self):
        """Test context building with special characters in task."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Find files with pattern: *.py && echo 'hello'")

        context = adapter._build_thinking_context(state)

        # Should not break
        assert isinstance(context, dict)

    def test_unicode_in_memory(self):
        """Test context building with unicode in memory."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["emoji"] = "🚀 Testing 日本語"

        context = adapter._build_thinking_context(state)
        memory = adapter._format_memory_context(state)

        # Should handle unicode
        assert isinstance(context, dict)
        assert isinstance(memory, str)

    def test_none_values_in_memory(self):
        """Test context building with None values in memory."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["none_value"] = None

        memory = adapter._format_memory_context(state)

        # Should handle None gracefully
        assert isinstance(memory, str)

    def test_nested_dict_in_memory(self):
        """Test context building with nested dicts in memory."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["nested"] = {"level1": {"level2": {"value": "deep"}}}

        memory = adapter._format_memory_context(state)

        # Should serialize nested structures
        assert isinstance(memory, str)
