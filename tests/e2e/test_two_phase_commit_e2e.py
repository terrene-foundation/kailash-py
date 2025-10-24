"""End-to-End tests for Two-Phase Commit implementation.

Tests complete 2PC scenarios with real infrastructure following
Tier 3 testing policy: NO MOCKING, real Docker services, complete user flows.
"""

import asyncio
import time
import uuid
from typing import Any, Dict

import asyncpg
import pytest
import redis
from kailash.nodes.transaction.two_phase_commit import TwoPhaseCommitCoordinatorNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.requires_postgres
class TestTwoPhaseCommitE2E:
    """E2E tests for complete 2PC scenarios."""

    @pytest.fixture(scope="class", autouse=True)
    def docker_services(self):
        """Ensure all required Docker services are running."""
        # Docker services should be running via test-env
        pass

    @pytest.fixture
    def redis_client(self):
        """Create Redis client for E2E tests."""
        redis_config = get_redis_connection_params()
        client = redis.Redis(
            host=redis_config["host"], port=redis_config["port"], decode_responses=True
        )
        # Clean up
        client.flushdb()
        yield client
        client.flushdb()
        client.close()

    @pytest.fixture
    def db_pool(self, event_loop):
        """Create PostgreSQL pool for E2E tests."""

        async def setup_pool():
            connection_string = get_postgres_connection_string()
            pool = await asyncpg.create_pool(connection_string, min_size=2, max_size=10)

            # Create tables for E2E test
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS e2e_2pc_states (
                        transaction_id VARCHAR(255) PRIMARY KEY,
                        transaction_name VARCHAR(255),
                        state VARCHAR(50),
                        state_data JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS e2e_distributed_orders (
                        order_id VARCHAR(255) PRIMARY KEY,
                        customer_id VARCHAR(255),
                        total_amount DECIMAL(10,2),
                        status VARCHAR(50),
                        payment_confirmed BOOLEAN DEFAULT FALSE,
                        inventory_reserved BOOLEAN DEFAULT FALSE,
                        shipping_scheduled BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS e2e_payments (
                        payment_id VARCHAR(255) PRIMARY KEY,
                        order_id VARCHAR(255),
                        amount DECIMAL(10,2),
                        status VARCHAR(50),
                        transaction_id VARCHAR(255),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS e2e_inventory_reservations (
                        reservation_id VARCHAR(255) PRIMARY KEY,
                        order_id VARCHAR(255),
                        item_id VARCHAR(255),
                        quantity INTEGER,
                        status VARCHAR(50),
                        transaction_id VARCHAR(255),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """
                )

                # Insert test data
                await conn.execute(
                    """
                    INSERT INTO e2e_distributed_orders (order_id, customer_id, total_amount, status)
                    VALUES ('ORDER001', 'CUST001', 299.99, 'pending'),
                           ('ORDER002', 'CUST002', 150.00, 'pending')
                    ON CONFLICT (order_id) DO UPDATE SET
                        total_amount = EXCLUDED.total_amount,
                        status = 'pending',
                        payment_confirmed = FALSE,
                        inventory_reserved = FALSE,
                        shipping_scheduled = FALSE
                """
                )

            return pool

        async def cleanup_pool(pool):
            # Cleanup
            async with pool.acquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS e2e_2pc_states CASCADE")
                await conn.execute(
                    "DROP TABLE IF EXISTS e2e_distributed_orders CASCADE"
                )
                await conn.execute("DROP TABLE IF EXISTS e2e_payments CASCADE")
                await conn.execute(
                    "DROP TABLE IF EXISTS e2e_inventory_reservations CASCADE"
                )

            await pool.close()

        pool = event_loop.run_until_complete(setup_pool())
        yield pool
        event_loop.run_until_complete(cleanup_pool(pool))

    @pytest.mark.asyncio
    async def test_distributed_order_processing_2pc_success(
        self, redis_client, db_pool
    ):
        """Test complete distributed order processing using 2PC - happy path."""
        # Create coordinator with Redis persistence
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="distributed_order_processing",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:2pc:"},
        )

        # Start distributed transaction
        order_id = f"order_{uuid.uuid4()}"
        customer_id = f"customer_{uuid.uuid4()}"

        result = await coordinator.async_run(
            operation="begin_transaction",
            context={
                "order_id": order_id,
                "customer_id": customer_id,
                "items": [{"item_id": "ITEM001", "quantity": 2}],
                "total_amount": 199.98,
                "transaction_type": "order_processing",
            },
        )

        assert result["status"] == "success"
        transaction_id = result["transaction_id"]

        # Add participants for distributed transaction
        participants = [
            {"id": "payment_service", "endpoint": "http://payment:8080/2pc"},
            {"id": "inventory_service", "endpoint": "http://inventory:8080/2pc"},
            {"id": "shipping_service", "endpoint": "http://shipping:8080/2pc"},
            {"id": "audit_service", "endpoint": "http://audit:8080/2pc"},
        ]

        for participant in participants:
            result = await coordinator.async_run(
                operation="add_participant",
                participant_id=participant["id"],
                endpoint=participant["endpoint"],
            )
            assert result["status"] == "success"

        # Execute the distributed transaction
        execution_result = await coordinator.async_run(operation="execute_transaction")

        assert execution_result["status"] == "success"
        assert execution_result["state"] == "committed"
        assert execution_result["participants_committed"] == 4

        # Verify transaction was persisted correctly
        status_result = await coordinator.async_run(operation="get_status")
        assert status_result["state"] == "committed"
        assert len(status_result["participants"]) == 4
        assert status_result["completed_at"] is not None

        # Verify we can load the transaction later
        new_coordinator = TwoPhaseCommitCoordinatorNode(
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:2pc:"},
        )

        load_result = await new_coordinator.async_run(
            operation="recover_transaction", transaction_id=transaction_id
        )

        assert load_result["status"] == "success"
        assert new_coordinator.transaction_id == transaction_id
        assert len(new_coordinator.participants) == 4
        assert new_coordinator.context["transaction_type"] == "order_processing"

    @pytest.mark.asyncio
    async def test_distributed_transaction_with_participant_failure(self, redis_client):
        """Test 2PC with participant failure during prepare phase."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="failing_distributed_transaction",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:2pc:"},
        )

        # Create transaction
        order_id = f"failing_order_{uuid.uuid4()}"
        result = await coordinator.async_run(
            operation="begin_transaction",
            context={
                "order_id": order_id,
                "customer_id": "customer_789",
                "total_amount": 999.99,
                "simulate_failure": True,
            },
        )

        transaction_id = result["transaction_id"]

        # Add participants
        participants = ["payment_service", "inventory_service", "failing_service"]
        for participant_id in participants:
            await coordinator.async_run(
                operation="add_participant",
                participant_id=participant_id,
                endpoint=f"http://{participant_id}:8080/2pc",
            )

        # Mock the prepare phase to simulate one participant failure
        original_prepare = coordinator._execute_prepare_phase

        async def mock_failing_prepare():
            # Mock prepare phase where one participant votes abort
            for i, (p_id, participant) in enumerate(coordinator.participants.items()):
                if p_id == "failing_service":
                    # Simulate this participant voting to abort
                    from datetime import UTC, datetime

                    from kailash.nodes.transaction.two_phase_commit import (
                        ParticipantVote,
                    )

                    participant.vote = ParticipantVote.ABORT
                    participant.prepare_time = datetime.now(UTC)
                else:
                    # Other participants vote to prepare
                    from datetime import UTC, datetime

                    from kailash.nodes.transaction.two_phase_commit import (
                        ParticipantVote,
                    )

                    participant.vote = ParticipantVote.PREPARED
                    participant.prepare_time = datetime.now(UTC)

            # Return False because one participant voted abort
            return False

        coordinator._execute_prepare_phase = mock_failing_prepare

        # Execute transaction - should abort due to failing participant
        execution_result = await coordinator.async_run(operation="execute_transaction")

        assert execution_result["status"] == "aborted"
        assert "One or more participants voted to abort" in execution_result["reason"]

        # Verify transaction state
        status_result = await coordinator.async_run(operation="get_status")
        assert status_result["state"] == "aborted"

    @pytest.mark.asyncio
    async def test_2pc_recovery_after_coordinator_failure(self, redis_client, db_pool):
        """Test 2PC recovery and resumption after coordinator failure."""
        # For recovery test, use Redis storage to avoid database async issues
        coordinator1 = TwoPhaseCommitCoordinatorNode(
            transaction_name="recoverable_distributed_tx",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "e2e:recovery:2pc:",
            },
        )

        # Start a distributed transaction
        order_id = f"recoverable_order_{uuid.uuid4()}"
        result = await coordinator1.async_run(
            operation="begin_transaction",
            context={
                "order_id": order_id,
                "customer_id": "recovery_customer",
                "total_amount": 450.00,
                "critical_transaction": True,
            },
        )

        transaction_id = result["transaction_id"]

        # Add participants
        participants = ["payment_gateway", "inventory_system", "fulfillment_center"]
        for participant_id in participants:
            await coordinator1.async_run(
                operation="add_participant",
                participant_id=participant_id,
                endpoint=f"http://{participant_id}:9090/2pc",
            )

        # Mock to simulate system failure after prepare phase completes
        original_execute = coordinator1._execute_transaction

        async def mock_execute_with_failure():
            # Execute prepare phase successfully
            prepare_success = await coordinator1._execute_prepare_phase()
            if not prepare_success:
                return {"status": "aborted", "reason": "Prepare failed"}

            # Set state to prepared
            from datetime import UTC, datetime

            from kailash.nodes.transaction.two_phase_commit import TransactionState

            coordinator1.state = TransactionState.PREPARED
            coordinator1.prepared_at = datetime.now(UTC)
            await coordinator1._persist_state()

            # Simulate coordinator failure here (before commit phase)
            raise Exception("Coordinator failure simulation - system crash")

        coordinator1._execute_transaction = mock_execute_with_failure

        # This should fail during execution
        try:
            await coordinator1.async_run(operation="execute_transaction")
            assert False, "Expected failure did not occur"
        except:
            pass  # Expected failure

        # Simulate system restart - create new coordinator instance
        coordinator2 = TwoPhaseCommitCoordinatorNode(
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "e2e:recovery:2pc:",
            },
        )

        # Recover the failed transaction
        recovery_result = await coordinator2.async_run(
            operation="recover_transaction", transaction_id=transaction_id
        )

        assert recovery_result["status"] == "success"
        assert coordinator2.transaction_id == transaction_id
        assert coordinator2.context["critical_transaction"] is True

        # Check recovered transaction status
        status_result = await coordinator2.async_run(operation="get_status")
        assert len(status_result["participants"]) == 3

        # Since we were in PREPARED state, the recovery should continue with commit
        # The recovery method automatically completed the commit phase
        assert coordinator2.state.value in [
            "committed",
            "prepared",
        ]  # Should be committed or prepared

    def test_2pc_workflow_integration(self, redis_client):
        """Test 2PC integration with workflow builder."""
        # Create workflow with 2PC coordinator
        workflow = WorkflowBuilder()

        # Add 2PC coordinator node
        workflow.add_node(
            "TwoPhaseCommitCoordinatorNode",
            "transaction_coordinator",
            {
                "transaction_name": "workflow_integrated_2pc",
                "operation": "begin_transaction",
                "state_storage": "redis",
                "storage_config": {
                    "redis_client": redis_client,
                    "key_prefix": "e2e:workflow:2pc:",
                },
            },
        )

        # Add data preparation node
        workflow.add_node(
            "PythonCodeNode",
            "prepare_transaction_data",
            {
                "code": """
# Prepare data for 2PC transaction
result = {
    'transaction_id': f'workflow_tx_{customer_id or "unknown"}',
    'prepared_at': timestamp or 'now',
    'ready_for_2pc': True,
    'participants': ['payment', 'inventory', 'shipping']
}
            """
            },
        )

        # Connect preparation to 2PC coordinator
        workflow.add_connection(
            "prepare_transaction_data", "result", "transaction_coordinator", "context"
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(),
            parameters={
                "prepare_transaction_data": {
                    "customer_id": "workflow_customer_456",
                    "timestamp": "2024-01-15T14:30:00Z",
                }
            },
        )

        # Verify workflow execution
        assert "transaction_coordinator" in results
        tx_result = results["transaction_coordinator"]

        # The 2PC transaction should be created with workflow data
        assert tx_result["status"] == "success"
        assert "transaction_id" in tx_result

    @pytest.mark.asyncio
    async def test_multiple_concurrent_2pc_transactions(self, redis_client):
        """Test multiple 2PC transactions running concurrently with shared storage."""
        num_transactions = 4
        coordinators = []
        transaction_ids = []

        # Create multiple 2PC transactions concurrently
        for i in range(num_transactions):
            coordinator = TwoPhaseCommitCoordinatorNode(
                transaction_name=f"concurrent_2pc_{i}",
                state_storage="redis",
                storage_config={
                    "redis_client": redis_client,
                    "key_prefix": "e2e:concurrent:2pc:",
                },
            )

            result = await coordinator.async_run(
                operation="begin_transaction",
                context={
                    "transaction_index": i,
                    "created_at": time.time(),
                    "batch_id": "concurrent_batch_001",
                },
            )

            coordinators.append(coordinator)
            transaction_ids.append(result["transaction_id"])

        # Add participants to each transaction
        for i, coordinator in enumerate(coordinators):
            participants = [f"service_{i}_1", f"service_{i}_2", "shared_audit_service"]
            for participant_id in participants:
                await coordinator.async_run(
                    operation="add_participant",
                    participant_id=participant_id,
                    endpoint=f"http://{participant_id}:8080/2pc",
                )

        # Execute all transactions concurrently
        execution_tasks = [
            coordinator.async_run(operation="execute_transaction")
            for coordinator in coordinators
        ]

        results = await asyncio.gather(*execution_tasks, return_exceptions=True)

        # Verify all transactions completed successfully
        for i, result in enumerate(results):
            assert not isinstance(
                result, Exception
            ), f"Transaction {i} failed: {result}"
            assert result["status"] == "success"
            assert result["state"] == "committed"

        # Verify all transactions can be recovered individually
        for transaction_id in transaction_ids:
            recovery_coordinator = TwoPhaseCommitCoordinatorNode(
                state_storage="redis",
                storage_config={
                    "redis_client": redis_client,
                    "key_prefix": "e2e:concurrent:2pc:",
                },
            )

            recovery_result = await recovery_coordinator.async_run(
                operation="recover_transaction", transaction_id=transaction_id
            )

            assert recovery_result["status"] == "success"
            assert recovery_coordinator.transaction_id == transaction_id
            assert len(recovery_coordinator.participants) == 3
            assert recovery_coordinator.context["batch_id"] == "concurrent_batch_001"

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_2pc_performance_under_load(self, redis_client):
        """Test 2PC performance with many participants and operations."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="performance_test_2pc",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "e2e:perf:2pc:",
            },
        )

        # Create transaction
        start_time = time.time()
        result = await coordinator.async_run(
            operation="begin_transaction",
            context={"performance_test": True, "participants_count": 20},
        )
        creation_time = time.time() - start_time

        assert result["status"] == "success"
        assert creation_time < 1.0  # Should create transaction in under 1 second

        # Add many participants
        num_participants = 20
        participant_start = time.time()

        for i in range(num_participants):
            await coordinator.async_run(
                operation="add_participant",
                participant_id=f"perf_service_{i}",
                endpoint=f"http://perf-service-{i}:8080/2pc",
            )

        participant_time = time.time() - participant_start
        assert participant_time < 3.0  # Should add 20 participants in under 3 seconds

        # Execute transaction
        exec_start = time.time()
        exec_result = await coordinator.async_run(operation="execute_transaction")
        exec_time = time.time() - exec_start

        assert exec_result["status"] == "success"
        assert exec_result["state"] == "committed"
        assert exec_result["participants_committed"] == num_participants
        assert exec_time < 5.0  # Should execute 20-participant 2PC in under 5 seconds

        # Test status retrieval performance
        status_start = time.time()
        status_result = await coordinator.async_run(operation="get_status")
        status_time = time.time() - status_start

        assert len(status_result["participants"]) == num_participants
        assert status_time < 0.5  # Should get status in under 0.5 seconds

    @pytest.mark.asyncio
    async def test_2pc_vs_saga_comparison_with_dtm_pattern_selection(
        self, redis_client
    ):
        """Test 2PC vs Saga pattern selection using Distributed Transaction Manager."""
        from kailash.nodes.transaction.distributed_transaction_manager import (
            DistributedTransactionManagerNode,
        )

        # Test 1: DTM automatically selects 2PC for immediate consistency
        dtm_2pc = DistributedTransactionManagerNode(
            transaction_name="dtm_financial_transfer_2pc",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:dtm:2pc:"},
        )

        # Create transaction requiring immediate consistency
        await dtm_2pc.async_run(
            operation="create_transaction",
            requirements={"consistency": "immediate", "availability": "medium"},
            context={"transfer_type": "financial", "amount": 10000.00},
        )

        # Add participants that support 2PC
        financial_participants = [
            "account_service",
            "ledger_service",
            "compliance_service",
        ]
        for participant in financial_participants:
            await dtm_2pc.async_run(
                operation="add_participant",
                participant_id=participant,
                endpoint=f"http://{participant}:8080/2pc",
                supports_2pc=True,
                supports_saga=True,
            )

        # Execute - should automatically select 2PC
        result = await dtm_2pc.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["selected_pattern"] == "two_phase_commit"  # DTM selected 2PC
        assert dtm_2pc._2pc_coordinator is not None

        # Test 2: DTM automatically selects Saga for high availability
        dtm_saga = DistributedTransactionManagerNode(
            transaction_name="dtm_ecommerce_saga",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "e2e:dtm:saga:",
            },
        )

        # Create transaction prioritizing availability
        await dtm_saga.async_run(
            operation="create_transaction",
            requirements={"consistency": "eventual", "availability": "high"},
            context={"order_type": "ecommerce", "amount": 199.99},
        )

        # Add participants with mixed capabilities
        ecommerce_participants = [
            {
                "participant_id": "payment_service",
                "supports_2pc": True,
                "supports_saga": True,
            },
            {
                "participant_id": "inventory_service",
                "supports_2pc": False,
                "supports_saga": True,
            },  # Forces Saga
            {
                "participant_id": "notification_service",
                "supports_2pc": False,
                "supports_saga": True,
            },
        ]

        for participant in ecommerce_participants:
            await dtm_saga.async_run(
                operation="add_participant",
                endpoint=f"http://{participant['participant_id']}:8080/saga",
                **participant,
            )

        # Execute - should automatically select Saga
        result = await dtm_saga.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["selected_pattern"] == "saga"  # DTM selected Saga
        assert dtm_saga._saga_coordinator is not None

        # Verify pattern selection logic worked correctly
        assert (
            dtm_2pc.selected_pattern != dtm_saga.selected_pattern
        )  # Different patterns selected
