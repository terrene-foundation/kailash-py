"""
Tier 1 Unit Tests for Audit Trail Storage.

Tests FileAuditStorage and AuditTrailManager with temporary files.
Validates append-only immutability, querying, and compliance requirements.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
Target: <10ms per append (NFR)
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kaizen.core.autonomy.observability.audit import AuditTrailManager, FileAuditStorage
from kaizen.core.autonomy.observability.types import AuditEntry


@pytest.fixture
def temp_audit_file(tmp_path):
    """Fixture providing temporary audit file path."""
    return str(tmp_path / "test_audit.jsonl")


class TestFileAuditStorageBasics:
    """Test basic FileAuditStorage initialization and setup."""

    def test_storage_initialization(self, temp_audit_file):
        """Test FileAuditStorage initializes and creates file."""
        storage = FileAuditStorage(temp_audit_file)

        assert storage.file_path == Path(temp_audit_file)
        assert storage.file_path.exists()

    def test_storage_creates_parent_directories(self, tmp_path):
        """Test FileAuditStorage creates parent directories if needed."""
        nested_path = str(tmp_path / "nested" / "dirs" / "audit.jsonl")
        storage = FileAuditStorage(nested_path)

        assert storage.file_path.exists()
        assert storage.file_path.parent.exists()

    def test_get_file_path(self, temp_audit_file):
        """Test get_file_path returns Path object."""
        storage = FileAuditStorage(temp_audit_file)

        path = storage.get_file_path()

        assert isinstance(path, Path)
        assert path == Path(temp_audit_file)


class TestFileAuditStorageAppend:
    """Test audit entry append operations."""

    @pytest.mark.asyncio
    async def test_append_single_entry(self, temp_audit_file):
        """Test appending single audit entry."""
        storage = FileAuditStorage(temp_audit_file)

        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id="test-agent",
            action="test_action",
            details={"key": "value"},
            result="success",
        )

        await storage.append(entry)

        # Verify file has content
        count = await storage.count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_append_multiple_entries(self, temp_audit_file):
        """Test appending multiple audit entries."""
        storage = FileAuditStorage(temp_audit_file)

        for i in range(5):
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id=f"agent-{i}",
                action="test_action",
                details={"index": i},
                result="success",
            )
            await storage.append(entry)

        count = await storage.count()
        assert count == 5

    @pytest.mark.asyncio
    async def test_append_preserves_all_fields(self, temp_audit_file):
        """Test append preserves all entry fields."""
        storage = FileAuditStorage(temp_audit_file)

        timestamp = datetime.now(timezone.utc)
        entry = AuditEntry(
            timestamp=timestamp,
            agent_id="test-agent",
            action="tool_execute",
            details={"tool": "bash", "command": "ls"},
            result="success",
            user_id="user@example.com",
            metadata={"danger_level": "MODERATE"},
        )

        await storage.append(entry)

        # Read back and verify
        entries = await storage.query()
        assert len(entries) == 1

        retrieved = entries[0]
        assert retrieved.agent_id == "test-agent"
        assert retrieved.action == "tool_execute"
        assert retrieved.details["tool"] == "bash"
        assert retrieved.result == "success"
        assert retrieved.user_id == "user@example.com"
        assert retrieved.metadata["danger_level"] == "MODERATE"

    @pytest.mark.asyncio
    async def test_append_concurrent_entries(self, temp_audit_file):
        """Test appending entries concurrently."""
        storage = FileAuditStorage(temp_audit_file)

        async def append_entry(index):
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id=f"agent-{index}",
                action="test_action",
                details={"index": index},
                result="success",
            )
            await storage.append(entry)

        # Append 10 entries concurrently
        await asyncio.gather(*[append_entry(i) for i in range(10)])

        count = await storage.count()
        assert count == 10


class TestFileAuditStorageQuery:
    """Test audit entry querying with filters."""

    @pytest.mark.asyncio
    async def test_run_all_entries(self, temp_audit_file):
        """Test querying all entries without filters."""
        storage = FileAuditStorage(temp_audit_file)

        # Append 3 entries
        for i in range(3):
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id=f"agent-{i}",
                action="test_action",
                details={},
                result="success",
            )
            await storage.append(entry)

        entries = await storage.query()

        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_run_by_agent_id(self, temp_audit_file):
        """Test querying by agent_id filter."""
        storage = FileAuditStorage(temp_audit_file)

        # Append entries from different agents
        for agent_id in ["agent-1", "agent-2", "agent-1", "agent-3"]:
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id=agent_id,
                action="test_action",
                details={},
                result="success",
            )
            await storage.append(entry)

        entries = await storage.query(agent_id="agent-1")

        assert len(entries) == 2
        assert all(e.agent_id == "agent-1" for e in entries)

    @pytest.mark.asyncio
    async def test_run_by_action(self, temp_audit_file):
        """Test querying by action filter."""
        storage = FileAuditStorage(temp_audit_file)

        # Append entries with different actions
        actions = ["tool_execute", "permission_grant", "tool_execute"]
        for action in actions:
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id="test-agent",
                action=action,
                details={},
                result="success",
            )
            await storage.append(entry)

        entries = await storage.query(action="tool_execute")

        assert len(entries) == 2
        assert all(e.action == "tool_execute" for e in entries)

    @pytest.mark.asyncio
    async def test_run_by_user_id(self, temp_audit_file):
        """Test querying by user_id filter."""
        storage = FileAuditStorage(temp_audit_file)

        # Append entries from different users
        for user_id in ["user1", "user2", "user1"]:
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id="test-agent",
                action="test_action",
                details={},
                result="success",
                user_id=user_id,
            )
            await storage.append(entry)

        entries = await storage.query(user_id="user1")

        assert len(entries) == 2
        assert all(e.user_id == "user1" for e in entries)

    @pytest.mark.asyncio
    async def test_run_by_result(self, temp_audit_file):
        """Test querying by result filter."""
        storage = FileAuditStorage(temp_audit_file)

        # Append entries with different results
        results = ["success", "failure", "success", "denied"]
        for result in results:
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id="test-agent",
                action="test_action",
                details={},
                result=result,  # type: ignore
            )
            await storage.append(entry)

        entries = await storage.query(result="success")

        assert len(entries) == 2
        assert all(e.result == "success" for e in entries)

    @pytest.mark.asyncio
    async def test_run_by_timerange(self, temp_audit_file):
        """Test querying by time range."""
        storage = FileAuditStorage(temp_audit_file)

        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=2)
        future = now + timedelta(hours=2)

        # Append entries with different timestamps
        for offset_hours in [-3, -1, 0, 1, 3]:
            timestamp = now + timedelta(hours=offset_hours)
            entry = AuditEntry(
                timestamp=timestamp,
                agent_id="test-agent",
                action="test_action",
                details={},
                result="success",
            )
            await storage.append(entry)

        entries = await storage.query(start_time=past, end_time=future)

        # Should get entries from -1, 0, 1 hours (3 entries)
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_run_with_multiple_filters(self, temp_audit_file):
        """Test querying with multiple filters combined."""
        storage = FileAuditStorage(temp_audit_file)

        # Append entries with various attributes
        for i in range(5):
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id="agent-1" if i < 3 else "agent-2",
                action="action-1" if i % 2 == 0 else "action-2",
                details={},
                result="success",
            )
            await storage.append(entry)

        # Query with multiple filters
        entries = await storage.query(agent_id="agent-1", action="action-1")

        # Should get entries 0 and 2 (agent-1 + action-1)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_run_empty_file(self, temp_audit_file):
        """Test querying empty file returns empty list."""
        storage = FileAuditStorage(temp_audit_file)

        entries = await storage.query()

        assert entries == []

    @pytest.mark.asyncio
    async def test_run_no_matches(self, temp_audit_file):
        """Test querying with no matches returns empty list."""
        storage = FileAuditStorage(temp_audit_file)

        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id="agent-1",
            action="test_action",
            details={},
            result="success",
        )
        await storage.append(entry)

        entries = await storage.query(agent_id="nonexistent")

        assert entries == []


class TestFileAuditStorageEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_count_empty_file(self, temp_audit_file):
        """Test count returns 0 for empty file."""
        storage = FileAuditStorage(temp_audit_file)

        count = await storage.count()

        assert count == 0

    @pytest.mark.asyncio
    async def test_run_skips_malformed_entries(self, temp_audit_file):
        """Test query skips malformed JSONL entries."""
        storage = FileAuditStorage(temp_audit_file)

        # Write valid entry
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id="test-agent",
            action="test_action",
            details={},
            result="success",
        )
        await storage.append(entry)

        # Manually write malformed entry
        with open(temp_audit_file, "a") as f:
            f.write("not valid json\n")
            f.write('{"incomplete": json\n')

        # Write another valid entry
        await storage.append(entry)

        # Query should skip malformed entries
        entries = await storage.query()
        assert len(entries) == 2  # Only valid entries


class TestAuditTrailManagerBasics:
    """Test AuditTrailManager initialization and basic operations."""

    @pytest.mark.asyncio
    async def test_manager_initialization_default_storage(self):
        """Test AuditTrailManager initializes with default FileAuditStorage."""
        manager = AuditTrailManager()

        assert manager.storage is not None
        assert isinstance(manager.storage, FileAuditStorage)

    @pytest.mark.asyncio
    async def test_manager_initialization_custom_storage(self, temp_audit_file):
        """Test AuditTrailManager accepts custom storage."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        assert manager.storage is storage


class TestAuditTrailManagerRecord:
    """Test audit trail recording via manager."""

    @pytest.mark.asyncio
    async def test_record_audit_entry(self, temp_audit_file):
        """Test recording audit entry via manager."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        await manager.record(
            agent_id="test-agent",
            action="tool_execute",
            details={"tool": "bash", "command": "ls"},
            result="success",
            user_id="user@example.com",
            metadata={"danger_level": "MODERATE"},
        )

        # Verify entry was recorded
        entries = await manager.query_all()
        assert len(entries) == 1

        entry = entries[0]
        assert entry.agent_id == "test-agent"
        assert entry.action == "tool_execute"
        assert entry.result == "success"
        assert entry.user_id == "user@example.com"

    @pytest.mark.asyncio
    async def test_record_auto_adds_timestamp(self, temp_audit_file):
        """Test record automatically adds timestamp."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        before = datetime.now(timezone.utc)
        await manager.record(
            agent_id="test-agent", action="test_action", details={}, result="success"
        )
        after = datetime.now(timezone.utc)

        entries = await manager.query_all()
        timestamp = entries[0].timestamp

        # Normalize timestamp to timezone-aware if needed for comparison
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        assert before <= timestamp <= after

    @pytest.mark.asyncio
    async def test_record_optional_fields(self, temp_audit_file):
        """Test record with optional fields omitted."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        await manager.record(
            agent_id="test-agent",
            action="test_action",
            details={},
            result="success",
            # No user_id or metadata
        )

        entries = await manager.query_all()
        entry = entries[0]

        assert entry.user_id is None
        assert entry.metadata == {}


class TestAuditTrailManagerQueries:
    """Test convenient run methods."""

    @pytest.mark.asyncio
    async def test_run_by_agent(self, temp_audit_file):
        """Test query_by_agent method."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        # Record entries from different agents
        for agent_id in ["agent-1", "agent-2", "agent-1"]:
            await manager.record(
                agent_id=agent_id, action="test_action", details={}, result="success"
            )

        entries = await manager.query_by_agent("agent-1")

        assert len(entries) == 2
        assert all(e.agent_id == "agent-1" for e in entries)

    @pytest.mark.asyncio
    async def test_run_by_action(self, temp_audit_file):
        """Test query_by_action method."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        # Record entries with different actions
        for action in ["tool_execute", "permission_grant", "tool_execute"]:
            await manager.record(
                agent_id="test-agent", action=action, details={}, result="success"
            )

        entries = await manager.query_by_action("tool_execute")

        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_run_by_user(self, temp_audit_file):
        """Test query_by_user method."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        # Record entries from different users
        for user_id in ["user1", "user2", "user1"]:
            await manager.record(
                agent_id="test-agent",
                action="test_action",
                details={},
                result="success",
                user_id=user_id,
            )

        entries = await manager.query_by_user("user1")

        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_run_by_result(self, temp_audit_file):
        """Test query_by_result method."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        # Record entries with different results
        for result in ["success", "failure", "success", "denied"]:
            await manager.record(
                agent_id="test-agent",
                action="test_action",
                details={},
                result=result,  # type: ignore
            )

        failures = await manager.query_by_result("failure")
        successes = await manager.query_by_result("success")

        assert len(failures) == 1
        assert len(successes) == 2

    @pytest.mark.asyncio
    async def test_run_by_timerange(self, temp_audit_file):
        """Test query_by_timerange method."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        now = datetime.now(timezone.utc)

        # Record 3 entries
        for i in range(3):
            await manager.record(
                agent_id="test-agent",
                action="test_action",
                details={},
                result="success",
            )
            await asyncio.sleep(0.01)  # Small delay

        # Query last 2 hours
        start = now - timedelta(hours=2)
        end = now + timedelta(hours=2)
        entries = await manager.query_by_timerange(start, end)

        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_run_all(self, temp_audit_file):
        """Test query_all method."""
        storage = FileAuditStorage(temp_audit_file)
        manager = AuditTrailManager(storage=storage)

        # Record 5 entries
        for i in range(5):
            await manager.record(
                agent_id=f"agent-{i}",
                action="test_action",
                details={},
                result="success",
            )

        entries = await manager.query_all()

        assert len(entries) == 5
