"""
Unit Tests for StreamingExecutor (Tier 1)

Tests the streaming execution wrapper for Enterprise-App integration.
Part of TODO-204 Enterprise-App Streaming Integration.

Coverage:
- StreamingExecutor initialization
- Event emission during execution
- ExecutionMetrics tracking
- SSE formatting
- Error handling
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from kaizen.execution.events import (
    CompletedEvent,
    ErrorEvent,
    EventType,
    MessageEvent,
    ProgressEvent,
    StartedEvent,
    ThinkingEvent,
)
from kaizen.execution.streaming_executor import (
    ExecutionMetrics,
    StreamingExecutor,
    format_sse,
)


class MockAgent:
    """Mock agent for testing."""

    def __init__(
        self,
        name: str = "MockAgent",
        agent_id: str = "mock-agent-001",
        return_value: Dict[str, Any] = None,
        raise_error: Exception = None,
    ):
        self.name = name
        self.agent_id = agent_id
        self._return_value = return_value or {"answer": "Test response"}
        self._raise_error = raise_error
        self.run_called = False
        self.run_inputs = None

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous run method."""
        self.run_called = True
        self.run_inputs = kwargs

        if self._raise_error:
            raise self._raise_error

        return self._return_value


class AsyncMockAgent:
    """Async mock agent for testing."""

    def __init__(
        self,
        name: str = "AsyncMockAgent",
        agent_id: str = "async-mock-001",
        return_value: Dict[str, Any] = None,
        raise_error: Exception = None,
    ):
        self.name = name
        self.agent_id = agent_id
        self._return_value = return_value or {"answer": "Async test response"}
        self._raise_error = raise_error
        self.run_called = False
        self.run_inputs = None

    async def run_async(self, **kwargs) -> Dict[str, Any]:
        """Asynchronous run method."""
        self.run_called = True
        self.run_inputs = kwargs

        if self._raise_error:
            raise self._raise_error

        return self._return_value


class TestExecutionMetrics:
    """Test ExecutionMetrics dataclass."""

    def test_default_values(self):
        """Test default values for ExecutionMetrics."""
        metrics = ExecutionMetrics(
            execution_id="exec-123",
            session_id="session-456",
        )

        assert metrics.execution_id == "exec-123"
        assert metrics.session_id == "session-456"
        assert metrics.total_tokens == 0
        assert metrics.total_cost_usd == 0.0
        assert metrics.cycles_used == 0
        assert metrics.tools_used == 0
        assert metrics.subagents_spawned == 0
        assert metrics.messages == []
        assert metrics.tool_calls == []
        assert metrics.subagent_calls == []
        assert metrics.end_time is None

    def test_duration_ms_ongoing(self):
        """Test duration_ms for ongoing execution."""
        metrics = ExecutionMetrics(
            execution_id="exec-123",
            session_id="session-456",
        )

        # Duration should be positive
        assert metrics.duration_ms >= 0

    def test_duration_ms_completed(self):
        """Test duration_ms for completed execution."""
        import time

        metrics = ExecutionMetrics(
            execution_id="exec-123",
            session_id="session-456",
        )
        metrics.start_time = time.time() - 1.5  # 1.5 seconds ago
        metrics.end_time = time.time()

        # Duration should be approximately 1500ms
        assert 1400 <= metrics.duration_ms <= 1600

    def test_total_cost_cents(self):
        """Test cost conversion to cents."""
        metrics = ExecutionMetrics(
            execution_id="exec-123",
            session_id="session-456",
        )
        metrics.total_cost_usd = 0.45

        assert metrics.total_cost_cents == 45


class TestStreamingExecutorInit:
    """Test StreamingExecutor initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        executor = StreamingExecutor()

        assert executor._on_event is None
        assert executor._cost_per_1k_input == 0.01
        assert executor._cost_per_1k_output == 0.03

    def test_custom_callback(self):
        """Test initialization with custom callback."""
        events = []
        executor = StreamingExecutor(on_event=lambda e: events.append(e))

        assert executor._on_event is not None

    def test_custom_cost_rates(self):
        """Test initialization with custom cost rates."""
        executor = StreamingExecutor(
            cost_per_1k_input_tokens=0.02,
            cost_per_1k_output_tokens=0.06,
        )

        assert executor._cost_per_1k_input == 0.02
        assert executor._cost_per_1k_output == 0.06


class TestStreamingExecutorExecution:
    """Test StreamingExecutor execution."""

    @pytest.mark.asyncio
    async def test_sync_agent_execution(self):
        """Test execution of sync agent."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        # Agent should have been called
        assert agent.run_called

        # Should have events
        assert len(events) > 0

        # Should have started event
        started_events = [e for e in events if isinstance(e, StartedEvent)]
        assert len(started_events) == 1

    @pytest.mark.asyncio
    async def test_async_agent_execution(self):
        """Test execution of async agent."""
        agent = AsyncMockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test async task",
        ):
            events.append(event)

        # Agent should have been called
        assert agent.run_called

        # Should have events
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_started_event_emitted_first(self):
        """Test that STARTED event is emitted first."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        # First event should be StartedEvent
        assert isinstance(events[0], StartedEvent)
        assert events[0].event_type == EventType.STARTED

    @pytest.mark.asyncio
    async def test_completed_event_emitted_last(self):
        """Test that COMPLETED event is emitted last."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        # Last event should be CompletedEvent
        assert isinstance(events[-1], CompletedEvent)
        assert events[-1].event_type == EventType.COMPLETED

    @pytest.mark.asyncio
    async def test_thinking_event_emitted(self):
        """Test that THINKING event is emitted."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        # Should have thinking event
        thinking_events = [e for e in events if isinstance(e, ThinkingEvent)]
        assert len(thinking_events) >= 1

    @pytest.mark.asyncio
    async def test_message_event_emitted(self):
        """Test that MESSAGE event is emitted."""
        agent = MockAgent(return_value={"answer": "Test answer"})
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        # Should have message event with output
        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert len(message_events) >= 1
        assert message_events[0].content == "Test answer"

    @pytest.mark.asyncio
    async def test_progress_events_emitted(self):
        """Test that PROGRESS events are emitted."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        # Should have progress events
        progress_events = [e for e in events if isinstance(e, ProgressEvent)]
        assert len(progress_events) >= 1

    @pytest.mark.asyncio
    async def test_session_id_provided(self):
        """Test execution with provided session_id."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
            session_id="custom-session-123",
        ):
            events.append(event)

        # All events should have the custom session_id
        for event in events:
            assert event.session_id == "custom-session-123"

    @pytest.mark.asyncio
    async def test_execution_id_provided(self):
        """Test execution with provided execution_id."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
            execution_id="custom-exec-456",
        ):
            events.append(event)

        # Started event should have the custom execution_id
        started = [e for e in events if isinstance(e, StartedEvent)][0]
        assert started.execution_id == "custom-exec-456"

    @pytest.mark.asyncio
    async def test_trust_chain_propagation(self):
        """Test trust chain is propagated in events."""
        agent = MockAgent()
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
            trust_chain_id="chain-abc",
        ):
            events.append(event)

        # Started event should have trust_chain_id
        started = [e for e in events if isinstance(e, StartedEvent)][0]
        assert started.trust_chain_id == "chain-abc"


class TestStreamingExecutorErrorHandling:
    """Test error handling in StreamingExecutor."""

    @pytest.mark.asyncio
    async def test_error_event_on_agent_error(self):
        """Test that ERROR event is emitted on agent error."""
        agent = MockAgent(raise_error=ValueError("Test error"))
        executor = StreamingExecutor()

        events = []
        with pytest.raises(ValueError):
            async for event in executor.execute_with_events(
                agent=agent,
                task="Test task",
            ):
                events.append(event)

        # Should have error event
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].message == "Test error"
        assert error_events[0].error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_recoverable_error_detection(self):
        """Test that recoverable errors are detected."""

        # Create a custom RateLimitError
        class RateLimitError(Exception):
            pass

        agent = MockAgent(raise_error=RateLimitError("Rate limit exceeded"))
        executor = StreamingExecutor()

        events = []
        with pytest.raises(RateLimitError):
            async for event in executor.execute_with_events(
                agent=agent,
                task="Test task",
            ):
                events.append(event)

        # Error event should mark as recoverable
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].recoverable is True


class TestStreamingExecutorCallback:
    """Test callback functionality."""

    @pytest.mark.asyncio
    async def test_callback_called_for_each_event(self):
        """Test that callback is called for each event."""
        agent = MockAgent()
        callback_events = []
        executor = StreamingExecutor(on_event=lambda e: callback_events.append(e))

        async for _ in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            pass

        # Callback should have been called
        assert len(callback_events) > 0


class TestFormatSSE:
    """Test SSE formatting function."""

    def test_format_started_event(self):
        """Test formatting StartedEvent to SSE."""
        event = StartedEvent(
            session_id="session-123",
            execution_id="exec-456",
            agent_id="agent-001",
            agent_name="Test Agent",
        )

        sse = format_sse(event)

        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        assert '"event_type": "started"' in sse
        assert '"execution_id": "exec-456"' in sse

    def test_format_completed_event(self):
        """Test formatting CompletedEvent to SSE."""
        event = CompletedEvent(
            session_id="session-123",
            execution_id="exec-456",
            total_tokens=1500,
            total_cost_cents=45,
        )

        sse = format_sse(event)

        assert '"event_type": "completed"' in sse
        assert '"total_tokens": 1500' in sse

    def test_format_message_event(self):
        """Test formatting MessageEvent to SSE."""
        event = MessageEvent(
            session_id="session-123",
            role="assistant",
            content="Hello, world!",
        )

        sse = format_sse(event)

        assert '"event_type": "message"' in sse
        assert '"role": "assistant"' in sse
        assert '"content": "Hello, world!"' in sse


class TestStreamingExecutorMetrics:
    """Test metrics tracking in StreamingExecutor."""

    @pytest.mark.asyncio
    async def test_completed_event_has_metrics(self):
        """Test that completed event includes metrics."""
        agent = MockAgent(return_value={"answer": "Test", "tokens_used": 100})
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        # Get completed event
        completed = [e for e in events if isinstance(e, CompletedEvent)][0]

        # Should have metrics
        assert completed.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_tokens_from_agent_result(self):
        """Test that tokens are extracted from agent result."""
        agent = MockAgent(return_value={"answer": "Test", "tokens_used": 500})
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        completed = [e for e in events if isinstance(e, CompletedEvent)][0]
        assert completed.total_tokens == 500

    @pytest.mark.asyncio
    async def test_cost_from_agent_result(self):
        """Test that cost is extracted from agent result."""
        agent = MockAgent(return_value={"answer": "Test", "cost_usd": 0.05})
        executor = StreamingExecutor()

        events = []
        async for event in executor.execute_with_events(
            agent=agent,
            task="Test task",
        ):
            events.append(event)

        completed = [e for e in events if isinstance(e, CompletedEvent)][0]
        assert completed.total_cost_usd == 0.05
