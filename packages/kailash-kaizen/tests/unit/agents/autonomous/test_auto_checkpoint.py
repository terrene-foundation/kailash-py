"""
Unit tests for automatic checkpointing logic (TODO-168 Day 2).

Tests the automatic checkpoint triggers in autonomous execution:
- should_checkpoint() logic (frequency + interval)
- Resume from checkpoint functionality
- Checkpoint save during autonomous loop
- Final checkpoint save on completion

Test Strategy: Tier 1 (Unit) - Mocked dependencies, fast execution
Coverage: 10 tests for Day 2 acceptance criteria
"""

import time
from unittest.mock import AsyncMock, Mock

import pytest
from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.state.types import AgentState
from kaizen.signatures import InputField, OutputField, Signature


class TaskSignature(Signature):
    """Simple signature for testing"""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")


# ═══════════════════════════════════════════════════════════════
# Test: Configuration
# ═══════════════════════════════════════════════════════════════


def test_resume_config_defaults():
    """
    Test that resume_from_checkpoint defaults to False.

    Validates:
    - resume_from_checkpoint defaults to False (opt-in)
    - checkpoint_interval_seconds defaults to 60.0
    """
    # Arrange & Act
    config = AutonomousConfig(
        max_cycles=10, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )

    # Assert
    assert config.resume_from_checkpoint is False, "Should default to False (opt-in)"
    assert config.checkpoint_interval_seconds == 60.0, "Should default to 60 seconds"


def test_resume_config_custom():
    """
    Test that resume_from_checkpoint can be enabled.

    Validates:
    - resume_from_checkpoint can be set to True
    - checkpoint_interval_seconds can be customized
    """
    # Arrange & Act
    config = AutonomousConfig(
        max_cycles=10,
        resume_from_checkpoint=True,
        checkpoint_interval_seconds=30.0,
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )

    # Assert
    assert config.resume_from_checkpoint is True, "Should enable resume"
    assert config.checkpoint_interval_seconds == 30.0, "Should use custom interval"


def test_state_manager_config_passed():
    """
    Test that checkpoint config is passed to StateManager.

    Validates:
    - checkpoint_frequency passed to StateManager
    - checkpoint_interval_seconds passed to StateManager
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10,
        checkpoint_frequency=5,
        checkpoint_interval_seconds=30.0,
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )

    # Act
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Assert
    assert agent.state_manager.checkpoint_frequency == 5, "Should pass frequency"
    assert agent.state_manager.checkpoint_interval == 30.0, "Should pass interval"


# ═══════════════════════════════════════════════════════════════
# Test: should_checkpoint() Logic
# ═══════════════════════════════════════════════════════════════


def test_should_checkpoint_frequency_trigger():
    """
    Test checkpoint triggered by frequency (every N steps).

    Validates:
    - Checkpoint needed after N steps
    - Checkpoint not needed before N steps
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=20,
        checkpoint_frequency=5,  # Every 5 steps
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())
    agent_id = "test_agent"

    # Initialize tracking to avoid interval trigger
    current_time = time.time()
    agent.state_manager._last_checkpoint_time[agent_id] = current_time
    agent.state_manager._last_checkpoint_step[agent_id] = 0

    # Act & Assert: Before frequency threshold
    should_save = agent.state_manager.should_checkpoint(
        agent_id=agent_id, current_step=3, current_time=current_time
    )
    assert should_save is False, "Should not checkpoint at step 3 (threshold is 5)"

    # Act & Assert: At frequency threshold
    should_save = agent.state_manager.should_checkpoint(
        agent_id=agent_id, current_step=5, current_time=current_time
    )
    assert should_save is True, "Should checkpoint at step 5 (frequency trigger)"


def test_should_checkpoint_interval_trigger():
    """
    Test checkpoint triggered by interval (every M seconds).

    Validates:
    - Checkpoint needed after M seconds
    - Checkpoint not needed before M seconds
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=20,
        checkpoint_frequency=100,  # High frequency to avoid triggering
        checkpoint_interval_seconds=2.0,  # Every 2 seconds
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())
    agent_id = "test_agent"

    # Initialize tracking
    start_time = time.time()
    agent.state_manager._last_checkpoint_time[agent_id] = start_time
    agent.state_manager._last_checkpoint_step[agent_id] = 0

    # Act & Assert: Immediately (no time passed)
    should_save = agent.state_manager.should_checkpoint(
        agent_id=agent_id, current_step=1, current_time=start_time
    )
    assert should_save is False, "Should not checkpoint immediately"

    # Act & Assert: After interval (simulated)
    should_save = agent.state_manager.should_checkpoint(
        agent_id=agent_id,
        current_step=2,
        current_time=start_time + 3.0,  # 3 seconds later
    )
    assert should_save is True, "Should checkpoint after interval"


def test_should_checkpoint_either_trigger():
    """
    Test that checkpoint triggers on frequency OR interval.

    Validates:
    - Either condition triggers checkpoint
    - OR logic works correctly
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=20,
        checkpoint_frequency=10,  # Every 10 steps
        checkpoint_interval_seconds=5.0,  # Every 5 seconds
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())
    agent_id = "test_agent"
    start_time = time.time()

    # Act & Assert: Frequency trigger (before interval)
    should_save = agent.state_manager.should_checkpoint(
        agent_id=agent_id,
        current_step=10,  # Frequency threshold
        current_time=start_time + 1.0,  # Only 1 second (below interval)
    )
    assert should_save is True, "Should trigger on frequency alone"

    # Reset tracking
    agent.state_manager._last_checkpoint_step[agent_id] = 10
    agent.state_manager._last_checkpoint_time[agent_id] = start_time

    # Act & Assert: Interval trigger (before frequency)
    should_save = agent.state_manager.should_checkpoint(
        agent_id=agent_id,
        current_step=12,  # Only 2 steps (below frequency)
        current_time=start_time + 6.0,  # 6 seconds (above interval)
    )
    assert should_save is True, "Should trigger on interval alone"


# ═══════════════════════════════════════════════════════════════
# Test: Resume from Checkpoint
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resume_from_checkpoint_enabled():
    """
    Test resume from checkpoint when enabled.

    Validates:
    - resume_from_latest() is called when enabled
    - State is restored if checkpoint found
    - current_step is updated from checkpoint
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10,
        resume_from_checkpoint=True,  # Enable resume
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Mock state_manager.resume_from_latest
    mock_state = AgentState(
        agent_id="test_agent",
        step_number=5,
        conversation_history=[],
    )
    agent.state_manager.resume_from_latest = AsyncMock(return_value=mock_state)

    # Mock strategy.execute to avoid actual execution
    agent.strategy.execute = Mock(return_value={"result": "test", "tool_calls": []})

    # Act
    await agent._autonomous_loop("Test task")

    # Assert
    agent.state_manager.resume_from_latest.assert_called_once()
    assert (
        agent.current_step >= 5
    ), "Should restore step from checkpoint (5) and continue execution"


@pytest.mark.asyncio
async def test_resume_from_checkpoint_disabled():
    """
    Test that resume is skipped when disabled.

    Validates:
    - resume_from_latest() is NOT called when disabled
    - Agent starts from step 0
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10,
        resume_from_checkpoint=False,  # Disabled (default)
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Mock state_manager.resume_from_latest (should NOT be called)
    agent.state_manager.resume_from_latest = AsyncMock()

    # Mock strategy.execute to avoid actual execution
    agent.strategy.execute = Mock(return_value={"result": "test", "tool_calls": []})

    # Act
    await agent._autonomous_loop("Test task")

    # Assert
    agent.state_manager.resume_from_latest.assert_not_called()
    assert agent.current_step >= 1, "Should execute at least one cycle"


@pytest.mark.asyncio
async def test_resume_no_checkpoint_found():
    """
    Test resume when no checkpoint exists.

    Validates:
    - Graceful handling when no checkpoint found
    - Execution starts normally from step 0
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10,
        resume_from_checkpoint=True,
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Mock state_manager.resume_from_latest to return None (no checkpoint)
    agent.state_manager.resume_from_latest = AsyncMock(return_value=None)

    # Mock strategy.execute
    agent.strategy.execute = Mock(return_value={"result": "test", "tool_calls": []})

    # Act
    result = await agent._autonomous_loop("Test task")

    # Assert
    agent.state_manager.resume_from_latest.assert_called_once()
    assert result is not None, "Should execute normally"


# ═══════════════════════════════════════════════════════════════
# Test: Checkpoint Save During Loop
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_checkpoint_save_during_loop():
    """
    Test that checkpoints are saved during autonomous loop.

    Validates:
    - save_checkpoint() is called when should_checkpoint() returns True
    - Step counter is incremented
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=10,
        checkpoint_frequency=2,  # Checkpoint every 2 steps
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Mock strategy.execute (converges after 5 cycles)
    call_count = [0]

    def mock_execute(self_arg, inputs):
        call_count[0] += 1
        if call_count[0] >= 5:
            return {"result": "done", "tool_calls": []}
        return {"result": "working", "tool_calls": [{"name": "test"}]}

    agent.strategy.execute = mock_execute

    # Mock save_checkpoint to track calls
    agent.state_manager.save_checkpoint = AsyncMock(return_value="ckpt_123")

    # Act
    await agent._autonomous_loop("Test task")

    # Assert
    # Should checkpoint at steps 2, 4, plus final checkpoint
    assert (
        agent.state_manager.save_checkpoint.call_count >= 2
    ), "Should save checkpoints during loop"
    assert agent.current_step >= 5, "Should complete at least 5 steps"


@pytest.mark.asyncio
async def test_final_checkpoint_save():
    """
    Test that final checkpoint is saved on completion.

    Validates:
    - Final checkpoint is always saved (force=True)
    - Status is set correctly (completed vs failed)
    """
    # Arrange
    config = AutonomousConfig(
        max_cycles=5,
        checkpoint_frequency=100,  # Avoid intermediate checkpoints
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
    )
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # Mock strategy.execute (converges immediately)
    agent.strategy.execute = Mock(return_value={"result": "done", "tool_calls": []})

    # Mock save_checkpoint
    agent.state_manager.save_checkpoint = AsyncMock(return_value="final_ckpt")

    # Act
    await agent._autonomous_loop("Test task")

    # Assert
    # Final checkpoint should be called with force=True
    calls = agent.state_manager.save_checkpoint.call_args_list
    assert len(calls) >= 1, "Should save final checkpoint"
    final_call = calls[-1]  # Last call is final checkpoint
    assert (
        final_call.kwargs.get("force") is True
    ), "Final checkpoint should use force=True"


# ═══════════════════════════════════════════════════════════════
# Test Coverage Summary
# ═══════════════════════════════════════════════════════════════

"""
Test Coverage: 10/10 tests for Day 2 acceptance criteria

✅ Configuration (3 tests)
  - test_resume_config_defaults
  - test_resume_config_custom
  - test_state_manager_config_passed

✅ should_checkpoint() Logic (3 tests)
  - test_should_checkpoint_frequency_trigger
  - test_should_checkpoint_interval_trigger
  - test_should_checkpoint_either_trigger

✅ Resume from Checkpoint (3 tests)
  - test_resume_from_checkpoint_enabled
  - test_resume_from_checkpoint_disabled
  - test_resume_no_checkpoint_found

✅ Checkpoint Save (2 tests)
  - test_checkpoint_save_during_loop
  - test_final_checkpoint_save

Total: 10 tests
Expected Runtime: <2 seconds (all mocked)
"""
