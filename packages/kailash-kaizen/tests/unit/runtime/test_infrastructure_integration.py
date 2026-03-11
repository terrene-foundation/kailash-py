"""
Unit Tests for LocalKaizenAdapter Infrastructure Integration (Tier 1)

Tests integration with Kaizen's existing infrastructure:
- StateManager: checkpoint save/restore
- HookManager: lifecycle event hooks
- InterruptManager: graceful shutdown handling

Coverage:
- Checkpoint creation during execution
- Checkpoint restoration on resume
- Hook firing at execution boundaries
- Interrupt handling during TAOD loop
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter
from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    AutonomousPhase,
    ExecutionState,
)
from kaizen.runtime.context import ExecutionContext, ExecutionStatus


class MockHookManager:
    """Mock HookManager for testing."""

    def __init__(self):
        self.events_triggered: List[Dict[str, Any]] = []
        self.registered_handlers: Dict[str, List] = {}

    async def trigger(
        self,
        event_type: str,
        agent_id: str,
        data: Dict[str, Any],
        timeout: float = 0.5,
        metadata: Dict[str, Any] = None,
        trace_id: str = None,
    ) -> List:
        """Record triggered event."""
        self.events_triggered.append(
            {
                "event_type": event_type,
                "agent_id": agent_id,
                "data": data,
                "metadata": metadata,
            }
        )
        return []

    def register(self, event_type: str, handler, priority=None):
        """Record registered handler."""
        if event_type not in self.registered_handlers:
            self.registered_handlers[event_type] = []
        self.registered_handlers[event_type].append(handler)


class MockStateManager:
    """Mock StateManager for testing."""

    def __init__(self):
        self.checkpoints: Dict[str, Dict[str, Any]] = {}
        self.checkpoint_count = 0

    def save_checkpoint(self, state: Any, force: bool = False) -> str:
        """Save checkpoint and return ID."""
        self.checkpoint_count += 1
        checkpoint_id = f"checkpoint_{self.checkpoint_count}"
        self.checkpoints[checkpoint_id] = {
            "id": checkpoint_id,
            "state": state.to_dict() if hasattr(state, "to_dict") else state,
            "forced": force,
        }
        return checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> Any:
        """Load checkpoint by ID."""
        if checkpoint_id not in self.checkpoints:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        return self.checkpoints[checkpoint_id]["state"]

    def resume_from_latest(self, agent_id: str) -> Any:
        """Resume from latest checkpoint."""
        if not self.checkpoints:
            return None
        latest_id = max(self.checkpoints.keys())
        return self.checkpoints[latest_id]["state"]

    def should_checkpoint(
        self, agent_id: str, current_step: int, current_time: float
    ) -> bool:
        """Determine if checkpoint needed."""
        return current_step % 10 == 0  # Every 10 steps


class MockInterruptManager:
    """Mock InterruptManager for testing."""

    def __init__(self):
        self._interrupted = False
        self._mode = None
        self._source = None
        self._callbacks: List = []

    def is_interrupted(self) -> bool:
        """Check if interrupt requested."""
        return self._interrupted

    def request_interrupt(
        self, mode: str = "graceful", source: str = "user", message: str = ""
    ):
        """Request interrupt."""
        self._interrupted = True
        self._mode = mode
        self._source = source

    def reset(self):
        """Reset interrupt state."""
        self._interrupted = False
        self._mode = None
        self._source = None

    def register_shutdown_callback(self, callback):
        """Register shutdown callback."""
        self._callbacks.append(callback)

    async def execute_shutdown_callbacks(self):
        """Execute all shutdown callbacks."""
        for callback in self._callbacks:
            await callback()


class TestHookManagerIntegration:
    """Test HookManager integration."""

    def test_adapter_stores_hook_manager(self):
        """Test adapter stores hook manager reference."""
        hook_manager = MockHookManager()
        adapter = LocalKaizenAdapter(hook_manager=hook_manager)

        assert adapter.hook_manager is hook_manager

    @pytest.mark.asyncio
    async def test_execution_start_hook(self):
        """Test hook fired at execution start."""
        hook_manager = MockHookManager()
        llm_provider = MagicMock()
        llm_provider.chat_async = AsyncMock(
            return_value={
                "content": "Task complete.",
                "tool_calls": None,
                "usage": {"total_tokens": 50},
            }
        )

        adapter = LocalKaizenAdapter(
            hook_manager=hook_manager,
            llm_provider=llm_provider,
        )

        context = ExecutionContext(task="Test task", session_id="test-session")
        await adapter.execute(context)

        # Verify execution_start hook was triggered
        start_events = [
            e
            for e in hook_manager.events_triggered
            if "start" in e["event_type"].lower()
        ]
        assert len(start_events) >= 1

    @pytest.mark.asyncio
    async def test_execution_complete_hook(self):
        """Test hook fired at execution complete."""
        hook_manager = MockHookManager()
        llm_provider = MagicMock()
        llm_provider.chat_async = AsyncMock(
            return_value={
                "content": "Task complete.",
                "tool_calls": None,
                "usage": {"total_tokens": 50},
            }
        )

        adapter = LocalKaizenAdapter(
            hook_manager=hook_manager,
            llm_provider=llm_provider,
        )

        context = ExecutionContext(task="Test task", session_id="test-session")
        await adapter.execute(context)

        # Verify execution_complete hook was triggered
        complete_events = [
            e
            for e in hook_manager.events_triggered
            if "complete" in e["event_type"].lower()
        ]
        assert len(complete_events) >= 1

    @pytest.mark.asyncio
    async def test_cycle_hooks(self):
        """Test hooks fired at cycle boundaries."""
        hook_manager = MockHookManager()
        llm_provider = MagicMock()

        # Two cycles: first with tool call, second without
        responses = [
            {
                "content": "Using tool",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "/tmp"}}],
                "usage": {"total_tokens": 50},
            },
            {"content": "Done.", "tool_calls": None, "usage": {"total_tokens": 30}},
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
        tool_registry.execute = AsyncMock(return_value="file contents")

        adapter = LocalKaizenAdapter(
            hook_manager=hook_manager,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Test task", session_id="test-session")
        await adapter.execute(context)

        # Verify cycle hooks were triggered
        cycle_events = [
            e
            for e in hook_manager.events_triggered
            if "cycle" in e["event_type"].lower()
        ]
        assert len(cycle_events) >= 1

    @pytest.mark.asyncio
    async def test_tool_execution_hooks(self):
        """Test hooks fired for tool execution."""
        hook_manager = MockHookManager()
        llm_provider = MagicMock()

        responses = [
            {
                "content": "Using tool",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "/tmp"}}],
                "usage": {"total_tokens": 50},
            },
            {"content": "Done.", "tool_calls": None, "usage": {"total_tokens": 30}},
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
        tool_registry.execute = AsyncMock(return_value="file contents")

        adapter = LocalKaizenAdapter(
            hook_manager=hook_manager,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Test task", session_id="test-session")
        await adapter.execute(context)

        # Verify tool hooks were triggered
        tool_events = [
            e
            for e in hook_manager.events_triggered
            if "tool" in e["event_type"].lower()
        ]
        assert len(tool_events) >= 1


class TestStateManagerIntegration:
    """Test StateManager integration."""

    def test_adapter_stores_state_manager(self):
        """Test adapter stores state manager reference."""
        state_manager = MockStateManager()
        adapter = LocalKaizenAdapter(state_manager=state_manager)

        assert adapter.state_manager is state_manager

    @pytest.mark.asyncio
    async def test_checkpoint_created_during_execution(self):
        """Test checkpoint created during long execution."""
        state_manager = MockStateManager()
        llm_provider = MagicMock()

        # Many cycles to trigger checkpoint
        responses = []
        for i in range(15):
            if i < 14:
                responses.append(
                    {
                        "content": f"Step {i}",
                        "tool_calls": [
                            {"name": "read_file", "arguments": {"path": f"/file{i}"}}
                        ],
                        "usage": {"total_tokens": 10},
                    }
                )
            else:
                responses.append(
                    {
                        "content": "Complete",
                        "tool_calls": None,
                        "usage": {"total_tokens": 10},
                    }
                )

        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            response = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return response

        llm_provider.chat_async = mock_chat

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = []
        tool_registry.execute = AsyncMock(return_value="ok")

        config = AutonomousConfig(checkpoint_frequency=5)  # Checkpoint every 5 cycles
        adapter = LocalKaizenAdapter(
            config=config,
            state_manager=state_manager,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Long task", session_id="test-session")
        await adapter.execute(context)

        # Verify checkpoints were created (at least 2 for 15 cycles with freq=5)
        assert state_manager.checkpoint_count >= 2

    @pytest.mark.asyncio
    async def test_checkpoint_on_interrupt(self):
        """Test checkpoint created on interrupt."""
        state_manager = MockStateManager()
        interrupt_manager = MockInterruptManager()
        llm_provider = MagicMock()

        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                interrupt_manager.request_interrupt()
            return {
                "content": f"Step {call_count}",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "/file"}}],
                "usage": {"total_tokens": 10},
            }

        llm_provider.chat_async = mock_chat

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = []
        tool_registry.execute = AsyncMock(return_value="ok")

        config = AutonomousConfig(checkpoint_on_interrupt=True)
        adapter = LocalKaizenAdapter(
            config=config,
            state_manager=state_manager,
            interrupt_manager=interrupt_manager,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Test task", session_id="test-session")
        result = await adapter.execute(context)

        # Verify checkpoint was created on interrupt
        assert state_manager.checkpoint_count >= 1
        assert result.status == ExecutionStatus.INTERRUPTED

    def test_resume_creates_state_from_checkpoint(self):
        """Test resume method creates state from checkpoint."""
        state_manager = MockStateManager()

        # Create a checkpoint
        original_state = ExecutionState(task="Original task")
        original_state.add_message({"role": "user", "content": "Hello"})
        original_state.current_cycle = 5
        checkpoint_id = state_manager.save_checkpoint(original_state)

        adapter = LocalKaizenAdapter(state_manager=state_manager)

        # Verify checkpoint exists
        checkpoint_data = state_manager.load_checkpoint(checkpoint_id)
        assert checkpoint_data is not None
        assert checkpoint_data["task"] == "Original task"
        assert checkpoint_data["current_cycle"] == 5


class TestInterruptManagerIntegration:
    """Test InterruptManager integration."""

    def test_adapter_stores_interrupt_manager(self):
        """Test adapter stores interrupt manager reference."""
        interrupt_manager = MockInterruptManager()
        adapter = LocalKaizenAdapter(interrupt_manager=interrupt_manager)

        assert adapter.interrupt_manager is interrupt_manager

    @pytest.mark.asyncio
    async def test_interrupt_stops_execution(self):
        """Test interrupt request stops execution."""
        interrupt_manager = MockInterruptManager()
        llm_provider = MagicMock()

        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                interrupt_manager.request_interrupt()
            return {
                "content": f"Step {call_count}",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "/file"}}],
                "usage": {"total_tokens": 10},
            }

        llm_provider.chat_async = mock_chat

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = []
        tool_registry.execute = AsyncMock(return_value="ok")

        adapter = LocalKaizenAdapter(
            interrupt_manager=interrupt_manager,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Test task", session_id="test-session")
        result = await adapter.execute(context)

        # Verify execution stopped with interrupted status
        assert result.status == ExecutionStatus.INTERRUPTED
        assert call_count >= 2  # Had at least 2 cycles before interrupt

    @pytest.mark.asyncio
    async def test_interrupt_via_adapter_method(self):
        """Test interrupt via adapter's interrupt() method."""
        interrupt_manager = MockInterruptManager()
        adapter = LocalKaizenAdapter(interrupt_manager=interrupt_manager)

        # Create a mock state to simulate active execution
        state = ExecutionState(task="Test task")
        adapter._current_state = state

        # Request interrupt via adapter method
        success = await adapter.interrupt(state.session_id, mode="graceful")

        assert success is True
        assert interrupt_manager.is_interrupted() is True

    @pytest.mark.asyncio
    async def test_interrupt_wrong_session_fails(self):
        """Test interrupt with wrong session ID fails."""
        interrupt_manager = MockInterruptManager()
        adapter = LocalKaizenAdapter(interrupt_manager=interrupt_manager)

        # Create a mock state
        state = ExecutionState(task="Test task")
        adapter._current_state = state

        # Try to interrupt wrong session
        success = await adapter.interrupt("wrong-session-id", mode="graceful")

        assert success is False
        assert interrupt_manager.is_interrupted() is False

    @pytest.mark.asyncio
    async def test_interrupt_no_active_session(self):
        """Test interrupt with no active session."""
        interrupt_manager = MockInterruptManager()
        adapter = LocalKaizenAdapter(interrupt_manager=interrupt_manager)

        # No active state
        adapter._current_state = None

        success = await adapter.interrupt("any-session-id", mode="graceful")

        assert success is False


class TestCombinedInfrastructure:
    """Test all infrastructure components working together."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_all_managers(self):
        """Test complete execution lifecycle with all managers."""
        hook_manager = MockHookManager()
        state_manager = MockStateManager()
        interrupt_manager = MockInterruptManager()
        llm_provider = MagicMock()

        responses = [
            {
                "content": "Step 1",
                "tool_calls": [{"name": "read", "arguments": {}}],
                "usage": {"total_tokens": 10},
            },
            {
                "content": "Step 2",
                "tool_calls": [{"name": "read", "arguments": {}}],
                "usage": {"total_tokens": 10},
            },
            {"content": "Done", "tool_calls": None, "usage": {"total_tokens": 10}},
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
        tool_registry.execute = AsyncMock(return_value="ok")

        adapter = LocalKaizenAdapter(
            hook_manager=hook_manager,
            state_manager=state_manager,
            interrupt_manager=interrupt_manager,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Full test", session_id="full-test-session")
        result = await adapter.execute(context)

        # Verify hooks were triggered
        assert len(hook_manager.events_triggered) >= 2  # At least start and complete

        # Verify execution completed
        assert result.status == ExecutionStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_interrupt_with_checkpoint_and_hooks(self):
        """Test interrupt triggers checkpoint and hooks."""
        hook_manager = MockHookManager()
        state_manager = MockStateManager()
        interrupt_manager = MockInterruptManager()
        llm_provider = MagicMock()

        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                interrupt_manager.request_interrupt()
            return {
                "content": f"Step {call_count}",
                "tool_calls": [{"name": "read", "arguments": {}}],
                "usage": {"total_tokens": 10},
            }

        llm_provider.chat_async = mock_chat

        tool_registry = MagicMock()
        tool_registry.get_tool_schemas.return_value = []
        tool_registry.execute = AsyncMock(return_value="ok")

        config = AutonomousConfig(checkpoint_on_interrupt=True)
        adapter = LocalKaizenAdapter(
            config=config,
            hook_manager=hook_manager,
            state_manager=state_manager,
            interrupt_manager=interrupt_manager,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
        )

        context = ExecutionContext(task="Interrupt test", session_id="interrupt-test")
        result = await adapter.execute(context)

        # Verify result
        assert result.status == ExecutionStatus.INTERRUPTED

        # Verify checkpoint was created
        assert state_manager.checkpoint_count >= 1

        # Verify interrupt hook was triggered
        interrupt_events = [
            e
            for e in hook_manager.events_triggered
            if "interrupt" in e["event_type"].lower()
        ]
        assert len(interrupt_events) >= 1


class TestLazyInitialization:
    """Test lazy initialization of infrastructure components."""

    def test_adapter_works_without_infrastructure(self):
        """Test adapter works without any infrastructure components."""
        adapter = LocalKaizenAdapter()

        assert adapter.state_manager is None
        assert adapter.hook_manager is None
        assert adapter.interrupt_manager is None

    @pytest.mark.asyncio
    async def test_execution_without_infrastructure(self):
        """Test execution works without infrastructure components."""
        llm_provider = MagicMock()
        llm_provider.chat_async = AsyncMock(
            return_value={
                "content": "Done",
                "tool_calls": None,
                "usage": {"total_tokens": 10},
            }
        )

        adapter = LocalKaizenAdapter(llm_provider=llm_provider)

        context = ExecutionContext(task="Simple test", session_id="simple-session")
        result = await adapter.execute(context)

        assert result.status == ExecutionStatus.COMPLETE
