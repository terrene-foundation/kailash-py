"""
Unit tests for StateManager.

Tests checkpoint orchestration: save, load, resume, fork, cleanup.
"""

import tempfile
import time

import pytest
from kaizen.core.autonomy.state import AgentState, FilesystemStorage, StateManager


class TestStateManager:
    """Test StateManager class"""

    @pytest.fixture
    def temp_manager(self):
        """Create temporary state manager for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemStorage(base_dir=tmpdir)
            manager = StateManager(storage=storage)
            yield manager

    def test_create_manager(self):
        """Test creating StateManager with defaults"""
        manager = StateManager()

        assert manager is not None
        assert manager.checkpoint_frequency == 10
        assert manager.checkpoint_interval == 60.0
        assert manager.retention_count == 100

    def test_create_manager_custom_config(self):
        """Test creating StateManager with custom configuration"""
        manager = StateManager(
            checkpoint_frequency=5,
            checkpoint_interval=30.0,
            retention_count=50,
        )

        assert manager.checkpoint_frequency == 5
        assert manager.checkpoint_interval == 30.0
        assert manager.retention_count == 50

    def test_should_checkpoint_frequency(self, temp_manager):
        """Test should_checkpoint based on step frequency"""
        agent_id = "test_agent"
        current_time = time.time()

        # Initial checkpoint
        assert temp_manager.should_checkpoint(
            agent_id, current_step=0, current_time=current_time
        )

        # Update tracking (both step and time to avoid interval trigger)
        temp_manager._last_checkpoint_step[agent_id] = 0
        temp_manager._last_checkpoint_time[agent_id] = current_time

        # Not yet time (only 5 steps, same time)
        assert not temp_manager.should_checkpoint(
            agent_id, current_step=5, current_time=current_time
        )

        # Time to checkpoint (10 steps, same time)
        assert temp_manager.should_checkpoint(
            agent_id, current_step=10, current_time=current_time
        )

    def test_should_checkpoint_interval(self, temp_manager):
        """Test should_checkpoint based on time interval"""
        agent_id = "test_agent"
        current_time = time.time()

        # Initial checkpoint
        assert temp_manager.should_checkpoint(
            agent_id, current_step=0, current_time=current_time
        )

        # Update tracking
        temp_manager._last_checkpoint_step[agent_id] = 0
        temp_manager._last_checkpoint_time[agent_id] = current_time

        # Not yet time (only 30 seconds)
        assert not temp_manager.should_checkpoint(
            agent_id, current_step=1, current_time=current_time + 30
        )

        # Time to checkpoint (60 seconds)
        assert temp_manager.should_checkpoint(
            agent_id, current_step=1, current_time=current_time + 60
        )

    @pytest.mark.asyncio
    async def test_save_checkpoint(self, temp_manager):
        """Test saving a checkpoint"""
        state = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            step_number=10,
        )

        checkpoint_id = await temp_manager.save_checkpoint(state)

        assert checkpoint_id == "ckpt_test"

        # Verify tracking updated
        assert temp_manager._last_checkpoint_step["agent1"] == 10

    @pytest.mark.asyncio
    async def test_save_checkpoint_force(self, temp_manager):
        """Test force checkpoint even if not needed"""
        state = AgentState(checkpoint_id="ckpt_test", agent_id="agent1")

        # Should always succeed with force=True
        checkpoint_id = await temp_manager.save_checkpoint(state, force=True)

        assert checkpoint_id == "ckpt_test"

    @pytest.mark.asyncio
    async def test_load_checkpoint(self, temp_manager):
        """Test loading a checkpoint"""
        # Save first
        original = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            step_number=5,
        )
        await temp_manager.save_checkpoint(original)

        # Load
        loaded = await temp_manager.load_checkpoint("ckpt_test")

        assert loaded.checkpoint_id == original.checkpoint_id
        assert loaded.agent_id == original.agent_id
        assert loaded.step_number == original.step_number

    @pytest.mark.asyncio
    async def test_load_nonexistent_checkpoint(self, temp_manager):
        """Test loading checkpoint that doesn't exist"""
        with pytest.raises(FileNotFoundError):
            await temp_manager.load_checkpoint("nonexistent")

    @pytest.mark.asyncio
    async def test_resume_from_latest(self, temp_manager):
        """Test resuming from latest checkpoint"""
        # Create multiple checkpoints
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_1", agent_id="agent1", step_number=10)
        )

        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_2", agent_id="agent1", step_number=20)
        )

        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_3", agent_id="agent1", step_number=30)
        )

        # Resume from latest
        state = await temp_manager.resume_from_latest("agent1")

        assert state is not None
        assert state.step_number == 30  # Latest checkpoint

    @pytest.mark.asyncio
    async def test_resume_from_latest_no_checkpoints(self, temp_manager):
        """Test resuming when no checkpoints exist"""
        state = await temp_manager.resume_from_latest("nonexistent_agent")

        assert state is None

    @pytest.mark.asyncio
    async def test_fork_from_checkpoint(self, temp_manager):
        """Test forking execution from checkpoint"""
        # Create original checkpoint
        original = AgentState(
            checkpoint_id="ckpt_original",
            agent_id="agent1",
            step_number=10,
            conversation_history=[{"role": "user", "content": "Hello"}],
        )
        await temp_manager.save_checkpoint(original)

        # Fork
        forked = await temp_manager.fork_from_checkpoint("ckpt_original")

        # Verify fork has new ID but same data
        assert forked.checkpoint_id != original.checkpoint_id
        assert forked.checkpoint_id.startswith("ckpt_")
        assert forked.parent_checkpoint_id == "ckpt_original"
        assert forked.agent_id == original.agent_id
        assert forked.step_number == original.step_number
        assert forked.conversation_history == original.conversation_history

    @pytest.mark.asyncio
    async def test_fork_creates_independent_copy(self, temp_manager):
        """Test forked state is independent (deep copy)"""
        original = AgentState(
            checkpoint_id="ckpt_original",
            agent_id="agent1",
            conversation_history=[{"role": "user", "content": "Hello"}],
        )
        await temp_manager.save_checkpoint(original)

        # Fork
        forked = await temp_manager.fork_from_checkpoint("ckpt_original")

        # Modify forked conversation
        forked.conversation_history.append({"role": "assistant", "content": "Hi"})

        # Load original and verify unchanged
        reloaded_original = await temp_manager.load_checkpoint("ckpt_original")
        assert len(reloaded_original.conversation_history) == 1

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, temp_manager):
        """Test listing all checkpoints"""
        # Create checkpoints
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_1", agent_id="agent1")
        )
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_2", agent_id="agent2")
        )

        # List all
        checkpoints = await temp_manager.list_checkpoints()

        assert len(checkpoints) == 2

    @pytest.mark.asyncio
    async def test_list_checkpoints_filter_by_agent(self, temp_manager):
        """Test listing checkpoints for specific agent"""
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_1", agent_id="agent1")
        )
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_2", agent_id="agent2")
        )
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_3", agent_id="agent1")
        )

        # Filter for agent1
        checkpoints = await temp_manager.list_checkpoints(agent_id="agent1")

        assert len(checkpoints) == 2
        assert all(c.agent_id == "agent1" for c in checkpoints)

    @pytest.mark.asyncio
    async def test_cleanup_old_checkpoints(self, temp_manager):
        """Test cleaning up old checkpoints"""
        # Set low retention for testing
        temp_manager.retention_count = 3

        # Create 5 checkpoints (disable auto-cleanup during save)
        import asyncio

        for i in range(5):
            state = AgentState(
                checkpoint_id=f"ckpt_{i}", agent_id="agent1", step_number=i
            )
            # Save without auto-cleanup by calling storage directly
            await temp_manager.storage.save(state)
            # Small delay to ensure different timestamps
            await asyncio.sleep(0.01)

        # Verify 5 checkpoints exist
        checkpoints_before = await temp_manager.list_checkpoints(agent_id="agent1")
        assert len(checkpoints_before) == 5

        # Manually call cleanup
        deleted_count = await temp_manager.cleanup_old_checkpoints("agent1")

        assert deleted_count == 2  # 5 - 3 = 2 deleted

        # Verify only 3 remain
        checkpoints = await temp_manager.list_checkpoints(agent_id="agent1")
        assert len(checkpoints) == 3

    @pytest.mark.asyncio
    async def test_cleanup_keeps_newest(self, temp_manager):
        """Test cleanup keeps newest checkpoints"""
        temp_manager.retention_count = 2

        # Create checkpoints with clear order
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_old", agent_id="agent1", step_number=1)
        )

        import asyncio

        await asyncio.sleep(0.01)

        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_newer", agent_id="agent1", step_number=2)
        )

        await asyncio.sleep(0.01)

        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_newest", agent_id="agent1", step_number=3)
        )

        # Cleanup
        await temp_manager.cleanup_old_checkpoints("agent1")

        # Verify newest 2 kept
        checkpoints = await temp_manager.list_checkpoints(agent_id="agent1")
        assert len(checkpoints) == 2
        assert checkpoints[0].checkpoint_id == "ckpt_newest"
        assert checkpoints[1].checkpoint_id == "ckpt_newer"

    @pytest.mark.asyncio
    async def test_cleanup_no_deletion_under_limit(self, temp_manager):
        """Test cleanup doesn't delete when under retention limit"""
        temp_manager.retention_count = 10

        # Create only 3 checkpoints
        for i in range(3):
            await temp_manager.save_checkpoint(
                AgentState(checkpoint_id=f"ckpt_{i}", agent_id="agent1")
            )

        # Cleanup
        deleted_count = await temp_manager.cleanup_old_checkpoints("agent1")

        assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_get_checkpoint_tree(self, temp_manager):
        """Test getting checkpoint parent-child relationships"""
        # Create parent
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_parent", agent_id="agent1")
        )

        # Create children (forks)
        child1 = await temp_manager.fork_from_checkpoint("ckpt_parent")
        child2 = await temp_manager.fork_from_checkpoint("ckpt_parent")

        # Get tree
        tree = await temp_manager.get_checkpoint_tree("agent1")

        # Verify parent has 2 children
        assert "ckpt_parent" in tree
        assert len(tree["ckpt_parent"]) == 2
        assert child1.checkpoint_id in tree["ckpt_parent"]
        assert child2.checkpoint_id in tree["ckpt_parent"]

    @pytest.mark.asyncio
    async def test_get_checkpoint_tree_nested(self, temp_manager):
        """Test checkpoint tree with nested forks"""
        # Create parent
        await temp_manager.save_checkpoint(
            AgentState(checkpoint_id="ckpt_parent", agent_id="agent1")
        )

        # Fork child
        child = await temp_manager.fork_from_checkpoint("ckpt_parent")

        # Fork grandchild
        grandchild = await temp_manager.fork_from_checkpoint(child.checkpoint_id)

        # Get tree
        tree = await temp_manager.get_checkpoint_tree("agent1")

        # Verify structure
        assert "ckpt_parent" in tree
        assert child.checkpoint_id in tree["ckpt_parent"]
        assert child.checkpoint_id in tree
        assert grandchild.checkpoint_id in tree[child.checkpoint_id]

    def test_create_snapshot(self, temp_manager):
        """Test creating state snapshot"""
        state = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            step_number=10,
        )

        snapshot = temp_manager.create_snapshot(state, reason="debug")

        assert snapshot.state.checkpoint_id == state.checkpoint_id
        assert snapshot.snapshot_reason == "debug"

    def test_snapshot_is_deep_copy(self, temp_manager):
        """Test snapshot creates independent copy"""
        state = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            conversation_history=[{"role": "user", "content": "Hello"}],
        )

        snapshot = temp_manager.create_snapshot(state)

        # Modify original
        state.conversation_history.append({"role": "assistant", "content": "Hi"})

        # Verify snapshot unchanged
        assert len(snapshot.state.conversation_history) == 1
