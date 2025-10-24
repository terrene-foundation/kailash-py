"""Integration tests for Saga State Persistence with real Docker services.

Tests saga state storage implementations against real Redis and PostgreSQL
following the Tier 2 testing policy: NO MOCKING, real Docker services only.
"""

import asyncio
import time
import uuid
from typing import Any, Dict

import asyncpg
import pytest
import redis
from kailash.nodes.transaction import SagaCoordinatorNode
from kailash.nodes.transaction.saga_state_storage import (
    DatabaseStateStorage,
    RedisStateStorage,
    StorageFactory,
)

from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_redis
class TestSagaRedisIntegration:
    """Integration tests for saga state persistence with real Redis."""

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

    @pytest.fixture
    def redis_storage(self, redis_client):
        """Create RedisStateStorage with real Redis."""
        return RedisStateStorage(redis_client, key_prefix="test:saga:")

    def test_saga_coordinator_with_redis_storage(self, redis_client):
        """Test SagaCoordinatorNode with Redis storage."""
        # Create coordinator with Redis storage
        coordinator = SagaCoordinatorNode(
            saga_name="redis_test_saga",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "test:saga:"},
        )

        # Create saga
        saga_id = str(uuid.uuid4())
        result = coordinator.execute(
            operation="create_saga",
            saga_id=saga_id,
            context={"test_type": "redis_integration"},
        )

        assert result["status"] == "success"
        assert result["saga_id"] == saga_id

        # Verify state was persisted in Redis
        redis_key = f"test:saga:{saga_id}"
        stored_data = redis_client.get(redis_key)
        assert stored_data is not None

        # Add a step
        result = coordinator.execute(
            operation="add_step",
            name="test_step",
            node_id="TestNode",
            compensation_node_id="CompTestNode",
        )

        assert result["status"] == "success"
        assert result["total_steps"] == 1

        # Load saga in new coordinator instance
        new_coordinator = SagaCoordinatorNode(
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "test:saga:"},
        )

        load_result = new_coordinator.execute(operation="load_saga", saga_id=saga_id)

        assert load_result["status"] == "success"
        assert new_coordinator.saga_id == saga_id
        assert len(new_coordinator.steps) == 1
        assert new_coordinator.steps[0].name == "test_step"

    def test_redis_storage_with_ttl(self, redis_storage, redis_client):
        """Test Redis storage TTL for completed sagas."""
        saga_id = "completed_saga_test"
        state_data = {
            "saga_id": saga_id,
            "state": "completed",  # Should trigger TTL
            "context": {"test": "ttl_test"},
        }

        # Save completed saga
        success = asyncio.run(redis_storage.save_state(saga_id, state_data))
        assert success is True

        # Check TTL was set (should be 7 days = 604800 seconds)
        ttl = redis_client.ttl(f"test:saga:{saga_id}")
        assert ttl > 0
        assert ttl <= 604800

    def test_redis_storage_listing_and_filtering(self, redis_storage):
        """Test listing and filtering sagas in Redis."""
        # Create multiple sagas with different states
        sagas = [
            {"id": "running_1", "state": "running", "type": "order"},
            {"id": "running_2", "state": "running", "type": "payment"},
            {"id": "completed_1", "state": "completed", "type": "order"},
            {"id": "failed_1", "state": "failed", "type": "payment"},
        ]

        # Save all sagas
        for saga in sagas:
            state_data = {
                "saga_id": saga["id"],
                "state": saga["state"],
                "type": saga["type"],
            }
            success = asyncio.run(redis_storage.save_state(saga["id"], state_data))
            assert success is True

        # List all sagas
        all_saga_ids = asyncio.run(redis_storage.list_sagas())
        assert len(all_saga_ids) == 4

        # Filter by state
        running_sagas = asyncio.run(redis_storage.list_sagas({"state": "running"}))
        assert len(running_sagas) == 2
        assert set(running_sagas) == {"running_1", "running_2"}

        # Clean up
        for saga in sagas:
            asyncio.run(redis_storage.delete_state(saga["id"]))


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
class TestSagaDatabaseIntegration:
    """Integration tests for saga state persistence with real PostgreSQL."""

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

            # Create test table
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS test_saga_states (
                        saga_id VARCHAR(255) PRIMARY KEY,
                        saga_name VARCHAR(255),
                        state VARCHAR(50),
                        state_data JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """
                )

                # Clean up any existing test data
                await conn.execute(
                    "DELETE FROM test_saga_states WHERE saga_id LIKE 'test_%'"
                )

            return pool

        async def cleanup_pool(pool):
            # Clean up after test
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM test_saga_states WHERE saga_id LIKE 'test_%'"
                )

            await pool.close()

        pool = event_loop.run_until_complete(setup_pool())
        yield pool
        event_loop.run_until_complete(cleanup_pool(pool))

    @pytest.fixture
    def db_storage(self, db_pool):
        """Create DatabaseStateStorage with real PostgreSQL."""
        # Override table creation for test
        storage = DatabaseStateStorage.__new__(DatabaseStateStorage)
        storage.db_pool = db_pool
        storage.table_name = "test_saga_states"
        return storage

    def test_database_storage_integration(self, db_storage, event_loop):
        """Test database storage integration directly."""

        async def run_test():
            # Test basic storage operations
            saga_id = f"test_{uuid.uuid4()}"
            state_data = {
                "saga_id": saga_id,
                "saga_name": "test_saga",
                "state": "pending",
                "context": {"test_type": "database_integration"},
                "steps": [],
            }

            # Save state
            success = await db_storage.save_state(saga_id, state_data)
            assert success is True

            # Load state
            loaded_data = await db_storage.load_state(saga_id)
            assert loaded_data is not None
            assert loaded_data["saga_id"] == saga_id
            assert loaded_data["state"] == "pending"

            # Update state
            state_data["state"] = "running"
            state_data["steps"] = [{"name": "step1", "state": "completed"}]
            success = await db_storage.save_state(saga_id, state_data)
            assert success is True

            # Verify update
            loaded_data = await db_storage.load_state(saga_id)
            assert loaded_data["state"] == "running"
            assert len(loaded_data["steps"]) == 1

            # Test listing
            saga_ids = await db_storage.list_sagas()
            assert saga_id in saga_ids

            # Test filtering
            running_sagas = await db_storage.list_sagas({"state": "running"})
            assert saga_id in running_sagas

            # Clean up
            success = await db_storage.delete_state(saga_id)
            assert success is True

            # Verify deletion
            loaded_data = await db_storage.load_state(saga_id)
            assert loaded_data is None

        event_loop.run_until_complete(run_test())

    def test_database_storage_transactions(self, db_storage, event_loop):
        """Test database storage with multiple concurrent operations."""

        async def run_test():
            saga_id = f"test_concurrent_{uuid.uuid4()}"

            # Simulate concurrent saga operations
            async def create_and_update_saga(suffix: str):
                test_id = f"{saga_id}_{suffix}"
                state_data = {
                    "saga_id": test_id,
                    "state": "running",
                    "context": {"operation": suffix},
                    "timestamp": time.time(),
                }

                # Save state
                success = await db_storage.save_state(test_id, state_data)
                assert success is True

                # Load state
                loaded = await db_storage.load_state(test_id)
                assert loaded["saga_id"] == test_id

                # Update state
                state_data["state"] = "completed"
                success = await db_storage.save_state(test_id, state_data)
                assert success is True

                return test_id

            # Run multiple concurrent operations
            tasks = [create_and_update_saga(f"op_{i}") for i in range(5)]

            saga_ids = await asyncio.gather(*tasks)
            assert len(saga_ids) == 5

            # Verify all sagas were saved correctly
            for saga_id in saga_ids:
                loaded = await db_storage.load_state(saga_id)
                assert loaded["state"] == "completed"

            # Clean up
            for saga_id in saga_ids:
                await db_storage.delete_state(saga_id)

        event_loop.run_until_complete(run_test())


@pytest.mark.integration
@pytest.mark.requires_docker
class TestSagaStorageFactory:
    """Integration tests for StorageFactory with real services."""

    @pytest.fixture(scope="class", autouse=True)
    def docker_services(self):
        """Ensure Docker services are running."""
        # Docker services should be running via test-env
        pass

    def test_factory_creates_working_redis_storage(self):
        """Test factory creates functional Redis storage."""
        redis_config = get_redis_connection_params()
        redis_client = redis.Redis(
            host=redis_config["host"], port=redis_config["port"], decode_responses=True
        )

        try:
            # Clean up any existing data
            redis_client.flushdb()

            storage = StorageFactory.create_storage(
                "redis", redis_client=redis_client, key_prefix="factory:test:"
            )

            # Test basic operations
            saga_id = "factory_test_saga"
            state_data = {"saga_id": saga_id, "state": "testing"}

            success = asyncio.run(storage.save_state(saga_id, state_data))
            assert success is True

            loaded = asyncio.run(storage.load_state(saga_id))
            assert loaded["saga_id"] == saga_id

            # Clean up
            redis_client.flushdb()
        finally:
            redis_client.close()

    def test_factory_creates_working_database_storage(self, event_loop):
        """Test factory creates functional database storage."""

        async def run_test():
            connection_string = get_postgres_connection_string()
            pool = await asyncpg.create_pool(connection_string, min_size=1, max_size=2)

            try:
                # Create test table
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS factory_test_saga_states (
                            saga_id VARCHAR(255) PRIMARY KEY,
                            saga_name VARCHAR(255),
                            state VARCHAR(50),
                            state_data JSONB,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                    """
                    )

                storage = StorageFactory.create_storage(
                    "database", db_pool=pool, table_name="factory_test_saga_states"
                )

                # Test basic operations
                saga_id = "factory_db_test_saga"
                state_data = {"saga_id": saga_id, "state": "testing"}

                success = await storage.save_state(saga_id, state_data)
                assert success is True

                loaded = await storage.load_state(saga_id)
                assert loaded["saga_id"] == saga_id

                # Clean up
                async with pool.acquire() as conn:
                    await conn.execute("DROP TABLE factory_test_saga_states")

            finally:
                await pool.close()

        event_loop.run_until_complete(run_test())
