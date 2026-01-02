"""Comprehensive integration tests for enterprise database connection pooling.

This test suite validates the production database adapters with real database
containers, covering PostgreSQL, MySQL, and SQLite with enterprise features.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pytest
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    CircuitBreakerState,
    DatabaseConfig,
    DatabasePoolCoordinator,
    DatabaseType,
    EnterpriseConnectionPool,
    HealthCheckResult,
    PoolMetrics,
    ProductionMySQLAdapter,
    ProductionPostgreSQLAdapter,
    ProductionSQLiteAdapter,
)
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow.builder import WorkflowBuilder

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def postgresql_config():
    """PostgreSQL test database configuration."""
    return {
        "database_type": "postgresql",
        "connection_string": os.getenv(
            "POSTGRESQL_TEST_URL",
            "postgresql://postgres:testpassword@localhost:5432/testdb",
        ),
        "pool_size": 5,
        "max_pool_size": 10,
        "enable_analytics": True,
        "enable_adaptive_sizing": True,
        "health_check_interval": 5,
        "min_pool_size": 2,
    }


@pytest.fixture
def mysql_config():
    """MySQL test database configuration."""
    return {
        "database_type": "mysql",
        "connection_string": os.getenv(
            "MYSQL_TEST_URL", "mysql://root:testpassword@localhost:3306/testdb"
        ),
        "pool_size": 5,
        "max_pool_size": 10,
        "enable_analytics": True,
        "enable_adaptive_sizing": True,
        "health_check_interval": 5,
        "min_pool_size": 2,
    }


@pytest.fixture
def sqlite_config(tmp_path):
    """SQLite test database configuration."""
    db_path = tmp_path / "test_enterprise.db"
    return {
        "database_type": "sqlite",
        "connection_string": f"sqlite:///{db_path}",
        "max_pool_size": 5,
        "enable_analytics": True,
        "enable_adaptive_sizing": False,  # SQLite doesn't benefit from adaptive sizing
        "health_check_interval": 10,
        "min_pool_size": 1,
    }


@pytest.fixture
async def setup_test_tables():
    """Setup test tables for all database types."""
    create_tables_sql = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            stock_count INTEGER DEFAULT 0
        )
        """,
    ]

    # SQLite version (different syntax)
    sqlite_tables_sql = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            stock_count INTEGER DEFAULT 0
        )
        """,
    ]

    return {
        "postgresql": create_tables_sql,
        "mysql": create_tables_sql,
        "sqlite": sqlite_tables_sql,
    }


class TestEnterpriseConnectionPool:
    """Test enterprise connection pool features."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlite"])
    async def test_basic_pool_creation(self, db_type, request):
        """Test basic pool creation and initialization."""
        config = request.getfixturevalue(f"{db_type}_config")

        # Skip if database not available
        if not await self._is_database_available(config):
            pytest.skip(f"{db_type.title()} database not available")

        db_config = self._create_database_config(config)
        adapter_classes = {
            "postgresql": ProductionPostgreSQLAdapter,
            "mysql": ProductionMySQLAdapter,
            "sqlite": ProductionSQLiteAdapter,
        }

        pool = EnterpriseConnectionPool(
            pool_id=f"test_{db_type}_pool",
            database_config=db_config,
            adapter_class=adapter_classes[db_type],
            min_size=config.get("min_pool_size", 1),
            max_size=config.get("max_pool_size", 5),
            enable_analytics=True,
            enable_adaptive_sizing=config.get("enable_adaptive_sizing", True),
        )

        try:
            # Initialize pool
            await pool.initialize()
            assert pool._adapter is not None
            assert pool._pool is not None

            # Test basic metrics
            metrics = pool.get_metrics()
            assert isinstance(metrics, PoolMetrics)
            assert metrics.pool_created_at is not None
            assert metrics.max_connections >= config.get("min_pool_size", 1)

            # Test health check
            health = await pool.health_check()
            assert isinstance(health, HealthCheckResult)
            assert health.is_healthy
            assert health.latency_ms >= 0

            logger.info(
                f"{db_type.title()} pool created successfully: {metrics.to_dict()}"
            )

        finally:
            await pool.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlite"])
    async def test_query_execution_with_monitoring(
        self, db_type, request, setup_test_tables
    ):
        """Test query execution with performance monitoring."""
        config = request.getfixturevalue(f"{db_type}_config")

        if not await self._is_database_available(config):
            pytest.skip(f"{db_type.title()} database not available")

        db_config = self._create_database_config(config)
        adapter_classes = {
            "postgresql": ProductionPostgreSQLAdapter,
            "mysql": ProductionMySQLAdapter,
            "sqlite": ProductionSQLiteAdapter,
        }

        pool = EnterpriseConnectionPool(
            pool_id=f"test_{db_type}_query_pool",
            database_config=db_config,
            adapter_class=adapter_classes[db_type],
            enable_analytics=True,
        )

        try:
            await pool.initialize()

            # Setup test table
            table_sql = setup_test_tables[db_type][0]
            await pool.execute_query(table_sql)

            # Test insert operations
            insert_queries = [
                (
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    ("Alice", "alice@example.com"),
                ),
                (
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    ("Bob", "bob@example.com"),
                ),
                (
                    "INSERT INTO users (name, email) VALUES (?, ?)",
                    ("Charlie", "charlie@example.com"),
                ),
            ]

            for query, params in insert_queries:
                await pool.execute_query(query, params)

            # Test select operations
            users = await pool.execute_query("SELECT COUNT(*) as count FROM users")
            assert len(users) > 0

            # Check metrics were recorded
            metrics = pool.get_metrics()
            assert metrics.total_queries >= 4  # 1 CREATE + 3 INSERT + 1 SELECT
            assert metrics.avg_query_time > 0

            # Check analytics summary
            analytics = pool.get_analytics_summary()
            assert "pool_id" in analytics
            assert "metrics" in analytics
            assert analytics["metrics"]["total_queries"] >= 4

            logger.info(f"{db_type.title()} query monitoring: {analytics}")

        finally:
            await pool.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "db_type", ["postgresql", "mysql"]
    )  # Skip SQLite for adaptive sizing
    async def test_adaptive_pool_sizing(self, db_type, request):
        """Test adaptive pool sizing based on workload."""
        config = request.getfixturevalue(f"{db_type}_config")

        if not await self._is_database_available(config):
            pytest.skip(f"{db_type.title()} database not available")

        db_config = self._create_database_config(config)
        adapter_classes = {
            "postgresql": ProductionPostgreSQLAdapter,
            "mysql": ProductionMySQLAdapter,
        }

        pool = EnterpriseConnectionPool(
            pool_id=f"test_{db_type}_adaptive_pool",
            database_config=db_config,
            adapter_class=adapter_classes[db_type],
            min_size=2,
            max_size=8,
            enable_analytics=True,
            enable_adaptive_sizing=True,
        )

        try:
            await pool.initialize()

            # Simulate high load
            tasks = []
            for i in range(20):
                task = asyncio.create_task(
                    pool.execute_query(
                        "SELECT pg_sleep(0.1)"
                        if db_type == "postgresql"
                        else "SELECT SLEEP(0.1)"
                    )
                )
                tasks.append(task)

            # Wait for some tasks to complete
            await asyncio.sleep(1)

            # Check if usage history is being tracked
            analytics = pool.get_analytics_summary()
            assert "usage_history" in analytics

            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()

            # Wait for adaptive sizing to potentially trigger
            await asyncio.sleep(2)

            # Check if any adaptive sizing decisions were made
            final_analytics = pool.get_analytics_summary()
            logger.info(
                f"{db_type.title()} adaptive sizing analytics: {final_analytics}"
            )

            # Verify analytics contains expected data
            assert final_analytics["pool_config"]["min_size"] == 2
            assert final_analytics["pool_config"]["max_size"] == 8

        finally:
            await pool.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlite"])
    async def test_circuit_breaker_functionality(self, db_type, request):
        """Test circuit breaker functionality with connection failures."""
        config = request.getfixturevalue(f"{db_type}_config")

        if not await self._is_database_available(config):
            pytest.skip(f"{db_type.title()} database not available")

        # Create config with invalid connection to trigger failures
        invalid_config = config.copy()
        if db_type == "postgresql":
            invalid_config["connection_string"] = (
                "postgresql://invalid:invalid@localhost:9999/invalid"
            )
        elif db_type == "mysql":
            invalid_config["connection_string"] = (
                "mysql://invalid:invalid@localhost:9999/invalid"
            )
        else:  # sqlite
            invalid_config["connection_string"] = "sqlite:///invalid/path/db.sqlite"

        db_config = self._create_database_config(invalid_config)
        adapter_classes = {
            "postgresql": ProductionPostgreSQLAdapter,
            "mysql": ProductionMySQLAdapter,
            "sqlite": ProductionSQLiteAdapter,
        }

        pool = EnterpriseConnectionPool(
            pool_id=f"test_{db_type}_circuit_breaker_pool",
            database_config=db_config,
            adapter_class=adapter_classes[db_type],
        )

        try:
            # This should fail and trigger circuit breaker
            with pytest.raises(Exception):
                await pool.initialize()

            # Circuit breaker should be open now
            breaker_state = pool._circuit_breaker.get_state()
            logger.info(f"{db_type.title()} circuit breaker state: {breaker_state}")

            # Verify circuit breaker has recorded failures
            assert breaker_state["failure_count"] > 0

        finally:
            await pool.close()

    async def _is_database_available(self, config: Dict[str, Any]) -> bool:
        """Check if database is available for testing."""
        try:
            # Create a simple adapter to test connection
            db_config = self._create_database_config(config)

            if config["database_type"] == "postgresql":
                adapter = ProductionPostgreSQLAdapter(db_config)
            elif config["database_type"] == "mysql":
                adapter = ProductionMySQLAdapter(db_config)
            else:  # sqlite
                adapter = ProductionSQLiteAdapter(db_config)

            await adapter.connect()
            await adapter.disconnect()
            return True
        except Exception as e:
            logger.warning(f"Database {config['database_type']} not available: {e}")
            return False

    def _create_database_config(self, config: Dict[str, Any]) -> DatabaseConfig:
        """Create DatabaseConfig from test config."""
        db_type = DatabaseType(config["database_type"])
        return DatabaseConfig(
            type=db_type,
            connection_string=config["connection_string"],
            pool_size=config.get("pool_size", 5),
            max_pool_size=config.get("max_pool_size", 10),
            command_timeout=config.get("timeout", 60.0),
            enable_analytics=config.get("enable_analytics", True),
            enable_adaptive_sizing=config.get("enable_adaptive_sizing", True),
            health_check_interval=config.get("health_check_interval", 30),
            min_pool_size=config.get("min_pool_size", 5),
        )


class TestDatabasePoolCoordinator:
    """Test database pool coordinator functionality."""

    @pytest.mark.asyncio
    async def test_pool_coordinator_creation_and_management(self, sqlite_config):
        """Test pool coordinator creation and basic pool management."""
        coordinator = DatabasePoolCoordinator()

        try:
            db_config = DatabaseConfig(
                type=DatabaseType.SQLITE,
                connection_string=sqlite_config["connection_string"],
                enable_analytics=True,
            )

            # Create pool through coordinator
            pool = await coordinator.get_or_create_pool(
                pool_id="test_coordinator_pool",
                database_config=db_config,
                adapter_type="sqlite",
            )

            assert pool is not None
            assert coordinator.get_active_pool_count() == 1

            # Get same pool again (should reuse)
            pool2 = await coordinator.get_or_create_pool(
                pool_id="test_coordinator_pool",
                database_config=db_config,
                adapter_type="sqlite",
            )

            assert pool is pool2
            assert coordinator.get_active_pool_count() == 1

            # Test pool metrics
            metrics = await coordinator.get_pool_metrics("test_coordinator_pool")
            assert "test_coordinator_pool" in metrics

            # Test health check
            health_results = await coordinator.health_check_all()
            assert "test_coordinator_pool" in health_results
            assert health_results["test_coordinator_pool"].is_healthy

            # Test pool summary
            summary = coordinator.get_pool_summary()
            assert summary["active_pools"] == 1
            assert "test_coordinator_pool" in summary["pool_ids"]

        finally:
            await coordinator.close_all_pools()

    @pytest.mark.asyncio
    async def test_pool_coordinator_with_multiple_databases(
        self, sqlite_config, tmp_path
    ):
        """Test coordinator managing multiple database pools."""
        coordinator = DatabasePoolCoordinator()

        try:
            # Create multiple SQLite databases
            db1_path = tmp_path / "test1.db"
            db2_path = tmp_path / "test2.db"

            configs = [
                DatabaseConfig(
                    type=DatabaseType.SQLITE,
                    connection_string=f"sqlite:///{db1_path}",
                    enable_analytics=True,
                ),
                DatabaseConfig(
                    type=DatabaseType.SQLITE,
                    connection_string=f"sqlite:///{db2_path}",
                    enable_analytics=True,
                ),
            ]

            pool_ids = ["pool_1", "pool_2"]

            # Create multiple pools
            pools = []
            for i, (pool_id, db_config) in enumerate(zip(pool_ids, configs)):
                pool = await coordinator.get_or_create_pool(
                    pool_id=pool_id, database_config=db_config, adapter_type="sqlite"
                )
                pools.append(pool)

            assert coordinator.get_active_pool_count() == 2

            # Test all pools health
            health_results = await coordinator.health_check_all()
            assert len(health_results) == 2
            for pool_id in pool_ids:
                assert health_results[pool_id].is_healthy

            # Test metrics for all pools
            all_metrics = await coordinator.get_pool_metrics()
            assert len(all_metrics) == 2

            # Close specific pool
            closed = await coordinator.close_pool("pool_1")
            assert closed
            assert coordinator.get_active_pool_count() == 1

            # Try to close non-existent pool
            closed = await coordinator.close_pool("non_existent")
            assert not closed

        finally:
            await coordinator.close_all_pools()

    @pytest.mark.asyncio
    async def test_pool_coordinator_idle_cleanup(self, sqlite_config):
        """Test idle pool cleanup functionality."""
        coordinator = DatabasePoolCoordinator()

        try:
            db_config = DatabaseConfig(
                type=DatabaseType.SQLITE,
                connection_string=sqlite_config["connection_string"],
                enable_analytics=True,
            )

            # Create pool
            pool = await coordinator.get_or_create_pool(
                pool_id="idle_test_pool",
                database_config=db_config,
                adapter_type="sqlite",
            )

            # Manually set last_used to old time to simulate idle pool
            metrics = pool.get_metrics()
            metrics.pool_last_used = datetime.now() - timedelta(hours=2)

            # Run cleanup with 1 hour timeout
            cleaned_up = await coordinator.cleanup_idle_pools(idle_timeout=3600)

            # Should have cleaned up the idle pool
            assert cleaned_up == 1
            assert coordinator.get_active_pool_count() == 0

        finally:
            await coordinator.close_all_pools()


class TestAsyncSQLDatabaseNodeEnterprise:
    """Test AsyncSQLDatabaseNode with enterprise features."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlite"])
    async def test_node_with_enterprise_adapters(
        self, db_type, request, setup_test_tables
    ):
        """Test AsyncSQLDatabaseNode uses enterprise adapters."""
        config = request.getfixturevalue(f"{db_type}_config")

        if not await self._is_database_available(config):
            pytest.skip(f"{db_type.title()} database not available")

        # Create node with enterprise features enabled
        node = AsyncSQLDatabaseNode(**config)

        try:
            # Test table creation
            table_sql = setup_test_tables[db_type][0]

            # Execute table creation through workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode", "create_table", {**config, "query": table_sql}
            )

            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())

            assert "create_table" in results

            # Verify adapter has enterprise features
            await node._get_or_create_adapter()
            assert node._adapter is not None

            # Check if it's a production adapter
            expected_types = {
                "postgresql": ProductionPostgreSQLAdapter,
                "mysql": ProductionMySQLAdapter,
                "sqlite": ProductionSQLiteAdapter,
            }

            assert isinstance(node._adapter, expected_types[db_type])

            # Test enterprise features if available
            if hasattr(node._adapter, "get_pool_metrics"):
                metrics = node._adapter.get_pool_metrics()
                if metrics:
                    assert isinstance(metrics, PoolMetrics)
                    logger.info(f"{db_type.title()} node metrics: {metrics.to_dict()}")

            if hasattr(node._adapter, "health_check"):
                health = await node._adapter.health_check()
                assert isinstance(health, HealthCheckResult)
                logger.info(
                    f"{db_type.title()} node health: healthy={health.is_healthy}"
                )

        finally:
            if node._adapter:
                await node._adapter.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlite"])
    async def test_enterprise_node_workflow_execution(
        self, db_type, request, setup_test_tables
    ):
        """Test full workflow execution with enterprise database features."""
        config = request.getfixturevalue(f"{db_type}_config")

        if not await self._is_database_available(config):
            pytest.skip(f"{db_type.title()} database not available")

        workflow = WorkflowBuilder()

        # Setup table
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "setup_table",
            {**config, "query": setup_test_tables[db_type][0]},
        )

        # Insert test data
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_user",
            {
                **config,
                "query": "INSERT INTO users (name, email) VALUES (?, ?)",
                "params": ["Enterprise Test User", "enterprise@example.com"],
            },
        )

        # Query data
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "query_users",
            {
                **config,
                "query": "SELECT * FROM users WHERE email = ?",
                "params": ["enterprise@example.com"],
            },
        )

        # Execute workflow
        runtime = LocalRuntime(enable_monitoring=True)
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert "setup_table" in results
        assert "insert_user" in results
        assert "query_users" in results

        query_result = results["query_users"]
        assert len(query_result) == 1
        assert query_result[0]["name"] == "Enterprise Test User"
        assert query_result[0]["email"] == "enterprise@example.com"

        logger.info(f"{db_type.title()} enterprise workflow completed successfully")

    async def _is_database_available(self, config: Dict[str, Any]) -> bool:
        """Check if database is available for testing."""
        try:
            node = AsyncSQLDatabaseNode(**config)
            await node._get_or_create_adapter()
            if node._adapter:
                await node._adapter.disconnect()
            return True
        except Exception as e:
            logger.warning(f"Database {config['database_type']} not available: {e}")
            return False


# Integration test markers and configuration
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


if __name__ == "__main__":
    # Run tests with proper async handling
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "-k",
            "test_basic_pool_creation",  # Run a basic test
        ]
    )
