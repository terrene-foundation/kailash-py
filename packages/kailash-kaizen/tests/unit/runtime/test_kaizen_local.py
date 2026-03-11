"""
Unit Tests for LocalKaizenAdapter (Tier 1)

Tests the LocalKaizenAdapter class that implements RuntimeAdapter interface.

Coverage:
- Constructor and dependency injection
- RuntimeAdapter interface compliance
- capabilities property
- map_tools() method
- normalize_result() method
- Basic execute() method (without full TAOD loop yet)
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from kaizen.runtime.adapter import RuntimeAdapter
from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter
from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    ExecutionState,
    PermissionMode,
    PlanningStrategy,
)
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus


class TestLocalKaizenAdapterInterface:
    """Test LocalKaizenAdapter implements RuntimeAdapter correctly."""

    def test_is_runtime_adapter_subclass(self):
        """Test LocalKaizenAdapter inherits from RuntimeAdapter."""
        assert issubclass(LocalKaizenAdapter, RuntimeAdapter)

    def test_instantiation(self):
        """Test basic instantiation works."""
        adapter = LocalKaizenAdapter()
        assert adapter is not None

    def test_has_capabilities_property(self):
        """Test adapter has capabilities property."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "capabilities")
        assert isinstance(adapter.capabilities, RuntimeCapabilities)

    def test_has_execute_method(self):
        """Test adapter has execute method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "execute")
        assert callable(adapter.execute)

    def test_has_stream_method(self):
        """Test adapter has stream method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "stream")
        assert callable(adapter.stream)

    def test_has_interrupt_method(self):
        """Test adapter has interrupt method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "interrupt")
        assert callable(adapter.interrupt)

    def test_has_map_tools_method(self):
        """Test adapter has map_tools method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "map_tools")
        assert callable(adapter.map_tools)

    def test_has_normalize_result_method(self):
        """Test adapter has normalize_result method."""
        adapter = LocalKaizenAdapter()
        assert hasattr(adapter, "normalize_result")
        assert callable(adapter.normalize_result)


class TestLocalKaizenAdapterConstructor:
    """Test LocalKaizenAdapter constructor and dependency injection."""

    def test_default_constructor(self):
        """Test constructor with no arguments uses defaults."""
        adapter = LocalKaizenAdapter()

        assert adapter.config is not None
        assert adapter.config.model == "gpt-4o"
        assert adapter.config.max_cycles == 50

    def test_constructor_with_config(self):
        """Test constructor with custom config."""
        config = AutonomousConfig(
            model="claude-3-opus",
            max_cycles=100,
            budget_limit_usd=5.0,
        )

        adapter = LocalKaizenAdapter(config=config)

        assert adapter.config.model == "claude-3-opus"
        assert adapter.config.max_cycles == 100
        assert adapter.config.budget_limit_usd == 5.0

    def test_constructor_with_state_manager(self):
        """Test constructor with state manager injection."""
        state_manager = MagicMock()

        adapter = LocalKaizenAdapter(state_manager=state_manager)

        assert adapter.state_manager is state_manager

    def test_constructor_with_hook_manager(self):
        """Test constructor with hook manager injection."""
        hook_manager = MagicMock()

        adapter = LocalKaizenAdapter(hook_manager=hook_manager)

        assert adapter.hook_manager is hook_manager

    def test_constructor_with_interrupt_manager(self):
        """Test constructor with interrupt manager injection."""
        interrupt_manager = MagicMock()

        adapter = LocalKaizenAdapter(interrupt_manager=interrupt_manager)

        assert adapter.interrupt_manager is interrupt_manager

    def test_constructor_with_tool_registry(self):
        """Test constructor with tool registry injection."""
        tool_registry = MagicMock()

        adapter = LocalKaizenAdapter(tool_registry=tool_registry)

        assert adapter.tool_registry is tool_registry

    def test_constructor_full_dependency_injection(self):
        """Test constructor with all dependencies."""
        config = AutonomousConfig(model="gpt-4o-mini")
        state_manager = MagicMock()
        hook_manager = MagicMock()
        interrupt_manager = MagicMock()
        tool_registry = MagicMock()

        adapter = LocalKaizenAdapter(
            config=config,
            state_manager=state_manager,
            hook_manager=hook_manager,
            interrupt_manager=interrupt_manager,
            tool_registry=tool_registry,
        )

        assert adapter.config.model == "gpt-4o-mini"
        assert adapter.state_manager is state_manager
        assert adapter.hook_manager is hook_manager
        assert adapter.interrupt_manager is interrupt_manager
        assert adapter.tool_registry is tool_registry


class TestLocalKaizenAdapterCapabilities:
    """Test capabilities property."""

    def test_capabilities_returns_runtime_capabilities(self):
        """Test capabilities returns RuntimeCapabilities instance."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert isinstance(caps, RuntimeCapabilities)

    def test_capabilities_runtime_name(self):
        """Test capabilities has correct runtime name."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert caps.runtime_name == "kaizen_local"

    def test_capabilities_provider(self):
        """Test capabilities has correct provider."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert caps.provider == "kaizen"

    def test_capabilities_supports_tool_calling(self):
        """Test capabilities indicates tool calling support."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert caps.supports_tool_calling is True

    def test_capabilities_supports_file_access(self):
        """Test capabilities indicates file access support."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert caps.supports_file_access is True

    def test_capabilities_supports_code_execution(self):
        """Test capabilities indicates code execution support."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert caps.supports_code_execution is True

    def test_capabilities_supports_streaming(self):
        """Test capabilities indicates streaming support."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert caps.supports_streaming is True

    def test_capabilities_supports_interrupt(self):
        """Test capabilities indicates interrupt support."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert caps.supports_interrupt is True

    def test_capabilities_native_tools(self):
        """Test capabilities lists native tools."""
        adapter = LocalKaizenAdapter()

        caps = adapter.capabilities

        assert "read_file" in caps.native_tools
        assert "bash_command" in caps.native_tools


class TestLocalKaizenAdapterMapTools:
    """Test map_tools method."""

    def test_map_tools_passthrough(self):
        """Test map_tools passes tools through unchanged."""
        adapter = LocalKaizenAdapter()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

        mapped = adapter.map_tools(tools)

        assert mapped == tools

    def test_map_tools_empty_list(self):
        """Test map_tools handles empty list."""
        adapter = LocalKaizenAdapter()

        mapped = adapter.map_tools([])

        assert mapped == []

    def test_map_tools_multiple_tools(self):
        """Test map_tools handles multiple tools."""
        adapter = LocalKaizenAdapter()
        tools = [
            {"type": "function", "function": {"name": "tool1"}},
            {"type": "function", "function": {"name": "tool2"}},
            {"type": "function", "function": {"name": "tool3"}},
        ]

        mapped = adapter.map_tools(tools)

        assert len(mapped) == 3
        assert mapped == tools


class TestLocalKaizenAdapterNormalizeResult:
    """Test normalize_result method."""

    def test_normalize_execution_result_passthrough(self):
        """Test normalize_result passes through ExecutionResult."""
        adapter = LocalKaizenAdapter()
        original = ExecutionResult.from_success("Result", "kaizen_local")

        normalized = adapter.normalize_result(original)

        assert normalized is original

    def test_normalize_string_result(self):
        """Test normalize_result handles string."""
        adapter = LocalKaizenAdapter()

        normalized = adapter.normalize_result("Task completed")

        assert isinstance(normalized, ExecutionResult)
        assert normalized.output == "Task completed"
        assert normalized.status == ExecutionStatus.COMPLETE
        assert normalized.runtime_name == "kaizen_local"

    def test_normalize_dict_result(self):
        """Test normalize_result handles dict with output key."""
        adapter = LocalKaizenAdapter()
        raw = {
            "output": "Output from dict",
            "status": "complete",
            "tokens_used": 100,
        }

        normalized = adapter.normalize_result(raw)

        assert isinstance(normalized, ExecutionResult)
        assert normalized.output == "Output from dict"

    def test_normalize_execution_state(self):
        """Test normalize_result handles ExecutionState."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.complete(result="Task done")

        normalized = adapter.normalize_result(state)

        assert isinstance(normalized, ExecutionResult)
        assert normalized.output == "Task done"
        assert normalized.status == ExecutionStatus.COMPLETE

    def test_normalize_error_state(self):
        """Test normalize_result handles error ExecutionState."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.fail(error="Something went wrong")

        normalized = adapter.normalize_result(state)

        assert isinstance(normalized, ExecutionResult)
        assert normalized.status == ExecutionStatus.ERROR
        assert normalized.error_message == "Something went wrong"

    def test_normalize_interrupted_state(self):
        """Test normalize_result handles interrupted ExecutionState."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Test task")
        state.interrupt()

        normalized = adapter.normalize_result(state)

        assert isinstance(normalized, ExecutionResult)
        assert normalized.status == ExecutionStatus.INTERRUPTED


class TestLocalKaizenAdapterRepr:
    """Test string representation."""

    def test_repr(self):
        """Test repr includes class name and runtime."""
        adapter = LocalKaizenAdapter()

        repr_str = repr(adapter)

        assert "LocalKaizenAdapter" in repr_str
        assert "kaizen_local" in repr_str


class TestLocalKaizenAdapterSessionManagement:
    """Test session management."""

    def test_has_current_state(self):
        """Test adapter tracks current execution state."""
        adapter = LocalKaizenAdapter()

        assert hasattr(adapter, "_current_state")

    def test_initial_state_is_none(self):
        """Test initial state is None when not executing."""
        adapter = LocalKaizenAdapter()

        assert adapter._current_state is None

    def test_get_current_session_id(self):
        """Test getting current session ID."""
        adapter = LocalKaizenAdapter()

        # No active session
        assert adapter.get_current_session_id() is None


class TestLocalKaizenAdapterHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true(self):
        """Test health check returns True when healthy."""
        adapter = LocalKaizenAdapter()

        result = await adapter.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_warmup_completes(self):
        """Test warmup completes without error."""
        adapter = LocalKaizenAdapter()

        await adapter.warmup()  # Should not raise

    @pytest.mark.asyncio
    async def test_cleanup_completes(self):
        """Test cleanup completes without error."""
        adapter = LocalKaizenAdapter()

        await adapter.cleanup()  # Should not raise
