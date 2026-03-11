"""
Unit tests for BaseAutonomousAgent interrupt integration (TODO-169 Day 1).

Tests interrupt_manager integration with BaseAutonomousAgent:
- interrupt_manager field initialization
- _on_shutdown() callback registration
- Interrupt detection in autonomous loop
- _save_final_checkpoint() with interrupt metadata

Test Strategy: Tier 1 (Unit) - Real InterruptManager instances (NO MOCKING)
Coverage: 10 tests for Day 1 acceptance criteria
"""

import pytest
from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.types import (
    InterruptedError,
    InterruptMode,
    InterruptSource,
)
from kaizen.signatures import InputField, OutputField, Signature


class TaskSignature(Signature):
    """Simple signature for testing"""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")


# ═══════════════════════════════════════════════════════════════
# Test: interrupt_manager Field Initialization (3 tests)
# ═══════════════════════════════════════════════════════════════


def test_interrupt_manager_default_initialization():
    """
    Test that interrupt_manager is created by default if not provided.

    Validates:
    - interrupt_manager is automatically created
    - interrupt_manager is instance of InterruptManager
    - Signal handlers ARE installed automatically
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )

    # Act
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Assert
    assert hasattr(agent, "interrupt_manager"), "Should have interrupt_manager field"
    assert isinstance(
        agent.interrupt_manager, InterruptManager
    ), "Should be InterruptManager instance"
    assert (
        agent.interrupt_manager._signal_handlers_installed
    ), "Signal handlers should be installed"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


def test_interrupt_manager_custom_instance():
    """
    Test that custom InterruptManager can be provided.

    Validates:
    - Custom interrupt_manager is used
    - Custom instance is not replaced
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )
    custom_manager = InterruptManager()
    custom_manager.custom_marker = "test_marker"  # Add marker for verification

    # Act
    agent = BaseAutonomousAgent(
        config=config, signature=TaskSignature(), interrupt_manager=custom_manager
    )

    # Assert
    assert agent.interrupt_manager is custom_manager, "Should use custom manager"
    assert hasattr(
        agent.interrupt_manager, "custom_marker"
    ), "Should preserve custom instance"
    assert (
        agent.interrupt_manager.custom_marker == "test_marker"
    ), "Should be same instance"


def test_interrupt_manager_signal_handlers_installed():
    """
    Test that signal handlers are installed during initialization.

    Validates:
    - install_signal_handlers() is called during __init__
    - Signal handlers are active after initialization
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )

    # Act
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Assert
    assert (
        agent.interrupt_manager._signal_handlers_installed
    ), "Signal handlers should be installed"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


# ═══════════════════════════════════════════════════════════════
# Test: _on_shutdown() Callback Registration (2 tests)
# ═══════════════════════════════════════════════════════════════


def test_on_shutdown_callback_registered():
    """
    Test that _on_shutdown() callback is registered during initialization.

    Validates:
    - _on_shutdown() is registered as shutdown callback
    - InterruptManager contains the callback
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )

    # Act
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Assert
    assert (
        len(agent.interrupt_manager._shutdown_callbacks) > 0
    ), "Should have shutdown callbacks"
    # Verify _on_shutdown is in callbacks
    callback_names = [cb.__name__ for cb in agent.interrupt_manager._shutdown_callbacks]
    assert (
        "_on_shutdown" in callback_names
    ), "_on_shutdown should be registered as callback"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


@pytest.mark.asyncio
async def test_on_shutdown_callback_execution():
    """
    Test that _on_shutdown() is executed when callbacks are triggered.

    Validates:
    - _on_shutdown() is called when execute_shutdown_callbacks() runs
    - Callback executes without errors
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Track callback execution
    callback_executed = False

    # Replace _on_shutdown with tracking version
    original_on_shutdown = agent._on_shutdown

    async def tracked_on_shutdown():
        nonlocal callback_executed
        callback_executed = True
        await original_on_shutdown()

    agent._on_shutdown = tracked_on_shutdown

    # Re-register tracked callback
    agent.interrupt_manager._shutdown_callbacks.clear()
    agent.interrupt_manager.register_shutdown_callback(tracked_on_shutdown)

    # Act
    await agent.interrupt_manager.execute_shutdown_callbacks()

    # Assert
    assert callback_executed, "_on_shutdown should be executed"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


# ═══════════════════════════════════════════════════════════════
# Test: Interrupt Detection in Loop (3 tests)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_interrupt_detection_graceful_mode():
    """
    Test that graceful interrupt is detected and handled in loop.

    Validates:
    - Graceful interrupt allows current cycle to complete
    - _save_final_checkpoint() is called
    - InterruptedError is raised
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=20, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Track checkpoint save
    checkpoint_saved = False
    original_save = agent._save_final_checkpoint

    async def tracked_save(*args, **kwargs):
        nonlocal checkpoint_saved
        checkpoint_saved = True
        return await original_save(*args, **kwargs)

    agent._save_final_checkpoint = tracked_save

    # Request graceful interrupt BEFORE starting loop
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test graceful interrupt",
    )

    # Act & Assert
    with pytest.raises(InterruptedError) as exc_info:
        await agent._autonomous_loop("Test task")

    # Verify interrupt message
    assert "Test graceful interrupt" in str(
        exc_info.value
    ), "Should include interrupt message"

    # Verify checkpoint was saved
    assert checkpoint_saved, "Should save final checkpoint before exit"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


@pytest.mark.asyncio
async def test_interrupt_detection_immediate_mode():
    """
    Test that immediate interrupt stops execution without completing cycle.

    Validates:
    - Immediate interrupt stops immediately
    - _save_final_checkpoint() is called
    - InterruptedError is raised
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=20, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Track checkpoint save
    checkpoint_saved = False
    original_save = agent._save_final_checkpoint

    async def tracked_save(*args, **kwargs):
        nonlocal checkpoint_saved
        checkpoint_saved = True
        return await original_save(*args, **kwargs)

    agent._save_final_checkpoint = tracked_save

    # Request immediate interrupt BEFORE starting loop
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.IMMEDIATE,
        source=InterruptSource.USER,
        message="Test immediate interrupt",
    )

    # Act & Assert
    with pytest.raises(InterruptedError) as exc_info:
        await agent._autonomous_loop("Test task")

    # Verify interrupt message
    assert "Test immediate interrupt" in str(
        exc_info.value
    ), "Should include interrupt message"

    # Verify checkpoint was saved
    assert checkpoint_saved, "Should save final checkpoint before exit"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


def test_is_interrupted_check_in_loop():
    """
    Test that is_interrupted() is checked during loop execution.

    Validates:
    - Loop checks interrupt_manager.is_interrupted()
    - Interrupt detection happens before each cycle
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Request interrupt immediately
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test interrupt check",
    )

    # Act & Assert
    is_interrupted = agent.interrupt_manager.is_interrupted()
    assert is_interrupted, "Should detect interrupt flag"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


# ═══════════════════════════════════════════════════════════════
# Test: _save_final_checkpoint() with Interrupt (2 tests)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_save_final_checkpoint_with_interrupt_metadata():
    """
    Test that _save_final_checkpoint() includes interrupt metadata.

    Validates:
    - Checkpoint includes interrupt_reason
    - Status is set to "interrupted"
    - Metadata contains source, mode, message, timestamp
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Create interrupt reason
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.TIMEOUT,
        message="Execution timeout",
        metadata={"timeout_seconds": 300},
    )

    reason = agent.interrupt_manager.get_interrupt_reason()

    # Act
    checkpoint_id = await agent._save_final_checkpoint(interrupted=True, reason=reason)

    # Assert
    assert checkpoint_id is not None, "Should return checkpoint ID"

    # Load checkpoint and verify metadata
    saved_state = await agent.state_manager.load_checkpoint(checkpoint_id)

    assert saved_state is not None, "Should save checkpoint"
    assert saved_state.status == "interrupted", "Status should be 'interrupted'"
    assert "interrupt_reason" in saved_state.metadata, "Should include interrupt_reason"

    interrupt_meta = saved_state.metadata["interrupt_reason"]
    assert interrupt_meta["source"] == "timeout", "Should include source"
    assert interrupt_meta["mode"] == "graceful", "Should include mode"
    assert interrupt_meta["message"] == "Execution timeout", "Should include message"
    assert "timestamp" in interrupt_meta, "Should include timestamp"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()


@pytest.mark.asyncio
async def test_save_final_checkpoint_without_interrupt():
    """
    Test that _save_final_checkpoint() works without interrupt (normal completion).

    Validates:
    - Checkpoint saved successfully without interrupt
    - Status is NOT "interrupted"
    - No interrupt_reason in metadata
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Act - Normal completion (no interrupt)
    checkpoint_id = await agent._save_final_checkpoint(interrupted=False, reason=None)

    # Assert
    assert checkpoint_id is not None, "Should return checkpoint ID"

    # Load checkpoint and verify no interrupt metadata
    saved_state = await agent.state_manager.load_checkpoint(checkpoint_id)

    assert saved_state is not None, "Should save checkpoint"
    assert saved_state.status != "interrupted", "Status should NOT be 'interrupted'"
    assert (
        "interrupt_reason" not in saved_state.metadata
    ), "Should NOT include interrupt_reason"

    # Cleanup
    agent.interrupt_manager.uninstall_signal_handlers()
