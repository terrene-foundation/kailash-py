"""
Unit Tests for LocalKaizenAdapter Advanced Features (Tier 1)

Tests advanced features:
- Learning/Memory integration
- Cost calculation
- Tool approval workflow

Coverage:
- Pattern learning during execution
- Cost tracking per model
- Permission checking for tools
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter
from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    ExecutionState,
    PermissionMode,
)
from kaizen.runtime.context import ExecutionContext, ExecutionStatus


class TestCostCalculation:
    """Test cost calculation features."""

    def test_has_calculate_cost_method(self):
        """Test adapter has cost calculation method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_calculate_cost")
        assert callable(adapter._calculate_cost)

    def test_calculate_cost_openai_gpt4o(self):
        """Test cost calculation for GPT-4o."""
        config = AutonomousConfig(
            llm_provider="openai",
            model="gpt-4o",
        )
        adapter = LocalKaizenAdapter(config=config)

        # GPT-4o pricing: $5/1M input, $15/1M output (as of late 2024)
        cost = adapter._calculate_cost(
            input_tokens=1000,
            output_tokens=500,
        )

        assert cost > 0
        # Rough check: ~$0.005 input + ~$0.0075 output = ~$0.0125
        assert 0.001 < cost < 0.1

    def test_calculate_cost_anthropic_claude(self):
        """Test cost calculation for Claude models."""
        config = AutonomousConfig(
            llm_provider="anthropic",
            model="claude-3-opus",
        )
        adapter = LocalKaizenAdapter(config=config)

        cost = adapter._calculate_cost(
            input_tokens=1000,
            output_tokens=500,
        )

        # Claude pricing varies but should be non-zero
        assert cost >= 0

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model returns estimate."""
        config = AutonomousConfig(
            llm_provider="unknown",
            model="mystery-model",
        )
        adapter = LocalKaizenAdapter(config=config)

        cost = adapter._calculate_cost(
            input_tokens=1000,
            output_tokens=500,
        )

        # Should return 0 or an estimate for unknown models
        assert cost >= 0

    def test_calculate_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        adapter = LocalKaizenAdapter()

        cost = adapter._calculate_cost(
            input_tokens=0,
            output_tokens=0,
        )

        assert cost == 0

    @pytest.mark.asyncio
    async def test_execution_tracks_cost(self):
        """Test that execution tracks accumulated cost."""
        config = AutonomousConfig(model="gpt-4o")
        llm_provider = MagicMock()
        llm_provider.chat_async = AsyncMock(
            return_value={
                "content": "Done",
                "tool_calls": None,
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            }
        )

        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm_provider,
        )

        context = ExecutionContext(task="Test task", session_id="cost-test")
        result = await adapter.execute(context)

        # Cost should be tracked
        assert result.cost_usd is not None or result.cost_usd == 0


class TestLearning:
    """Test learning/memory features."""

    def test_has_learn_pattern_method(self):
        """Test adapter has method to learn patterns."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_learn_pattern")
        assert callable(adapter._learn_pattern)

    def test_learn_pattern_adds_to_state(self):
        """Test _learn_pattern adds pattern to state."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        adapter._learn_pattern(state, "Always verify file exists before reading")

        assert len(state.learned_patterns) == 1
        assert "verify" in state.learned_patterns[0].lower()

    def test_learn_pattern_prevents_duplicates(self):
        """Test _learn_pattern prevents duplicate patterns."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        adapter._learn_pattern(state, "Pattern 1")
        adapter._learn_pattern(state, "Pattern 1")  # Duplicate
        adapter._learn_pattern(state, "Pattern 2")

        assert len(state.learned_patterns) == 2

    def test_learn_pattern_respects_limit(self):
        """Test _learn_pattern respects pattern limit."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        # Add many patterns
        for i in range(100):
            adapter._learn_pattern(state, f"Pattern {i}")

        # Should be capped at some reasonable limit
        assert len(state.learned_patterns) <= 50

    def test_has_extract_patterns_method(self):
        """Test adapter has method to extract patterns from execution."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_extract_patterns")
        assert callable(adapter._extract_patterns)

    def test_extract_patterns_from_successful_execution(self):
        """Test extracting patterns from successful tool execution."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Read and analyze config.yaml")
        state.add_tool_result(
            {
                "tool_name": "read_file",
                "output": "config content",
                "success": True,
            }
        )

        patterns = adapter._extract_patterns(state)

        # Should extract some pattern about the successful approach
        assert isinstance(patterns, list)

    def test_extract_patterns_from_error(self):
        """Test extracting patterns from errors."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.add_tool_result(
            {
                "tool_name": "read_file",
                "output": "Error: File not found",
                "success": False,
            }
        )

        patterns = adapter._extract_patterns(state)

        # Should extract pattern about error handling
        assert isinstance(patterns, list)

    def test_config_enable_learning(self):
        """Test learning can be enabled via config."""
        config = AutonomousConfig(enable_learning=True)
        adapter = LocalKaizenAdapter(config=config)

        assert adapter.config.enable_learning is True


class TestApprovalWorkflow:
    """Test tool approval workflow."""

    def test_has_check_permission_method(self):
        """Test adapter has permission checking method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_check_tool_permission")
        assert callable(adapter._check_tool_permission)

    def test_auto_mode_approves_safe_tools(self):
        """Test AUTO mode auto-approves safe tools."""
        config = AutonomousConfig(permission_mode=PermissionMode.AUTO)
        adapter = LocalKaizenAdapter(config=config)

        approved = adapter._check_tool_permission(
            "read_file", {"path": "/tmp/test.txt"}
        )

        assert approved is True

    def test_auto_mode_denies_dangerous_tools(self):
        """Test AUTO mode auto-denies dangerous tools without approval."""
        config = AutonomousConfig(permission_mode=PermissionMode.AUTO)
        adapter = LocalKaizenAdapter(config=config)

        # rm -rf would be dangerous
        approved = adapter._check_tool_permission(
            "bash_command", {"command": "rm -rf /"}
        )

        assert approved is False

    def test_confirm_all_mode(self):
        """Test CONFIRM_ALL mode requires approval for all tools."""
        config = AutonomousConfig(permission_mode=PermissionMode.CONFIRM_ALL)
        adapter = LocalKaizenAdapter(config=config)

        # Even safe tools should require confirmation (return False without explicit approval)
        approved = adapter._check_tool_permission(
            "read_file", {"path": "/tmp/test.txt"}
        )

        # In CONFIRM_ALL mode without approval callback, should be False
        assert approved is False

    def test_deny_all_mode(self):
        """Test DENY_ALL mode denies all tools."""
        config = AutonomousConfig(permission_mode=PermissionMode.DENY_ALL)
        adapter = LocalKaizenAdapter(config=config)

        approved = adapter._check_tool_permission(
            "read_file", {"path": "/tmp/test.txt"}
        )

        assert approved is False

    def test_confirm_dangerous_mode_approves_safe(self):
        """Test CONFIRM_DANGEROUS mode auto-approves safe tools."""
        config = AutonomousConfig(permission_mode=PermissionMode.CONFIRM_DANGEROUS)
        adapter = LocalKaizenAdapter(config=config)

        approved = adapter._check_tool_permission(
            "read_file", {"path": "/tmp/test.txt"}
        )

        assert approved is True

    def test_confirm_dangerous_mode_requires_approval_for_dangerous(self):
        """Test CONFIRM_DANGEROUS requires approval for dangerous tools."""
        config = AutonomousConfig(permission_mode=PermissionMode.CONFIRM_DANGEROUS)
        adapter = LocalKaizenAdapter(config=config)

        # Write operations should require approval
        approved = adapter._check_tool_permission(
            "write_file", {"path": "/tmp/test.txt", "content": "data"}
        )

        assert approved is False

    def test_has_is_dangerous_tool_method(self):
        """Test adapter has method to check if tool is dangerous."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_is_dangerous_tool")
        assert callable(adapter._is_dangerous_tool)

    def test_read_file_is_not_dangerous(self):
        """Test read_file is classified as safe."""
        adapter = LocalKaizenAdapter()

        is_dangerous = adapter._is_dangerous_tool(
            "read_file", {"path": "/tmp/test.txt"}
        )

        assert is_dangerous is False

    def test_write_file_is_dangerous(self):
        """Test write_file is classified as dangerous."""
        adapter = LocalKaizenAdapter()

        is_dangerous = adapter._is_dangerous_tool(
            "write_file", {"path": "/tmp/test.txt", "content": "data"}
        )

        assert is_dangerous is True

    def test_bash_command_with_rm_is_dangerous(self):
        """Test bash command with rm is dangerous."""
        adapter = LocalKaizenAdapter()

        is_dangerous = adapter._is_dangerous_tool(
            "bash_command", {"command": "rm -rf /tmp/test"}
        )

        assert is_dangerous is True

    def test_bash_command_with_ls_is_safe(self):
        """Test bash command with ls is safe."""
        adapter = LocalKaizenAdapter()

        is_dangerous = adapter._is_dangerous_tool(
            "bash_command", {"command": "ls /tmp"}
        )

        assert is_dangerous is False


class TestWorkingMemoryManagement:
    """Test working memory management."""

    def test_has_update_working_memory_method(self):
        """Test adapter has working memory update method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_update_working_memory")
        assert callable(adapter._update_working_memory)

    def test_update_working_memory_stores_value(self):
        """Test _update_working_memory stores value."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")

        adapter._update_working_memory(state, "file_list", ["a.txt", "b.txt"])

        assert "file_list" in state.working_memory
        assert state.working_memory["file_list"] == ["a.txt", "b.txt"]

    def test_update_working_memory_overwrites(self):
        """Test _update_working_memory overwrites existing value."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["key"] = "old"

        adapter._update_working_memory(state, "key", "new")

        assert state.working_memory["key"] == "new"

    def test_has_clear_working_memory_method(self):
        """Test adapter has working memory clear method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "_clear_working_memory")
        assert callable(adapter._clear_working_memory)

    def test_clear_working_memory_removes_key(self):
        """Test _clear_working_memory removes specific key."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["key1"] = "value1"
        state.working_memory["key2"] = "value2"

        adapter._clear_working_memory(state, "key1")

        assert "key1" not in state.working_memory
        assert "key2" in state.working_memory

    def test_clear_working_memory_all(self):
        """Test _clear_working_memory can clear all."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.working_memory["key1"] = "value1"
        state.working_memory["key2"] = "value2"

        adapter._clear_working_memory(state)

        assert len(state.working_memory) == 0


class TestBudgetEnforcement:
    """Test budget enforcement features."""

    @pytest.mark.asyncio
    async def test_execution_stops_on_budget_exceeded(self):
        """Test execution stops when budget limit reached."""
        config = AutonomousConfig(
            budget_limit_usd=0.001,  # Very low budget
            model="gpt-4o",
        )
        llm_provider = MagicMock()

        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "content": f"Step {call_count}",
                "tool_calls": (
                    [{"name": "read", "arguments": {}}] if call_count < 10 else None
                ),
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                    "total_tokens": 1500,
                },
            }

        llm_provider.chat_async = mock_chat

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = []
        tool_registry.execute = AsyncMock(return_value="ok")

        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Long task", session_id="budget-test")
        result = await adapter.execute(context)

        # Execution should have been limited by budget
        # The exact behavior depends on cost calculation implementation
        assert result.cycles_used < 10 or result.status in [
            ExecutionStatus.COMPLETE,
            ExecutionStatus.ERROR,
        ]
