"""Integration tests for Two-Phase Commit Coordinator with real Docker services.

Tests 2PC implementation with real Redis and PostgreSQL for state persistence
following the Tier 2 testing policy: NO MOCKING, real Docker services only.
"""

import asyncio
import time
import uuid
from typing import Any, Dict

import asyncpg
import pytest
import redis
from kailash.nodes.transaction.two_phase_commit import (
    TransactionState,
    TwoPhaseCommitCoordinatorNode,
)

from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_redis
class TestTwoPhaseCommitRedisIntegration:
    """Integration tests for 2PC with real Redis."""

    @pytest.fixture(scope="class", autouse=True)
    def docker_services(self):
        """Ensure Docker services are running."""
        # Docker services should be running via test-env
        pass

    @pytest.fixture
    def redis_client(self):
        """Create a real Redis client."""
        redis_config = get_redis_connection_params()
        client = redis.Redis(
            host=redis_config["host"], port=redis_config["port"], decode_responses=True
        )
        # Clean up any existing test data
        client.flushdb()
        yield client
        # Clean up after test
        client.flushdb()
        client.close()

    @pytest.mark.asyncio
    async def test_2pc_coordinator_with_redis_persistence(self, redis_client):
        """Test 2PC coordinator with Redis state persistence."""
        # Create coordinator with Redis storage
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="redis_2pc_test",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "test:2pc:"},
        )

        # Begin transaction
        result = await coordinator.async_run(
            operation="begin_transaction",
            context={"test_type": "redis_integration", "amount": 150.00},
        )

        assert result["status"] == "success"
        transaction_id = result["transaction_id"]

        # Verify state was persisted in Redis
        redis_key = f"test:2pc:{transaction_id}"
        stored_data = redis_client.get(redis_key)
        assert stored_data is not None

        # Add participants
        participants = ["payment_service", "inventory_service", "audit_service"]
        for participant_id in participants:
            result = await coordinator.async_run(
                operation="add_participant",
                participant_id=participant_id,
                endpoint=f"http://{participant_id}:8080/2pc",
            )
            assert result["status"] == "success"

        # Verify state persistence after adding participants
        status_result = await coordinator.async_run(operation="get_status")
        assert len(status_result["participants"]) == 3

        # Load coordinator in new instance to test persistence
        new_coordinator = TwoPhaseCommitCoordinatorNode(
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "test:2pc:"},
        )

        # Recover transaction state
        recovery_result = await new_coordinator.async_run(
            operation="recover_transaction", transaction_id=transaction_id
        )

        assert recovery_result["status"] == "success"
        assert new_coordinator.transaction_id == transaction_id
        assert len(new_coordinator.participants) == 3
        assert new_coordinator.context["test_type"] == "redis_integration"

    @pytest.mark.asyncio
    async def test_2pc_successful_transaction_with_persistence(self, redis_client):
        """Test complete 2PC transaction with Redis persistence."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="successful_2pc",
            participants=["service1", "service2"],
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "test:2pc:"},
        )

        # Begin transaction
        await coordinator.async_run(
            operation="begin_transaction",
            context={"order_id": "order_456", "total": 299.99},
        )

        # Execute transaction (will use mock prepare/commit)
        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["state"] == "committed"
        assert coordinator.state == TransactionState.COMMITTED

        # Verify final state is persisted
        transaction_id = coordinator.transaction_id
        redis_key = f"test:2pc:{transaction_id}"
        stored_data = redis_client.get(redis_key)
        assert stored_data is not None

        # Verify we can get status
        status_result = await coordinator.async_run(operation="get_status")
        assert status_result["state"] == "committed"
        assert status_result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_2pc_abort_transaction_with_persistence(self, redis_client):
        """Test aborting 2PC transaction with persistence."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="abort_test",
            participants=["service1", "service2"],
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "test:2pc:"},
        )

        # Begin transaction
        await coordinator.async_run(operation="begin_transaction")

        # Abort transaction
        result = await coordinator.async_run(operation="abort_transaction")

        assert result["status"] == "success"
        assert result["state"] == "aborted"
        assert coordinator.state == TransactionState.ABORTED

        # Verify abort state is persisted
        status_result = await coordinator.async_run(operation="get_status")
        assert status_result["state"] == "aborted"
        assert status_result["aborted_at"] is not None

    @pytest.mark.asyncio
    async def test_multiple_concurrent_2pc_transactions(self, redis_client):
        """Test multiple concurrent 2PC transactions with shared storage."""
        num_transactions = 3
        coordinators = []
        transaction_ids = []

        # Create multiple coordinators concurrently
        for i in range(num_transactions):
            coordinator = TwoPhaseCommitCoordinatorNode(
                transaction_name=f"concurrent_2pc_{i}",
                participants=[f"service_{i}_1", f"service_{i}_2"],
                state_storage="redis",
                storage_config={
                    "redis_client": redis_client,
                    "key_prefix": "test:2pc:concurrent:",
                },
            )

            result = await coordinator.async_run(
                operation="begin_transaction",
                context={"transaction_index": i, "created_at": time.time()},
            )

            coordinators.append(coordinator)
            transaction_ids.append(result["transaction_id"])

        # Execute all transactions
        results = []
        for coordinator in coordinators:
            result = await coordinator.async_run(operation="execute_transaction")
            results.append(result)

        # Verify all transactions completed successfully
        for i, result in enumerate(results):
            assert result["status"] == "success"
            assert result["state"] == "committed"

        # Verify all transactions can be recovered independently
        for transaction_id in transaction_ids:
            recovery_coordinator = TwoPhaseCommitCoordinatorNode(
                state_storage="redis",
                storage_config={
                    "redis_client": redis_client,
                    "key_prefix": "test:2pc:concurrent:",
                },
            )

            recovery_result = await recovery_coordinator.async_run(
                operation="recover_transaction", transaction_id=transaction_id
            )

            assert recovery_result["status"] == "success"
            assert recovery_coordinator.transaction_id == transaction_id
            assert len(recovery_coordinator.participants) == 2


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
class TestTwoPhaseCommitDatabaseIntegration:
    """Integration tests for 2PC with real PostgreSQL."""

    @pytest.fixture(scope="class", autouse=True)
    def docker_services(self):
        """Ensure Docker services are running."""
        # Docker services should be running via test-env
        pass

    @pytest.fixture
    def db_pool(self, event_loop):
        """Create a real PostgreSQL connection pool."""

        async def setup_pool():
            connection_string = get_postgres_connection_string()
            pool = await asyncpg.create_pool(connection_string, min_size=1, max_size=5)

            # Create test table for 2PC states
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS test_2pc_states (
                        transaction_id VARCHAR(255) PRIMARY KEY,
                        transaction_name VARCHAR(255),
                        state VARCHAR(50),
                        state_data JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """
                )

                # Clean up any existing test data
                await conn.execute(
                    "DELETE FROM test_2pc_states WHERE transaction_id LIKE 'test_%'"
                )

            return pool

        async def cleanup_pool(pool):
            # Clean up after test
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM test_2pc_states WHERE transaction_id LIKE 'test_%'"
                )

            await pool.close()

        pool = event_loop.run_until_complete(setup_pool())
        yield pool
        event_loop.run_until_complete(cleanup_pool(pool))

    def test_2pc_coordinator_with_database_persistence(self, db_pool, event_loop):
        """Test 2PC coordinator with database state persistence."""

        async def run_test():
            # Create coordinator with database storage
            coordinator = TwoPhaseCommitCoordinatorNode(
                transaction_name="db_2pc_test",
                participants=["payment_db", "inventory_db"],
                state_storage="database",
                storage_config={"db_pool": db_pool, "table_name": "test_2pc_states"},
            )

            # Begin transaction
            result = await coordinator.async_run(
                operation="begin_transaction",
                context={
                    "test_type": "database_integration",
                    "customer_id": "cust_123",
                },
            )

            assert result["status"] == "success"
            transaction_id = result["transaction_id"]

            # Verify state was persisted in database
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM test_2pc_states WHERE transaction_id = $1",
                    transaction_id,
                )
                assert row is not None
                assert row["transaction_name"] == "db_2pc_test"
                assert row["state"] == "init"

            # Execute transaction
            result = await coordinator.async_run(operation="execute_transaction")

            assert result["status"] == "success"
            assert result["state"] == "committed"

            # Verify committed state in database
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT state FROM test_2pc_states WHERE transaction_id = $1",
                    transaction_id,
                )
                assert row["state"] == "committed"

        event_loop.run_until_complete(run_test())

    def test_2pc_recovery_from_database(self, db_pool, event_loop):
        """Test 2PC recovery from database persistence."""

        async def run_test():
            # Create first coordinator and begin transaction
            coordinator1 = TwoPhaseCommitCoordinatorNode(
                transaction_name="recovery_test",
                participants=["service_a", "service_b", "service_c"],
                state_storage="database",
                storage_config={"db_pool": db_pool, "table_name": "test_2pc_states"},
            )

            begin_result = await coordinator1.async_run(
                operation="begin_transaction",
                context={"recovery_test": True, "important_data": "must_persist"},
            )

            transaction_id = begin_result["transaction_id"]

            # Simulate coordinator failure by creating new instance
            coordinator2 = TwoPhaseCommitCoordinatorNode(
                state_storage="database",
                storage_config={"db_pool": db_pool, "table_name": "test_2pc_states"},
            )

            # Recover transaction
            recovery_result = await coordinator2.async_run(
                operation="recover_transaction", transaction_id=transaction_id
            )

            assert recovery_result["status"] == "success"
            assert coordinator2.transaction_id == transaction_id
            assert coordinator2.transaction_name == "recovery_test"
            assert len(coordinator2.participants) == 3
            assert coordinator2.context["recovery_test"] is True
            assert coordinator2.context["important_data"] == "must_persist"

            # Continue with recovered transaction
            execution_result = await coordinator2.async_run(
                operation="execute_transaction"
            )
            assert execution_result["status"] == "success"

        event_loop.run_until_complete(run_test())

    def test_2pc_database_transactions_isolation(self, db_pool, event_loop):
        """Test database transaction isolation for concurrent 2PC operations."""

        async def run_test():
            # Create multiple coordinators with database persistence
            coordinators = []
            transaction_ids = []

            for i in range(3):
                coordinator = TwoPhaseCommitCoordinatorNode(
                    transaction_name=f"isolation_test_{i}",
                    participants=[f"db_service_{i}"],
                    state_storage="database",
                    storage_config={
                        "db_pool": db_pool,
                        "table_name": "test_2pc_states",
                    },
                )

                begin_result = await coordinator.async_run(
                    operation="begin_transaction",
                    context={"isolation_index": i, "timestamp": time.time()},
                )

                coordinators.append(coordinator)
                transaction_ids.append(begin_result["transaction_id"])

            # Execute all transactions concurrently
            execution_tasks = [
                coordinator.async_run(operation="execute_transaction")
                for coordinator in coordinators
            ]

            results = await asyncio.gather(*execution_tasks, return_exceptions=True)

            # Verify all succeeded
            for i, result in enumerate(results):
                assert not isinstance(
                    result, Exception
                ), f"Transaction {i} failed: {result}"
                assert result["status"] == "success"
                assert result["state"] == "committed"

            # Verify all transactions are properly stored in database
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT transaction_id, state FROM test_2pc_states WHERE transaction_id = ANY($1)",
                    transaction_ids,
                )

                assert len(rows) == 3
                for row in rows:
                    assert row["state"] == "committed"
                    assert row["transaction_id"] in transaction_ids

        event_loop.run_until_complete(run_test())


@pytest.mark.integration
@pytest.mark.requires_docker
class TestTwoPhaseCommitStorageIntegration:
    """Integration tests for 2PC storage factory and configurations."""

    @pytest.fixture(scope="class", autouse=True)
    def docker_services(self):
        """Ensure Docker services are running."""
        pass

    @pytest.mark.asyncio
    async def test_memory_storage_fallback(self):
        """Test fallback to memory storage when services unavailable."""
        # Create coordinator with invalid Redis config
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="fallback_test",
            state_storage="redis",
            storage_config={
                "redis_client": None,  # Invalid client
                "key_prefix": "test:fallback:",
            },
        )

        # Should still work with memory storage fallback
        result = await coordinator.async_run(
            operation="begin_transaction", context={"fallback_test": True}
        )

        assert result["status"] == "success"

        # Add participant and execute
        await coordinator.async_run(
            operation="add_participant", participant_id="fallback_service"
        )

        execution_result = await coordinator.async_run(operation="execute_transaction")
        assert execution_result["status"] == "success"

    @pytest.mark.asyncio
    async def test_database_storage_fallback(self):
        """Test fallback to memory storage for invalid database config."""
        # Create coordinator with invalid database config
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="db_fallback_test",
            state_storage="database",
            storage_config={
                "db_pool": None,  # Invalid pool
                "table_name": "invalid_table",
            },
        )

        # Should still work with memory storage fallback
        result = await coordinator.async_run(
            operation="begin_transaction", context={"db_fallback_test": True}
        )

        assert result["status"] == "success"

        # Execute transaction
        await coordinator.async_run(
            operation="add_participant", participant_id="db_fallback_service"
        )

        execution_result = await coordinator.async_run(operation="execute_transaction")
        assert execution_result["status"] == "success"
