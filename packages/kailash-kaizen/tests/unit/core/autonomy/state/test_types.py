"""
Unit tests for state persistence types.

Tests AgentState, CheckpointMetadata, and StateSnapshot.
"""

from datetime import datetime, timezone

from kaizen.core.autonomy.state.types import (
    AgentState,
    CheckpointMetadata,
    StateSnapshot,
)


class TestAgentState:
    """Test AgentState dataclass"""

    def test_create_default_state(self):
        """Test creating AgentState with defaults"""
        state = AgentState()

        # Check defaults
        assert state.checkpoint_id.startswith("ckpt_")
        assert len(state.checkpoint_id) == 17  # "ckpt_" + 12 hex chars
        assert state.agent_id == ""
        assert isinstance(state.timestamp, datetime)
        assert state.step_number == 0
        assert state.conversation_history == []
        assert state.memory_contents == {}
        assert state.pending_actions == []
        assert state.completed_actions == []
        assert state.budget_spent_usd == 0.0
        assert state.approval_history == []
        assert state.tool_usage_counts == {}
        assert state.tool_results_cache == {}
        assert state.active_specialists == []
        assert state.specialist_invocations == []
        assert state.workflow_run_id is None
        assert state.workflow_state == {}
        assert state.control_protocol_state == {}
        assert state.registered_hooks == []
        assert state.hook_event_history == []
        assert state.parent_checkpoint_id is None
        assert state.status == "running"
        assert state.metadata == {}

    def test_create_state_with_data(self):
        """Test creating AgentState with custom data"""
        timestamp = datetime(2025, 1, 22, 12, 0, 0)

        state = AgentState(
            checkpoint_id="ckpt_test123",
            agent_id="test_agent",
            timestamp=timestamp,
            step_number=42,
            conversation_history=[{"role": "user", "content": "Hello"}],
            memory_contents={"key": "value"},
            budget_spent_usd=1.50,
            status="completed",
        )

        assert state.checkpoint_id == "ckpt_test123"
        assert state.agent_id == "test_agent"
        assert state.timestamp == timestamp
        assert state.step_number == 42
        assert len(state.conversation_history) == 1
        assert state.memory_contents["key"] == "value"
        assert state.budget_spent_usd == 1.50
        assert state.status == "completed"

    def test_state_to_dict(self):
        """Test AgentState.to_dict() serialization"""
        timestamp = datetime(2025, 1, 22, 12, 0, 0)

        state = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            timestamp=timestamp,
            step_number=10,
        )

        state_dict = state.to_dict()

        assert isinstance(state_dict, dict)
        assert state_dict["checkpoint_id"] == "ckpt_test"
        assert state_dict["agent_id"] == "agent1"
        assert state_dict["timestamp"] == "2025-01-22T12:00:00"  # ISO format
        assert state_dict["step_number"] == 10
        assert "conversation_history" in state_dict
        assert "memory_contents" in state_dict

    def test_state_from_dict(self):
        """Test AgentState.from_dict() deserialization"""
        state_dict = {
            "checkpoint_id": "ckpt_test",
            "agent_id": "agent1",
            "timestamp": "2025-01-22T12:00:00",
            "step_number": 10,
            "conversation_history": [],
            "memory_contents": {},
            "pending_actions": [],
            "completed_actions": [],
            "budget_spent_usd": 0.0,
            "approval_history": [],
            "tool_usage_counts": {},
            "tool_results_cache": {},
            "active_specialists": [],
            "specialist_invocations": [],
            "workflow_run_id": None,
            "workflow_state": {},
            "control_protocol_state": {},
            "registered_hooks": [],
            "hook_event_history": [],
            "parent_checkpoint_id": None,
            "status": "running",
            "metadata": {},
        }

        state = AgentState.from_dict(state_dict)

        assert state.checkpoint_id == "ckpt_test"
        assert state.agent_id == "agent1"
        assert isinstance(state.timestamp, datetime)
        assert state.step_number == 10

    def test_state_roundtrip(self):
        """Test serialization roundtrip (to_dict → from_dict)"""
        original = AgentState(
            agent_id="test",
            step_number=5,
            conversation_history=[{"role": "user", "content": "Hello"}],
            memory_contents={"key": "value"},
            budget_spent_usd=2.50,
        )

        # Serialize and deserialize
        state_dict = original.to_dict()
        restored = AgentState.from_dict(state_dict)

        assert restored.checkpoint_id == original.checkpoint_id
        assert restored.agent_id == original.agent_id
        assert restored.step_number == original.step_number
        assert restored.conversation_history == original.conversation_history
        assert restored.memory_contents == original.memory_contents
        assert restored.budget_spent_usd == original.budget_spent_usd

    def test_state_with_parent_checkpoint(self):
        """Test AgentState with parent_checkpoint_id (forking)"""
        state = AgentState(
            checkpoint_id="ckpt_child",
            parent_checkpoint_id="ckpt_parent",
            agent_id="test",
        )

        assert state.parent_checkpoint_id == "ckpt_parent"

        # Verify in serialization
        state_dict = state.to_dict()
        assert state_dict["parent_checkpoint_id"] == "ckpt_parent"

    def test_state_all_status_values(self):
        """Test all valid status values"""
        for status in ["running", "completed", "failed", "interrupted"]:
            state = AgentState(status=status)
            assert state.status == status


class TestCheckpointMetadata:
    """Test CheckpointMetadata dataclass"""

    def test_create_metadata(self):
        """Test creating CheckpointMetadata"""
        timestamp = datetime(2025, 1, 22, 12, 0, 0)

        metadata = CheckpointMetadata(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            timestamp=timestamp,
            step_number=10,
            status="running",
            size_bytes=1024,
        )

        assert metadata.checkpoint_id == "ckpt_test"
        assert metadata.agent_id == "agent1"
        assert metadata.timestamp == timestamp
        assert metadata.step_number == 10
        assert metadata.status == "running"
        assert metadata.size_bytes == 1024
        assert metadata.parent_checkpoint_id is None

    def test_metadata_with_parent(self):
        """Test metadata with parent checkpoint"""
        metadata = CheckpointMetadata(
            checkpoint_id="ckpt_child",
            agent_id="agent1",
            timestamp=datetime.now(timezone.utc),
            step_number=20,
            status="running",
            size_bytes=2048,
            parent_checkpoint_id="ckpt_parent",
        )

        assert metadata.parent_checkpoint_id == "ckpt_parent"

    def test_metadata_to_dict(self):
        """Test CheckpointMetadata.to_dict()"""
        timestamp = datetime(2025, 1, 22, 12, 0, 0)

        metadata = CheckpointMetadata(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            timestamp=timestamp,
            step_number=10,
            status="running",
            size_bytes=1024,
        )

        meta_dict = metadata.to_dict()

        assert meta_dict["checkpoint_id"] == "ckpt_test"
        assert meta_dict["agent_id"] == "agent1"
        assert meta_dict["timestamp"] == "2025-01-22T12:00:00"
        assert meta_dict["step_number"] == 10
        assert meta_dict["status"] == "running"
        assert meta_dict["size_bytes"] == 1024

    def test_metadata_from_dict(self):
        """Test CheckpointMetadata.from_dict()"""
        meta_dict = {
            "checkpoint_id": "ckpt_test",
            "agent_id": "agent1",
            "timestamp": "2025-01-22T12:00:00",
            "step_number": 10,
            "status": "running",
            "size_bytes": 1024,
            "parent_checkpoint_id": None,
        }

        metadata = CheckpointMetadata.from_dict(meta_dict)

        assert metadata.checkpoint_id == "ckpt_test"
        assert isinstance(metadata.timestamp, datetime)
        assert metadata.step_number == 10

    def test_metadata_roundtrip(self):
        """Test metadata serialization roundtrip"""
        original = CheckpointMetadata(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            timestamp=datetime(2025, 1, 22, 12, 0, 0),
            step_number=10,
            status="completed",
            size_bytes=2048,
        )

        meta_dict = original.to_dict()
        restored = CheckpointMetadata.from_dict(meta_dict)

        assert restored.checkpoint_id == original.checkpoint_id
        assert restored.agent_id == original.agent_id
        assert restored.step_number == original.step_number
        assert restored.status == original.status
        assert restored.size_bytes == original.size_bytes


class TestStateSnapshot:
    """Test StateSnapshot dataclass"""

    def test_create_snapshot(self):
        """Test creating StateSnapshot"""
        state = AgentState(agent_id="test", step_number=5)

        snapshot = StateSnapshot(state=state, snapshot_reason="manual")

        assert snapshot.state == state
        assert isinstance(snapshot.created_at, datetime)
        assert snapshot.snapshot_reason == "manual"

    def test_snapshot_default_reason(self):
        """Test snapshot with default reason"""
        state = AgentState(agent_id="test")

        snapshot = StateSnapshot(state=state)

        assert snapshot.snapshot_reason == "manual"

    def test_snapshot_get_summary(self):
        """Test StateSnapshot.get_summary()"""
        state = AgentState(
            checkpoint_id="ckpt_test",
            agent_id="agent1",
            step_number=10,
            status="running",
            conversation_history=[{"role": "user", "content": "Hello"}],
            pending_actions=[{"tool": "search"}],
            completed_actions=[{"tool": "read"}],
            budget_spent_usd=1.50,
        )

        snapshot = StateSnapshot(state=state, snapshot_reason="debug")

        summary = snapshot.get_summary()

        assert summary["checkpoint_id"] == "ckpt_test"
        assert summary["agent_id"] == "agent1"
        assert summary["step_number"] == 10
        assert summary["status"] == "running"
        assert summary["conversation_turns"] == 1
        assert summary["pending_actions"] == 1
        assert summary["completed_actions"] == 1
        assert summary["budget_spent_usd"] == 1.50
        assert summary["snapshot_reason"] == "debug"
        assert "created_at" in summary

    def test_snapshot_summary_format(self):
        """Test summary is in expected format"""
        state = AgentState(agent_id="test")
        snapshot = StateSnapshot(state=state)

        summary = snapshot.get_summary()

        # Check all expected keys present
        expected_keys = [
            "checkpoint_id",
            "agent_id",
            "step_number",
            "status",
            "conversation_turns",
            "pending_actions",
            "completed_actions",
            "budget_spent_usd",
            "snapshot_reason",
            "created_at",
        ]

        for key in expected_keys:
            assert key in summary
