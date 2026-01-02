"""Unit tests for DurableRequest."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.middleware.gateway.durable_request import (
    Checkpoint,
    DurableRequest,
    ExecutionJournal,
    RequestMetadata,
    RequestState,
)


class TestRequestMetadata:
    """Test RequestMetadata dataclass."""

    def test_create_metadata(self):
        """Test creating request metadata."""
        now = datetime.now(UTC)
        metadata = RequestMetadata(
            request_id="req_123",
            method="POST",
            path="/api/workflow",
            headers={"Content-Type": "application/json"},
            query_params={"debug": "true"},
            body={"workflow": "test"},
            client_ip="192.168.1.1",
            user_id="user_123",
            tenant_id="tenant_456",
            idempotency_key="idem_789",
            created_at=now,
            updated_at=now,
        )

        assert metadata.request_id == "req_123"
        assert metadata.method == "POST"
        assert metadata.idempotency_key == "idem_789"


class TestCheckpoint:
    """Test Checkpoint dataclass."""

    def test_checkpoint_serialization(self):
        """Test checkpoint to/from dict."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt_123",
            request_id="req_456",
            sequence=0,
            name="test_checkpoint",
            state=RequestState.EXECUTING,
            data={"key": "value"},
            workflow_state={"nodes": []},
            created_at=datetime.now(UTC),
            size_bytes=100,
        )

        # Convert to dict
        checkpoint_dict = checkpoint.to_dict()
        assert checkpoint_dict["checkpoint_id"] == "ckpt_123"
        assert checkpoint_dict["state"] == "executing"

        # Convert back
        restored = Checkpoint.from_dict(checkpoint_dict)
        assert restored.checkpoint_id == checkpoint.checkpoint_id
        assert restored.state == checkpoint.state


class TestExecutionJournal:
    """Test ExecutionJournal."""

    @pytest.mark.asyncio
    async def test_record_event(self):
        """Test recording events."""
        journal = ExecutionJournal("req_123")

        await journal.record("test_event", {"data": "value"})

        assert len(journal.events) == 1
        assert journal.events[0]["type"] == "test_event"
        assert journal.events[0]["data"] == {"data": "value"}
        assert journal.events[0]["sequence"] == 0

    def test_get_events_by_type(self):
        """Test filtering events by type."""
        journal = ExecutionJournal("req_123")
        journal.events = [
            {"type": "start", "data": {}, "sequence": 0},
            {"type": "checkpoint", "data": {}, "sequence": 1},
            {"type": "start", "data": {}, "sequence": 2},
        ]

        start_events = journal.get_events("start")
        assert len(start_events) == 2
        assert all(e["type"] == "start" for e in start_events)


class TestDurableRequest:
    """Test DurableRequest class."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test request initialization."""
        request = DurableRequest()

        assert request.id.startswith("req_")
        assert request.state == RequestState.INITIALIZED
        assert request.checkpoints == []
        assert request.workflow is None
        assert request.result is None
        assert request.error is None

    @pytest.mark.asyncio
    async def test_execute_simple(self):
        """Test simple request execution."""
        request = DurableRequest()
        request.metadata.body = {"workflow": {"name": "test"}}

        # Mock workflow creation
        request._create_workflow = AsyncMock()
        request._execute_workflow = AsyncMock(return_value={"status": "success"})

        result = await request.execute()

        assert result["status"] == "completed"
        assert result["result"] == {"status": "success"}
        assert request.state == RequestState.COMPLETED
        assert request.checkpoint_count > 0

    @pytest.mark.asyncio
    async def test_checkpoint_creation(self):
        """Test creating checkpoints."""
        request = DurableRequest()

        checkpoint_id = await request.checkpoint("test_point", {"value": 42})

        assert checkpoint_id.startswith("ckpt_")
        assert len(request.checkpoints) == 1
        assert request.checkpoints[0].name == "test_point"
        assert request.checkpoints[0].data == {"value": 42}
        assert request.checkpoint_count == 1

    @pytest.mark.asyncio
    async def test_checkpoint_with_manager(self):
        """Test checkpoint with checkpoint manager."""
        mock_manager = AsyncMock()
        request = DurableRequest(checkpoint_manager=mock_manager)

        await request.checkpoint("test_point", {"value": 42})

        # Verify checkpoint was saved to manager
        mock_manager.save_checkpoint.assert_called_once()
        saved_checkpoint = mock_manager.save_checkpoint.call_args[0][0]
        assert saved_checkpoint.name == "test_point"

    @pytest.mark.asyncio
    async def test_cancellation(self):
        """Test request cancellation."""
        request = DurableRequest()

        await request.cancel()

        assert request.state == RequestState.CANCELLED
        assert request._cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_checkpoint_after_cancel(self):
        """Test checkpoint fails after cancellation."""
        request = DurableRequest()
        await request.cancel()

        with pytest.raises(asyncio.CancelledError):
            await request.checkpoint("should_fail")

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling during execution."""
        request = DurableRequest()
        request.metadata.body = {"workflow": {"name": "test"}}

        # Mock workflow creation to raise error
        error = RuntimeError("Test error")
        request._create_workflow = AsyncMock(side_effect=error)

        with pytest.raises(RuntimeError):
            await request.execute()

        assert request.state == RequestState.FAILED
        assert request.error == error
        assert request.checkpoint_count > 0  # Should have error checkpoint

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self):
        """Test resuming from checkpoint."""
        # Create checkpoint
        checkpoint = Checkpoint(
            checkpoint_id="ckpt_123",
            request_id="req_456",
            sequence=2,
            name="test_checkpoint",
            state=RequestState.EXECUTING,
            data={"progress": 50},
            workflow_state={"completed_nodes": ["node1", "node2"]},
            created_at=datetime.now(UTC),
            size_bytes=100,
        )

        # Mock checkpoint manager
        mock_manager = AsyncMock()
        mock_manager.load_checkpoint.return_value = checkpoint

        request = DurableRequest(checkpoint_manager=mock_manager)
        request.execute = AsyncMock(return_value={"status": "completed"})

        result = await request.resume("ckpt_123")

        assert result["status"] == "completed"
        # State should be restored from checkpoint
        assert request.state == RequestState.EXECUTING
        mock_manager.load_checkpoint.assert_called_with("ckpt_123")

    @pytest.mark.asyncio
    async def test_resume_latest_checkpoint(self):
        """Test resuming from latest checkpoint."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt_latest",
            request_id="req_456",
            sequence=5,
            name="latest",
            state=RequestState.EXECUTING,
            data={},
            workflow_state=None,
            created_at=datetime.now(UTC),
            size_bytes=50,
        )

        mock_manager = AsyncMock()
        mock_manager.load_latest_checkpoint.return_value = checkpoint

        request = DurableRequest(request_id="req_456", checkpoint_manager=mock_manager)
        request.execute = AsyncMock(return_value={"status": "completed"})

        result = await request.resume()

        mock_manager.load_latest_checkpoint.assert_called_with("req_456")

    def test_get_status(self):
        """Test getting request status."""
        request = DurableRequest()
        request.state = RequestState.EXECUTING
        request.checkpoint_count = 3
        request.journal.events = [1, 2, 3, 4, 5]  # Mock events
        request.start_time = 1000.0
        request.end_time = 1005.0
        request.result = {"data": "test"}

        status = request.get_status()

        assert status["request_id"] == request.id
        assert status["state"] == "executing"
        assert status["checkpoints"] == 3
        assert status["events"] == 5
        assert status["duration_ms"] == 5000.0
        assert status["result"] == {"data": "test"}

    @pytest.mark.asyncio
    async def test_validate_request(self):
        """Test request validation."""
        request = DurableRequest()

        await request._validate_request()

        assert request.state == RequestState.VALIDATED
        assert len(request.checkpoints) == 1
        assert request.checkpoints[0].name == "request_validated"

    @pytest.mark.asyncio
    async def test_workflow_creation(self):
        """Test workflow creation from request."""
        request = DurableRequest()
        request.metadata.body = {"workflow": {"name": "TestWorkflow", "nodes": []}}

        await request._create_workflow()

        assert request.state == RequestState.WORKFLOW_CREATED
        assert request.workflow is not None
        assert request.workflow_id.startswith("wf_")
        assert len(request.checkpoints) == 1
