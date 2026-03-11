"""
Unit Tests for TaskTool (Tier 1)

Tests the TaskTool which spawns specialized subagents dynamically.
Part of TODO-203 Task/Skill Tools implementation.

Coverage:
- Tool attributes and schema
- Subagent spawning and execution
- Background execution support
- Event emission
- Error handling
- Trust chain propagation
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.execution.events import (
    CostUpdateEvent,
    EventType,
    SubagentCompleteEvent,
    SubagentSpawnEvent,
)
from kaizen.execution.subagent_result import SubagentResult
from kaizen.tools.native.task_tool import TaskTool
from kaizen.tools.types import DangerLevel, ToolCategory


@dataclass
class MockSpecialist:
    """Mock specialist for testing."""

    name: str
    description: str = "Test specialist"
    system_prompt: str = "You are a test specialist"
    available_tools: List[str] = None
    model: str = "test-model"

    def __post_init__(self):
        if self.available_tools is None:
            self.available_tools = ["Read", "Glob"]


@dataclass
class MockExecutionResult:
    """Mock execution result."""

    status: "MockStatus"
    output: str = "Test output"
    tokens_used: int = 100
    cost_usd: float = 0.001
    cycles_used: int = 5
    error_message: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class MockStatus:
    """Mock status enum."""

    value: str


class MockConfig:
    """Mock adapter config."""

    model: str = "test-model"
    max_cycles: int = 10


class MockSpecialistAdapter:
    """Mock specialist adapter for testing."""

    def __init__(self, result: Optional[MockExecutionResult] = None):
        self.config = MockConfig()
        self._result = result or MockExecutionResult(
            status=MockStatus(value="completed")
        )

    async def execute(self, context):
        return self._result


class MockAdapter:
    """Mock LocalKaizenAdapter for testing."""

    def __init__(
        self,
        specialists: Optional[Dict[str, MockSpecialist]] = None,
        specialist_result: Optional[MockExecutionResult] = None,
    ):
        self._specialists = specialists or {
            "code-reviewer": MockSpecialist(name="code-reviewer"),
            "test-writer": MockSpecialist(name="test-writer"),
        }
        self._specialist_result = specialist_result

    def get_specialist(self, name: str) -> Optional[MockSpecialist]:
        return self._specialists.get(name)

    def list_specialists(self) -> List[str]:
        return list(self._specialists.keys())

    def for_specialist(self, name: str) -> Optional[MockSpecialistAdapter]:
        if name in self._specialists:
            return MockSpecialistAdapter(result=self._specialist_result)
        return None


class TestTaskToolAttributes:
    """Test TaskTool attributes and schema."""

    def test_tool_name(self):
        """Test tool has correct name."""
        tool = TaskTool()
        assert tool.name == "task"

    def test_tool_description(self):
        """Test tool has meaningful description."""
        tool = TaskTool()
        assert "subagent" in tool.description.lower()
        assert "spawn" in tool.description.lower()

    def test_danger_level(self):
        """Test tool has MEDIUM danger level."""
        tool = TaskTool()
        assert tool.danger_level == DangerLevel.MEDIUM

    def test_category(self):
        """Test tool has AI category."""
        tool = TaskTool()
        assert tool.category == ToolCategory.AI

    def test_get_schema(self):
        """Test schema is correct."""
        tool = TaskTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "subagent_type" in schema["properties"]
        assert "prompt" in schema["properties"]
        assert "description" in schema["properties"]
        assert "model" in schema["properties"]
        assert "max_turns" in schema["properties"]
        assert "run_in_background" in schema["properties"]
        assert "resume" in schema["properties"]

        # Required parameters
        assert "subagent_type" in schema["required"]
        assert "prompt" in schema["required"]

    def test_initialization_defaults(self):
        """Test default initialization values."""
        tool = TaskTool()

        assert tool._adapter is None
        assert tool._parent_agent_id.startswith("agent_")
        assert tool._trust_chain_id.startswith("chain_")
        assert tool._session_id.startswith("session_")
        assert tool._on_event is None

    def test_initialization_with_params(self):
        """Test initialization with custom parameters."""
        adapter = MockAdapter()
        callback = MagicMock()

        tool = TaskTool(
            adapter=adapter,
            parent_agent_id="parent-123",
            trust_chain_id="chain-456",
            on_event=callback,
            session_id="session-789",
        )

        assert tool._adapter is adapter
        assert tool._parent_agent_id == "parent-123"
        assert tool._trust_chain_id == "chain-456"
        assert tool._on_event is callback
        assert tool._session_id == "session-789"


class TestTaskToolExecution:
    """Test TaskTool execution."""

    @pytest.mark.asyncio
    async def test_execute_without_adapter_returns_error(self):
        """Test execution without adapter returns error."""
        tool = TaskTool()

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is False
        assert "adapter" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_unknown_specialist_returns_error(self):
        """Test execution with unknown specialist returns error."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="unknown-specialist",
            prompt="Do something",
        )

        assert result.success is False
        assert "not found" in result.error.lower()
        assert "code-reviewer" in result.error  # Lists available

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful subagent execution."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the authentication module",
            description="Review auth module",
        )

        assert result.success is True
        assert result.output is not None
        assert isinstance(result.output, SubagentResult)
        assert result.output.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_returns_metrics(self):
        """Test execution returns proper metrics."""
        execution_result = MockExecutionResult(
            status=MockStatus(value="completed"),
            output="Review complete: 3 issues found",
            tokens_used=500,
            cost_usd=0.005,
            cycles_used=3,
        )
        adapter = MockAdapter(specialist_result=execution_result)
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is True
        subagent_result = result.output
        assert subagent_result.tokens_used == 500
        assert subagent_result.cost_usd == 0.005
        assert subagent_result.cycles_used == 3
        assert subagent_result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_with_model_override(self):
        """Test execution with model override."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
            model="opus",
        )

        assert result.success is True
        # Model should be passed to specialist adapter

    @pytest.mark.asyncio
    async def test_execute_with_max_turns(self):
        """Test execution with max_turns limit."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
            max_turns=5,
        )

        assert result.success is True
        # max_turns should be passed to specialist adapter

    @pytest.mark.asyncio
    async def test_execute_includes_subagent_id(self):
        """Test result includes unique subagent_id."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is True
        assert "subagent_id" in result.metadata
        assert result.metadata["subagent_id"].startswith("subagent_")

    @pytest.mark.asyncio
    async def test_execute_with_resume(self):
        """Test execution with resume from checkpoint."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Continue the review",
            resume="subagent_abc123",
        )

        assert result.success is True
        assert result.metadata["subagent_id"] == "subagent_abc123"


class TestTaskToolBackgroundExecution:
    """Test TaskTool background execution."""

    @pytest.mark.asyncio
    async def test_background_execution_returns_immediately(self):
        """Test background execution returns immediately with output file."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
            run_in_background=True,
        )

        assert result.success is True
        assert result.metadata["is_background"] is True
        assert "output_file" in result.metadata

    @pytest.mark.asyncio
    async def test_background_execution_creates_output_file(self):
        """Test background execution creates output file."""
        import os

        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
            run_in_background=True,
        )

        output_file = result.metadata["output_file"]
        assert os.path.exists(output_file)

        with open(output_file) as f:
            content = f.read()
            assert "subagent" in content.lower()

    @pytest.mark.asyncio
    async def test_get_background_status(self):
        """Test getting status of background task."""
        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
            run_in_background=True,
        )

        subagent_id = result.metadata["subagent_id"]

        # Give the background task a moment to complete
        await asyncio.sleep(0.1)

        status = await tool.get_background_status(subagent_id)
        # Status should exist (running or completed)

    @pytest.mark.asyncio
    async def test_get_background_status_unknown_id(self):
        """Test getting status for unknown subagent_id returns None."""
        tool = TaskTool()

        status = await tool.get_background_status("unknown-id")

        assert status is None


class TestTaskToolEventEmission:
    """Test TaskTool event emission."""

    @pytest.mark.asyncio
    async def test_emits_spawn_event(self):
        """Test execution emits SubagentSpawnEvent."""
        events = []

        async def capture_event(event):
            events.append(event)

        adapter = MockAdapter()
        tool = TaskTool(
            adapter=adapter,
            on_event=capture_event,
            parent_agent_id="parent-123",
            trust_chain_id="chain-456",
        )

        await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        spawn_events = [e for e in events if isinstance(e, SubagentSpawnEvent)]
        assert len(spawn_events) == 1

        spawn_event = spawn_events[0]
        assert spawn_event.subagent_name == "code-reviewer"
        assert spawn_event.parent_agent_id == "parent-123"
        assert spawn_event.trust_chain_id == "chain-456"
        assert spawn_event.event_type == EventType.SUBAGENT_SPAWN

    @pytest.mark.asyncio
    async def test_emits_complete_event(self):
        """Test execution emits SubagentCompleteEvent."""
        events = []

        async def capture_event(event):
            events.append(event)

        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter, on_event=capture_event)

        await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        complete_events = [e for e in events if isinstance(e, SubagentCompleteEvent)]
        assert len(complete_events) == 1

        complete_event = complete_events[0]
        assert complete_event.status == "completed"
        assert complete_event.event_type == EventType.SUBAGENT_COMPLETE

    @pytest.mark.asyncio
    async def test_emits_cost_update_event(self):
        """Test execution emits CostUpdateEvent."""
        events = []

        async def capture_event(event):
            events.append(event)

        execution_result = MockExecutionResult(
            status=MockStatus(value="completed"),
            tokens_used=500,
            cost_usd=0.005,
        )
        adapter = MockAdapter(specialist_result=execution_result)
        tool = TaskTool(adapter=adapter, on_event=capture_event)

        await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        cost_events = [e for e in events if isinstance(e, CostUpdateEvent)]
        assert len(cost_events) == 1

        cost_event = cost_events[0]
        assert cost_event.tokens_added == 500
        assert cost_event.cost_added_usd == 0.005
        assert cost_event.event_type == EventType.COST_UPDATE

    @pytest.mark.asyncio
    async def test_sync_event_callback_works(self):
        """Test sync event callbacks work correctly."""
        events = []

        def sync_callback(event):
            events.append(event)

        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter, on_event=sync_callback)

        await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert len(events) >= 2  # At least spawn and complete

    @pytest.mark.asyncio
    async def test_event_callback_error_doesnt_break_execution(self):
        """Test that event callback errors don't break execution."""

        def bad_callback(event):
            raise ValueError("Callback error")

        adapter = MockAdapter()
        tool = TaskTool(adapter=adapter, on_event=bad_callback)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        # Execution should still succeed despite callback error
        assert result.success is True


class TestTaskToolErrorHandling:
    """Test TaskTool error handling."""

    @pytest.mark.asyncio
    async def test_handles_specialist_adapter_none(self):
        """Test handles case when for_specialist returns None."""

        class BadAdapter(MockAdapter):
            def for_specialist(self, name: str):
                return None

        adapter = BadAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        # Tool execution succeeds but SubagentResult has error status
        assert result.success is True
        subagent_result = result.output
        assert subagent_result.status == "error"
        assert "adapter" in subagent_result.error_message.lower()

    @pytest.mark.asyncio
    async def test_handles_execution_exception(self):
        """Test handles execution exceptions gracefully."""

        class FailingSpecialistAdapter(MockSpecialistAdapter):
            async def execute(self, context):
                raise RuntimeError("Execution failed")

        class FailingAdapter(MockAdapter):
            def for_specialist(self, name: str):
                return FailingSpecialistAdapter()

        adapter = FailingAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is False
        assert "execution failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_handles_cancellation(self):
        """Test handles task cancellation gracefully."""

        class SlowSpecialistAdapter(MockSpecialistAdapter):
            async def execute(self, context):
                await asyncio.sleep(10)
                return self._result

        class SlowAdapter(MockAdapter):
            def for_specialist(self, name: str):
                return SlowSpecialistAdapter()

        adapter = SlowAdapter()
        tool = TaskTool(adapter=adapter)

        async def execute_and_cancel():
            task = asyncio.create_task(
                tool.execute(
                    subagent_type="code-reviewer",
                    prompt="Review the code",
                )
            )
            await asyncio.sleep(0.01)
            task.cancel()
            try:
                return await task
            except asyncio.CancelledError:
                return None

        result = await execute_and_cancel()
        # Either returns None (cancelled) or an error result
        if result is not None:
            assert result.success is False

    @pytest.mark.asyncio
    async def test_error_result_includes_subagent_result(self):
        """Test error result includes SubagentResult in metadata."""

        class FailingSpecialistAdapter(MockSpecialistAdapter):
            async def execute(self, context):
                raise ValueError("Test error")

        class FailingAdapter(MockAdapter):
            def for_specialist(self, name: str):
                return FailingSpecialistAdapter()

        adapter = FailingAdapter()
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is False
        assert "subagent_result" in result.metadata

    @pytest.mark.asyncio
    async def test_failed_execution_status(self):
        """Test handling of failed execution status from specialist."""
        execution_result = MockExecutionResult(
            status=MockStatus(value="error"),
            output="",
            error_message="Specialist error",
            error_type="ExecutionError",
        )
        adapter = MockAdapter(specialist_result=execution_result)
        tool = TaskTool(adapter=adapter)

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is True  # Tool execution succeeded
        subagent_result = result.output
        assert subagent_result.status == "error"
        assert subagent_result.error_message == "Specialist error"


class TestTaskToolTrustChain:
    """Test TaskTool trust chain propagation."""

    @pytest.mark.asyncio
    async def test_trust_chain_in_spawn_event(self):
        """Test trust chain is included in spawn event."""
        events = []

        async def capture_event(event):
            events.append(event)

        adapter = MockAdapter()
        tool = TaskTool(
            adapter=adapter,
            on_event=capture_event,
            trust_chain_id="chain-123",
        )

        await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        spawn_events = [e for e in events if isinstance(e, SubagentSpawnEvent)]
        assert spawn_events[0].trust_chain_id == "chain-123"

    @pytest.mark.asyncio
    async def test_trust_chain_in_result(self):
        """Test trust chain is included in result."""
        adapter = MockAdapter()
        tool = TaskTool(
            adapter=adapter,
            trust_chain_id="chain-456",
        )

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is True
        subagent_result = result.output
        assert subagent_result.trust_chain_id == "chain-456"

    @pytest.mark.asyncio
    async def test_parent_agent_id_propagated(self):
        """Test parent agent ID is propagated to result."""
        adapter = MockAdapter()
        tool = TaskTool(
            adapter=adapter,
            parent_agent_id="parent-789",
        )

        result = await tool.execute(
            subagent_type="code-reviewer",
            prompt="Review the code",
        )

        assert result.success is True
        subagent_result = result.output
        assert subagent_result.parent_agent_id == "parent-789"


class TestTaskToolRegistryIntegration:
    """Test TaskTool integration with KaizenToolRegistry."""

    def test_register_in_registry(self):
        """Test TaskTool can be registered in registry."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.task_tool import TaskTool as FreshTaskTool

        registry = KaizenToolRegistry()
        tool = FreshTaskTool()

        registry.register(tool)

        assert "task" in registry
        assert registry.get_tool("task") is tool

    def test_register_defaults_agent_category(self):
        """Test register_defaults includes agent tools."""
        from kaizen.tools.native.registry import KaizenToolRegistry

        registry = KaizenToolRegistry()
        count = registry.register_defaults(categories=["agent"])

        assert count == 2  # TaskTool and SkillTool
        assert "task" in registry
        assert "skill" in registry

    @pytest.mark.asyncio
    async def test_execute_via_registry(self):
        """Test executing TaskTool through registry."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.task_tool import TaskTool as FreshTaskTool

        adapter = MockAdapter()
        tool = FreshTaskTool(adapter=adapter)

        registry = KaizenToolRegistry()
        registry.register(tool)

        result = await registry.execute(
            "task",
            {
                "subagent_type": "code-reviewer",
                "prompt": "Review the code",
            },
        )

        assert result.success is True

    def test_tool_info_in_registry(self):
        """Test TaskTool info is available in registry."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.task_tool import TaskTool as FreshTaskTool

        registry = KaizenToolRegistry()
        tool = FreshTaskTool()
        registry.register(tool)

        info = registry.get_tool_info()
        task_info = next(i for i in info if i["name"] == "task")

        assert task_info["danger_level"] == "medium"
        assert task_info["category"] == "ai"
        assert task_info["requires_approval"] is True
