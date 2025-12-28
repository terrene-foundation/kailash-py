"""Unit tests for Two-Phase Commit Coordinator Node.

Tests the 2PC protocol implementation including prepare/commit phases,
participant management, and state persistence.

Following Tier 1 testing policy: Fast execution, mocking allowed.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.transaction.two_phase_commit import (
    ParticipantVote,
    TransactionState,
    TwoPhaseCommitCoordinatorNode,
    TwoPhaseCommitParticipant,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestTwoPhaseCommitParticipant:
    """Test TwoPhaseCommitParticipant class."""

    def test_participant_creation(self):
        """Test creating a participant."""
        participant = TwoPhaseCommitParticipant(
            participant_id="test_service",
            endpoint="http://test:8080/2pc",
            timeout=30,
            retry_count=3,
        )

        assert participant.participant_id == "test_service"
        assert participant.endpoint == "http://test:8080/2pc"
        assert participant.timeout == 30
        assert participant.retry_count == 3
        assert participant.vote is None
        assert participant.last_contact is None

    def test_participant_to_dict(self):
        """Test participant serialization."""
        participant = TwoPhaseCommitParticipant(
            participant_id="test_service", endpoint="http://test:8080/2pc"
        )
        participant.vote = ParticipantVote.PREPARED
        participant.last_contact = datetime.now(UTC)

        data = participant.to_dict()

        assert data["participant_id"] == "test_service"
        assert data["endpoint"] == "http://test:8080/2pc"
        assert data["vote"] == "prepared"
        assert data["last_contact"] is not None

    def test_participant_from_dict(self):
        """Test participant deserialization."""
        data = {
            "participant_id": "test_service",
            "endpoint": "http://test:8080/2pc",
            "timeout": 30,
            "retry_count": 3,
            "vote": "prepared",
            "last_contact": "2024-01-15T10:00:00+00:00",
        }

        participant = TwoPhaseCommitParticipant.from_dict(data)

        assert participant.participant_id == "test_service"
        assert participant.endpoint == "http://test:8080/2pc"
        assert participant.vote == ParticipantVote.PREPARED
        assert participant.last_contact is not None


class TestTwoPhaseCommitCoordinatorNode:
    """Test TwoPhaseCommitCoordinatorNode."""

    def test_coordinator_initialization(self):
        """Test coordinator initialization."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="test_transaction",
            participants=["service1", "service2"],
            timeout=300,
        )

        assert coordinator.transaction_name == "test_transaction"
        assert coordinator.timeout == 300
        assert coordinator.state == TransactionState.INIT
        assert len(coordinator.participants) == 2
        assert "service1" in coordinator.participants
        assert "service2" in coordinator.participants

    def test_coordinator_with_defaults(self):
        """Test coordinator with default values."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        assert coordinator.transaction_name.startswith("2pc_")
        assert coordinator.timeout == 300
        assert coordinator.prepare_timeout == 30
        assert coordinator.commit_timeout == 30
        assert coordinator.state == TransactionState.INIT
        assert len(coordinator.participants) == 0

    @pytest.mark.asyncio
    async def test_begin_transaction(self):
        """Test beginning a transaction."""
        coordinator = TwoPhaseCommitCoordinatorNode(transaction_name="test_tx")

        result = await coordinator.async_run(
            operation="begin_transaction", context={"order_id": "123", "amount": 100.0}
        )

        assert result["status"] == "success"
        assert result["transaction_id"] == coordinator.transaction_id
        assert result["state"] == "init"
        assert coordinator.context["order_id"] == "123"
        assert coordinator.started_at is not None

    @pytest.mark.asyncio
    async def test_begin_transaction_already_started(self):
        """Test beginning transaction when already started."""
        coordinator = TwoPhaseCommitCoordinatorNode()
        coordinator.state = TransactionState.PREPARING

        result = await coordinator.async_run(operation="begin_transaction")

        assert result["status"] == "error"
        assert "already in state" in result["error"]

    @pytest.mark.asyncio
    async def test_add_participant(self):
        """Test adding a participant."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        result = await coordinator.async_run(
            operation="add_participant",
            participant_id="payment_service",
            endpoint="http://payment:8080/2pc",
        )

        assert result["status"] == "success"
        assert result["participant_id"] == "payment_service"
        assert result["total_participants"] == 1
        assert "payment_service" in coordinator.participants

        participant = coordinator.participants["payment_service"]
        assert participant.endpoint == "http://payment:8080/2pc"

    @pytest.mark.asyncio
    async def test_add_participant_default_endpoint(self):
        """Test adding participant with default endpoint."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        result = await coordinator.async_run(
            operation="add_participant", participant_id="inventory_service"
        )

        assert result["status"] == "success"
        participant = coordinator.participants["inventory_service"]
        assert participant.endpoint == "http://inventory_service/2pc"

    @pytest.mark.asyncio
    async def test_add_participant_already_exists(self):
        """Test adding participant that already exists."""
        coordinator = TwoPhaseCommitCoordinatorNode(participants=["existing_service"])

        result = await coordinator.async_run(
            operation="add_participant", participant_id="existing_service"
        )

        assert result["status"] == "exists"
        assert result["participant_id"] == "existing_service"

    @pytest.mark.asyncio
    async def test_add_participant_missing_id(self):
        """Test adding participant without ID."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        result = await coordinator.async_run(operation="add_participant")

        assert result["status"] == "error"
        assert "participant_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_transaction_no_participants(self):
        """Test executing transaction with no participants."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "error"
        assert "No participants defined" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_transaction_success(self):
        """Test successful transaction execution."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            participants=["service1", "service2"]
        )

        # Mock the prepare and commit methods to succeed
        coordinator._execute_prepare_phase = AsyncMock(return_value=True)
        coordinator._execute_commit_phase = AsyncMock(return_value=True)
        coordinator._persist_state = AsyncMock()

        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["state"] == "committed"
        assert coordinator.state == TransactionState.COMMITTED
        assert coordinator.completed_at is not None
        assert coordinator._execute_prepare_phase.called
        assert coordinator._execute_commit_phase.called

    @pytest.mark.asyncio
    async def test_execute_transaction_prepare_failure(self):
        """Test transaction execution with prepare phase failure."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            participants=["service1", "service2"]
        )

        # Mock prepare to fail
        coordinator._execute_prepare_phase = AsyncMock(return_value=False)
        coordinator._abort_all_participants = AsyncMock()
        coordinator._persist_state = AsyncMock()

        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "aborted"
        assert result["state"] == "aborted"
        assert coordinator.state == TransactionState.ABORTED
        assert coordinator._execute_prepare_phase.called
        assert coordinator._abort_all_participants.called

    @pytest.mark.asyncio
    async def test_execute_transaction_commit_failure(self):
        """Test transaction execution with commit phase failure."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            participants=["service1", "service2"]
        )

        # Mock prepare to succeed, commit to fail
        coordinator._execute_prepare_phase = AsyncMock(return_value=True)
        coordinator._execute_commit_phase = AsyncMock(return_value=False)
        coordinator._persist_state = AsyncMock()

        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "failed"
        assert result["state"] == "failed"
        assert coordinator.state == TransactionState.FAILED
        assert "Commit phase failed" in result["error"]

    @pytest.mark.asyncio
    async def test_prepare_phase_execution(self):
        """Test prepare phase execution."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        # Add participants
        participant1 = TwoPhaseCommitParticipant("service1", "http://service1/2pc")
        participant2 = TwoPhaseCommitParticipant("service2", "http://service2/2pc")
        coordinator.participants = {"service1": participant1, "service2": participant2}

        # Mock the send_prepare_request method
        async def mock_prepare(participant):
            participant.vote = ParticipantVote.PREPARED
            participant.prepare_time = datetime.now(UTC)

        coordinator._send_prepare_request = mock_prepare

        result = await coordinator._execute_prepare_phase()

        assert result is True
        assert participant1.vote == ParticipantVote.PREPARED
        assert participant2.vote == ParticipantVote.PREPARED

    @pytest.mark.asyncio
    async def test_prepare_phase_with_abort_vote(self):
        """Test prepare phase with one participant voting abort."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        # Add participants
        participant1 = TwoPhaseCommitParticipant("service1", "http://service1/2pc")
        participant2 = TwoPhaseCommitParticipant("service2", "http://service2/2pc")
        coordinator.participants = {"service1": participant1, "service2": participant2}

        # Mock prepare requests - one votes abort
        async def mock_prepare(participant):
            if participant.participant_id == "service1":
                participant.vote = ParticipantVote.PREPARED
            else:
                participant.vote = ParticipantVote.ABORT
            participant.prepare_time = datetime.now(UTC)

        coordinator._send_prepare_request = mock_prepare

        result = await coordinator._execute_prepare_phase()

        assert result is False
        assert participant1.vote == ParticipantVote.PREPARED
        assert participant2.vote == ParticipantVote.ABORT

    @pytest.mark.asyncio
    async def test_prepare_phase_timeout(self):
        """Test prepare phase timeout."""
        coordinator = TwoPhaseCommitCoordinatorNode(prepare_timeout=0.1)

        # Add a participant
        participant = TwoPhaseCommitParticipant("service1", "http://service1/2pc")
        coordinator.participants = {"service1": participant}

        # Mock slow prepare request
        async def slow_prepare(participant):
            await asyncio.sleep(0.2)  # Longer than timeout
            participant.vote = ParticipantVote.PREPARED

        coordinator._send_prepare_request = slow_prepare

        result = await coordinator._execute_prepare_phase()

        assert result is False

    @pytest.mark.asyncio
    async def test_commit_phase_execution(self):
        """Test commit phase execution."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        # Add participants
        participant1 = TwoPhaseCommitParticipant("service1", "http://service1/2pc")
        participant2 = TwoPhaseCommitParticipant("service2", "http://service2/2pc")
        coordinator.participants = {"service1": participant1, "service2": participant2}

        # Mock commit request
        async def mock_commit(participant):
            participant.commit_time = datetime.now(UTC)

        coordinator._send_commit_request = mock_commit

        result = await coordinator._execute_commit_phase()

        assert result is True
        assert participant1.commit_time is not None
        assert participant2.commit_time is not None

    @pytest.mark.asyncio
    async def test_commit_phase_timeout(self):
        """Test commit phase timeout."""
        coordinator = TwoPhaseCommitCoordinatorNode(commit_timeout=0.1)

        # Add a participant
        participant = TwoPhaseCommitParticipant("service1", "http://service1/2pc")
        coordinator.participants = {"service1": participant}

        # Mock slow commit request
        async def slow_commit(participant):
            await asyncio.sleep(0.2)  # Longer than timeout
            participant.commit_time = datetime.now(UTC)

        coordinator._send_commit_request = slow_commit

        result = await coordinator._execute_commit_phase()

        assert result is False

    @pytest.mark.asyncio
    async def test_abort_transaction(self):
        """Test aborting a transaction."""
        coordinator = TwoPhaseCommitCoordinatorNode()
        coordinator.state = TransactionState.PREPARING
        coordinator._abort_all_participants = AsyncMock()
        coordinator._persist_state = AsyncMock()

        result = await coordinator.async_run(operation="abort_transaction")

        assert result["status"] == "success"
        assert result["state"] == "aborted"
        assert coordinator.state == TransactionState.ABORTED
        assert coordinator.completed_at is not None
        assert coordinator._abort_all_participants.called

    @pytest.mark.asyncio
    async def test_abort_already_finished_transaction(self):
        """Test aborting an already finished transaction."""
        coordinator = TwoPhaseCommitCoordinatorNode()
        coordinator.state = TransactionState.COMMITTED

        result = await coordinator.async_run(operation="abort_transaction")

        assert result["status"] == "already_finished"
        assert result["state"] == "committed"

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test getting transaction status."""
        coordinator = TwoPhaseCommitCoordinatorNode(transaction_name="test_transaction")
        coordinator.started_at = datetime.now(UTC)
        coordinator.context = {"order_id": "123"}

        # Add a participant with vote
        participant = TwoPhaseCommitParticipant("service1", "http://service1/2pc")
        participant.vote = ParticipantVote.PREPARED
        participant.prepare_time = datetime.now(UTC)
        coordinator.participants["service1"] = participant

        result = await coordinator.async_run(operation="get_status")

        assert result["status"] == "success"
        assert result["transaction_name"] == "test_transaction"
        assert result["state"] == "init"
        assert result["context"]["order_id"] == "123"
        assert len(result["participants"]) == 1
        assert result["participants"][0]["participant_id"] == "service1"
        assert result["participants"][0]["vote"] == "prepared"

    @pytest.mark.asyncio
    async def test_unknown_operation(self):
        """Test unknown operation."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        result = await coordinator.async_run(operation="unknown_operation")

        assert result["status"] == "error"
        assert "Unknown 2PC operation" in result["error"]

    @pytest.mark.asyncio
    async def test_state_persistence(self):
        """Test state persistence functionality."""
        # Mock storage
        mock_storage = AsyncMock()
        coordinator = TwoPhaseCommitCoordinatorNode()
        coordinator._storage = mock_storage

        # Test state persistence
        await coordinator._persist_state()

        assert mock_storage.save_state.called
        call_args = mock_storage.save_state.call_args
        assert call_args[0][0] == coordinator.transaction_id  # transaction_id
        assert isinstance(call_args[0][1], dict)  # state_data

    def test_get_state_data(self):
        """Test getting state data for persistence."""
        coordinator = TwoPhaseCommitCoordinatorNode(transaction_name="test_tx")
        coordinator.started_at = datetime.now(UTC)
        coordinator.context = {"test": "data"}

        # Add participant
        participant = TwoPhaseCommitParticipant("service1", "http://service1/2pc")
        coordinator.participants["service1"] = participant

        state_data = coordinator._get_state_data()

        assert state_data["transaction_id"] == coordinator.transaction_id
        assert state_data["transaction_name"] == "test_tx"
        assert state_data["state"] == "init"
        assert state_data["context"]["test"] == "data"
        assert "service1" in state_data["participants"]
        assert state_data["started_at"] is not None

    def test_restore_from_state(self):
        """Test restoring state from persistence data."""
        coordinator = TwoPhaseCommitCoordinatorNode()

        state_data = {
            "transaction_id": "test_tx_123",
            "transaction_name": "restored_transaction",
            "state": "prepared",
            "context": {"order_id": "456"},
            "timeout": 600,
            "started_at": "2024-01-15T10:00:00+00:00",
            "prepared_at": "2024-01-15T10:01:00+00:00",
            "participants": {
                "service1": {
                    "participant_id": "service1",
                    "endpoint": "http://service1/2pc",
                    "timeout": 30,
                    "retry_count": 3,
                    "vote": "prepared",
                }
            },
        }

        coordinator._restore_from_state(state_data)

        assert coordinator.transaction_id == "test_tx_123"
        assert coordinator.transaction_name == "restored_transaction"
        assert coordinator.state == TransactionState.PREPARED
        assert coordinator.context["order_id"] == "456"
        assert coordinator.timeout == 600
        assert coordinator.started_at is not None
        assert coordinator.prepared_at is not None
        assert "service1" in coordinator.participants
        assert coordinator.participants["service1"].vote == ParticipantVote.PREPARED

    @pytest.mark.asyncio
    async def test_mock_prepare_request(self):
        """Test mock prepare request implementation."""
        coordinator = TwoPhaseCommitCoordinatorNode()
        participant = TwoPhaseCommitParticipant("test_service", "http://test/2pc")

        await coordinator._send_prepare_request(participant)

        assert participant.vote == ParticipantVote.PREPARED
        assert participant.prepare_time is not None
        assert participant.last_contact is not None

    @pytest.mark.asyncio
    async def test_mock_commit_request(self):
        """Test mock commit request implementation."""
        coordinator = TwoPhaseCommitCoordinatorNode()
        participant = TwoPhaseCommitParticipant("test_service", "http://test/2pc")

        await coordinator._send_commit_request(participant)

        assert participant.commit_time is not None
        assert participant.last_contact is not None

    @pytest.mark.asyncio
    async def test_mock_abort_request(self):
        """Test mock abort request implementation."""
        coordinator = TwoPhaseCommitCoordinatorNode()
        participant = TwoPhaseCommitParticipant("test_service", "http://test/2pc")

        await coordinator._send_abort_request(participant)

        assert participant.last_contact is not None
