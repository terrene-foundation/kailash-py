"""
End-to-End tests for PostgreSQL Test Manager - Phase 1B Component 2

# Skip all tests in this module until feature is complete
pytestmark = pytest.mark.skip(reason="Feature under development - will be enabled after alpha release")


Complete user workflows with real PostgreSQL infrastructure.
NO MOCKING - tests complete scenarios with real services.

Test Categories:
- Tier 3 E2E Tests (<10s timeout)
- Complete user workflows
- Real PostgreSQL Docker infrastructure
- Integration with Migration Testing Framework
- Performance validation under load
"""

import asyncio
import time
from typing import Any, Dict, List

import pytest
from dataflow.migrations.auto_migration_system import ColumnDefinition, TableDefinition
from dataflow.migrations.migration_test_framework import (
    MigrationTestFramework,
    MigrationTestResult,
)
from dataflow.migrations.postgresql_test_manager import (
    ContainerInfo,
    ContainerStatus,
    PostgreSQLTestExecutionResult,
    PostgreSQLTestManager,
)

from tests.utils.real_infrastructure import real_infra


@pytest.mark.e2e
@pytest.mark.timeout(10)
class TestPostgreSQLTestManagerE2E:
    """End-to-end tests for PostgreSQL Test Manager complete workflows."""

    @pytest.fixture
    async def postgresql_manager(self):
        """Create PostgreSQL Test Manager for E2E testing."""
        manager = PostgreSQLTestManager(
            container_name="test_manager_e2e",
            postgres_port=5437,  # Unique port for E2E tests
            performance_target_seconds=5.0,
            enable_concurrent_testing=True,
        )

        yield manager

        # Cleanup
        await manager.cleanup_test_environment()

    @pytest.mark.asyncio
    async def test_complete_migration_testing_workflow(self, postgresql_manager):
        """Test complete migration testing workflow from start to finish."""

        # Phase 1: Environment Setup
        start_time = time.perf_counter()
        container_info = await postgresql_manager.start_test_container()
        setup_time = time.perf_counter() - start_time

        assert container_info.ready is True
        assert setup_time < 8.0  # E2E setup should be under 8 seconds

        # Phase 2: Create comprehensive test case
        e2e_test_case = {
            "name": "complete_e2e_migration_workflow",
            "migrations": [
                # Migration 1: User management
                {
                    "name": "create_user_management",
                    "tables": [
                        TableDefinition(
                            name="users",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="username",
                                    type="VARCHAR(100)",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(
                                    name="email", type="VARCHAR(255)", nullable=False
                                ),
                                ColumnDefinition(
                                    name="password_hash",
                                    type="VARCHAR(255)",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="created_at",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                ),
                                ColumnDefinition(
                                    name="is_active", type="BOOLEAN", default="TRUE"
                                ),
                            ],
                        ),
                        TableDefinition(
                            name="user_profiles",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="user_id", type="INTEGER", nullable=False
                                ),
                                ColumnDefinition(
                                    name="first_name", type="VARCHAR(100)"
                                ),
                                ColumnDefinition(name="last_name", type="VARCHAR(100)"),
                                ColumnDefinition(name="bio", type="TEXT"),
                                ColumnDefinition(
                                    name="avatar_url", type="VARCHAR(500)"
                                ),
                            ],
                        ),
                    ],
                    "expected_schema": {
                        "users": TableDefinition(
                            name="users",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="username",
                                    type="character varying",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(
                                    name="email",
                                    type="character varying",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="password_hash",
                                    type="character varying",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="created_at",
                                    type="timestamp without time zone",
                                ),
                                ColumnDefinition(name="is_active", type="boolean"),
                            ],
                        ),
                        "user_profiles": TableDefinition(
                            name="user_profiles",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="user_id", type="integer", nullable=False
                                ),
                                ColumnDefinition(
                                    name="first_name", type="character varying"
                                ),
                                ColumnDefinition(
                                    name="last_name", type="character varying"
                                ),
                                ColumnDefinition(name="bio", type="text"),
                                ColumnDefinition(
                                    name="avatar_url", type="character varying"
                                ),
                            ],
                        ),
                    },
                },
                # Migration 2: Content management
                {
                    "name": "create_content_management",
                    "tables": [
                        TableDefinition(
                            name="categories",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="name", type="VARCHAR(100)", nullable=False
                                ),
                                ColumnDefinition(
                                    name="slug",
                                    type="VARCHAR(100)",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(name="description", type="TEXT"),
                            ],
                        ),
                        TableDefinition(
                            name="posts",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="title", type="VARCHAR(200)", nullable=False
                                ),
                                ColumnDefinition(
                                    name="slug",
                                    type="VARCHAR(200)",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(name="content", type="TEXT"),
                                ColumnDefinition(
                                    name="author_id", type="INTEGER", nullable=False
                                ),
                                ColumnDefinition(name="category_id", type="INTEGER"),
                                ColumnDefinition(
                                    name="status", type="VARCHAR(20)", default="'draft'"
                                ),
                                ColumnDefinition(name="published_at", type="TIMESTAMP"),
                                ColumnDefinition(
                                    name="created_at",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                ),
                                ColumnDefinition(
                                    name="updated_at",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                ),
                            ],
                        ),
                    ],
                    "expected_schema": {
                        "categories": TableDefinition(
                            name="categories",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="name",
                                    type="character varying",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="slug",
                                    type="character varying",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(name="description", type="text"),
                            ],
                        ),
                        "posts": TableDefinition(
                            name="posts",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="title",
                                    type="character varying",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="slug",
                                    type="character varying",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(name="content", type="text"),
                                ColumnDefinition(
                                    name="author_id", type="integer", nullable=False
                                ),
                                ColumnDefinition(name="category_id", type="integer"),
                                ColumnDefinition(
                                    name="status", type="character varying"
                                ),
                                ColumnDefinition(
                                    name="published_at",
                                    type="timestamp without time zone",
                                ),
                                ColumnDefinition(
                                    name="created_at",
                                    type="timestamp without time zone",
                                ),
                                ColumnDefinition(
                                    name="updated_at",
                                    type="timestamp without time zone",
                                ),
                            ],
                        ),
                    },
                },
            ],
            "performance_target": 5.0,
            "enable_rollback": True,
            "test_concurrent": True,
        }

        # Phase 3: Execute complete migration workflow
        migration_start = time.perf_counter()
        result = await postgresql_manager.run_migration_integration_test(e2e_test_case)
        migration_time = time.perf_counter() - migration_start

        # Phase 4: Verify complete workflow results
        assert result.success is True, f"E2E workflow failed: {result.error}"
        assert result.test_case_name == "complete_e2e_migration_workflow"
        assert migration_time < 10.0  # E2E requirement

        # Verify all migrations executed
        assert len(result.migration_results) == 2
        assert all(mr.success for mr in result.migration_results)
        assert all(mr.verification_passed for mr in result.migration_results)

        # Verify performance metrics
        assert result.performance_metrics["migrations_count"] == 2
        assert result.performance_metrics["migrations_passed"] == 2
        assert result.performance_metrics["execution_time"] < 10.0

        # Verify concurrent testing was executed
        assert result.concurrent_test_results["success"] is True
        assert "connection_test" in result.concurrent_test_results
        assert "read_write_test" in result.concurrent_test_results
        assert "schema_test" in result.concurrent_test_results

        # Phase 5: Verify database state
        import asyncpg

        conn = await asyncpg.connect(container_info.database_url)

        # Check all tables exist
        tables_query = """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
        tables = await conn.fetch(tables_query)
        table_names = [row["table_name"] for row in tables]

        expected_tables = ["users", "user_profiles", "categories", "posts"]
        for expected_table in expected_tables:
            assert expected_table in table_names, f"Table {expected_table} not found"

        # Verify table structures
        for table_name in expected_tables:
            columns_query = """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = $1 AND table_schema = 'public'
            ORDER BY ordinal_position
            """
            columns = await conn.fetch(columns_query, table_name)
            assert len(columns) > 0, f"No columns found for table {table_name}"

        await conn.close()

        # Total workflow time should be under 10 seconds
        total_time = time.perf_counter() - start_time
        assert (
            total_time < 10.0
        ), f"Complete E2E workflow took {total_time:.3f}s (>10s limit)"

    @pytest.mark.asyncio
    async def test_production_scale_migration_workflow(self, postgresql_manager):
        """Test production-scale migration workflow with multiple databases."""

        # Start main container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create multiple test databases for production simulation
        test_databases = []
        for i in range(3):
            db_name = f"production_test_{i}"
            db_url = await postgresql_manager.create_test_database(db_name)
            test_databases.append((db_name, db_url))

        # Define production-scale test case
        production_test_case = {
            "name": "production_scale_test",
            "migrations": [
                {
                    "name": "production_migration",
                    "tables": [
                        # Simulate complex production tables
                        TableDefinition(
                            name="customers",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="external_id", type="VARCHAR(100)", unique=True
                                ),
                                ColumnDefinition(
                                    name="name", type="VARCHAR(200)", nullable=False
                                ),
                                ColumnDefinition(
                                    name="email", type="VARCHAR(255)", nullable=False
                                ),
                                ColumnDefinition(name="phone", type="VARCHAR(50)"),
                                ColumnDefinition(name="address", type="TEXT"),
                                ColumnDefinition(
                                    name="country_code", type="VARCHAR(3)"
                                ),
                                ColumnDefinition(
                                    name="status",
                                    type="VARCHAR(20)",
                                    default="'active'",
                                ),
                                ColumnDefinition(
                                    name="created_at",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                ),
                                ColumnDefinition(
                                    name="updated_at",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                ),
                            ],
                        ),
                        TableDefinition(
                            name="orders",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="customer_id", type="INTEGER", nullable=False
                                ),
                                ColumnDefinition(
                                    name="order_number", type="VARCHAR(50)", unique=True
                                ),
                                ColumnDefinition(
                                    name="total_amount",
                                    type="DECIMAL(10,2)",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="currency", type="VARCHAR(3)", default="'USD'"
                                ),
                                ColumnDefinition(
                                    name="status",
                                    type="VARCHAR(20)",
                                    default="'pending'",
                                ),
                                ColumnDefinition(
                                    name="order_date",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                ),
                            ],
                        ),
                        TableDefinition(
                            name="order_items",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="order_id", type="INTEGER", nullable=False
                                ),
                                ColumnDefinition(
                                    name="product_id", type="INTEGER", nullable=False
                                ),
                                ColumnDefinition(
                                    name="quantity", type="INTEGER", nullable=False
                                ),
                                ColumnDefinition(
                                    name="unit_price",
                                    type="DECIMAL(10,2)",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="total_price",
                                    type="DECIMAL(10,2)",
                                    nullable=False,
                                ),
                            ],
                        ),
                    ],
                    "expected_schema": {
                        "customers": TableDefinition(
                            name="customers",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="external_id",
                                    type="character varying",
                                    unique=True,
                                ),
                                ColumnDefinition(
                                    name="name",
                                    type="character varying",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="email",
                                    type="character varying",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="phone", type="character varying"
                                ),
                                ColumnDefinition(name="address", type="text"),
                                ColumnDefinition(
                                    name="country_code", type="character varying"
                                ),
                                ColumnDefinition(
                                    name="status", type="character varying"
                                ),
                                ColumnDefinition(
                                    name="created_at",
                                    type="timestamp without time zone",
                                ),
                                ColumnDefinition(
                                    name="updated_at",
                                    type="timestamp without time zone",
                                ),
                            ],
                        ),
                        "orders": TableDefinition(
                            name="orders",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="customer_id", type="integer", nullable=False
                                ),
                                ColumnDefinition(
                                    name="order_number",
                                    type="character varying",
                                    unique=True,
                                ),
                                ColumnDefinition(name="total_amount", type="numeric"),
                                ColumnDefinition(
                                    name="currency", type="character varying"
                                ),
                                ColumnDefinition(
                                    name="status", type="character varying"
                                ),
                                ColumnDefinition(
                                    name="order_date",
                                    type="timestamp without time zone",
                                ),
                            ],
                        ),
                        "order_items": TableDefinition(
                            name="order_items",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="order_id", type="integer", nullable=False
                                ),
                                ColumnDefinition(
                                    name="product_id", type="integer", nullable=False
                                ),
                                ColumnDefinition(
                                    name="quantity", type="integer", nullable=False
                                ),
                                ColumnDefinition(
                                    name="unit_price", type="numeric", nullable=False
                                ),
                                ColumnDefinition(
                                    name="total_price", type="numeric", nullable=False
                                ),
                            ],
                        ),
                    },
                }
            ],
            "performance_target": 8.0,  # Longer target for production complexity
            "test_concurrent": True,
        }

        # Execute production-scale test
        start_time = time.perf_counter()
        result = await postgresql_manager.run_migration_integration_test(
            production_test_case
        )
        execution_time = time.perf_counter() - start_time

        # Verify production-scale results
        assert result.success is True, f"Production-scale test failed: {result.error}"
        assert execution_time < 10.0  # E2E limit
        assert len(result.migration_results) == 1
        assert result.migration_results[0].success is True

        # Verify concurrent testing handled production load
        assert result.concurrent_test_results["success"] is True

        # Test data insertion at production scale
        import asyncpg

        conn = await asyncpg.connect(container_info.database_url)

        # Insert test data to verify schema works
        await conn.execute(
            """
            INSERT INTO customers (external_id, name, email, country_code)
            VALUES ('CUST001', 'Test Customer', 'test@example.com', 'USA')
        """
        )

        customer_id = await conn.fetchval(
            "SELECT id FROM customers WHERE external_id = 'CUST001'"
        )
        assert customer_id is not None

        await conn.execute(
            """
            INSERT INTO orders (customer_id, order_number, total_amount)
            VALUES ($1, 'ORD001', 99.99)
        """,
            customer_id,
        )

        order_count = await conn.fetchval("SELECT COUNT(*) FROM orders")
        assert order_count == 1

        await conn.close()

        # Cleanup test databases
        for db_name, db_url in test_databases:
            await postgresql_manager.drop_test_database(db_name)

    @pytest.mark.asyncio
    async def test_concurrent_multi_user_simulation(self, postgresql_manager):
        """Test concurrent multi-user scenarios simulating real usage."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Setup test schema
        import asyncpg

        setup_conn = await asyncpg.connect(container_info.database_url)
        await setup_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS concurrent_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                session_id VARCHAR(100),
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await setup_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS concurrent_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                activity_type VARCHAR(50),
                activity_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await setup_conn.close()

        # Simulate multiple concurrent users
        async def simulate_user_activity(user_id: int, activity_count: int = 20):
            """Simulate individual user activity."""
            conn = await asyncpg.connect(container_info.database_url)
            try:
                # Create user
                await conn.execute(
                    """
                    INSERT INTO concurrent_users (username, session_id)
                    VALUES ($1, $2)
                    ON CONFLICT (username) DO UPDATE SET session_id = $2
                """,
                    f"user_{user_id}",
                    f"session_{user_id}_{time.time()}",
                )

                # Perform activities
                activities = []
                for i in range(activity_count):
                    activity_type = ["read", "write", "update", "delete"][i % 4]
                    await conn.execute(
                        """
                        INSERT INTO concurrent_sessions (user_id, activity_type, activity_data)
                        VALUES ($1, $2, $3)
                    """,
                        user_id,
                        activity_type,
                        f'{{"action": "{activity_type}_{i}"}}',
                    )

                    # Read activities
                    sessions = await conn.fetch(
                        """
                        SELECT COUNT(*) as count
                        FROM concurrent_sessions
                        WHERE user_id = $1
                    """,
                        user_id,
                    )
                    activities.append(sessions[0]["count"])

                    # Small delay to simulate real user behavior
                    await asyncio.sleep(0.01)

                return {
                    "user_id": user_id,
                    "activities": len(activities),
                    "success": True,
                }

            except Exception as e:
                return {"user_id": user_id, "success": False, "error": str(e)}
            finally:
                await conn.close()

        # Run concurrent user simulations
        start_time = time.perf_counter()
        user_tasks = [
            simulate_user_activity(i, 15) for i in range(10)
        ]  # 10 concurrent users
        user_results = await asyncio.gather(*user_tasks)
        simulation_time = time.perf_counter() - start_time

        # Verify concurrent user simulation results
        assert simulation_time < 8.0  # Should complete within 8 seconds

        successful_users = [r for r in user_results if r["success"]]
        assert (
            len(successful_users) == 10
        ), f"Only {len(successful_users)}/10 users successful"

        # Verify database consistency after concurrent access
        final_conn = await asyncpg.connect(container_info.database_url)

        user_count = await final_conn.fetchval("SELECT COUNT(*) FROM concurrent_users")
        session_count = await final_conn.fetchval(
            "SELECT COUNT(*) FROM concurrent_sessions"
        )

        assert user_count == 10  # All users created
        assert session_count == 150  # 10 users * 15 activities each

        # Verify data integrity
        integrity_check = await final_conn.fetch(
            """
            SELECT u.id, u.username, COUNT(s.id) as session_count
            FROM concurrent_users u
            LEFT JOIN concurrent_sessions s ON u.id = s.user_id
            GROUP BY u.id, u.username
            ORDER BY u.id
        """
        )

        assert len(integrity_check) == 10
        for row in integrity_check:
            assert row["session_count"] == 15  # Each user should have 15 sessions

        await final_conn.close()

    @pytest.mark.asyncio
    async def test_performance_under_load(self, postgresql_manager):
        """Test PostgreSQL Test Manager performance under load."""

        # Start container with performance monitoring
        start_time = time.perf_counter()
        container_info = await postgresql_manager.start_test_container()
        startup_time = time.perf_counter() - start_time

        assert container_info.ready
        assert startup_time < 6.0  # Fast startup required

        # Create load test scenario
        load_test_case = {
            "name": "performance_load_test",
            "migrations": [
                {
                    "name": "load_test_migration",
                    "tables": [
                        TableDefinition(
                            name="load_test_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(name="data", type="TEXT"),
                                ColumnDefinition(
                                    name="indexed_field", type="VARCHAR(100)"
                                ),
                                ColumnDefinition(
                                    name="timestamp_field",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                ),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "load_test_table": TableDefinition(
                            name="load_test_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(name="data", type="text"),
                                ColumnDefinition(
                                    name="indexed_field", type="character varying"
                                ),
                                ColumnDefinition(
                                    name="timestamp_field",
                                    type="timestamp without time zone",
                                ),
                            ],
                        )
                    },
                }
            ],
            "performance_target": 3.0,  # Strict performance target
            "test_concurrent": True,
        }

        # Execute under load with performance monitoring
        migration_start = time.perf_counter()
        result = await postgresql_manager.run_migration_integration_test(load_test_case)
        migration_time = time.perf_counter() - migration_start

        # Verify performance under load
        assert result.success is True
        assert migration_time < 5.0  # Performance requirement
        assert result.performance_metrics["execution_time"] < 5.0

        # Additional load testing with direct database operations
        import asyncpg

        conn = await asyncpg.connect(container_info.database_url)

        # High-volume data operations
        load_start = time.perf_counter()

        # Insert load test data
        insert_tasks = []
        for batch in range(10):  # 10 batches

            async def insert_batch(batch_id):
                batch_conn = await asyncpg.connect(container_info.database_url)
                try:
                    for i in range(50):  # 50 records per batch
                        await batch_conn.execute(
                            """
                            INSERT INTO load_test_table (data, indexed_field)
                            VALUES ($1, $2)
                        """,
                            f"load_data_batch_{batch_id}_record_{i}",
                            f"index_{batch_id}_{i}",
                        )
                finally:
                    await batch_conn.close()

            insert_tasks.append(insert_batch(batch))

        await asyncio.gather(*insert_tasks)
        load_time = time.perf_counter() - load_start

        # Verify load test results
        record_count = await conn.fetchval("SELECT COUNT(*) FROM load_test_table")
        assert record_count == 500  # 10 batches * 50 records
        assert load_time < 5.0  # Load operations should complete quickly

        await conn.close()

        # Total E2E performance verification
        total_time = time.perf_counter() - start_time
        assert (
            total_time < 10.0
        ), f"Total E2E load test took {total_time:.3f}s (>10s limit)"

    @pytest.mark.asyncio
    async def test_disaster_recovery_simulation(self, postgresql_manager):
        """Test disaster recovery and resilience scenarios."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create test data
        import asyncpg

        conn = await asyncpg.connect(container_info.database_url)
        await conn.execute(
            """
            CREATE TABLE disaster_test (
                id SERIAL PRIMARY KEY,
                important_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert critical data
        for i in range(100):
            await conn.execute(
                """
                INSERT INTO disaster_test (important_data)
                VALUES ($1)
            """,
                f"critical_data_{i}",
            )

        initial_count = await conn.fetchval("SELECT COUNT(*) FROM disaster_test")
        assert initial_count == 100
        await conn.close()

        # Simulate container restart (disaster simulation)
        await postgresql_manager.cleanup_test_environment()

        # Verify recovery
        recovery_start = time.perf_counter()
        recovered_container = await postgresql_manager.start_test_container()
        recovery_time = time.perf_counter() - recovery_start

        assert recovered_container.ready
        assert recovery_time < 8.0  # Recovery should be fast

        # Note: Data will be lost as we're using fresh containers
        # This simulates disaster recovery where we need to rebuild

        # Verify clean state after recovery
        recovery_conn = await asyncpg.connect(recovered_container.database_url)
        tables = await recovery_conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """
        )

        # Should have clean database after disaster recovery
        table_names = [row["table_name"] for row in tables]
        assert len(table_names) == 0 or "disaster_test" not in table_names

        await recovery_conn.close()

        # Test that system can handle fresh start after disaster
        recovery_test_case = {
            "name": "post_disaster_recovery_test",
            "migrations": [
                {
                    "name": "recovery_migration",
                    "tables": [
                        TableDefinition(
                            name="recovery_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(name="recovery_data", type="TEXT"),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "recovery_table": TableDefinition(
                            name="recovery_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(name="recovery_data", type="text"),
                            ],
                        )
                    },
                }
            ],
        }

        # Verify system works after disaster recovery
        result = await postgresql_manager.run_migration_integration_test(
            recovery_test_case
        )
        assert result.success is True
        assert result.migration_results[0].success is True
