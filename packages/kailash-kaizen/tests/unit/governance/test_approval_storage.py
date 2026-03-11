"""
Unit tests for ExternalAgentApprovalStorage DataFlow persistence.

Tests the storage backend that persists approval requests to database
using DataFlow-generated nodes.

Note: These tests focus on:
1. Record conversion logic (to_db_record, from_db_record)
2. Manager integration with storage backend

The actual storage operations (save, load, update) require DataFlow
to be properly configured and are tested in integration tests.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.governance.approval_manager import (
    ApprovalStatus,
    ExternalAgentApprovalRequest,
)

# Check if DataFlow is available
try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False


# Create test request helper
def create_test_request(
    id: str = "req-001",
    external_agent_id: str = "agent-123",
    requested_by: str = "user-456",
    approvers: list = None,
    status: ApprovalStatus = ApprovalStatus.PENDING,
    approval_reason: str = "Test approval required",
    request_metadata: dict = None,
    approved_at: datetime = None,
    approved_by: str = None,
    rejection_reason: str = None,
) -> ExternalAgentApprovalRequest:
    """Create a test approval request."""
    return ExternalAgentApprovalRequest(
        id=id,
        external_agent_id=external_agent_id,
        requested_by=requested_by,
        approvers=approvers or ["approver-1", "approver-2"],
        status=status,
        approval_reason=approval_reason,
        request_metadata=request_metadata or {"cost": 10.0, "environment": "staging"},
        created_at=datetime.now(timezone.utc),
        approved_at=approved_at,
        approved_by=approved_by,
        rejection_reason=rejection_reason,
    )


def create_mock_storage():
    """Create a storage instance for testing without DataFlow dependency."""
    from kaizen.governance.storage import ExternalAgentApprovalStorage

    storage = object.__new__(ExternalAgentApprovalStorage)
    storage.db = MagicMock()
    storage._models = {}
    storage.runtime = AsyncMock()
    storage.MODEL_NAME = "ExternalAgentApprovalRequest"
    return storage


class TestStorageRecordConversion:
    """Tests for converting between ExternalAgentApprovalRequest and database records."""

    def test_to_db_record_serializes_approvers_list(self):
        """Test that approvers list is serialized to JSON string."""
        storage = create_mock_storage()

        request = create_test_request(approvers=["lead-1", "lead-2", "admin-1"])
        record = storage._to_db_record(request)

        assert "approvers_json" in record
        assert record["approvers_json"] == '["lead-1", "lead-2", "admin-1"]'
        assert json.loads(record["approvers_json"]) == ["lead-1", "lead-2", "admin-1"]

    def test_to_db_record_serializes_metadata_dict(self):
        """Test that request_metadata dict is serialized to JSON string."""
        storage = create_mock_storage()

        metadata = {"cost": 25.50, "environment": "production", "tags": ["critical"]}
        request = create_test_request(request_metadata=metadata)
        record = storage._to_db_record(request)

        assert "request_metadata_json" in record
        parsed = json.loads(record["request_metadata_json"])
        assert parsed["cost"] == 25.50
        assert parsed["environment"] == "production"
        assert parsed["tags"] == ["critical"]

    def test_to_db_record_converts_status_to_string(self):
        """Test that ApprovalStatus enum is converted to string value."""
        storage = create_mock_storage()

        request = create_test_request(status=ApprovalStatus.APPROVED)
        record = storage._to_db_record(request)

        assert record["status"] == "approved"

    def test_to_db_record_handles_approved_at_datetime(self):
        """Test that approved_at datetime is converted to ISO string."""
        storage = create_mock_storage()

        approved_time = datetime(2025, 1, 15, 10, 30, 0)
        request = create_test_request(
            status=ApprovalStatus.APPROVED,
            approved_at=approved_time,
            approved_by="approver-1",
        )
        record = storage._to_db_record(request)

        assert record["approved_at"] == "2025-01-15T10:30:00"

    def test_to_db_record_handles_none_approved_at(self):
        """Test that None approved_at is preserved."""
        storage = create_mock_storage()

        request = create_test_request()  # Pending, no approved_at
        record = storage._to_db_record(request)

        assert record["approved_at"] is None

    def test_from_db_record_deserializes_approvers_json(self):
        """Test that approvers_json string is deserialized to list."""
        storage = create_mock_storage()

        record = {
            "id": "req-001",
            "external_agent_id": "agent-123",
            "requested_by": "user-456",
            "approvers_json": '["approver-1", "approver-2"]',
            "status": "pending",
            "approval_reason": "Test",
            "request_metadata_json": "{}",
            "created_at": "2025-01-15T10:00:00",
        }

        request = storage._from_db_record(record)

        assert request.approvers == ["approver-1", "approver-2"]
        assert isinstance(request.approvers, list)

    def test_from_db_record_deserializes_metadata_json(self):
        """Test that request_metadata_json string is deserialized to dict."""
        storage = create_mock_storage()

        record = {
            "id": "req-001",
            "external_agent_id": "agent-123",
            "requested_by": "user-456",
            "approvers_json": "[]",
            "status": "pending",
            "approval_reason": "Test",
            "request_metadata_json": '{"cost": 15.0, "environment": "production"}',
            "created_at": "2025-01-15T10:00:00",
        }

        request = storage._from_db_record(record)

        assert request.request_metadata == {"cost": 15.0, "environment": "production"}
        assert isinstance(request.request_metadata, dict)

    def test_from_db_record_converts_status_to_enum(self):
        """Test that status string is converted to ApprovalStatus enum."""
        storage = create_mock_storage()

        for status_str, expected_enum in [
            ("pending", ApprovalStatus.PENDING),
            ("approved", ApprovalStatus.APPROVED),
            ("rejected", ApprovalStatus.REJECTED),
            ("timeout", ApprovalStatus.TIMEOUT),
        ]:
            record = {
                "id": "req-001",
                "external_agent_id": "agent-123",
                "requested_by": "user-456",
                "approvers_json": "[]",
                "status": status_str,
                "approval_reason": "Test",
                "request_metadata_json": "{}",
                "created_at": "2025-01-15T10:00:00",
            }

            request = storage._from_db_record(record)
            assert request.status == expected_enum

    def test_from_db_record_parses_datetime_strings(self):
        """Test that datetime strings are parsed to datetime objects."""
        storage = create_mock_storage()

        record = {
            "id": "req-001",
            "external_agent_id": "agent-123",
            "requested_by": "user-456",
            "approvers_json": "[]",
            "status": "approved",
            "approval_reason": "Test",
            "request_metadata_json": "{}",
            "created_at": "2025-01-15T10:00:00",
            "approved_at": "2025-01-15T11:30:00",
            "approved_by": "approver-1",
        }

        request = storage._from_db_record(record)

        assert isinstance(request.created_at, datetime)
        assert isinstance(request.approved_at, datetime)
        assert request.approved_at.hour == 11
        assert request.approved_at.minute == 30

    def test_roundtrip_conversion_preserves_data(self):
        """Test that converting to record and back preserves all data."""
        storage = create_mock_storage()

        original = create_test_request(
            id="roundtrip-001",
            external_agent_id="agent-xyz",
            requested_by="user-abc",
            approvers=["lead-1", "admin-1"],
            status=ApprovalStatus.REJECTED,
            approval_reason="Cost threshold exceeded",
            request_metadata={"cost": 50.0, "tags": ["critical", "production"]},
            approved_at=datetime(2025, 1, 15, 12, 0, 0),
            approved_by="admin-1",
            rejection_reason="Budget exceeded for Q1",
        )

        # Convert to record and back
        record = storage._to_db_record(original)
        # Simulate database storage (created_at would be from record)
        record["created_at"] = original.created_at.isoformat()
        restored = storage._from_db_record(record)

        # Verify all fields preserved
        assert restored.id == original.id
        assert restored.external_agent_id == original.external_agent_id
        assert restored.requested_by == original.requested_by
        assert restored.approvers == original.approvers
        assert restored.status == original.status
        assert restored.approval_reason == original.approval_reason
        assert restored.request_metadata == original.request_metadata
        assert restored.approved_by == original.approved_by
        assert restored.rejection_reason == original.rejection_reason


@pytest.mark.skipif(
    not DATAFLOW_AVAILABLE,
    reason="DataFlow not installed - storage operations require DataFlow",
)
class TestStorageOperations:
    """
    Tests for storage CRUD operations.

    Note: These tests require DataFlow to be properly configured since
    the storage methods create workflows with DataFlow-generated nodes.
    The tests are skipped when DataFlow is not available.

    For unit testing of the manager integration with storage, see
    TestApprovalManagerIntegration which uses mocked storage backends.
    """

    pass  # Integration tests go in tests/integration/governance/


class TestApprovalManagerIntegration:
    """Tests for approval manager integration with storage backend."""

    @pytest.mark.asyncio
    async def test_request_approval_persists_to_storage(self):
        """Test that request_approval saves to storage when configured."""
        from kaizen.governance.approval_manager import (
            ApprovalLevel,
            ApprovalRequirement,
            ExternalAgentApprovalManager,
        )

        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="req-001")

        manager = ExternalAgentApprovalManager(
            control_protocol=None,
            storage_backend=mock_storage,
        )

        # Configure approval requirement
        requirement = ApprovalRequirement(
            require_for_environments=["production"],
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("test-agent", requirement)

        # Configure team routing
        manager._user_teams["user-123"] = "team-1"
        manager._team_leads["team-1"] = ["lead-1"]

        # Request approval
        request_id = await manager.request_approval(
            external_agent_id="test-agent",
            requested_by="user-123",
            metadata={"environment": "production"},
        )

        # Verify storage.save was called
        mock_storage.save.assert_called_once()
        saved_request = mock_storage.save.call_args[0][0]
        assert saved_request.external_agent_id == "test-agent"
        assert saved_request.requested_by == "user-123"
        assert saved_request.status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_approve_request_updates_storage(self):
        """Test that approve_request updates storage when configured."""
        from kaizen.governance.approval_manager import (
            ApprovalLevel,
            ApprovalRequirement,
            ExternalAgentApprovalManager,
        )

        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="req-001")
        mock_storage.update = AsyncMock()

        manager = ExternalAgentApprovalManager(
            control_protocol=None,
            storage_backend=mock_storage,
        )

        # Configure and create request
        requirement = ApprovalRequirement(
            require_for_environments=["production"],
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("test-agent", requirement)
        manager._user_teams["user-123"] = "team-1"
        manager._team_leads["team-1"] = ["lead-1"]

        request_id = await manager.request_approval(
            external_agent_id="test-agent",
            requested_by="user-123",
            metadata={"environment": "production"},
        )

        # Approve the request
        await manager.approve_request(request_id, "lead-1")

        # Verify storage.update was called
        mock_storage.update.assert_called_once()
        updated_request = mock_storage.update.call_args[0][0]
        assert updated_request.status == ApprovalStatus.APPROVED
        assert updated_request.approved_by == "lead-1"

    @pytest.mark.asyncio
    async def test_reject_request_updates_storage(self):
        """Test that reject_request updates storage when configured."""
        from kaizen.governance.approval_manager import (
            ApprovalLevel,
            ApprovalRequirement,
            ExternalAgentApprovalManager,
        )

        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="req-001")
        mock_storage.update = AsyncMock()

        manager = ExternalAgentApprovalManager(
            control_protocol=None,
            storage_backend=mock_storage,
        )

        # Configure and create request
        requirement = ApprovalRequirement(
            require_for_environments=["production"],
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("test-agent", requirement)
        manager._user_teams["user-123"] = "team-1"
        manager._team_leads["team-1"] = ["lead-1"]

        request_id = await manager.request_approval(
            external_agent_id="test-agent",
            requested_by="user-123",
            metadata={"environment": "production"},
        )

        # Reject the request
        await manager.reject_request(request_id, "lead-1", "Budget exceeded")

        # Verify storage.update was called
        mock_storage.update.assert_called_once()
        updated_request = mock_storage.update.call_args[0][0]
        assert updated_request.status == ApprovalStatus.REJECTED
        assert updated_request.rejection_reason == "Budget exceeded"

    @pytest.mark.asyncio
    async def test_timeout_updates_storage(self):
        """Test that timeout_pending_approvals updates storage."""
        from kaizen.governance.approval_manager import (
            ApprovalLevel,
            ApprovalRequirement,
            ExternalAgentApprovalManager,
        )

        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="req-001")
        mock_storage.update = AsyncMock()

        manager = ExternalAgentApprovalManager(
            control_protocol=None,
            storage_backend=mock_storage,
        )

        # Configure with very short timeout
        requirement = ApprovalRequirement(
            require_for_environments=["production"],
            approval_level=ApprovalLevel.TEAM_LEAD,
            approval_timeout_seconds=0,  # Immediate timeout
        )
        manager.add_requirement("test-agent", requirement)
        manager._user_teams["user-123"] = "team-1"
        manager._team_leads["team-1"] = ["lead-1"]

        # Create request
        await manager.request_approval(
            external_agent_id="test-agent",
            requested_by="user-123",
            metadata={"environment": "production"},
        )

        # Trigger timeout check
        timed_out = await manager.timeout_pending_approvals()

        assert timed_out == 1
        mock_storage.update.assert_called_once()
        updated_request = mock_storage.update.call_args[0][0]
        assert updated_request.status == ApprovalStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_no_storage_calls_without_storage_backend(self):
        """Test that operations work without storage backend configured."""
        from kaizen.governance.approval_manager import (
            ApprovalLevel,
            ApprovalRequirement,
            ExternalAgentApprovalManager,
        )

        # No storage backend
        manager = ExternalAgentApprovalManager(
            control_protocol=None,
            storage_backend=None,
        )

        # Configure and create request
        requirement = ApprovalRequirement(
            require_for_environments=["production"],
            approval_level=ApprovalLevel.TEAM_LEAD,
        )
        manager.add_requirement("test-agent", requirement)
        manager._user_teams["user-123"] = "team-1"
        manager._team_leads["team-1"] = ["lead-1"]

        # These should work without errors
        request_id = await manager.request_approval(
            external_agent_id="test-agent",
            requested_by="user-123",
            metadata={"environment": "production"},
        )
        await manager.approve_request(request_id, "lead-1")

        # Verify in-memory storage
        assert manager._requests[request_id].status == ApprovalStatus.APPROVED
