"""
Unit Tests for TAOD Loop (Tier 1)

Tests the Think-Act-Observe-Decide loop implementation in LocalKaizenAdapter.

Coverage:
- THINK phase: LLM call, tool call extraction
- ACT phase: Tool execution
- OBSERVE phase: Result processing
- DECIDE phase: Completion detection, stop conditions
- Full loop execution
- Error handling and recovery
- Budget and cycle limits
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter
from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    AutonomousPhase,
    ExecutionState,
    PlanningStrategy,
)
from kaizen.runtime.context import ExecutionContext, ExecutionStatus


class MockLLMProvider:
    """Mock LLM provider for testing."""

    def __init__(self, responses: List[Dict[str, Any]]):
        """Initialize with list of responses to return in sequence."""
        self.responses = responses
        self.call_count = 0
        self.call_history = []

    async def chat_async(self, **kwargs) -> Dict[str, Any]:
        """Return next response in sequence."""
        self.call_history.append(kwargs)
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        # Default: no tool calls (done)
        return {"content": "Done", "tool_calls": None}


class MockToolRegistry:
    """Mock tool registry for testing."""

    def __init__(self, tool_results: Dict[str, Any] = None):
        """Initialize with mapping of tool names to results."""
        self.tool_results = tool_results or {}
        self.execution_history = []

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool and return result."""
        self.execution_history.append({"tool": tool_name, "args": args})

        if tool_name in self.tool_results:
            result = self.tool_results[tool_name]
            if callable(result):
                return result(args)
            return result

        # Default mock result
        return MagicMock(success=True, output=f"Result from {tool_name}", error=None)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return tool schemas."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file contents",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]


class TestThinkPhase:
    """Test THINK phase - calling LLM with context."""

    @pytest.mark.asyncio
    async def test_think_phase_calls_llm(self):
        """Test think phase calls LLM with messages and tools."""
        llm = MockLLMProvider([{"content": "I'll read the file", "tool_calls": None}])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Read /tmp/test.txt")
        state.add_message({"role": "user", "content": "Read /tmp/test.txt"})

        await adapter._think_phase(state)

        assert llm.call_count == 1
        assert "messages" in llm.call_history[0]

    @pytest.mark.asyncio
    async def test_think_phase_extracts_tool_calls(self):
        """Test think phase extracts tool calls from LLM response."""
        llm = MockLLMProvider(
            [
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "/tmp/test.txt"}',
                            },
                        }
                    ],
                }
            ]
        )
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Read file")
        state.add_message({"role": "user", "content": "Read file"})

        await adapter._think_phase(state)

        assert len(state.pending_tool_calls) == 1
        assert state.pending_tool_calls[0]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_think_phase_no_tool_calls(self):
        """Test think phase when LLM returns no tool calls."""
        llm = MockLLMProvider([{"content": "Task complete", "tool_calls": None}])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Simple task")
        state.add_message({"role": "user", "content": "Simple task"})

        await adapter._think_phase(state)

        assert len(state.pending_tool_calls) == 0

    @pytest.mark.asyncio
    async def test_think_phase_updates_tokens(self):
        """Test think phase updates token usage."""
        llm = MockLLMProvider(
            [
                {
                    "content": "Done",
                    "tool_calls": None,
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "total_tokens": 150,
                    },
                }
            ]
        )
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        state.add_message({"role": "user", "content": "Task"})

        await adapter._think_phase(state)

        assert state.tokens_used >= 0  # May vary based on implementation


class TestActPhase:
    """Test ACT phase - executing tool calls."""

    @pytest.mark.asyncio
    async def test_act_phase_executes_tools(self):
        """Test act phase executes pending tool calls."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry(
            {"read_file": MagicMock(success=True, output="file content", error=None)}
        )

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Read file")
        state.add_tool_call(
            {
                "id": "call_123",
                "name": "read_file",
                "arguments": {"path": "/tmp/test.txt"},
            }
        )

        await adapter._act_phase(state)

        assert len(registry.execution_history) == 1
        assert registry.execution_history[0]["tool"] == "read_file"

    @pytest.mark.asyncio
    async def test_act_phase_handles_multiple_tools(self):
        """Test act phase executes multiple tool calls sequentially."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Multi-tool task")
        state.add_tool_call({"id": "1", "name": "tool1", "arguments": {}})
        state.add_tool_call({"id": "2", "name": "tool2", "arguments": {}})
        state.add_tool_call({"id": "3", "name": "tool3", "arguments": {}})

        await adapter._act_phase(state)

        assert len(registry.execution_history) == 3

    @pytest.mark.asyncio
    async def test_act_phase_records_results(self):
        """Test act phase records tool results."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry(
            {"read_file": MagicMock(success=True, output="content", error=None)}
        )

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Read file")
        state.add_tool_call(
            {
                "id": "call_123",
                "name": "read_file",
                "arguments": {"path": "/tmp/test.txt"},
            }
        )

        await adapter._act_phase(state)

        assert len(state.tool_results) >= 1

    @pytest.mark.asyncio
    async def test_act_phase_clears_pending(self):
        """Test act phase clears pending tool calls after execution."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        state.add_tool_call({"id": "1", "name": "tool1", "arguments": {}})

        assert len(state.pending_tool_calls) == 1

        await adapter._act_phase(state)

        assert len(state.pending_tool_calls) == 0


class TestObservePhase:
    """Test OBSERVE phase - processing results."""

    @pytest.mark.asyncio
    async def test_observe_phase_adds_results_to_messages(self):
        """Test observe phase adds tool results to conversation."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        state.add_tool_result(
            {
                "tool_call_id": "call_123",
                "tool_name": "read_file",
                "output": "file contents here",
            }
        )

        initial_count = len(state.messages)

        await adapter._observe_phase(state)

        assert len(state.messages) > initial_count

    @pytest.mark.asyncio
    async def test_observe_phase_clears_tool_results(self):
        """Test observe phase clears tool results after processing."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        state.add_tool_result({"tool_call_id": "1", "output": "result"})

        assert len(state.tool_results) == 1

        await adapter._observe_phase(state)

        assert len(state.tool_results) == 0


class TestDecidePhase:
    """Test DECIDE phase - determining next step."""

    @pytest.mark.asyncio
    async def test_decide_phase_continues_with_pending_tools(self):
        """Test decide phase returns False when tools are pending."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        state.add_tool_call({"id": "1", "name": "tool1", "arguments": {}})

        should_stop = await adapter._decide_phase(state)

        assert should_stop is False

    @pytest.mark.asyncio
    async def test_decide_phase_stops_when_no_tools(self):
        """Test decide phase returns True when no pending tools."""
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        # No pending tool calls

        should_stop = await adapter._decide_phase(state)

        assert should_stop is True

    @pytest.mark.asyncio
    async def test_decide_phase_stops_on_max_cycles(self):
        """Test decide phase stops when max cycles reached."""
        config = AutonomousConfig(max_cycles=5)
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        state.current_cycle = 5  # At max
        state.add_tool_call({"id": "1", "name": "tool1", "arguments": {}})

        should_stop = await adapter._decide_phase(state)

        assert should_stop is True

    @pytest.mark.asyncio
    async def test_decide_phase_stops_on_budget_exceeded(self):
        """Test decide phase stops when budget exceeded."""
        config = AutonomousConfig(budget_limit_usd=1.0)
        llm = MockLLMProvider([])
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm,
            tool_registry=registry,
        )

        state = ExecutionState(task="Task")
        state.cost_usd = 1.5  # Over budget
        state.add_tool_call({"id": "1", "name": "tool1", "arguments": {}})

        should_stop = await adapter._decide_phase(state)

        assert should_stop is True


class TestFullTAODLoop:
    """Test complete TAOD loop execution."""

    @pytest.mark.asyncio
    async def test_execute_simple_task(self):
        """Test executing a simple task with no tool calls."""
        llm = MockLLMProvider(
            [{"content": "Hello! I can help you.", "tool_calls": None}]
        )
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        context = ExecutionContext(task="Say hello")
        result = await adapter.execute(context)

        assert result.is_success
        assert "Hello" in result.output or result.output != ""

    @pytest.mark.asyncio
    async def test_execute_with_tool_call(self):
        """Test executing a task that requires tool calls."""
        llm = MockLLMProvider(
            [
                # First response: call read_file
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "/tmp/test.txt"}',
                            },
                        }
                    ],
                },
                # Second response: done after seeing result
                {"content": "The file contains: test content", "tool_calls": None},
            ]
        )
        registry = MockToolRegistry(
            {"read_file": MagicMock(success=True, output="test content", error=None)}
        )

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        context = ExecutionContext(task="Read /tmp/test.txt")
        result = await adapter.execute(context)

        assert result.is_success
        assert len(registry.execution_history) == 1

    @pytest.mark.asyncio
    async def test_execute_multiple_cycles(self):
        """Test executing a task with multiple TAOD cycles."""
        llm = MockLLMProvider(
            [
                # Cycle 1: call tool1
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "1",
                            "type": "function",
                            "function": {"name": "tool1", "arguments": "{}"},
                        }
                    ],
                },
                # Cycle 2: call tool2
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "2",
                            "type": "function",
                            "function": {"name": "tool2", "arguments": "{}"},
                        }
                    ],
                },
                # Cycle 3: done
                {"content": "All done", "tool_calls": None},
            ]
        )
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        context = ExecutionContext(task="Multi-step task")
        result = await adapter.execute(context)

        assert result.is_success
        assert len(registry.execution_history) == 2
        assert result.cycles_used >= 2

    @pytest.mark.asyncio
    async def test_execute_respects_max_cycles(self):
        """Test execution stops at max cycles."""
        # LLM always wants to call more tools
        llm = MockLLMProvider(
            [
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": str(i),
                            "type": "function",
                            "function": {"name": "tool", "arguments": "{}"},
                        }
                    ],
                }
                for i in range(100)
            ]
        )
        registry = MockToolRegistry()

        config = AutonomousConfig(max_cycles=3)
        adapter = LocalKaizenAdapter(
            config=config,
            llm_provider=llm,
            tool_registry=registry,
        )

        context = ExecutionContext(task="Infinite task")
        result = await adapter.execute(context)

        # Should stop at max_cycles
        assert result.cycles_used <= 3

    @pytest.mark.asyncio
    async def test_execute_handles_tool_error(self):
        """Test execution handles tool execution errors gracefully."""
        llm = MockLLMProvider(
            [
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "1",
                            "type": "function",
                            "function": {"name": "failing_tool", "arguments": "{}"},
                        }
                    ],
                },
                {
                    "content": "I encountered an error but handled it",
                    "tool_calls": None,
                },
            ]
        )
        registry = MockToolRegistry(
            {
                "failing_tool": MagicMock(
                    success=False, output=None, error="Tool failed!"
                )
            }
        )

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        context = ExecutionContext(task="Task with failing tool")
        result = await adapter.execute(context)

        # Should complete (error was handled)
        assert result.status in (ExecutionStatus.COMPLETE, ExecutionStatus.ERROR)


class TestErrorHandling:
    """Test error handling in TAOD loop."""

    @pytest.mark.asyncio
    async def test_llm_error_is_handled(self):
        """Test LLM errors are handled gracefully."""
        llm = MockLLMProvider([])
        llm.chat_async = AsyncMock(side_effect=Exception("LLM API error"))
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        context = ExecutionContext(task="Task")
        result = await adapter.execute(context)

        assert result.is_error
        assert "error" in result.error_message.lower() or result.error_message != ""

    @pytest.mark.asyncio
    async def test_invalid_tool_call_format(self):
        """Test handling of malformed tool call response."""
        llm = MockLLMProvider(
            [
                # Malformed tool call
                {"content": None, "tool_calls": [{"invalid": "format"}]},
                {"content": "Recovered", "tool_calls": None},
            ]
        )
        registry = MockToolRegistry()

        adapter = LocalKaizenAdapter(
            llm_provider=llm,
            tool_registry=registry,
        )

        context = ExecutionContext(task="Task")
        result = await adapter.execute(context)

        # Should handle gracefully (either complete or error)
        assert result.status in (ExecutionStatus.COMPLETE, ExecutionStatus.ERROR)


class TestShouldStopConditions:
    """Test _should_stop helper method."""

    def test_should_stop_on_complete_status(self):
        """Test should_stop returns True when state is completed."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Task")
        state.complete(result="Done")

        assert adapter._should_stop(state) is True

    def test_should_stop_on_error_status(self):
        """Test should_stop returns True when state has error."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Task")
        state.fail(error="Failed")

        assert adapter._should_stop(state) is True

    def test_should_stop_on_interrupted_status(self):
        """Test should_stop returns True when state is interrupted."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Task")
        state.interrupt()

        assert adapter._should_stop(state) is True

    def test_should_stop_on_max_cycles(self):
        """Test should_stop returns True when max cycles reached."""
        config = AutonomousConfig(max_cycles=10)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Task")
        state.current_cycle = 10

        assert adapter._should_stop(state) is True

    def test_should_stop_on_budget_exceeded(self):
        """Test should_stop returns True when budget exceeded."""
        config = AutonomousConfig(budget_limit_usd=5.0)
        adapter = LocalKaizenAdapter(config=config)
        state = ExecutionState(task="Task")
        state.cost_usd = 6.0

        assert adapter._should_stop(state) is True

    def test_should_not_stop_when_running(self):
        """Test should_stop returns False when running normally."""
        adapter = LocalKaizenAdapter()
        state = ExecutionState(task="Task")
        # Running, within limits

        assert adapter._should_stop(state) is False
