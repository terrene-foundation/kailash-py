"""
Integration Tests for Streaming Executor (Tier 2)

Tests the streaming execution system with real agent execution.
Part of TODO-204 Enterprise-App Streaming Integration.

NO MOCKING: Uses real execution to validate integration.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

import pytest

from kaizen.execution.events import (
    CompletedEvent,
    ErrorEvent,
    EventType,
    ExecutionEvent,
    MessageEvent,
    ProgressEvent,
    StartedEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from kaizen.execution.streaming_executor import (
    ExecutionMetrics,
    StreamingExecutor,
    format_sse,
)
from kaizen.session.manager import InMemorySessionStorage, KaizenSessionManager
from kaizen.session.state import Message, SessionState, SessionStatus


class SimpleTestAgent:
    """Simple agent for integration testing."""

    def __init__(
        self,
        name: str = "TestAgent",
        agent_id: str = "test-agent-001",
    ):
        self.name = name
        self.agent_id = agent_id
        self.execution_count = 0

    def run(self, task: str = "", **kwargs) -> Dict[str, Any]:
        """Synchronous execution."""
        self.execution_count += 1
        return {
            "answer": f"Processed: {task}",
            "tokens_used": 100,
            "cost_usd": 0.01,
        }


class AsyncTestAgent:
    """Async agent for integration testing."""

    def __init__(
        self,
        name: str = "AsyncTestAgent",
        agent_id: str = "async-test-001",
        delay: float = 0.1,
    ):
        self.name = name
        self.agent_id = agent_id
        self.delay = delay
        self.execution_count = 0

    async def run_async(self, task: str = "", **kwargs) -> Dict[str, Any]:
        """Asynchronous execution with delay."""
        await asyncio.sleep(self.delay)
        self.execution_count += 1
        return {
            "answer": f"Async processed: {task}",
            "tokens_used": 150,
            "cost_usd": 0.015,
        }


class ToolUsingAgent:
    """Agent that simulates tool usage."""

    def __init__(self, name: str = "ToolAgent", agent_id: str = "tool-agent-001"):
        self.name = name
        self.agent_id = agent_id
        self.tools_used = []

    def run(self, task: str = "", **kwargs) -> Dict[str, Any]:
        """Execute with tool simulation."""
        # Simulate tool usage
        self.tools_used.append("search")
        self.tools_used.append("calculator")

        return {
            "answer": f"Used tools to process: {task}",
            "tokens_used": 200,
            "cost_usd": 0.02,
            "tools_used": self.tools_used,
        }


class FailingAgent:
    """Agent that always fails."""

    def __init__(self, error_type: str = "ValueError"):
        self.name = "FailingAgent"
        self.agent_id = "failing-agent-001"
        self.error_type = error_type

    def run(self, **kwargs) -> Dict[str, Any]:
        """Always raises an error."""
        if self.error_type == "RateLimitError":
            raise Exception("RateLimitError: Rate limit exceeded")
        raise ValueError("Intentional test error")


class TestStreamingExecutorIntegration:
    """Integration tests for StreamingExecutor."""

    @pytest.mark.asyncio
    async def test_complete_execution_flow(self):
        """Test complete execution flow with all events."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        events: List[ExecutionEvent] = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test integration task",
            session_id="int-session-001",
        ):
            events.append(event)

        # Verify event sequence
        event_types = [e.event_type for e in events]
        assert EventType.STARTED in event_types
        assert EventType.COMPLETED in event_types
        assert event_types[0] == EventType.STARTED
        assert event_types[-1] == EventType.COMPLETED

        # Verify agent executed
        assert agent.execution_count == 1

    @pytest.mark.asyncio
    async def test_async_agent_execution(self):
        """Test async agent execution with events."""
        agent = AsyncTestAgent(delay=0.05)
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Async test task",
        ):
            events.append(event)

        # Verify execution completed
        assert agent.execution_count == 1
        assert any(isinstance(e, CompletedEvent) for e in events)

    @pytest.mark.asyncio
    async def test_multiple_executions_sequential(self):
        """Test multiple sequential executions."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        for i in range(3):
            events = []
            async for event in executor.execute_with_events(
                agent=agent,
                task=f"Task {i}",
                execution_id=f"exec-{i}",
            ):
                events.append(event)

            assert any(isinstance(e, CompletedEvent) for e in events)

        assert agent.execution_count == 3

    @pytest.mark.asyncio
    async def test_event_callback_integration(self):
        """Test event callback receives all events."""
        agent = SimpleTestAgent()
        callback_events = []

        executor = StreamingExecutor(on_event=lambda e: callback_events.append(e))

        async for _ in executor.execute_with_events(
            agent=agent,
            task="Callback test",
        ):
            pass

        # Callback should have received events
        assert len(callback_events) > 0
        assert any(isinstance(e, StartedEvent) for e in callback_events)
        assert any(isinstance(e, CompletedEvent) for e in callback_events)

    @pytest.mark.asyncio
    async def test_error_handling_integration(self):
        """Test error handling with real error."""
        agent = FailingAgent()
        executor = StreamingExecutor()

        events = []
        with pytest.raises(ValueError):
            async for event in executor.execute_with_events(
                agent=agent,
                task="Error test",
            ):
                events.append(event)

        # Should have error event
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert "Intentional test error" in error_events[0].message

    @pytest.mark.asyncio
    async def test_metrics_tracking(self):
        """Test metrics are properly tracked."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Metrics test",
        ):
            events.append(event)

        completed = [e for e in events if isinstance(e, CompletedEvent)][0]
        assert completed.total_tokens == 100
        assert completed.total_cost_usd == 0.01
        assert completed.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_sse_format_integration(self):
        """Test SSE formatting for all event types."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        async for event in executor.execute_with_events(
            agent=agent,
            task="SSE test",
        ):
            sse = format_sse(event)
            assert sse.startswith("data: ")
            assert sse.endswith("\n\n")

            # Verify JSON parseable
            json_str = sse[6:-2]  # Remove "data: " and "\n\n"
            data = json.loads(json_str)
            assert "event_type" in data

    @pytest.mark.asyncio
    async def test_trust_chain_propagation(self):
        """Test trust chain ID propagates through execution."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Trust chain test",
            trust_chain_id="chain-integration-001",
        ):
            events.append(event)

        started = [e for e in events if isinstance(e, StartedEvent)][0]
        assert started.trust_chain_id == "chain-integration-001"

    @pytest.mark.asyncio
    async def test_session_id_consistency(self):
        """Test session ID is consistent across all events."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Session test",
            session_id="session-consistency-001",
        ):
            events.append(event)

        for event in events:
            assert event.session_id == "session-consistency-001"


class TestSessionManagerIntegration:
    """Integration tests for KaizenSessionManager."""

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()

        # Start session
        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-lifecycle-001",
        )

        # Add messages
        await manager.add_message(session_id, "user", "Hello")
        await manager.add_message(session_id, "assistant", "Hi there!")

        # Add tool invocation
        await manager.add_tool_invocation(
            session_id=session_id,
            tool_name="search",
            tool_call_id="call-001",
            input={"query": "test"},
            output={"results": []},
        )

        # Update metrics
        await manager.update_metrics(
            session_id=session_id,
            tokens_added=500,
            cost_added_usd=0.05,
        )

        # End session
        summary = await manager.end_session(
            session_id=session_id,
            status="completed",
            final_output="Task completed",
        )

        assert summary.total_messages == 2
        assert summary.total_tool_calls == 1
        assert summary.total_tokens == 500
        assert summary.total_cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_pause_resume_cycle(self):
        """Test pause and resume functionality."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-pause-001",
        )

        # Add initial message
        await manager.add_message(session_id, "user", "Start task")

        # Pause
        await manager.pause_session(session_id)
        state = await manager.get_session_state(session_id)
        assert state.status == SessionStatus.PAUSED

        # Resume
        resumed_state = await manager.resume_session(session_id)
        assert resumed_state.status == SessionStatus.ACTIVE

        # Continue adding messages
        await manager.add_message(session_id, "assistant", "Continuing...")

        state = await manager.get_session_state(session_id)
        assert len(state.messages) == 2

    @pytest.mark.asyncio
    async def test_multiple_concurrent_sessions(self):
        """Test multiple sessions running concurrently."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)

        # Start multiple sessions
        session_ids = []
        for i in range(5):
            agent = SimpleTestAgent(agent_id=f"agent-{i}")
            sid = await manager.start_session(
                agent=agent,
                trust_chain_id=f"chain-{i}",
            )
            session_ids.append(sid)

        # Verify all active
        sessions = await manager.list_sessions()
        assert len(sessions) == 5

        # Update each session
        for i, sid in enumerate(session_ids):
            await manager.add_message(sid, "user", f"Message {i}")
            await manager.update_metrics(sid, tokens_added=100 * (i + 1))

        # Verify each session has correct state
        for i, sid in enumerate(session_ids):
            state = await manager.get_session_state(sid)
            assert len(state.messages) == 1
            assert state.tokens_used == 100 * (i + 1)

    @pytest.mark.asyncio
    async def test_session_with_subagent_calls(self):
        """Test session tracking with subagent calls."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-subagent-001",
        )

        # Add subagent call
        await manager.add_subagent_call(
            session_id=session_id,
            subagent_id="sub-agent-001",
            subagent_name="DataAnalyzer",
            task="Analyze dataset",
            parent_agent_id=agent.agent_id,
            trust_chain_id="chain-subagent-001",
            capabilities=["data_analysis"],
        )

        state = await manager.get_session_state(session_id)
        assert len(state.subagent_calls) == 1
        assert state.subagent_calls[0].subagent_name == "DataAnalyzer"

    @pytest.mark.asyncio
    async def test_session_error_handling(self):
        """Test session handles errors properly."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-error-001",
        )

        # End with error
        summary = await manager.end_session(
            session_id=session_id,
            status="failed",
            error_message="Execution failed due to API error",
        )

        assert summary.status == SessionStatus.FAILED
        assert summary.error_message == "Execution failed due to API error"

    @pytest.mark.asyncio
    async def test_session_cost_accumulation(self):
        """Test cost accumulates correctly over session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-cost-001",
        )

        # Multiple cost updates
        await manager.update_metrics(session_id, cost_added_usd=0.01)
        await manager.update_metrics(session_id, cost_added_usd=0.02)
        await manager.update_metrics(session_id, cost_added_usd=0.03)

        state = await manager.get_session_state(session_id)
        assert state.cost_usd == 0.06

    @pytest.mark.asyncio
    async def test_session_token_accumulation(self):
        """Test tokens accumulate correctly over session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-tokens-001",
        )

        # Multiple token updates
        await manager.update_metrics(session_id, tokens_added=100)
        await manager.update_metrics(session_id, tokens_added=200)
        await manager.update_metrics(session_id, tokens_added=300)

        state = await manager.get_session_state(session_id)
        assert state.tokens_used == 600


class TestStreamingWithSessionIntegration:
    """Integration tests combining streaming executor with session management."""

    @pytest.mark.asyncio
    async def test_streaming_with_session_tracking(self):
        """Test streaming execution with session state tracking."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        # Start session
        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-streaming-session",
        )

        # Execute with streaming
        async for event in executor.execute_with_events(
            agent=agent,
            task="Streaming session task",
            session_id=session_id,
        ):
            # Track messages
            if isinstance(event, MessageEvent):
                await manager.add_message(
                    session_id,
                    event.role,
                    event.content,
                )

            # Update metrics on completion
            if isinstance(event, CompletedEvent):
                await manager.update_metrics(
                    session_id=session_id,
                    tokens_added=event.total_tokens,
                    cost_added_usd=event.total_cost_usd,
                )

        # End session
        summary = await manager.end_session(
            session_id=session_id,
            status="completed",
        )

        assert summary.total_tokens == 100

    @pytest.mark.asyncio
    async def test_error_propagates_to_session(self):
        """Test errors are captured in session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = FailingAgent()
        executor = StreamingExecutor()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-error-session",
        )

        error_message = None
        try:
            async for event in executor.execute_with_events(
                agent=agent,
                task="Error task",
                session_id=session_id,
            ):
                if isinstance(event, ErrorEvent):
                    error_message = event.message
        except ValueError:
            pass

        # End session with error
        summary = await manager.end_session(
            session_id=session_id,
            status="failed",
            error_message=error_message,
        )

        assert summary.status == SessionStatus.FAILED
        assert "Intentional test error" in summary.error_message

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self):
        """Test multi-turn conversation with session tracking."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-multi-turn",
        )

        # Simulate 3 turns
        for turn in range(3):
            # Add user message
            await manager.add_message(
                session_id,
                "user",
                f"User message turn {turn}",
            )

            # Execute agent
            async for event in executor.execute_with_events(
                agent=agent,
                task=f"Task turn {turn}",
                session_id=session_id,
                execution_id=f"exec-turn-{turn}",
            ):
                if isinstance(event, MessageEvent):
                    await manager.add_message(
                        session_id,
                        event.role,
                        event.content,
                    )
                if isinstance(event, CompletedEvent):
                    await manager.update_metrics(
                        session_id,
                        tokens_added=event.total_tokens,
                        cycles_added=1,
                    )

        # Verify session state
        state = await manager.get_session_state(session_id)
        assert state.cycles_used == 3
        assert state.tokens_used == 300  # 100 * 3 turns
        assert len(state.messages) >= 3  # At least user messages


class TestEventSerializationIntegration:
    """Integration tests for event serialization."""

    @pytest.mark.asyncio
    async def test_all_events_json_serializable(self):
        """Test all events can be JSON serialized."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        async for event in executor.execute_with_events(
            agent=agent,
            task="JSON test",
        ):
            # Should not raise
            event_dict = event.to_dict()
            json_str = json.dumps(event_dict)
            assert isinstance(json_str, str)

            # Round-trip
            parsed = json.loads(json_str)
            assert "event_type" in parsed

    @pytest.mark.asyncio
    async def test_sse_stream_simulation(self):
        """Test simulated SSE stream."""
        agent = SimpleTestAgent()
        executor = StreamingExecutor()

        sse_stream = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="SSE stream test",
        ):
            sse = format_sse(event)
            sse_stream.append(sse)

        # Verify stream structure
        assert len(sse_stream) > 0
        for sse in sse_stream:
            assert sse.startswith("data: ")
            assert sse.endswith("\n\n")
