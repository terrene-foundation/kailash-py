"""
Unit tests for state persistence storage backends.

Tests FilesystemStorage operations: save, load, list, delete, exists.
"""

import tempfile

import pytest
from kaizen.core.autonomy.state import AgentState, FilesystemStorage


class TestFilesystemStorage:
    """Test FilesystemStorage backend"""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemStorage(base_dir=tmpdir)
            yield storage

    @pytest.mark.asyncio
    async def test_create_storage(self, temp_storage):
        """Test creating FilesystemStorage"""
        assert temp_storage is not None
        assert temp_storage.base_dir.exists()
        assert temp_storage.base_dir.is_dir()

    @pytest.mark.asyncio
    async def test_save_checkpoint(self, temp_storage):
        """Test saving a checkpoint"""
        state = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            step_number=5,
        )

        checkpoint_id = await temp_storage.save(state)

        assert checkpoint_id == "ckpt_test"

        # Verify file was created
        checkpoint_file = temp_storage.base_dir / "ckpt_test.jsonl"
        assert checkpoint_file.exists()

    @pytest.mark.asyncio
    async def test_save_creates_jsonl_file(self, temp_storage):
        """Test save creates valid JSONL file"""
        state = AgentState(checkpoint_id="ckpt_test", agent_id="agent1")

        await temp_storage.save(state)

        checkpoint_file = temp_storage.base_dir / "ckpt_test.jsonl"

        # Read and verify JSONL format
        content = checkpoint_file.read_text()
        assert content.endswith("\n")  # JSONL ends with newline

        import json

        data = json.loads(content.strip())
        assert data["checkpoint_id"] == "ckpt_test"
        assert data["agent_id"] == "agent1"

    @pytest.mark.asyncio
    async def test_load_checkpoint(self, temp_storage):
        """Test loading a checkpoint"""
        # Save first
        original = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            step_number=10,
        )
        await temp_storage.save(original)

        # Load
        loaded = await temp_storage.load("ckpt_test")

        assert loaded.checkpoint_id == original.checkpoint_id
        assert loaded.agent_id == original.agent_id
        assert loaded.step_number == original.step_number

    @pytest.mark.asyncio
    async def test_load_nonexistent_checkpoint(self, temp_storage):
        """Test loading checkpoint that doesn't exist"""
        with pytest.raises(FileNotFoundError, match="Checkpoint not found"):
            await temp_storage.load("nonexistent")

    @pytest.mark.asyncio
    async def test_exists_true(self, temp_storage):
        """Test exists() returns True for existing checkpoint"""
        state = AgentState(checkpoint_id="ckpt_test", agent_id="agent1")
        await temp_storage.save(state)

        exists = await temp_storage.exists("ckpt_test")

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self, temp_storage):
        """Test exists() returns False for non-existing checkpoint"""
        exists = await temp_storage.exists("nonexistent")

        assert exists is False

    @pytest.mark.asyncio
    async def test_delete_checkpoint(self, temp_storage):
        """Test deleting a checkpoint"""
        state = AgentState(checkpoint_id="ckpt_test", agent_id="agent1")
        await temp_storage.save(state)

        # Verify exists before delete
        assert await temp_storage.exists("ckpt_test")

        # Delete
        await temp_storage.delete("ckpt_test")

        # Verify deleted
        assert not await temp_storage.exists("ckpt_test")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_checkpoint(self, temp_storage):
        """Test deleting checkpoint that doesn't exist"""
        with pytest.raises(FileNotFoundError, match="Checkpoint not found"):
            await temp_storage.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_list_checkpoints_empty(self, temp_storage):
        """Test listing checkpoints when none exist"""
        checkpoints = await temp_storage.list_checkpoints()

        assert len(checkpoints) == 0

    @pytest.mark.asyncio
    async def test_list_checkpoints_single(self, temp_storage):
        """Test listing single checkpoint"""
        state = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            step_number=5,
        )
        await temp_storage.save(state)

        checkpoints = await temp_storage.list_checkpoints()

        assert len(checkpoints) == 1
        assert checkpoints[0].checkpoint_id == "ckpt_test"
        assert checkpoints[0].agent_id == "agent1"
        assert checkpoints[0].step_number == 5

    @pytest.mark.asyncio
    async def test_list_checkpoints_multiple(self, temp_storage):
        """Test listing multiple checkpoints"""
        # Create multiple checkpoints
        for i in range(3):
            state = AgentState(
                checkpoint_id=f"ckpt_{i}",
                agent_id="agent1",
                step_number=i * 10,
            )
            await temp_storage.save(state)

        checkpoints = await temp_storage.list_checkpoints()

        assert len(checkpoints) == 3

    @pytest.mark.asyncio
    async def test_list_checkpoints_sorted_by_timestamp(self, temp_storage):
        """Test checkpoints are sorted by timestamp (newest first)"""
        import asyncio

        # Create checkpoints with delays
        state1 = AgentState(checkpoint_id="ckpt_1", agent_id="agent1")
        await temp_storage.save(state1)

        await asyncio.sleep(0.01)  # Small delay

        state2 = AgentState(checkpoint_id="ckpt_2", agent_id="agent1")
        await temp_storage.save(state2)

        checkpoints = await temp_storage.list_checkpoints()

        # Newest should be first
        assert checkpoints[0].checkpoint_id == "ckpt_2"
        assert checkpoints[1].checkpoint_id == "ckpt_1"

    @pytest.mark.asyncio
    async def test_list_checkpoints_filter_by_agent(self, temp_storage):
        """Test filtering checkpoints by agent_id"""
        # Create checkpoints for different agents
        await temp_storage.save(AgentState(checkpoint_id="ckpt_1", agent_id="agent1"))
        await temp_storage.save(AgentState(checkpoint_id="ckpt_2", agent_id="agent2"))
        await temp_storage.save(AgentState(checkpoint_id="ckpt_3", agent_id="agent1"))

        # Filter for agent1
        checkpoints = await temp_storage.list_checkpoints(agent_id="agent1")

        assert len(checkpoints) == 2
        assert all(c.agent_id == "agent1" for c in checkpoints)

    @pytest.mark.asyncio
    async def test_roundtrip_with_complex_state(self, temp_storage):
        """Test save/load roundtrip with complex state data"""
        original = AgentState(
            checkpoint_id="ckpt_complex",
            agent_id="agent1",
            step_number=42,
            conversation_history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            memory_contents={"key1": "value1", "key2": [1, 2, 3]},
            pending_actions=[{"tool": "search", "query": "test"}],
            completed_actions=[{"tool": "read", "result": "data"}],
            budget_spent_usd=2.50,
            tool_usage_counts={"search": 3, "read": 5},
            status="running",
        )

        # Save and load
        await temp_storage.save(original)
        loaded = await temp_storage.load("ckpt_complex")

        # Verify all fields preserved
        assert loaded.checkpoint_id == original.checkpoint_id
        assert loaded.agent_id == original.agent_id
        assert loaded.step_number == original.step_number
        assert loaded.conversation_history == original.conversation_history
        assert loaded.memory_contents == original.memory_contents
        assert loaded.pending_actions == original.pending_actions
        assert loaded.completed_actions == original.completed_actions
        assert loaded.budget_spent_usd == original.budget_spent_usd
        assert loaded.tool_usage_counts == original.tool_usage_counts
        assert loaded.status == original.status

    @pytest.mark.asyncio
    async def test_checkpoint_metadata_has_size(self, temp_storage):
        """Test checkpoint metadata includes file size"""
        state = AgentState(checkpoint_id="ckpt_test", agent_id="agent1")
        await temp_storage.save(state)

        checkpoints = await temp_storage.list_checkpoints()

        assert len(checkpoints) == 1
        assert checkpoints[0].size_bytes > 0

    @pytest.mark.asyncio
    async def test_atomic_write(self, temp_storage):
        """Test atomic write pattern (temp file + rename)"""
        state = AgentState(checkpoint_id="ckpt_test", agent_id="agent1")

        # Save checkpoint
        await temp_storage.save(state)

        # Verify no temp files left behind
        temp_files = list(temp_storage.base_dir.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify checkpoint file exists
        checkpoint_file = temp_storage.base_dir / "ckpt_test.jsonl"
        assert checkpoint_file.exists()
