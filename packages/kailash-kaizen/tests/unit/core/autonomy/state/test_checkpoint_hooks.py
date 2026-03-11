"""
Unit tests for checkpoint hook integration (TODO-168 Day 4).

Tests the PRE_CHECKPOINT_SAVE and POST_CHECKPOINT_SAVE hooks:
- Hook triggering during save_checkpoint
- Hook data validation
- Hook error handling
- Hook opt-in design (disabled by default)

Test Strategy: Tier 1 (Unit) - Mocked dependencies, fast execution
Coverage: 5 tests for Day 4 acceptance criteria
"""

import tempfile

import pytest
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import HookEvent, HookPriority, HookResult
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.core.autonomy.state.types import AgentState

# ═══════════════════════════════════════════════════════════════
# Test: PRE_CHECKPOINT_SAVE Hook
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pre_checkpoint_save_hook_triggered():
    """
    Test PRE_CHECKPOINT_SAVE hook is triggered before save.

    Validates:
    - Hook is called with correct event type
    - Hook receives state metadata (agent_id, step, status)
    - Hook is called before storage.save()
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        hook_manager = HookManager()
        manager = StateManager(storage=storage, hook_manager=hook_manager)

        # Track hook calls
        hook_calls = []

        async def pre_hook_handler(context):
            hook_calls.append(
                {
                    "event": context.event_type,
                    "data": context.data.copy(),
                }
            )
            return HookResult(success=True)

        hook_manager.register(
            HookEvent.PRE_CHECKPOINT_SAVE, pre_hook_handler, HookPriority.NORMAL
        )

        state = AgentState(
            agent_id="test_agent",
            step_number=5,
            conversation_history=[],
        )

        # Act
        await manager.save_checkpoint(state, force=True)

        # Assert: Hook was called
        assert len(hook_calls) == 1, "PRE_CHECKPOINT_SAVE should be triggered once"

        # Assert: Hook received correct data
        hook_call = hook_calls[0]
        assert hook_call["event"] == HookEvent.PRE_CHECKPOINT_SAVE
        assert hook_call["data"]["agent_id"] == "test_agent"
        assert hook_call["data"]["step_number"] == 5
        assert hook_call["data"]["status"] == "running"  # Default status
        assert "timestamp" in hook_call["data"]


@pytest.mark.asyncio
async def test_post_checkpoint_save_hook_triggered():
    """
    Test POST_CHECKPOINT_SAVE hook is triggered after save.

    Validates:
    - Hook is called with correct event type
    - Hook receives checkpoint_id from save
    - Hook is called after storage.save()
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        hook_manager = HookManager()
        manager = StateManager(storage=storage, hook_manager=hook_manager)

        # Track hook calls
        hook_calls = []

        async def post_hook_handler(context):
            hook_calls.append(
                {
                    "event": context.event_type,
                    "data": context.data.copy(),
                }
            )
            return HookResult(success=True)

        hook_manager.register(
            HookEvent.POST_CHECKPOINT_SAVE, post_hook_handler, HookPriority.NORMAL
        )

        state = AgentState(
            agent_id="test_agent",
            step_number=3,
            conversation_history=[],
        )

        # Act
        checkpoint_id = await manager.save_checkpoint(state, force=True)

        # Assert: Hook was called
        assert len(hook_calls) == 1, "POST_CHECKPOINT_SAVE should be triggered once"

        # Assert: Hook received correct data including checkpoint_id
        hook_call = hook_calls[0]
        assert hook_call["event"] == HookEvent.POST_CHECKPOINT_SAVE
        assert hook_call["data"]["agent_id"] == "test_agent"
        assert hook_call["data"]["checkpoint_id"] == checkpoint_id
        assert hook_call["data"]["step_number"] == 3
        assert hook_call["data"]["status"] == "running"  # Default status
        assert "timestamp" in hook_call["data"]


# ═══════════════════════════════════════════════════════════════
# Test: Hook Execution Order
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hooks_execution_order():
    """
    Test hooks execute in correct order (PRE before save, POST after).

    Validates:
    - PRE_CHECKPOINT_SAVE executes before storage.save()
    - POST_CHECKPOINT_SAVE executes after storage.save()
    - Checkpoint is saved between PRE and POST hooks
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        hook_manager = HookManager()
        manager = StateManager(storage=storage, hook_manager=hook_manager)

        # Track execution order
        execution_order = []

        async def pre_hook_handler(context):
            execution_order.append("PRE_HOOK")
            return HookResult(success=True)

        async def post_hook_handler(context):
            execution_order.append("POST_HOOK")
            return HookResult(success=True)

        hook_manager.register(
            HookEvent.PRE_CHECKPOINT_SAVE, pre_hook_handler, HookPriority.NORMAL
        )
        hook_manager.register(
            HookEvent.POST_CHECKPOINT_SAVE, post_hook_handler, HookPriority.NORMAL
        )

        # Mock storage.save to track when it's called
        original_save = storage.save

        async def tracked_save(state):
            execution_order.append("STORAGE_SAVE")
            return await original_save(state)

        storage.save = tracked_save

        state = AgentState(
            agent_id="test_agent",
            step_number=1,
            conversation_history=[],
        )

        # Act
        await manager.save_checkpoint(state, force=True)

        # Assert: Execution order is correct
        assert execution_order == [
            "PRE_HOOK",
            "STORAGE_SAVE",
            "POST_HOOK",
        ], "Hooks should execute in order: PRE -> SAVE -> POST"


# ═══════════════════════════════════════════════════════════════
# Test: Hook Opt-In Design
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hooks_disabled_by_default():
    """
    Test hooks are not triggered when hook_manager is None.

    Validates:
    - Opt-in design (hooks disabled by default)
    - Checkpoint save works without hook_manager
    - No errors raised when hooks are disabled
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        manager = StateManager(storage=storage, hook_manager=None)  # No hook_manager

        state = AgentState(
            agent_id="test_agent",
            step_number=2,
            conversation_history=[],
        )

        # Act: Save checkpoint without hooks
        checkpoint_id = await manager.save_checkpoint(state, force=True)

        # Assert: Checkpoint saved successfully
        assert checkpoint_id is not None
        assert await storage.exists(checkpoint_id)

        # Assert: No errors raised (hooks were skipped)


# ═══════════════════════════════════════════════════════════════
# Test: Hook Error Handling
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hook_errors_do_not_fail_checkpoint():
    """
    Test checkpoint save succeeds even if hooks fail.

    Validates:
    - Hook errors are logged but don't raise exceptions
    - Checkpoint is saved even when PRE hook fails
    - Checkpoint is saved even when POST hook fails
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        hook_manager = HookManager()
        manager = StateManager(storage=storage, hook_manager=hook_manager)

        # Register hooks that raise errors
        async def failing_pre_hook(context):
            raise RuntimeError("PRE hook error")

        async def failing_post_hook(context):
            raise RuntimeError("POST hook error")

        hook_manager.register(
            HookEvent.PRE_CHECKPOINT_SAVE, failing_pre_hook, HookPriority.NORMAL
        )
        hook_manager.register(
            HookEvent.POST_CHECKPOINT_SAVE, failing_post_hook, HookPriority.NORMAL
        )

        state = AgentState(
            agent_id="test_agent",
            step_number=4,
            conversation_history=[],
        )

        # Act: Save checkpoint (hooks will fail but shouldn't raise)
        checkpoint_id = await manager.save_checkpoint(state, force=True)

        # Assert: Checkpoint saved successfully despite hook errors
        assert checkpoint_id is not None
        assert await storage.exists(checkpoint_id)

        # Assert: Checkpoint can be loaded
        loaded_state = await storage.load(checkpoint_id)
        assert loaded_state.agent_id == "test_agent"
        assert loaded_state.step_number == 4


# ═══════════════════════════════════════════════════════════════
# Test Coverage Summary
# ═══════════════════════════════════════════════════════════════

"""
Test Coverage: 5/5 tests for Day 4 acceptance criteria

✅ Hook Triggering (2 tests)
  - test_pre_checkpoint_save_hook_triggered
  - test_post_checkpoint_save_hook_triggered

✅ Hook Execution Order (1 test)
  - test_hooks_execution_order

✅ Opt-In Design (1 test)
  - test_hooks_disabled_by_default

✅ Error Handling (1 test)
  - test_hook_errors_do_not_fail_checkpoint

Total: 5 tests
Expected Runtime: <2 seconds (all mocked, temp directories)
"""
