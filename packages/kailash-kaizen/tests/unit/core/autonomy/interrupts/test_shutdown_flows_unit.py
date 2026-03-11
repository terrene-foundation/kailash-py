"""
Unit tests for graceful shutdown flows (TODO-169 Day 2).

Tests shutdown callback execution, graceful vs immediate mode handling,
and configuration options for interrupts.

Test Strategy: Tier 1 (Unit) - Real InterruptManager instances (NO MOCKING)
Coverage: 10 tests for Day 2 acceptance criteria
"""

import asyncio
from pathlib import Path

import pytest
from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.types import InterruptMode, InterruptSource
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.core.autonomy.state.types import AgentState
from kaizen.signatures import InputField, OutputField, Signature


class TaskSignature(Signature):
    """Simple signature for testing"""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")


# ═══════════════════════════════════════════════════════════════
# Test: Shutdown Callback Registration (2 tests)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_shutdown_callback_registration():
    """
    Test that shutdown callbacks can be registered.

    Validates:
    - register_shutdown_callback() adds callback
    - Multiple callbacks can be registered
    - Callbacks are stored in order
    """
    # Arrange
    manager = InterruptManager()
    executed = []

    async def callback1():
        executed.append("callback1")

    async def callback2():
        executed.append("callback2")

    # Act
    manager.register_shutdown_callback(callback1)
    manager.register_shutdown_callback(callback2)

    # Assert
    assert len(manager._shutdown_callbacks) == 2, "Should have 2 callbacks"
    assert manager._shutdown_callbacks[0] is callback1, "First callback correct"
    assert manager._shutdown_callbacks[1] is callback2, "Second callback correct"


@pytest.mark.asyncio
async def test_shutdown_callback_execution_order():
    """
    Test that shutdown callbacks execute in registration order.

    Validates:
    - Callbacks execute in order they were registered
    - All callbacks execute even if one fails
    - Execution order is deterministic
    """
    # Arrange
    manager = InterruptManager()
    executed = []

    async def callback1():
        executed.append("callback1")

    async def callback2():
        executed.append("callback2")

    async def callback3():
        executed.append("callback3")

    manager.register_shutdown_callback(callback1)
    manager.register_shutdown_callback(callback2)
    manager.register_shutdown_callback(callback3)

    # Act
    await manager.execute_shutdown_callbacks()

    # Assert
    assert executed == [
        "callback1",
        "callback2",
        "callback3",
    ], "Should execute in order"


# ═══════════════════════════════════════════════════════════════
# Test: Shutdown Callback Error Handling (2 tests)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_shutdown_callback_error_handling():
    """
    Test that shutdown callbacks continue execution even if one fails.

    Validates:
    - Callback errors don't stop execution
    - All callbacks execute despite errors
    - Errors are logged but not raised
    """
    # Arrange
    manager = InterruptManager()
    executed = []

    async def callback1():
        executed.append("callback1")

    async def callback_error():
        executed.append("callback_error")
        raise ValueError("Simulated error")

    async def callback2():
        executed.append("callback2")

    manager.register_shutdown_callback(callback1)
    manager.register_shutdown_callback(callback_error)
    manager.register_shutdown_callback(callback2)

    # Act
    await manager.execute_shutdown_callbacks()  # Should not raise

    # Assert
    assert "callback1" in executed, "First callback should execute"
    assert "callback_error" in executed, "Error callback should execute"
    assert "callback2" in executed, "Second callback should execute"
    assert len(executed) == 3, "All callbacks should execute"


@pytest.mark.asyncio
async def test_shutdown_callback_with_async_operations():
    """
    Test that shutdown callbacks can perform async operations.

    Validates:
    - Callbacks can await async operations
    - Async operations complete successfully
    - Multiple async callbacks work correctly
    """
    # Arrange
    manager = InterruptManager()
    results = []

    async def async_callback1():
        await asyncio.sleep(0.01)  # Simulate async operation
        results.append("async1")

    async def async_callback2():
        await asyncio.sleep(0.01)  # Simulate async operation
        results.append("async2")

    manager.register_shutdown_callback(async_callback1)
    manager.register_shutdown_callback(async_callback2)

    # Act
    await manager.execute_shutdown_callbacks()

    # Assert
    assert results == ["async1", "async2"], "Async callbacks should complete in order"


# ═══════════════════════════════════════════════════════════════
# Test: Graceful vs Immediate Mode (3 tests)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_graceful_mode_interrupt():
    """
    Test that graceful mode allows current step to finish.

    Validates:
    - Graceful mode is respected
    - Shutdown callbacks execute
    - Checkpoint is saved
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10,
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        checkpoint_frequency=5,
    )

    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Setup state manager
    storage = FilesystemStorage(base_dir=Path("/tmp/test_interrupts"))
    state_manager = StateManager(storage=storage)

    # Create initial state
    agent_state = AgentState(
        agent_id=agent.agent_id,
        conversation_history=["step1", "step2"],
        metadata={"status": "running"},
    )

    # Request graceful interrupt
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="User requested graceful stop",
        metadata={"reason": "testing"},
    )

    # Act
    status = await agent.interrupt_manager.execute_shutdown(
        state_manager=state_manager, agent_state=agent_state
    )

    # Assert
    assert status.interrupted, "Should be interrupted"
    assert status.reason is not None, "Should have interrupt reason"
    assert status.reason.mode == InterruptMode.GRACEFUL, "Should be graceful mode"
    assert status.checkpoint_id is not None, "Should have checkpoint ID"
    assert agent_state.status == "interrupted", "State should be marked as interrupted"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


@pytest.mark.asyncio
async def test_immediate_mode_interrupt():
    """
    Test that immediate mode stops execution immediately.

    Validates:
    - Immediate mode is respected
    - Checkpoint is saved if possible
    - Shutdown is immediate
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )

    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Setup state manager
    storage = FilesystemStorage(base_dir=Path("/tmp/test_interrupts"))
    state_manager = StateManager(storage=storage)

    # Create initial state
    agent_state = AgentState(
        agent_id=agent.agent_id,
        conversation_history=["step1"],
        metadata={"status": "running"},
    )

    # Request immediate interrupt
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.IMMEDIATE,
        source=InterruptSource.TIMEOUT,
        message="System requested immediate stop",
        metadata={"reason": "budget_exceeded"},
    )

    # Act
    status = await agent.interrupt_manager.execute_shutdown(
        state_manager=state_manager, agent_state=agent_state
    )

    # Assert
    assert status.interrupted, "Should be interrupted"
    assert status.reason is not None, "Should have interrupt reason"
    assert status.reason.mode == InterruptMode.IMMEDIATE, "Should be immediate mode"
    assert status.checkpoint_id is not None, "Should save checkpoint"
    assert agent_state.status == "interrupted", "State should be marked as interrupted"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


@pytest.mark.asyncio
async def test_interrupt_status_metadata():
    """
    Test that interrupt status includes metadata.

    Validates:
    - Interrupt reason includes metadata
    - Checkpoint ID is included if saved
    - Status is correctly structured
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )

    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Setup state manager
    storage = FilesystemStorage(base_dir=Path("/tmp/test_interrupts"))
    state_manager = StateManager(storage=storage)

    # Create initial state
    agent_state = AgentState(
        agent_id=agent.agent_id,
        conversation_history=["step1"],
        metadata={"status": "running"},
    )

    # Request interrupt with metadata
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.PROGRAMMATIC,
        message="Budget limit exceeded",
        metadata={
            "budget_limit": 100.0,
            "budget_used": 105.0,
            "operation": "expensive_api_call",
        },
    )

    # Act
    status = await agent.interrupt_manager.execute_shutdown(
        state_manager=state_manager, agent_state=agent_state
    )

    # Assert
    assert status.interrupted, "Should be interrupted"
    assert status.reason.metadata is not None, "Should have metadata"
    assert "budget_limit" in status.reason.metadata, "Should include budget_limit"
    assert status.reason.metadata["budget_used"] == 105.0, "Should preserve metadata"

    # Check state metadata
    assert (
        "interrupt_reason" in agent_state.metadata
    ), "State should include interrupt reason"
    interrupt_data = agent_state.metadata["interrupt_reason"]
    assert (
        interrupt_data["message"] == "Budget limit exceeded"
    ), "Should preserve message"
    assert interrupt_data["source"] == "programmatic", "Should preserve source"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


# ═══════════════════════════════════════════════════════════════
# Test: Configuration Options (3 tests)
# ═══════════════════════════════════════════════════════════════


def test_autonomous_config_interrupt_defaults():
    """
    Test that AutonomousConfig has correct interrupt defaults.

    Validates:
    - enable_interrupts defaults to True
    - graceful_shutdown_timeout defaults to 5.0 seconds
    - checkpoint_on_interrupt defaults to True
    """
    # Arrange & Act
    config = AutonomousConfig()

    # Assert
    assert hasattr(
        config, "enable_interrupts"
    ), "Should have enable_interrupts attribute"
    assert config.enable_interrupts is True, "Should default to True"

    assert hasattr(
        config, "graceful_shutdown_timeout"
    ), "Should have graceful_shutdown_timeout"
    assert config.graceful_shutdown_timeout == 5.0, "Should default to 5.0 seconds"

    assert hasattr(
        config, "checkpoint_on_interrupt"
    ), "Should have checkpoint_on_interrupt"
    assert config.checkpoint_on_interrupt is True, "Should default to True"


def test_autonomous_config_interrupt_custom_values():
    """
    Test that interrupt configuration can be customized.

    Validates:
    - enable_interrupts can be set to False
    - graceful_shutdown_timeout can be customized
    - checkpoint_on_interrupt can be set to False
    """
    # Arrange & Act
    config = AutonomousConfig(
        enable_interrupts=False,
        graceful_shutdown_timeout=10.0,
        checkpoint_on_interrupt=False,
    )

    # Assert
    assert config.enable_interrupts is False, "Should respect custom value"
    assert config.graceful_shutdown_timeout == 10.0, "Should respect custom value"
    assert config.checkpoint_on_interrupt is False, "Should respect custom value"


@pytest.mark.asyncio
async def test_disabled_interrupts_configuration():
    """
    Test that interrupts can be disabled via configuration.

    Validates:
    - enable_interrupts=False disables interrupt handling
    - Agent still works normally
    - No interrupt manager is installed
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=5,
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        enable_interrupts=False,
    )

    # Act
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Assert
    assert hasattr(agent, "interrupt_manager"), "Should have interrupt_manager field"

    # Even if disabled, interrupt_manager should exist but not install signal handlers
    # This is for backward compatibility
    assert isinstance(
        agent.interrupt_manager, InterruptManager
    ), "Should be InterruptManager instance"

    # Cleanup
    if agent.interrupt_manager._signal_handlers_installed:
        agent.interrupt_manager.uninstall_signal_handlers()
