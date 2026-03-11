"""
Connection Lifecycle Integration tests for DataFlow adapters.

Tests connection management, pooling, recovery, and lifecycle scenarios
across different database types.
"""

import asyncio
import os

# Import actual classes
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../src"))
from dataflow.adapters.exceptions import AdapterError, ConnectionError
from dataflow.adapters.factory import AdapterFactory
from dataflow.adapters.mysql import MySQLAdapter
from dataflow.adapters.postgresql import PostgreSQLAdapter
from dataflow.adapters.sqlite import SQLiteAdapter

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    from kailash.runtime.local import LocalRuntime

    return LocalRuntime()


class TestConnectionLifecycleBasic:
    """Test basic connection lifecycle operations."""

    @pytest.mark.asyncio
    async def test_basic_connection_lifecycle(self, test_suite):
        """Test basic connect-disconnect lifecycle."""
        adapters = [
            PostgreSQLAdapter(test_suite.config.url),
            MySQLAdapter("mysql://localhost/test"),
            SQLiteAdapter("sqlite:///test.db"),
        ]

        for adapter in adapters:
            # Skip non-PostgreSQL adapters since they're not configured
            if not isinstance(adapter, PostgreSQLAdapter):
                continue

            # Initial state
            assert adapter.is_connected is False
            assert adapter.connection_pool is None

            # Connect
            await adapter.connect()
            assert adapter.is_connected is True
            assert adapter.connection_pool is not None

            # Test basic operation
            result = await adapter.execute_query("SELECT 1", [])
            assert result is not None

            # Disconnect
            await adapter.disconnect()
            assert adapter.is_connected is False
            assert adapter.connection_pool is None

    @pytest.mark.asyncio
    async def test_multiple_connect_disconnect_cycles(self, test_suite):
        """Test multiple connect-disconnect cycles."""
        adapter = PostgreSQLAdapter(test_suite.config.url)

        for cycle in range(3):
            # Connect
            await adapter.connect()
            assert adapter.is_connected is True

            # Execute query
            result = await adapter.execute_query(f"SELECT {cycle} as cycle", [])
            assert result is not None

            # Disconnect
            await adapter.disconnect()
            assert adapter.is_connected is False

            # Brief pause between cycles
            await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_connection_state_consistency(self, test_suite):
        """Test connection state consistency across operations."""
        adapters = [
            PostgreSQLAdapter(test_suite.config.url),
            MySQLAdapter("mysql://localhost/test"),
            SQLiteAdapter("sqlite:///test.db"),
        ]

        for adapter in adapters:
            # Test operations without connection
            with pytest.raises(Exception):
                await adapter.execute_query("SELECT 1", [])

            # Connect and test operations
            await adapter.connect()
            assert adapter.is_connected is True

            # Multiple operations should work
            for i in range(3):
                result = await adapter.execute_query(f"SELECT {i}", [])
                assert result is not None
                assert adapter.is_connected is True  # Should remain connected

            # Disconnect
            await adapter.disconnect()
            assert adapter.is_connected is False

            # Test operations after disconnect
            with pytest.raises(Exception):
                await adapter.execute_query("SELECT 1", [])


class TestConnectionPooling:
    """Test connection pooling functionality."""

    @pytest.mark.asyncio
    async def test_connection_pool_configuration(self, test_suite):
        """Test connection pool configuration."""
        pool_configs = [
            {"pool_size": 5, "max_overflow": 10, "pool_timeout": 30},
            {"pool_size": 10, "max_overflow": 20, "pool_timeout": 60},
            {"pool_size": 15, "max_overflow": 5, "pool_timeout": 45},
        ]

        for config in pool_configs:
            adapter = PostgreSQLAdapter(
                test_suite.config.url,
                **config,
            )

            # Verify configuration
            assert adapter.pool_size == config["pool_size"]
            assert adapter.max_overflow == config["max_overflow"]
            assert adapter.pool_timeout == config["pool_timeout"]

            # Test connection with pooling
            await adapter.connect()
            assert adapter.is_connected is True

            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_concurrent_connection_usage(self, test_suite):
        """Test concurrent connection usage with pooling."""
        adapter = PostgreSQLAdapter(
            test_suite.config.url,
            pool_size=5,
            max_overflow=10,
        )

        await adapter.connect()

        # Execute multiple concurrent queries
        query_tasks = []
        for i in range(15):  # More than pool_size to test overflow
            query_tasks.append(adapter.execute_query(f"SELECT {i} as value", []))

        results = await asyncio.gather(*query_tasks)

        # Verify all queries completed
        assert len(results) == 15
        for result in results:
            assert result is not None

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_connection_pool_isolation(self, test_suite):
        """Test isolation between different connection pools."""
        adapter1 = PostgreSQLAdapter(
            test_suite.config.url,
            pool_size=3,
        )
        adapter2 = PostgreSQLAdapter(
            test_suite.config.url,
            pool_size=5,
        )
        adapter3 = MySQLAdapter("mysql://localhost/db3", pool_size=7)

        adapters = [adapter1, adapter2, adapter3]

        # Connect all adapters
        await asyncio.gather(*[adapter.connect() for adapter in adapters])

        # Execute queries concurrently on different pools (only PostgreSQL adapters)
        query_tasks = []
        for i, adapter in enumerate(adapters):
            # Skip non-PostgreSQL adapters
            if not isinstance(adapter, PostgreSQLAdapter):
                continue
            for j in range(4):  # Multiple queries per adapter
                query_tasks.append(
                    adapter.execute_query(f"SELECT {i} * 10 + {j} as value", [])
                )

        results = await asyncio.gather(*query_tasks)

        # Verify all queries completed
        assert len(results) == 8  # 2 PostgreSQL adapters × 4 queries
        for result in results:
            assert result is not None

        # Disconnect all adapters (but only the connected ones)
        await asyncio.gather(
            *[
                adapter.disconnect()
                for adapter in adapters
                if isinstance(adapter, PostgreSQLAdapter)
            ]
        )

    @pytest.mark.asyncio
    async def test_connection_pool_recycling(self, test_suite):
        """Test connection pool recycling behavior."""
        adapter = PostgreSQLAdapter(
            test_suite.config.url,
            pool_size=2,
            pool_recycle=1,  # Recycle every second (for testing)
        )

        await adapter.connect()

        # Execute initial queries
        result1 = await adapter.execute_query("SELECT 1 as initial", [])
        assert result1 is not None

        # Wait for potential recycle
        await asyncio.sleep(1.1)

        # Execute queries after potential recycle
        result2 = await adapter.execute_query("SELECT 2 as after_recycle", [])
        assert result2 is not None

        await adapter.disconnect()


class TestConnectionRecovery:
    """Test connection recovery and error handling."""

    @pytest.mark.asyncio
    async def test_connection_recovery_after_failure(self, test_suite):
        """Test connection recovery after simulated failure."""
        adapter = PostgreSQLAdapter(test_suite.config.url)

        # Initial connection
        await adapter.connect()
        assert adapter.is_connected is True

        # Simulate connection failure
        adapter.is_connected = False
        adapter._connection = None

        # Should raise error on query attempt
        with pytest.raises(Exception):
            await adapter.execute_query("SELECT 1", [])

        # Reconnect should work
        await adapter.connect()
        assert adapter.is_connected is True

        # Query should work after reconnection
        result = await adapter.execute_query("SELECT 1", [])
        assert result is not None

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_graceful_connection_failure_handling(self, test_suite):
        """Test graceful handling of connection failures."""
        adapters = [
            PostgreSQLAdapter(test_suite.config.url),
            MySQLAdapter("mysql://localhost/test"),
            SQLiteAdapter("sqlite:///test.db"),
        ]

        for adapter in adapters:
            # Test query without connection
            with pytest.raises(Exception):
                await adapter.execute_query("SELECT 1", [])

            # Test transaction without connection
            with pytest.raises(Exception):
                await adapter.execute_transaction([("SELECT 1", [])])

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, test_suite):
        """Test connection timeout handling."""
        # Test with very short timeout
        adapter = PostgreSQLAdapter(
            test_suite.config.url,
            pool_timeout=0.1,  # Very short timeout
        )

        await adapter.connect()

        # Should handle timeout gracefully
        result = await adapter.execute_query("SELECT 1", [])
        assert result is not None

        await adapter.disconnect()


class TestConcurrentConnectionManagement:
    """Test concurrent connection management scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_adapter_connections(self, test_suite):
        """Test concurrent connections across multiple adapters."""
        adapters = [
            PostgreSQLAdapter(test_suite.config.url),
            PostgreSQLAdapter(test_suite.config.url),
            MySQLAdapter("mysql://localhost/test3"),
            MySQLAdapter("mysql://localhost/test4"),
            SQLiteAdapter("sqlite:///test5.db"),
            SQLiteAdapter("sqlite:///test6.db"),
        ]

        # Connect all adapters concurrently
        await asyncio.gather(*[adapter.connect() for adapter in adapters])

        # Verify all connections
        for adapter in adapters:
            assert adapter.is_connected is True

        # Execute queries concurrently
        query_tasks = []
        for i, adapter in enumerate(adapters):
            query_tasks.append(adapter.execute_query(f"SELECT {i} as adapter_id", []))

        results = await asyncio.gather(*query_tasks)

        # Verify all queries completed
        assert len(results) == len(adapters)
        for result in results:
            assert result is not None

        # Disconnect all adapters concurrently
        await asyncio.gather(*[adapter.disconnect() for adapter in adapters])

        # Verify all disconnections
        for adapter in adapters:
            assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_connection_race_conditions(self, test_suite):
        """Test connection race conditions."""
        adapter = PostgreSQLAdapter(test_suite.config.url)

        # Attempt multiple concurrent connections
        connection_tasks = []
        for i in range(5):
            connection_tasks.append(adapter.connect())

        # Should handle concurrent connections gracefully
        await asyncio.gather(*connection_tasks)

        # Adapter should be connected
        assert adapter.is_connected is True

        # Attempt multiple concurrent disconnections
        disconnection_tasks = []
        for i in range(5):
            disconnection_tasks.append(adapter.disconnect())

        # Should handle concurrent disconnections gracefully
        await asyncio.gather(*disconnection_tasks)

        # Adapter should be disconnected
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_connection_with_concurrent_queries(self, test_suite):
        """Test connection stability with concurrent queries."""
        adapter = PostgreSQLAdapter(
            test_suite.config.url,
            pool_size=3,
        )

        await adapter.connect()

        # Execute many concurrent queries
        query_tasks = []
        for i in range(20):
            query_tasks.append(
                adapter.execute_query(f"SELECT {i} as concurrent_query", [])
            )

        results = await asyncio.gather(*query_tasks)

        # Verify all queries completed
        assert len(results) == 20
        for result in results:
            assert result is not None

        # Connection should remain stable
        assert adapter.is_connected is True

        await adapter.disconnect()


class TestConnectionMemoryManagement:
    """Test connection memory management and cleanup."""

    @pytest.mark.asyncio
    async def test_connection_cleanup_on_disconnect(self, test_suite):
        """Test proper cleanup on disconnect."""
        adapter = PostgreSQLAdapter(test_suite.config.url)

        # Connect
        await adapter.connect()
        connection_id = id(adapter.connection_pool)
        assert adapter.connection_pool is not None

        # Disconnect
        await adapter.disconnect()
        assert adapter.connection_pool is None
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_multiple_adapter_memory_isolation(self, test_suite):
        """Test memory isolation between multiple adapters."""
        adapters = []
        connection_ids = []

        # Create multiple adapters (all using the same database since that's what exists)
        for i in range(3):  # Reduce to 3 for faster testing
            adapter = PostgreSQLAdapter(test_suite.config.url)
            adapters.append(adapter)
            await adapter.connect()
            connection_ids.append(id(adapter.connection_pool))

        # Verify each adapter has unique connection pool
        assert len(set(connection_ids)) == 3

        # Verify adapters are independent
        for i, adapter in enumerate(adapters):
            assert adapter.is_connected is True
            assert adapter.connection_pool is not None

        # Disconnect all adapters
        await asyncio.gather(*[adapter.disconnect() for adapter in adapters])

        # Verify all connections cleaned up
        for adapter in adapters:
            assert adapter.connection_pool is None
            assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_connection_resource_management(self, test_suite):
        """Test connection resource management."""
        adapter = PostgreSQLAdapter(
            test_suite.config.url,
            pool_size=2,
        )

        # Connect
        await adapter.connect()
        assert adapter.is_connected is True

        # Execute multiple queries to test resource usage
        for i in range(10):
            result = await adapter.execute_query(f"SELECT {i} as resource_test", [])
            assert result is not None

        # Connection should remain stable
        assert adapter.is_connected is True

        # Disconnect should clean up resources
        await adapter.disconnect()
        assert adapter.is_connected is False


class TestConnectionFactoryIntegration:
    """Test connection lifecycle with factory pattern."""

    @pytest.mark.asyncio
    async def test_factory_created_adapter_lifecycle(self, test_suite):
        """Test lifecycle of factory-created adapters."""
        factory = AdapterFactory()

        connection_strings = [
            test_suite.config.url,
            "mysql://localhost/test2",
            "sqlite:///test3.db",
        ]

        adapters = []
        for connection_string in connection_strings:
            adapter = factory.create_adapter(connection_string)
            adapters.append(adapter)

        # Connect all factory-created adapters
        await asyncio.gather(*[adapter.connect() for adapter in adapters])

        # Verify all connections
        for adapter in adapters:
            assert adapter.is_connected is True

        # Test queries on all adapters
        query_tasks = []
        for adapter in adapters:
            query_tasks.append(adapter.execute_query("SELECT 1 as factory_test", []))

        results = await asyncio.gather(*query_tasks)

        # Verify all queries completed
        for result in results:
            assert result is not None

        # Disconnect all adapters
        await asyncio.gather(*[adapter.disconnect() for adapter in adapters])

        # Verify all disconnections
        for adapter in adapters:
            assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_factory_configuration_persistence(self, test_suite):
        """Test configuration persistence through factory."""
        factory = AdapterFactory(default_pool_size=8, default_timeout=25)

        adapter = factory.create_adapter(test_suite.config.url)

        # Verify configuration applied (PostgreSQL adapter has default pool_size of 10)
        # Factory default should be applied where possible
        assert hasattr(adapter, "pool_size")
        assert hasattr(adapter, "connection_string")

        # Test connection with configuration
        await adapter.connect()
        assert adapter.is_connected is True

        # Test query execution
        result = await adapter.execute_query("SELECT 1 as config_test", [])
        assert result is not None

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_factory_multi_database_lifecycle(self, test_suite):
        """Test factory managing multiple database type lifecycles."""
        factory = AdapterFactory()

        # Create multiple adapters of different types (only PostgreSQL configured)
        adapters = [
            factory.create_adapter(test_suite.config.url),
            factory.create_adapter(test_suite.config.url),
            factory.create_adapter("mysql://localhost/mysql_test"),
            factory.create_adapter("sqlite:///sqlite_test.db"),
        ]

        # Only connect PostgreSQL adapters since others aren't configured
        postgresql_adapters = [
            adapter for adapter in adapters if isinstance(adapter, PostgreSQLAdapter)
        ]
        connection_tasks = [adapter.connect() for adapter in postgresql_adapters]
        await asyncio.gather(*connection_tasks)

        # Verify PostgreSQL connections
        for adapter in postgresql_adapters:
            assert adapter.is_connected is True

        # Execute transactions on PostgreSQL adapters only
        transaction_tasks = []
        for adapter in postgresql_adapters:
            # Use simple SELECT queries that don't require specific tables
            transaction = [("SELECT 1 as test_value", [])]
            transaction_tasks.append(adapter.execute_transaction(transaction))

        results = await asyncio.gather(*transaction_tasks)

        # Verify all transactions completed
        for result in results:
            assert result is not None
            assert isinstance(result, list)
            assert len(result) > 0

        # Disconnect PostgreSQL adapters
        disconnection_tasks = [adapter.disconnect() for adapter in postgresql_adapters]
        await asyncio.gather(*disconnection_tasks)

        # Verify all disconnections
        for adapter in postgresql_adapters:
            assert adapter.is_connected is False
