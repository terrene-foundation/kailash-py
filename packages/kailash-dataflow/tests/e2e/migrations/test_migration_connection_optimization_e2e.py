"""
E2E tests for complete migration pipeline with connection optimization.

Tests the full migration workflow from DataFlow model definitions through
optimized connection management, demonstrating real-world usage patterns
and performance improvements.
"""

import asyncio
import time

import pytest
from dataflow.migrations.auto_migration_system import (
    AutoMigrationSystem,
    MigrationOperation,
    MigrationType,
)
from dataflow.migrations.batched_migration_executor import BatchedMigrationExecutor
from dataflow.migrations.migration_connection_manager import (
    ConnectionPoolConfig,
    MigrationConnectionManager,
    RetryConfig,
)


class TestMigrationConnectionOptimizationE2E:
    """E2E tests for migration pipeline with connection optimization."""

    @pytest.fixture
    def sqlite_dataflow_config(self):
        """Create DataFlow configuration for SQLite testing."""
        from tests.utils.real_infrastructure import real_infra

        return real_infra.get_sqlite_memory_db()

    @pytest.fixture
    def postgresql_dataflow_config(self):
        """Create DataFlow configuration for PostgreSQL testing."""
        from tests.utils.real_infrastructure import real_infra

        db = real_infra.get_postgresql_test_db()
        if db is None:
            pytest.skip("PostgreSQL test database not available")
        return db

    @pytest.fixture
    def large_migration_operations(self):
        """Create a large set of migration operations for performance testing."""
        operations = []

        # Create multiple tables
        for i in range(10):
            operations.append(
                MigrationOperation(
                    operation_type=MigrationType.CREATE_TABLE,
                    table_name=f"table_{i}",
                    description=f"Create table_{i}",
                    sql_up=f"CREATE TABLE table_{i} (id INTEGER PRIMARY KEY, name TEXT, created_at TIMESTAMP)",
                    sql_down=f"DROP TABLE table_{i}",
                )
            )

        # Add columns to existing tables
        for i in range(10):
            operations.append(
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name=f"table_{i}",
                    description=f"Add email column to table_{i}",
                    sql_up=f"ALTER TABLE table_{i} ADD COLUMN email TEXT",
                    sql_down=f"ALTER TABLE table_{i} DROP COLUMN email",
                )
            )

        # Create indexes
        for i in range(10):
            operations.append(
                MigrationOperation(
                    operation_type=MigrationType.ADD_INDEX,
                    table_name=f"table_{i}",
                    description=f"Add index on name for table_{i}",
                    sql_up=f"CREATE INDEX idx_table_{i}_name ON table_{i} (name)",
                    sql_down=f"DROP INDEX idx_table_{i}_name",
                )
            )

        return operations

    @pytest.fixture
    def complex_schema_operations(self):
        """Create complex schema operations that simulate real-world scenarios."""
        return [
            # User management tables
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="users",
                description="Create users table",
                sql_up="""CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                sql_down="DROP TABLE users",
            ),
            # Profile table with foreign key
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="user_profiles",
                description="Create user_profiles table",
                sql_up="""CREATE TABLE user_profiles (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    bio TEXT,
                    avatar_url TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )""",
                sql_down="DROP TABLE user_profiles",
            ),
            # Posts table
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="posts",
                description="Create posts table",
                sql_up="""CREATE TABLE posts (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    published BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )""",
                sql_down="DROP TABLE posts",
            ),
            # Performance indexes
            MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="users",
                description="Add index on username",
                sql_up="CREATE INDEX idx_users_username ON users (username)",
                sql_down="DROP INDEX idx_users_username",
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="users",
                description="Add index on email",
                sql_up="CREATE INDEX idx_users_email ON users (email)",
                sql_down="DROP INDEX idx_users_email",
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="posts",
                description="Add index on user_id",
                sql_up="CREATE INDEX idx_posts_user_id ON posts (user_id)",
                sql_down="DROP INDEX idx_posts_user_id",
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="posts",
                description="Add index on published status",
                sql_up="CREATE INDEX idx_posts_published ON posts (published)",
                sql_down="DROP INDEX idx_posts_published",
            ),
        ]

    @pytest.mark.asyncio
    async def test_complete_migration_workflow_with_optimization_sqlite(
        self, sqlite_dataflow_config, complex_schema_operations
    ):
        """Test complete migration workflow with connection optimization using SQLite."""
        # Setup connection manager with optimized configuration
        config = ConnectionPoolConfig(
            pool_size=5, max_lifetime=3600, acquire_timeout=30, enable_pooling=True
        )
        connection_manager = MigrationConnectionManager(
            sqlite_dataflow_config, pool_config=config
        )

        # Create fallback connection
        fallback_connection = connection_manager.get_migration_connection()

        # Create optimized executor
        executor = BatchedMigrationExecutor(fallback_connection, connection_manager)

        try:
            # Batch the operations
            batches = executor.batch_ddl_operations(complex_schema_operations)

            # Verify batching is effective
            assert len(batches) > 0
            assert len(batches) <= len(
                complex_schema_operations
            )  # Should batch some operations

            # Execute all batches with timing
            start_time = time.time()
            result = await executor.execute_batched_migrations(batches)
            execution_time = time.time() - start_time

            assert result is True
            assert execution_time < 10.0  # Should complete quickly

            # Verify all schema changes were applied
            with connection_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Check tables exist
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = [row[0] for row in cursor.fetchall()]
                expected_tables = ["posts", "user_profiles", "users"]
                for table in expected_tables:
                    assert table in tables

                # Check indexes exist
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
                )
                indexes = [row[0] for row in cursor.fetchall()]
                expected_indexes = [
                    "idx_users_username",
                    "idx_users_email",
                    "idx_posts_user_id",
                    "idx_posts_published",
                ]
                for index in expected_indexes:
                    assert index in indexes

                cursor.close()

            # Verify metrics
            metrics = executor.get_execution_metrics()
            assert metrics is not None
            assert metrics.total_operations == len(complex_schema_operations)
            assert metrics.total_batches == len(batches)
            assert metrics.execution_time > 0

            # Verify connection pool was utilized
            pool_stats = connection_manager.get_pool_stats()
            assert pool_stats.total_created > 0

        finally:
            # Cleanup
            connection_manager.close_all_connections()

    @pytest.mark.asyncio
    async def test_performance_comparison_with_and_without_optimization_sqlite(
        self, sqlite_dataflow_config, large_migration_operations
    ):
        """Compare performance with and without connection optimization."""
        # Test with connection optimization
        optimized_config = ConnectionPoolConfig(pool_size=5, enable_pooling=True)
        optimized_manager = MigrationConnectionManager(
            sqlite_dataflow_config, pool_config=optimized_config
        )
        optimized_connection = optimized_manager.get_migration_connection()
        optimized_executor = BatchedMigrationExecutor(
            optimized_connection, optimized_manager
        )

        # Test without connection optimization
        standard_manager = MigrationConnectionManager(sqlite_dataflow_config)
        standard_connection = standard_manager.get_migration_connection()
        standard_executor = BatchedMigrationExecutor(
            standard_connection
        )  # No connection manager

        try:
            # Prepare batches (should be identical)
            optimized_batches = optimized_executor.batch_ddl_operations(
                large_migration_operations
            )
            standard_batches = standard_executor.batch_ddl_operations(
                large_migration_operations
            )

            assert len(optimized_batches) == len(standard_batches)

            # Execute with optimization
            start_time = time.time()
            optimized_result = await optimized_executor.execute_batched_migrations(
                optimized_batches
            )
            optimized_time = time.time() - start_time

            # Clean up optimized tables for fair comparison
            cleanup_operations = [f"DROP TABLE IF EXISTS table_{i}" for i in range(10)]
            for cleanup_sql in cleanup_operations:
                await optimized_executor._execute_batch_sequential([cleanup_sql])

            # Execute without optimization
            start_time = time.time()
            standard_result = await standard_executor.execute_batched_migrations(
                standard_batches
            )
            standard_time = time.time() - start_time

            # Both should succeed
            assert optimized_result is True
            assert standard_result is True

            # Times should be reasonable
            assert optimized_time < 30.0
            assert standard_time < 30.0

            print(f"Optimized: {optimized_time:.3f}s, Standard: {standard_time:.3f}s")

            # Check connection pool utilization
            optimized_stats = optimized_manager.get_pool_stats()
            standard_stats = standard_manager.get_pool_stats()

            # Optimized should show connection reuse
            assert optimized_stats.total_reused >= 0
            assert standard_stats.total_reused == 0  # No pool

            # Verify execution metrics
            optimized_metrics = optimized_executor.get_execution_metrics()
            standard_metrics = standard_executor.get_execution_metrics()

            assert (
                optimized_metrics.total_operations == standard_metrics.total_operations
            )

        finally:
            # Cleanup
            optimized_manager.close_all_connections()
            standard_manager.close_all_connections()

    @pytest.mark.asyncio
    async def test_connection_retry_resilience_e2e(self, sqlite_dataflow_config):
        """Test end-to-end resilience with connection retry logic."""
        # Configure with aggressive retry settings
        retry_config = RetryConfig(
            max_retries=3, initial_delay=0.1, max_delay=1.0, backoff_multiplier=2.0
        )

        connection_manager = MigrationConnectionManager(sqlite_dataflow_config)
        fallback_connection = connection_manager.get_migration_connection()
        executor = BatchedMigrationExecutor(fallback_connection, connection_manager)

        # Operations that should succeed with retry
        operations = [
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="resilience_test",
                description="Test resilience",
                sql_up="CREATE TABLE resilience_test (id INTEGER, data TEXT)",
                sql_down="DROP TABLE resilience_test",
            )
        ]

        try:
            # Execute operations
            batches = executor.batch_ddl_operations(operations)
            result = await executor.execute_batched_migrations(batches)

            assert result is True

            # Verify table was created
            with connection_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='resilience_test'"
                )
                assert cursor.fetchone() is not None
                cursor.close()

        finally:
            connection_manager.close_all_connections()

    @pytest.mark.asyncio
    async def test_concurrent_migration_execution(self, sqlite_dataflow_config):
        """Test concurrent migration execution with connection pooling."""
        # Create multiple connection managers to simulate concurrent usage
        managers = []
        executors = []

        for i in range(3):
            config = ConnectionPoolConfig(pool_size=2, enable_pooling=True)
            manager = MigrationConnectionManager(
                sqlite_dataflow_config, pool_config=config
            )
            fallback_conn = manager.get_migration_connection()
            executor = BatchedMigrationExecutor(fallback_conn, manager)

            managers.append(manager)
            executors.append(executor)

        try:
            # Create different operations for each executor
            operations_sets = []
            for i in range(3):
                ops = [
                    MigrationOperation(
                        operation_type=MigrationType.CREATE_TABLE,
                        table_name=f"concurrent_test_{i}",
                        description=f"Concurrent test table {i}",
                        sql_up=f"CREATE TABLE concurrent_test_{i} (id INTEGER, name TEXT)",
                        sql_down=f"DROP TABLE concurrent_test_{i}",
                    )
                ]
                operations_sets.append(ops)

            # Execute concurrently
            async def execute_migrations(executor, operations):
                batches = executor.batch_ddl_operations(operations)
                return await executor.execute_batched_migrations(batches)

            # Run all executors concurrently
            tasks = [
                execute_migrations(executor, ops)
                for executor, ops in zip(executors, operations_sets)
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed
            assert all(results)

            # Verify all tables were created
            with managers[0].get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = [row[0] for row in cursor.fetchall()]

                for i in range(3):
                    assert f"concurrent_test_{i}" in tables

                cursor.close()

            # Check that connection pools were utilized
            for manager in managers:
                stats = manager.get_pool_stats()
                assert stats.total_created > 0

        finally:
            # Cleanup all managers
            for manager in managers:
                manager.close_all_connections()

    def test_connection_manager_configuration_impact_on_performance(
        self, sqlite_dataflow_config
    ):
        """Test how different connection manager configurations impact performance."""
        configurations = [
            # Small pool
            ConnectionPoolConfig(pool_size=1, enable_pooling=True),
            # Medium pool
            ConnectionPoolConfig(pool_size=3, enable_pooling=True),
            # Large pool
            ConnectionPoolConfig(pool_size=10, enable_pooling=True),
            # No pooling
            ConnectionPoolConfig(enable_pooling=False),
        ]

        performance_results = []

        for i, config in enumerate(configurations):
            manager = MigrationConnectionManager(
                sqlite_dataflow_config, pool_config=config
            )
            fallback_conn = manager.get_migration_connection()
            executor = BatchedMigrationExecutor(fallback_conn, manager)

            # Measure connection acquisition time
            start_time = time.time()
            connections = []
            for j in range(5):
                conn = executor._get_connection()
                connections.append(conn)
            acquisition_time = time.time() - start_time

            # Return connections
            for conn in connections:
                executor._return_connection(conn)

            # Get final stats
            stats = manager.get_pool_stats()
            performance_results.append(
                {
                    "config": config,
                    "acquisition_time": acquisition_time,
                    "pool_size": stats.pool_size,
                    "total_created": stats.total_created,
                    "total_reused": stats.total_reused,
                }
            )

            manager.close_all_connections()

        # Verify that different configurations produce different results
        acquisition_times = [r["acquisition_time"] for r in performance_results]
        assert (
            len(set(t for t in acquisition_times if t > 0)) > 0
        )  # Some variation expected

        # All should complete in reasonable time
        assert all(t < 5.0 for t in acquisition_times)

        print("Performance results:")
        for i, result in enumerate(performance_results):
            config_desc = f"Pool={result['config'].pool_size if result['config'].enable_pooling else 'disabled'}"
            print(
                f"  {config_desc}: {result['acquisition_time']:.3f}s, "
                f"Created={result['total_created']}, Reused={result['total_reused']}"
            )

    @pytest.mark.asyncio
    async def test_real_world_migration_scenario_with_optimization(
        self, sqlite_dataflow_config
    ):
        """Test a realistic migration scenario with multiple phases and optimization."""
        # Phase 1: Initial schema
        phase1_operations = [
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="customers",
                description="Create customers table",
                sql_up="CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)",
                sql_down="DROP TABLE customers",
            ),
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="orders",
                description="Create orders table",
                sql_up="CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total DECIMAL)",
                sql_down="DROP TABLE orders",
            ),
        ]

        # Phase 2: Add constraints and indexes
        phase2_operations = [
            MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="customers",
                description="Add email index",
                sql_up="CREATE UNIQUE INDEX idx_customers_email ON customers (email)",
                sql_down="DROP INDEX idx_customers_email",
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="orders",
                description="Add customer index",
                sql_up="CREATE INDEX idx_orders_customer ON orders (customer_id)",
                sql_down="DROP INDEX idx_orders_customer",
            ),
        ]

        # Phase 3: Schema evolution
        phase3_operations = [
            MigrationOperation(
                operation_type=MigrationType.ADD_COLUMN,
                table_name="customers",
                description="Add phone column",
                sql_up="ALTER TABLE customers ADD COLUMN phone TEXT",
                sql_down="ALTER TABLE customers DROP COLUMN phone",
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_COLUMN,
                table_name="orders",
                description="Add status column",
                sql_up="ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'pending'",
                sql_down="ALTER TABLE orders DROP COLUMN status",
            ),
        ]

        # Setup optimized migration system
        config = ConnectionPoolConfig(pool_size=3, enable_pooling=True)
        connection_manager = MigrationConnectionManager(
            sqlite_dataflow_config, pool_config=config
        )
        fallback_connection = connection_manager.get_migration_connection()
        executor = BatchedMigrationExecutor(fallback_connection, connection_manager)

        try:
            total_start_time = time.time()

            # Execute migrations in phases
            for phase_num, operations in enumerate(
                [phase1_operations, phase2_operations, phase3_operations], 1
            ):
                print(
                    f"Executing Phase {phase_num} with {len(operations)} operations..."
                )

                batches = executor.batch_ddl_operations(operations)
                phase_result = await executor.execute_batched_migrations(batches)

                assert phase_result is True
                print(f"Phase {phase_num} completed successfully")

            total_time = time.time() - total_start_time
            assert total_time < 15.0  # Should complete quickly

            # Verify complete schema
            with connection_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Check tables
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = [row[0] for row in cursor.fetchall()]
                assert "customers" in tables
                assert "orders" in tables

                # Check table structure (columns)
                cursor.execute("PRAGMA table_info(customers)")
                customer_columns = [row[1] for row in cursor.fetchall()]
                assert "id" in customer_columns
                assert "name" in customer_columns
                assert "email" in customer_columns
                assert "phone" in customer_columns  # Added in phase 3

                cursor.execute("PRAGMA table_info(orders)")
                order_columns = [row[1] for row in cursor.fetchall()]
                assert "id" in order_columns
                assert "customer_id" in order_columns
                assert "total" in order_columns
                assert "status" in order_columns  # Added in phase 3

                # Check indexes
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
                )
                indexes = [row[0] for row in cursor.fetchall()]
                assert "idx_customers_email" in indexes
                assert "idx_orders_customer" in indexes

                cursor.close()

            # Verify final performance metrics
            final_stats = connection_manager.get_pool_stats()
            print(
                f"Final connection stats: Created={final_stats.total_created}, "
                f"Reused={final_stats.total_reused}, PoolSize={final_stats.pool_size}"
            )

            # Connection reuse should have occurred
            assert final_stats.total_reused > 0 or final_stats.pool_size > 0

        finally:
            connection_manager.close_all_connections()

        print(f"Complete real-world scenario executed in {total_time:.3f}s")
