"""Unit tests for Distributed Transaction Manager Node.

Tests the high-level transaction manager that orchestrates different transaction
patterns (Saga, Two-Phase Commit) based on requirements and capabilities.

Following Tier 1 testing policy: Fast execution, mocking allowed.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.transaction.distributed_transaction_manager import (
    AvailabilityLevel,
    ConsistencyLevel,
    DistributedTransactionManagerNode,
    ParticipantCapability,
    TransactionPattern,
    TransactionRequirements,
    TransactionStatus,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestParticipantCapability:
    """Test ParticipantCapability class."""

    def test_capability_creation(self):
        """Test creating a participant capability."""
        capability = ParticipantCapability(
            participant_id="payment_service",
            endpoint="http://payment:8080",
            supports_2pc=True,
            supports_saga=True,
            compensation_action="refund",
            timeout=30,
            retry_count=3,
            priority=1,
        )

        assert capability.participant_id == "payment_service"
        assert capability.endpoint == "http://payment:8080"
        assert capability.supports_2pc is True
        assert capability.supports_saga is True
        assert capability.compensation_action == "refund"
        assert capability.timeout == 30
        assert capability.retry_count == 3
        assert capability.priority == 1

    def test_capability_defaults(self):
        """Test participant capability with default values."""
        capability = ParticipantCapability(
            participant_id="inventory_service", endpoint="http://inventory:8080"
        )

        assert capability.supports_2pc is False
        assert capability.supports_saga is True
        assert capability.compensation_action is None
        assert capability.timeout == 30
        assert capability.retry_count == 3
        assert capability.priority == 1

    def test_capability_serialization(self):
        """Test capability to_dict and from_dict."""
        capability = ParticipantCapability(
            participant_id="audit_service",
            endpoint="http://audit:8080",
            supports_2pc=False,
            compensation_action="log_rollback",
        )

        data = capability.to_dict()

        assert data["participant_id"] == "audit_service"
        assert data["supports_2pc"] is False
        assert data["compensation_action"] == "log_rollback"

        restored = ParticipantCapability.from_dict(data)

        assert restored.participant_id == capability.participant_id
        assert restored.supports_2pc == capability.supports_2pc
        assert restored.compensation_action == capability.compensation_action


class TestTransactionRequirements:
    """Test TransactionRequirements class."""

    def test_requirements_creation(self):
        """Test creating transaction requirements."""
        requirements = TransactionRequirements(
            consistency=ConsistencyLevel.STRONG,
            availability=AvailabilityLevel.MEDIUM,
            timeout=600,
            isolation_level="serializable",
            durability=True,
            allow_partial_failure=False,
        )

        assert requirements.consistency == ConsistencyLevel.STRONG
        assert requirements.availability == AvailabilityLevel.MEDIUM
        assert requirements.timeout == 600
        assert requirements.isolation_level == "serializable"
        assert requirements.durability is True
        assert requirements.allow_partial_failure is False

    def test_requirements_string_conversion(self):
        """Test creating requirements with string values."""
        requirements = TransactionRequirements(
            consistency="immediate", availability="high"
        )

        assert requirements.consistency == ConsistencyLevel.IMMEDIATE
        assert requirements.availability == AvailabilityLevel.HIGH

    def test_requirements_defaults(self):
        """Test requirements with default values."""
        requirements = TransactionRequirements()

        assert requirements.consistency == ConsistencyLevel.EVENTUAL
        assert requirements.availability == AvailabilityLevel.HIGH
        assert requirements.timeout == 300
        assert requirements.isolation_level == "read_committed"
        assert requirements.durability is True
        assert requirements.allow_partial_failure is True


class TestDistributedTransactionManagerNode:
    """Test DistributedTransactionManagerNode."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = DistributedTransactionManagerNode(
            transaction_name="test_transaction",
            default_pattern=TransactionPattern.AUTO,
            default_timeout=600,
            monitoring_enabled=True,
        )

        assert manager.transaction_name == "test_transaction"
        assert manager.default_pattern == TransactionPattern.AUTO
        assert manager.default_timeout == 600
        assert manager.monitoring_enabled is True
        assert manager.status == TransactionStatus.PENDING
        assert len(manager.participants) == 0

    def test_manager_with_defaults(self):
        """Test manager with default values."""
        manager = DistributedTransactionManagerNode()

        assert manager.transaction_name.startswith("dtx_")
        assert manager.default_pattern == TransactionPattern.AUTO
        assert manager.default_timeout == 300
        assert manager.status == TransactionStatus.PENDING
        assert manager.retry_policy["max_attempts"] == 3

    @pytest.mark.asyncio
    async def test_create_transaction(self):
        """Test creating a transaction."""
        manager = DistributedTransactionManagerNode()
        manager._persist_state = AsyncMock()

        result = await manager.async_run(
            operation="create_transaction",
            transaction_name="order_processing",
            requirements={
                "consistency": "strong",
                "availability": "medium",
                "timeout": 600,
            },
            context={"order_id": "123", "customer_id": "456"},
        )

        assert result["status"] == "success"
        assert result["transaction_name"] == "order_processing"
        assert manager.transaction_name == "order_processing"
        assert manager.requirements.consistency == ConsistencyLevel.STRONG
        assert manager.requirements.availability == AvailabilityLevel.MEDIUM
        assert manager.requirements.timeout == 600
        assert manager.context["order_id"] == "123"
        assert manager.created_at is not None
        assert manager._persist_state.called

    @pytest.mark.asyncio
    async def test_create_transaction_already_created(self):
        """Test creating transaction when already created."""
        manager = DistributedTransactionManagerNode()
        manager.status = TransactionStatus.RUNNING

        result = await manager.async_run(operation="create_transaction")

        assert result["status"] == "error"
        assert "already in status" in result["error"]

    @pytest.mark.asyncio
    async def test_add_participant(self):
        """Test adding a participant."""
        manager = DistributedTransactionManagerNode()
        manager._persist_state = AsyncMock()

        result = await manager.async_run(
            operation="add_participant",
            participant_id="payment_service",
            endpoint="http://payment:8080",
            supports_2pc=True,
            supports_saga=True,
            compensation_action="refund",
            timeout=45,
            retry_count=5,
            priority=2,
        )

        assert result["status"] == "success"
        assert result["participant_id"] == "payment_service"
        assert result["total_participants"] == 1

        participant = manager.participants[0]
        assert participant.participant_id == "payment_service"
        assert participant.endpoint == "http://payment:8080"
        assert participant.supports_2pc is True
        assert participant.supports_saga is True
        assert participant.compensation_action == "refund"
        assert participant.timeout == 45
        assert participant.retry_count == 5
        assert participant.priority == 2
        assert manager._persist_state.called

    @pytest.mark.asyncio
    async def test_add_participant_alternative_format(self):
        """Test adding participant with alternative parameter format."""
        manager = DistributedTransactionManagerNode()
        manager._persist_state = AsyncMock()

        participant_data = {
            "participant_id": "inventory_service",
            "endpoint": "http://inventory:8080",
            "supports_2pc": False,
            "compensation_action": "release_stock",
        }

        result = await manager.async_run(
            operation="add_participant", participant=participant_data
        )

        assert result["status"] == "success"
        assert result["participant_id"] == "inventory_service"

        participant = manager.participants[0]
        assert participant.participant_id == "inventory_service"
        assert participant.supports_2pc is False
        assert participant.compensation_action == "release_stock"

    @pytest.mark.asyncio
    async def test_add_participant_already_exists(self):
        """Test adding participant that already exists."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("existing_service", "http://existing:8080")
        ]

        result = await manager.async_run(
            operation="add_participant",
            participant_id="existing_service",
            endpoint="http://existing:8080",
        )

        assert result["status"] == "exists"
        assert result["participant_id"] == "existing_service"

    @pytest.mark.asyncio
    async def test_add_participant_missing_id(self):
        """Test adding participant without ID."""
        manager = DistributedTransactionManagerNode()

        result = await manager.async_run(operation="add_participant")

        assert result["status"] == "error"
        assert "participant_id is required" in result["error"]

    def test_select_optimal_pattern_all_2pc_strong_consistency(self):
        """Test pattern selection: all participants support 2PC, strong consistency."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True),
            ParticipantCapability("service2", "http://s2:8080", supports_2pc=True),
        ]
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.STRONG, availability=AvailabilityLevel.MEDIUM
        )

        pattern = manager._select_optimal_pattern()

        assert pattern == TransactionPattern.TWO_PHASE_COMMIT

    def test_select_optimal_pattern_immediate_consistency(self):
        """Test pattern selection: immediate consistency requires 2PC."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True),
            ParticipantCapability("service2", "http://s2:8080", supports_2pc=True),
        ]
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.IMMEDIATE
        )

        pattern = manager._select_optimal_pattern()

        assert pattern == TransactionPattern.TWO_PHASE_COMMIT

    def test_select_optimal_pattern_immediate_consistency_incompatible(self):
        """Test pattern selection: immediate consistency with incompatible participants."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True),
            ParticipantCapability("service2", "http://s2:8080", supports_2pc=False),
        ]
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.IMMEDIATE
        )

        with pytest.raises(NodeExecutionError) as exc_info:
            manager._select_optimal_pattern()

        assert "Immediate consistency requires all participants to support 2PC" in str(
            exc_info.value
        )

    def test_select_optimal_pattern_high_availability(self):
        """Test pattern selection: high availability prefers Saga."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True),
            ParticipantCapability("service2", "http://s2:8080", supports_2pc=True),
        ]
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.STRONG, availability=AvailabilityLevel.HIGH
        )

        pattern = manager._select_optimal_pattern()

        assert pattern == TransactionPattern.SAGA

    def test_select_optimal_pattern_mixed_support(self):
        """Test pattern selection: mixed 2PC support defaults to Saga."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True),
            ParticipantCapability("service2", "http://s2:8080", supports_2pc=False),
        ]
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.EVENTUAL, availability=AvailabilityLevel.MEDIUM
        )

        pattern = manager._select_optimal_pattern()

        assert pattern == TransactionPattern.SAGA

    def test_select_optimal_pattern_default_saga(self):
        """Test pattern selection: default to Saga for flexibility."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True)
        ]
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.EVENTUAL, availability=AvailabilityLevel.MEDIUM
        )

        pattern = manager._select_optimal_pattern()

        assert pattern == TransactionPattern.SAGA

    def test_validate_pattern_compatibility_2pc_success(self):
        """Test pattern validation: 2PC with compatible participants."""
        manager = DistributedTransactionManagerNode()
        manager.selected_pattern = TransactionPattern.TWO_PHASE_COMMIT
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True),
            ParticipantCapability("service2", "http://s2:8080", supports_2pc=True),
        ]

        # Should not raise exception
        manager._validate_pattern_compatibility()

    def test_validate_pattern_compatibility_2pc_failure(self):
        """Test pattern validation: 2PC with incompatible participants."""
        manager = DistributedTransactionManagerNode()
        manager.selected_pattern = TransactionPattern.TWO_PHASE_COMMIT
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True),
            ParticipantCapability("service2", "http://s2:8080", supports_2pc=False),
        ]

        with pytest.raises(NodeExecutionError) as exc_info:
            manager._validate_pattern_compatibility()

        assert "do not support 2PC" in str(exc_info.value)

    def test_validate_pattern_compatibility_saga_success(self):
        """Test pattern validation: Saga with compatible participants."""
        manager = DistributedTransactionManagerNode()
        manager.selected_pattern = TransactionPattern.SAGA
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_saga=True),
            ParticipantCapability("service2", "http://s2:8080", supports_saga=True),
        ]

        # Should not raise exception
        manager._validate_pattern_compatibility()

    def test_validate_pattern_compatibility_saga_failure(self):
        """Test pattern validation: Saga with incompatible participants."""
        manager = DistributedTransactionManagerNode()
        manager.selected_pattern = TransactionPattern.SAGA
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_saga=True),
            ParticipantCapability("service2", "http://s2:8080", supports_saga=False),
        ]

        with pytest.raises(NodeExecutionError) as exc_info:
            manager._validate_pattern_compatibility()

        assert "do not support Saga" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_transaction_no_participants(self):
        """Test executing transaction with no participants."""
        manager = DistributedTransactionManagerNode()

        result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "error"
        assert "No participants defined" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_transaction_saga_pattern(self):
        """Test executing transaction with Saga pattern."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_saga=True)
        ]
        manager.requirements = TransactionRequirements()
        manager._persist_state = AsyncMock()

        # Mock saga execution
        mock_saga_result = {
            "status": "success",
            "state": "committed",
            "steps_completed": 1,
        }

        with patch.object(
            manager, "_execute_saga_pattern", return_value=mock_saga_result
        ):
            result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["selected_pattern"] == "saga"
        assert manager.status == TransactionStatus.COMMITTED
        assert manager.selected_pattern == TransactionPattern.SAGA
        assert manager.started_at is not None
        assert manager.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_transaction_2pc_pattern(self):
        """Test executing transaction with 2PC pattern."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_2pc=True)
        ]
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.IMMEDIATE
        )
        manager._persist_state = AsyncMock()

        # Mock 2PC execution
        mock_2pc_result = {
            "status": "success",
            "state": "committed",
            "participants_committed": 1,
        }

        with patch.object(
            manager, "_execute_2pc_pattern", return_value=mock_2pc_result
        ):
            result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["selected_pattern"] == "two_phase_commit"
        assert manager.status == TransactionStatus.COMMITTED
        assert manager.selected_pattern == TransactionPattern.TWO_PHASE_COMMIT

    @pytest.mark.asyncio
    async def test_execute_transaction_explicit_pattern(self):
        """Test executing transaction with explicit pattern selection."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [
            ParticipantCapability(
                "service1", "http://s1:8080", supports_2pc=True, supports_saga=True
            )
        ]
        manager._persist_state = AsyncMock()

        # Mock 2PC execution
        mock_2pc_result = {"status": "success", "state": "committed"}

        with patch.object(
            manager, "_execute_2pc_pattern", return_value=mock_2pc_result
        ):
            result = await manager.async_run(
                operation="execute_transaction", pattern="two_phase_commit"
            )

        assert result["status"] == "success"
        assert result["selected_pattern"] == "two_phase_commit"
        assert manager.selected_pattern == TransactionPattern.TWO_PHASE_COMMIT

    @pytest.mark.asyncio
    async def test_execute_transaction_failure(self):
        """Test executing transaction with failure."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [ParticipantCapability("service1", "http://s1:8080")]
        manager.requirements = TransactionRequirements()  # Add requirements
        manager._persist_state = AsyncMock()

        # Mock saga execution failure
        mock_saga_result = {"status": "failed", "error": "Service unavailable"}

        with patch.object(
            manager, "_execute_saga_pattern", return_value=mock_saga_result
        ):
            result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "failed"
        assert manager.status == TransactionStatus.FAILED
        assert manager.error_message == "Service unavailable"
        assert manager.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_transaction_abort(self):
        """Test executing transaction that gets aborted."""
        manager = DistributedTransactionManagerNode()
        manager.participants = [ParticipantCapability("service1", "http://s1:8080")]
        manager.requirements = TransactionRequirements()  # Add requirements
        manager._persist_state = AsyncMock()

        # Mock saga execution abort
        mock_saga_result = {"status": "aborted", "reason": "Participant failure"}

        with patch.object(
            manager, "_execute_saga_pattern", return_value=mock_saga_result
        ):
            result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "aborted"
        assert manager.status == TransactionStatus.ABORTED

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test getting transaction status."""
        manager = DistributedTransactionManagerNode()
        manager.transaction_name = "test_transaction"
        manager.status = TransactionStatus.RUNNING
        manager.selected_pattern = TransactionPattern.SAGA
        manager.created_at = datetime.now(UTC)
        manager.context = {"order_id": "123"}

        # Add participants
        manager.participants = [
            ParticipantCapability("service1", "http://s1:8080", supports_saga=True)
        ]

        # Add requirements
        manager.requirements = TransactionRequirements(
            consistency=ConsistencyLevel.EVENTUAL, availability=AvailabilityLevel.HIGH
        )

        # Mock active coordinator
        mock_coordinator = AsyncMock()
        mock_coordinator.async_run.return_value = {
            "status": "success",
            "state": "running",
        }
        manager._active_coordinator = mock_coordinator

        result = await manager.async_run(operation="get_status")

        assert result["status"] == "success"
        assert result["transaction_name"] == "test_transaction"
        assert result["transaction_status"] == "running"
        assert result["selected_pattern"] == "saga"
        assert len(result["participants"]) == 1
        assert result["context"]["order_id"] == "123"
        assert result["requirements"]["consistency"] == "eventual"
        assert result["requirements"]["availability"] == "high"
        assert "coordinator_status" in result

    @pytest.mark.asyncio
    async def test_abort_transaction(self):
        """Test aborting a transaction."""
        manager = DistributedTransactionManagerNode()
        manager.status = TransactionStatus.RUNNING
        manager._persist_state = AsyncMock()

        # Mock active coordinator
        mock_coordinator = AsyncMock()
        manager._active_coordinator = mock_coordinator

        result = await manager.async_run(operation="abort_transaction")

        assert result["status"] == "success"
        assert result["transaction_status"] == "aborted"
        assert manager.status == TransactionStatus.ABORTED
        assert manager.completed_at is not None
        assert mock_coordinator.async_run.called
        assert manager._persist_state.called

    @pytest.mark.asyncio
    async def test_abort_already_finished_transaction(self):
        """Test aborting an already finished transaction."""
        manager = DistributedTransactionManagerNode()
        manager.status = TransactionStatus.COMMITTED

        result = await manager.async_run(operation="abort_transaction")

        assert result["status"] == "already_finished"
        assert result["transaction_status"] == "committed"

    @pytest.mark.asyncio
    async def test_unknown_operation(self):
        """Test unknown operation."""
        manager = DistributedTransactionManagerNode()

        result = await manager.async_run(operation="unknown_operation")

        assert result["status"] == "error"
        assert "Unknown transaction manager operation" in result["error"]

    def test_get_state_data(self):
        """Test getting state data for persistence."""
        manager = DistributedTransactionManagerNode()
        manager.transaction_name = "test_tx"
        manager.status = TransactionStatus.RUNNING
        manager.selected_pattern = TransactionPattern.SAGA
        manager.created_at = datetime.now(UTC)

        # Add participant
        manager.participants = [ParticipantCapability("service1", "http://s1:8080")]

        # Add requirements
        manager.requirements = TransactionRequirements()
        manager.context = {"test": "data"}

        state_data = manager._get_state_data()

        assert state_data["transaction_name"] == "test_tx"
        assert state_data["status"] == "running"
        assert state_data["selected_pattern"] == "saga"
        assert len(state_data["participants"]) == 1
        assert state_data["context"]["test"] == "data"
        assert state_data["requirements"]["consistency"] == "eventual"
        assert state_data["created_at"] is not None

    def test_restore_from_state(self):
        """Test restoring state from persistence data."""
        manager = DistributedTransactionManagerNode()

        state_data = {
            "transaction_id": "test_tx_123",
            "transaction_name": "restored_transaction",
            "status": "committed",
            "selected_pattern": "saga",
            "participants": [
                {
                    "participant_id": "service1",
                    "endpoint": "http://s1:8080",
                    "supports_2pc": False,
                    "supports_saga": True,
                    "compensation_action": "rollback",
                    "timeout": 30,
                    "retry_count": 3,
                    "priority": 1,
                }
            ],
            "requirements": {
                "consistency": "strong",
                "availability": "medium",
                "timeout": 600,
                "isolation_level": "read_committed",
                "durability": True,
                "allow_partial_failure": False,
            },
            "context": {"order_id": "456"},
            "default_timeout": 300,
            "created_at": "2024-01-15T10:00:00+00:00",
            "started_at": "2024-01-15T10:01:00+00:00",
            "completed_at": "2024-01-15T10:05:00+00:00",
        }

        manager._restore_from_state(state_data)

        assert manager.transaction_id == "test_tx_123"
        assert manager.transaction_name == "restored_transaction"
        assert manager.status == TransactionStatus.COMMITTED
        assert manager.selected_pattern == TransactionPattern.SAGA
        assert len(manager.participants) == 1
        assert manager.participants[0].participant_id == "service1"
        assert manager.participants[0].compensation_action == "rollback"
        assert manager.requirements.consistency == ConsistencyLevel.STRONG
        assert manager.requirements.availability == AvailabilityLevel.MEDIUM
        assert manager.requirements.timeout == 600
        assert manager.context["order_id"] == "456"
        assert manager.default_timeout == 300
        assert manager.created_at is not None
        assert manager.started_at is not None
        assert manager.completed_at is not None
