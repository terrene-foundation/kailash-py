"""Integration tests for Distributed Transaction Manager Node.

Tests DTM's unique functionality: storage integration, pattern selection, and coordinator management.
Focuses on component interactions, not business scenarios (covered in saga/2PC integration tests).

Following Tier 2 testing policy: NO MOCKING, real Docker services.
"""

import asyncio
import uuid
from typing import Any, Dict

import asyncpg
import pytest
import pytest_asyncio
import redis
from kailash.nodes.transaction.distributed_transaction_manager import (
    AvailabilityLevel,
    ConsistencyLevel,
    DistributedTransactionManagerNode,
    ParticipantCapability,
    TransactionPattern,
    TransactionRequirements,
    TransactionStatus,
)

from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.requires_postgres
class TestDistributedTransactionManagerIntegration:
    """Integration tests for Distributed Transaction Manager with real infrastructure."""

    @pytest.fixture(scope="class", autouse=True)
    def docker_services(self):
        """Ensure Docker services are running."""
        # Docker services should be started via test environment
        pass

    @pytest.fixture
    def redis_client(self):
        """Create Redis client for integration tests."""
        redis_config = get_redis_connection_params()
        client = redis.Redis(
            host=redis_config["host"], port=redis_config["port"], decode_responses=True
        )
        # Clean up
        client.flushdb()
        yield client
        client.flushdb()
        client.close()

    @pytest_asyncio.fixture
    async def db_pool(self):
        """Create PostgreSQL pool for integration tests."""
        connection_string = get_postgres_connection_string()
        pool = await asyncpg.create_pool(connection_string, min_size=2, max_size=10)

        # Create tables for integration test
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_dtx_states (
                    transaction_id VARCHAR(255) PRIMARY KEY,
                    transaction_name VARCHAR(255),
                    status VARCHAR(50),
                    state_data JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS integration_saga_states (
                    saga_id VARCHAR(255) PRIMARY KEY,
                    saga_name VARCHAR(255),
                    state VARCHAR(50),
                    state_data JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS integration_2pc_states (
                    transaction_id VARCHAR(255) PRIMARY KEY,
                    transaction_name VARCHAR(255),
                    state VARCHAR(50),
                    state_data JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """
            )

        yield pool

        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS integration_dtx_states CASCADE")
            await conn.execute("DROP TABLE IF EXISTS integration_saga_states CASCADE")
            await conn.execute("DROP TABLE IF EXISTS integration_2pc_states CASCADE")

        await pool.close()

    @pytest.mark.asyncio
    async def test_manager_with_redis_storage(self, redis_client):
        """Test manager operations with Redis storage backend."""
        manager = DistributedTransactionManagerNode(
            transaction_name="redis_integration_test",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "integration:dtx:",
            },
        )

        # Create transaction
        result = await manager.async_run(
            operation="create_transaction",
            transaction_name="redis_distributed_tx",
            requirements={
                "consistency": "strong",
                "availability": "medium",
                "timeout": 600,
            },
            context={"test_type": "redis_integration", "batch_id": "batch_001"},
        )

        assert result["status"] == "success"
        transaction_id = result["transaction_id"]

        # Add participants
        participants = [
            {
                "participant_id": "redis_payment_service",
                "endpoint": "http://payment:8080/api",
                "supports_2pc": True,
                "supports_saga": True,
                "compensation_action": "refund_payment",
            },
            {
                "participant_id": "redis_inventory_service",
                "endpoint": "http://inventory:8080/api",
                "supports_2pc": True,
                "supports_saga": True,
                "compensation_action": "release_inventory",
            },
        ]

        for participant in participants:
            result = await manager.async_run(operation="add_participant", **participant)
            assert result["status"] == "success"

        # Verify state is persisted in Redis
        redis_key = f"integration:dtx:{transaction_id}"
        stored_data = redis_client.get(redis_key)
        assert stored_data is not None

        # Execute transaction with pattern selection
        result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert (
            result["selected_pattern"] == "two_phase_commit"
        )  # Strong consistency + 2PC support
        assert manager.status == TransactionStatus.COMMITTED

        # Verify final state in Redis
        final_data = redis_client.get(redis_key)
        assert final_data is not None

        # Test recovery from Redis
        new_manager = DistributedTransactionManagerNode(
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "integration:dtx:",
            },
        )

        recovery_result = await new_manager.async_run(
            operation="recover_transaction", transaction_id=transaction_id
        )

        assert recovery_result["status"] == "success"
        assert new_manager.transaction_id == transaction_id
        assert new_manager.transaction_name == "redis_distributed_tx"
        assert len(new_manager.participants) == 2
        assert new_manager.context["test_type"] == "redis_integration"

    @pytest.mark.asyncio
    async def test_manager_with_database_storage(self, db_pool):
        """Test manager operations with database storage backend."""
        manager = DistributedTransactionManagerNode(
            transaction_name="database_integration_test",
            state_storage="database",
            storage_config={
                "db_pool": db_pool,
                "table_name": "integration_dtx_states",
                "saga_table_name": "integration_saga_states",
                "twophase_table_name": "integration_2pc_states",
            },
        )

        # Create transaction
        result = await manager.async_run(
            operation="create_transaction",
            transaction_name="database_distributed_tx",
            requirements={
                "consistency": "strong",  # Force 2PC pattern
                "availability": "medium",
                "timeout": 300,
            },
            context={"test_type": "database_integration", "order_id": "order_123"},
        )

        assert result["status"] == "success"
        transaction_id = result["transaction_id"]

        # Add participants with 2PC capabilities (for testing database storage)
        participants = [
            {
                "participant_id": "db_payment_service",
                "endpoint": "http://payment:8080/api",
                "supports_2pc": True,  # Test with 2PC pattern
                "supports_saga": True,
                "compensation_action": "cancel_payment",
            },
            {
                "participant_id": "db_shipping_service",
                "endpoint": "http://shipping:8080/api",
                "supports_2pc": True,
                "supports_saga": True,
                "compensation_action": "cancel_shipment",
            },
        ]

        for participant in participants:
            result = await manager.async_run(operation="add_participant", **participant)
            assert result["status"] == "success"

        # Verify state is persisted in database
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state_data FROM integration_dtx_states WHERE transaction_id = $1",
                transaction_id,
            )
            assert row is not None
            assert "db_payment_service" in str(row["state_data"])

        # Execute transaction
        result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert (
            result["selected_pattern"] == "two_phase_commit"
        )  # Strong consistency + 2PC support
        assert manager.status == TransactionStatus.COMMITTED

        # Test database recovery
        new_manager = DistributedTransactionManagerNode(
            state_storage="database",
            storage_config={
                "db_pool": db_pool,
                "table_name": "integration_dtx_states",
                "saga_table_name": "integration_saga_states",
                "twophase_table_name": "integration_2pc_states",
            },
        )

        recovery_result = await new_manager.async_run(
            operation="recover_transaction", transaction_id=transaction_id
        )

        assert recovery_result["status"] == "success"
        assert new_manager.transaction_id == transaction_id
        assert len(new_manager.participants) == 2
        assert new_manager.context["order_id"] == "order_123"

    @pytest.mark.asyncio
    async def test_pattern_selection_with_real_coordinators(self, redis_client):
        """Test automatic pattern selection creates correct coordinators."""
        # Test 1: Should select Saga pattern
        saga_manager = DistributedTransactionManagerNode(
            transaction_name="saga_pattern_test",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "integration:saga:",
            },
        )

        await saga_manager.async_run(
            operation="create_transaction",
            requirements={"consistency": "eventual", "availability": "high"},
        )

        # Add participant that doesn't support 2PC
        await saga_manager.async_run(
            operation="add_participant",
            participant_id="saga_only_service",
            endpoint="http://saga-service:8080",
            supports_2pc=False,
            supports_saga=True,
        )

        result = await saga_manager.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["selected_pattern"] == "saga"
        assert saga_manager._saga_coordinator is not None
        assert saga_manager._2pc_coordinator is None

        # Test 2: Should select 2PC pattern
        tpc_manager = DistributedTransactionManagerNode(
            transaction_name="2pc_pattern_test",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "integration:2pc:",
            },
        )

        await tpc_manager.async_run(
            operation="create_transaction",
            requirements={"consistency": "immediate", "availability": "medium"},
        )

        # Add participants that support 2PC
        for i in range(2):
            await tpc_manager.async_run(
                operation="add_participant",
                participant_id=f"2pc_service_{i}",
                endpoint=f"http://2pc-service-{i}:8080",
                supports_2pc=True,
                supports_saga=True,
            )

        result = await tpc_manager.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["selected_pattern"] == "two_phase_commit"
        assert tpc_manager._2pc_coordinator is not None
        assert tpc_manager._saga_coordinator is None

    @pytest.mark.asyncio
    async def test_transaction_abort_with_real_storage(self, redis_client):
        """Test transaction abort with state persistence."""
        manager = DistributedTransactionManagerNode(
            transaction_name="abort_test_transaction",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "integration:abort:",
            },
        )

        # Create and start transaction
        await manager.async_run(operation="create_transaction")

        await manager.async_run(
            operation="add_participant",
            participant_id="abort_test_service",
            endpoint="http://test:8080",
        )

        # Simulate starting execution then aborting
        manager.status = TransactionStatus.RUNNING
        await manager._persist_state()

        # Abort the transaction
        result = await manager.async_run(operation="abort_transaction")

        assert result["status"] == "success"
        assert result["transaction_status"] == "aborted"
        assert manager.status == TransactionStatus.ABORTED
        assert manager.completed_at is not None

        # Verify aborted state is persisted
        redis_key = f"integration:abort:{manager.transaction_id}"
        stored_data = redis_client.get(redis_key)
        assert stored_data is not None
        assert '"status": "aborted"' in stored_data

    @pytest.mark.asyncio
    async def test_storage_backend_persistence_consistency(self, redis_client, db_pool):
        """Test state persistence consistency across different storage backends."""
        # Test Redis storage
        redis_manager = DistributedTransactionManagerNode(
            transaction_name="redis_storage_test",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "integration:storage:redis:",
            },
        )

        await redis_manager.async_run(
            operation="create_transaction",
            requirements={"consistency": "eventual", "availability": "high"},
        )

        # Test Database storage
        db_manager = DistributedTransactionManagerNode(
            transaction_name="db_storage_test",
            state_storage="database",
            storage_config={
                "db_pool": db_pool,
                "table_name": "integration_dtx_states",
                "saga_table_name": "integration_saga_states",
                "twophase_table_name": "integration_2pc_states",
            },
        )

        await db_manager.async_run(
            operation="create_transaction",
            requirements={"consistency": "strong", "availability": "medium"},
        )

        # Both should persist state in their respective backends
        redis_key = f"integration:storage:redis:{redis_manager.transaction_id}"
        redis_data = redis_client.get(redis_key)
        assert redis_data is not None

        async with db_pool.acquire() as conn:
            db_row = await conn.fetchrow(
                "SELECT state_data FROM integration_dtx_states WHERE transaction_id = $1",
                db_manager.transaction_id,
            )
            assert db_row is not None

    @pytest.mark.asyncio
    async def test_error_handling_with_real_storage(self, redis_client):
        """Test error handling and recovery with real storage."""
        manager = DistributedTransactionManagerNode(
            transaction_name="error_handling_test",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "integration:error:",
            },
        )

        # Test missing participant error
        result = await manager.async_run(operation="execute_transaction")

        assert result["status"] == "error"
        assert "No participants defined" in result["error"]

        # Create valid transaction
        await manager.async_run(operation="create_transaction")

        # Test adding participant without ID
        result = await manager.async_run(operation="add_participant")

        assert result["status"] == "error"
        assert "participant_id is required" in result["error"]

        # Test invalid pattern selection
        await manager.async_run(
            operation="add_participant",
            participant_id="incompatible_service",
            endpoint="http://service:8080",
            supports_2pc=False,
        )

        result = await manager.async_run(
            operation="execute_transaction",
            pattern="two_phase_commit",  # Force 2PC with incompatible participant
        )

        assert result["status"] == "failed"
        assert "do not support 2PC" in result["error"]

        # Verify error state is persisted
        redis_key = f"integration:error:{manager.transaction_id}"
        stored_data = redis_client.get(redis_key)
        assert stored_data is not None
        assert '"status": "failed"' in stored_data

    @pytest.mark.asyncio
    async def test_requirements_processing_with_storage(self, redis_client):
        """Test transaction requirements processing with real storage."""
        test_cases = [
            {
                "name": "immediate_consistency_test",
                "requirements": {"consistency": "immediate", "availability": "low"},
                "participant_2pc_support": True,
                "expected_pattern": "two_phase_commit",
            },
            {
                "name": "high_availability_test",
                "requirements": {"consistency": "strong", "availability": "high"},
                "participant_2pc_support": True,
                "expected_pattern": "saga",
            },
            {
                "name": "eventual_consistency_test",
                "requirements": {"consistency": "eventual", "availability": "medium"},
                "participant_2pc_support": False,
                "expected_pattern": "saga",
            },
        ]

        for i, test_case in enumerate(test_cases):
            manager = DistributedTransactionManagerNode(
                transaction_name=test_case["name"],
                state_storage="redis",
                storage_config={
                    "redis_client": redis_client,
                    "key_prefix": f"integration:req:{i}:",
                },
            )

            await manager.async_run(
                operation="create_transaction", requirements=test_case["requirements"]
            )

            await manager.async_run(
                operation="add_participant",
                participant_id=f"test_service_{i}",
                endpoint=f"http://service-{i}:8080",
                supports_2pc=test_case["participant_2pc_support"],
                supports_saga=True,
            )

            result = await manager.async_run(operation="execute_transaction")

            assert result["status"] == "success"
            assert result["selected_pattern"] == test_case["expected_pattern"]

            # Verify requirements are persisted correctly
            status_result = await manager.async_run(operation="get_status")
            requirements = status_result["requirements"]
            assert (
                requirements["consistency"] == test_case["requirements"]["consistency"]
            )
            assert (
                requirements["availability"]
                == test_case["requirements"]["availability"]
            )
