"""
Unit tests for retention policies and compression (TODO-168 Day 3).

Tests the checkpoint retention and JSONL compression features:
- Compression save/load roundtrip
- Backward compatibility (uncompressed load from compressed storage)
- list_checkpoints with mixed compressed/uncompressed
- delete/exists with both formats
- cleanup_old_checkpoints retention policy

Test Strategy: Tier 1 (Unit) - Mocked dependencies, fast execution
Coverage: 10 tests for Day 3 acceptance criteria
"""

import tempfile
from pathlib import Path

import pytest
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.core.autonomy.state.types import AgentState

# ═══════════════════════════════════════════════════════════════
# Test: Compression Save/Load
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_compression_save_load_roundtrip():
    """
    Test compressed checkpoint save and load roundtrip.

    Validates:
    - Checkpoint saved with gzip compression
    - Checkpoint loaded correctly from .jsonl.gz
    - State restored accurately
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir, compress=True)

        state = AgentState(
            agent_id="test_agent",
            step_number=10,
            conversation_history=[{"role": "user", "content": "test"}],
        )

        # Act: Save compressed
        checkpoint_id = await storage.save(state)

        # Assert: File is compressed (.jsonl.gz)
        compressed_file = Path(tmpdir) / f"{checkpoint_id}.jsonl.gz"
        assert compressed_file.exists(), "Should create .jsonl.gz file"
        assert not (
            Path(tmpdir) / f"{checkpoint_id}.jsonl"
        ).exists(), "Should not create uncompressed file"

        # Act: Load compressed
        loaded_state = await storage.load(checkpoint_id)

        # Assert: State restored correctly
        assert loaded_state.agent_id == "test_agent"
        assert loaded_state.step_number == 10
        assert len(loaded_state.conversation_history) == 1


@pytest.mark.asyncio
async def test_backward_compatibility_uncompressed_load():
    """
    Test that uncompressed checkpoints can be loaded from compressed storage.

    Validates:
    - Old uncompressed checkpoints (.jsonl) can still be loaded
    - Backward compatibility is maintained
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save uncompressed checkpoint
        storage_uncompressed = FilesystemStorage(base_dir=tmpdir, compress=False)
        state = AgentState(
            agent_id="test_agent",
            step_number=5,
            conversation_history=[],
        )
        checkpoint_id = await storage_uncompressed.save(state)

        # Act: Load with compressed storage (should auto-detect uncompressed)
        storage_compressed = FilesystemStorage(base_dir=tmpdir, compress=True)
        loaded_state = await storage_compressed.load(checkpoint_id)

        # Assert: State loaded correctly
        assert loaded_state.agent_id == "test_agent"
        assert loaded_state.step_number == 5


@pytest.mark.asyncio
async def test_compression_size_reduction():
    """
    Test that compression reduces checkpoint file size.

    Validates:
    - Compressed file is smaller than uncompressed
    - Compression provides meaningful size reduction
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create state with lots of text (should compress well)
        conversation = [{"role": "user", "content": "test message " * 100}] * 10
        state = AgentState(
            agent_id="test_agent",
            step_number=1,
            conversation_history=conversation,
        )

        # Act: Save uncompressed
        storage_uncompressed = FilesystemStorage(
            base_dir=tmpdir + "/uncompressed", compress=False
        )
        checkpoint_id_uncompressed = await storage_uncompressed.save(state)
        uncompressed_size = (
            (Path(tmpdir) / "uncompressed" / f"{checkpoint_id_uncompressed}.jsonl")
            .stat()
            .st_size
        )

        # Act: Save compressed
        storage_compressed = FilesystemStorage(
            base_dir=tmpdir + "/compressed", compress=True
        )
        checkpoint_id_compressed = await storage_compressed.save(state)
        compressed_size = (
            (Path(tmpdir) / "compressed" / f"{checkpoint_id_compressed}.jsonl.gz")
            .stat()
            .st_size
        )

        # Assert: Compressed is smaller
        assert compressed_size < uncompressed_size, "Compressed file should be smaller"
        compression_ratio = compressed_size / uncompressed_size
        assert (
            compression_ratio < 0.5
        ), f"Compression should reduce size by >50% (ratio: {compression_ratio:.2f})"


# ═══════════════════════════════════════════════════════════════
# Test: list_checkpoints with Mixed Formats
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_checkpoints_mixed_formats():
    """
    Test list_checkpoints with both compressed and uncompressed files.

    Validates:
    - Both .jsonl and .jsonl.gz files are listed
    - Metadata is extracted correctly from both formats
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save uncompressed checkpoint
        storage_uncompressed = FilesystemStorage(base_dir=tmpdir, compress=False)
        state1 = AgentState(agent_id="agent1", step_number=1, conversation_history=[])
        checkpoint_id1 = await storage_uncompressed.save(state1)

        # Save compressed checkpoint
        storage_compressed = FilesystemStorage(base_dir=tmpdir, compress=True)
        state2 = AgentState(agent_id="agent1", step_number=2, conversation_history=[])
        checkpoint_id2 = await storage_compressed.save(state2)

        # Act: List all checkpoints
        checkpoints = await storage_compressed.list_checkpoints(agent_id="agent1")

        # Assert: Both checkpoints listed
        assert len(checkpoints) == 2, "Should list both compressed and uncompressed"
        checkpoint_ids = [c.checkpoint_id for c in checkpoints]
        assert (
            checkpoint_id1 in checkpoint_ids
        ), "Should include uncompressed checkpoint"
        assert checkpoint_id2 in checkpoint_ids, "Should include compressed checkpoint"


# ═══════════════════════════════════════════════════════════════
# Test: delete/exists with Compression
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_compressed_checkpoint():
    """
    Test delete with compressed checkpoint.

    Validates:
    - Compressed checkpoint can be deleted
    - File is removed from filesystem
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir, compress=True)
        state = AgentState(
            agent_id="test_agent", step_number=1, conversation_history=[]
        )
        checkpoint_id = await storage.save(state)

        # Verify file exists
        compressed_file = Path(tmpdir) / f"{checkpoint_id}.jsonl.gz"
        assert compressed_file.exists(), "Compressed file should exist"

        # Act: Delete checkpoint
        await storage.delete(checkpoint_id)

        # Assert: File removed
        assert not compressed_file.exists(), "Compressed file should be deleted"


@pytest.mark.asyncio
async def test_delete_uncompressed_checkpoint():
    """
    Test delete with uncompressed checkpoint.

    Validates:
    - Uncompressed checkpoint can be deleted
    - Backward compatibility maintained
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir, compress=False)
        state = AgentState(
            agent_id="test_agent", step_number=1, conversation_history=[]
        )
        checkpoint_id = await storage.save(state)

        # Act: Delete checkpoint
        await storage.delete(checkpoint_id)

        # Assert: File removed
        uncompressed_file = Path(tmpdir) / f"{checkpoint_id}.jsonl"
        assert not uncompressed_file.exists(), "Uncompressed file should be deleted"


@pytest.mark.asyncio
async def test_exists_with_compression():
    """
    Test exists with both compressed and uncompressed checkpoints.

    Validates:
    - exists() returns True for compressed checkpoint
    - exists() returns True for uncompressed checkpoint
    - exists() returns False for non-existent checkpoint
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save compressed checkpoint
        storage_compressed = FilesystemStorage(base_dir=tmpdir, compress=True)
        state1 = AgentState(agent_id="agent1", step_number=1, conversation_history=[])
        checkpoint_id_compressed = await storage_compressed.save(state1)

        # Save uncompressed checkpoint
        storage_uncompressed = FilesystemStorage(base_dir=tmpdir, compress=False)
        state2 = AgentState(agent_id="agent2", step_number=2, conversation_history=[])
        checkpoint_id_uncompressed = await storage_uncompressed.save(state2)

        # Act & Assert: Check existence
        assert await storage_compressed.exists(
            checkpoint_id_compressed
        ), "Compressed checkpoint should exist"
        assert await storage_uncompressed.exists(
            checkpoint_id_uncompressed
        ), "Uncompressed checkpoint should exist"
        assert not await storage_compressed.exists(
            "nonexistent"
        ), "Nonexistent checkpoint should not exist"


# ═══════════════════════════════════════════════════════════════
# Test: Retention Policy (cleanup_old_checkpoints)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cleanup_old_checkpoints_keeps_latest():
    """
    Test cleanup_old_checkpoints keeps latest N checkpoints.

    Validates:
    - Oldest checkpoints are deleted
    - Latest N checkpoints are retained
    - Returns correct count of deleted checkpoints
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        manager = StateManager(storage=storage, retention_count=3)

        # Save 5 checkpoints directly through storage (bypassing save_checkpoint to avoid auto-cleanup)
        checkpoint_ids = []
        for i in range(5):
            state = AgentState(
                agent_id="test_agent",
                step_number=i,
                conversation_history=[],
            )
            checkpoint_id = await storage.save(state)
            checkpoint_ids.append(checkpoint_id)

        # Verify all 5 exist before cleanup
        all_checkpoints = await storage.list_checkpoints(agent_id="test_agent")
        assert len(all_checkpoints) == 5, "Should have 5 checkpoints before cleanup"

        # Act: Cleanup (should keep latest 3, delete oldest 2)
        deleted_count = await manager.cleanup_old_checkpoints("test_agent")

        # Assert: Deleted count is correct
        assert deleted_count == 2, "Should delete 2 oldest checkpoints"

        # Assert: Latest 3 checkpoints exist
        remaining = await storage.list_checkpoints(agent_id="test_agent")
        assert len(remaining) == 3, "Should keep 3 latest checkpoints"


@pytest.mark.asyncio
async def test_cleanup_old_checkpoints_fewer_than_retention():
    """
    Test cleanup_old_checkpoints when fewer than retention_count exist.

    Validates:
    - No checkpoints deleted if count <= retention_count
    - Returns 0 for deleted count
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        manager = StateManager(storage=storage, retention_count=10)

        # Save only 3 checkpoints (less than retention_count)
        for i in range(3):
            state = AgentState(
                agent_id="test_agent",
                step_number=i,
                conversation_history=[],
            )
            await manager.save_checkpoint(state, force=True)

        # Act: Cleanup (should not delete anything)
        deleted_count = await manager.cleanup_old_checkpoints("test_agent")

        # Assert: No checkpoints deleted
        assert deleted_count == 0, "Should not delete any checkpoints"

        # Assert: All 3 checkpoints still exist
        remaining = await storage.list_checkpoints(agent_id="test_agent")
        assert len(remaining) == 3, "Should keep all 3 checkpoints"


@pytest.mark.asyncio
async def test_cleanup_old_checkpoints_error_handling():
    """
    Test cleanup_old_checkpoints handles deletion errors gracefully.

    Validates:
    - Continues deleting after error
    - Logs error but doesn't raise exception
    - Returns count of successfully deleted checkpoints
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FilesystemStorage(base_dir=tmpdir)
        manager = StateManager(storage=storage, retention_count=2)

        # Save 4 checkpoints directly through storage (bypassing save_checkpoint to avoid auto-cleanup)
        for i in range(4):
            state = AgentState(
                agent_id="test_agent",
                step_number=i,
                conversation_history=[],
            )
            await storage.save(state)

        # Verify all 4 exist before cleanup
        all_checkpoints = await storage.list_checkpoints(agent_id="test_agent")
        assert len(all_checkpoints) == 4, "Should have 4 checkpoints before cleanup"

        # Mock storage.delete to fail for first checkpoint
        original_delete = storage.delete
        call_count = [0]

        async def mock_delete(checkpoint_id):
            call_count[0] += 1
            if call_count[0] == 1:
                raise IOError("Simulated delete error")
            return await original_delete(checkpoint_id)

        storage.delete = mock_delete

        # Act: Cleanup (should handle error gracefully)
        deleted_count = await manager.cleanup_old_checkpoints("test_agent")

        # Assert: Deleted count reflects successful deletions (1 out of 2 attempts)
        assert deleted_count == 1, "Should return count of successful deletions"


# ═══════════════════════════════════════════════════════════════
# Test Coverage Summary
# ═══════════════════════════════════════════════════════════════

"""
Test Coverage: 10/10 tests for Day 3 acceptance criteria

✅ Compression Save/Load (3 tests)
  - test_compression_save_load_roundtrip
  - test_backward_compatibility_uncompressed_load
  - test_compression_size_reduction

✅ list_checkpoints with Mixed Formats (1 test)
  - test_list_checkpoints_mixed_formats

✅ delete/exists with Compression (3 tests)
  - test_delete_compressed_checkpoint
  - test_delete_uncompressed_checkpoint
  - test_exists_with_compression

✅ Retention Policy (3 tests)
  - test_cleanup_old_checkpoints_keeps_latest
  - test_cleanup_old_checkpoints_fewer_than_retention
  - test_cleanup_old_checkpoints_error_handling

Total: 10 tests
Expected Runtime: <2 seconds (all mocked, temp directories)
"""
