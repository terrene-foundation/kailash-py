#!/usr/bin/env python3
"""
Enterprise Database Connection Pool Demo

This demo shows how to use the new enterprise database connection pooling
features with real database connections, health monitoring, and analytics.
"""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseConfig,
    DatabasePoolCoordinator,
    DatabaseType,
    EnterpriseConnectionPool,
    ProductionSQLiteAdapter,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def demo_basic_enterprise_pool():
    """Demonstrate basic enterprise connection pool features."""
    logger.info("=== Basic Enterprise Pool Demo ===")

    # Create temporary SQLite database
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
        db_path = temp_db.name

    try:
        # Create database configuration
        db_config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=f"sqlite:///{db_path}",
            enable_analytics=True,
            enable_adaptive_sizing=False,  # SQLite doesn't benefit from this
            health_check_interval=5,
            min_pool_size=1,
            max_pool_size=3,
        )

        # Create enterprise connection pool
        pool = EnterpriseConnectionPool(
            pool_id="demo_sqlite_pool",
            database_config=db_config,
            adapter_class=ProductionSQLiteAdapter,
            enable_analytics=True,
            health_check_interval=5,
        )

        # Initialize pool
        logger.info("Initializing enterprise connection pool...")
        await pool.initialize()

        # Create test table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS demo_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        await pool.execute_query(create_table_sql)
        logger.info("Created demo_users table")

        # Insert test data
        test_users = [
            ("Alice Johnson", "alice@example.com"),
            ("Bob Smith", "bob@example.com"),
            ("Charlie Brown", "charlie@example.com"),
        ]

        for name, email in test_users:
            await pool.execute_query(
                "INSERT INTO demo_users (name, email) VALUES (?, ?)", (name, email)
            )

        logger.info(f"Inserted {len(test_users)} test users")

        # Query data
        users = await pool.execute_query("SELECT * FROM demo_users")
        logger.info(f"Retrieved {len(users)} users: {[user['name'] for user in users]}")

        # Get pool metrics
        metrics = pool.get_metrics()
        logger.info(f"Pool metrics: {metrics.to_dict()}")

        # Perform health check
        health = await pool.health_check()
        logger.info(
            f"Health check: healthy={health.is_healthy}, latency={health.latency_ms:.2f}ms"
        )

        # Get comprehensive analytics
        analytics = pool.get_analytics_summary()
        logger.info("Pool analytics summary:")
        logger.info(f"  - Pool ID: {analytics['pool_id']}")
        logger.info(f"  - Current size: {analytics['pool_config']['current_size']}")
        logger.info(f"  - Total queries: {analytics['metrics']['total_queries']}")
        logger.info(
            f"  - Avg query time: {analytics['metrics']['avg_query_time']:.4f}s"
        )
        logger.info(
            f"  - Circuit breaker state: {analytics['circuit_breaker']['state']}"
        )

        return True

    finally:
        # Cleanup
        await pool.close()
        Path(db_path).unlink(missing_ok=True)
        logger.info("Cleaned up database and pool")


async def demo_pool_coordinator():
    """Demonstrate DatabasePoolCoordinator functionality."""
    logger.info("=== Pool Coordinator Demo ===")

    coordinator = DatabasePoolCoordinator()

    try:
        # Create multiple database pools
        pools = []
        db_paths = []

        for i in range(3):
            # Create temporary database
            temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=f"_db_{i}.db")
            db_path = temp_db.name
            temp_db.close()
            db_paths.append(db_path)

            # Create database config
            db_config = DatabaseConfig(
                type=DatabaseType.SQLITE,
                connection_string=f"sqlite:///{db_path}",
                enable_analytics=True,
            )

            # Create pool through coordinator
            pool = await coordinator.get_or_create_pool(
                pool_id=f"demo_pool_{i}",
                database_config=db_config,
                adapter_type="sqlite",
            )

            pools.append(pool)
            logger.info(f"Created pool {i}: demo_pool_{i}")

        logger.info(f"Active pools: {coordinator.get_active_pool_count()}")

        # Test each pool
        for i, pool in enumerate(pools):
            # Create table and insert data
            await pool.execute_query(
                f"""
                CREATE TABLE test_table_{i} (
                    id INTEGER PRIMARY KEY,
                    data TEXT
                )
            """
            )

            await pool.execute_query(
                f"INSERT INTO test_table_{i} (data) VALUES (?)", (f"Test data {i}",)
            )

        # Perform health checks on all pools
        health_results = await coordinator.health_check_all()
        logger.info("Health check results:")
        for pool_id, health in health_results.items():
            logger.info(
                f"  - {pool_id}: healthy={health.is_healthy}, latency={health.latency_ms:.2f}ms"
            )

        # Get metrics for all pools
        all_metrics = await coordinator.get_pool_metrics()
        logger.info("Pool metrics:")
        for pool_id, metrics in all_metrics.items():
            logger.info(f"  - {pool_id}: {metrics['metrics']['total_queries']} queries")

        # Get coordinator summary
        summary = coordinator.get_pool_summary()
        logger.info(f"Coordinator summary: {summary}")

        return True

    finally:
        # Cleanup
        await coordinator.close_all_pools()
        for db_path in db_paths:
            Path(db_path).unlink(missing_ok=True)
        logger.info("Cleaned up all pools and databases")


async def demo_async_sql_node_enterprise():
    """Demonstrate AsyncSQLDatabaseNode with enterprise features."""
    logger.info("=== AsyncSQLDatabaseNode Enterprise Demo ===")

    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
        db_path = temp_db.name

    try:
        # Configure node with enterprise features
        node_config = {
            "database_type": "sqlite",
            "connection_string": f"sqlite:///{db_path}",
            "enable_analytics": True,
            "enable_adaptive_sizing": False,
            "health_check_interval": 5,
            "min_pool_size": 1,
            "max_pool_size": 3,
            "circuit_breaker_enabled": True,
        }

        # Create workflow with multiple database operations
        workflow = WorkflowBuilder()

        # Setup table
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "setup",
            {
                **node_config,
                "query": """
                    CREATE TABLE enterprise_demo (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        value INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
            },
        )

        # Insert data
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert1",
            {
                **node_config,
                "query": "INSERT INTO enterprise_demo (name, value) VALUES (?, ?)",
                "params": ("Enterprise Test", 100),
            },
        )

        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert2",
            {
                **node_config,
                "query": "INSERT INTO enterprise_demo (name, value) VALUES (?, ?)",
                "params": ("Production Ready", 200),
            },
        )

        # Query data
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "query_all",
            {**node_config, "query": "SELECT * FROM enterprise_demo ORDER BY id"},
        )

        # Execute workflow with enterprise runtime
        logger.info("Executing workflow with enterprise features...")
        runtime = LocalRuntime(
            enable_monitoring=True,
            persistent_mode=True,  # Enable enterprise coordination
        )

        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        logger.info(f"Workflow executed in {execution_time:.3f}s")
        logger.info(f"Results: {len(results)} operations completed")

        # Display query results
        query_results = results.get("query_all", [])
        logger.info(f"Retrieved {len(query_results)} records:")
        for record in query_results:
            logger.info(
                f"  - ID: {record['id']}, Name: {record['name']}, Value: {record['value']}"
            )

        # Test enterprise monitoring features
        logger.info("\n=== Enterprise Monitoring Features ===")

        # Create a node instance to test monitoring
        test_node = AsyncSQLDatabaseNode(**node_config)

        try:
            # Get pool metrics
            metrics = await test_node.get_pool_metrics()
            if metrics:
                logger.info(f"Pool metrics: {metrics.to_dict()}")

            # Get pool analytics
            analytics = await test_node.get_pool_analytics()
            if analytics:
                logger.info(
                    f"Pool analytics: queries={analytics['metrics']['total_queries']}"
                )

            # Perform health check
            health = await test_node.health_check()
            if health:
                logger.info(f"Health check: healthy={health.is_healthy}")

            # Get comprehensive status
            status = await test_node.get_enterprise_status_summary()
            logger.info("Enterprise status summary:")
            logger.info(
                f"  - Features enabled: analytics={status['enterprise_features']['analytics_enabled']}"
            )
            logger.info(f"  - Pool health: {status['health_status']['is_healthy']}")
            logger.info(f"  - Adapter type: {status['adapter_type']}")
            logger.info(f"  - Runtime coordinated: {status['runtime_coordinated']}")

        finally:
            await test_node.cleanup()

        return True

    finally:
        Path(db_path).unlink(missing_ok=True)
        logger.info("Cleaned up test database")


async def demo_performance_monitoring():
    """Demonstrate performance monitoring and analytics."""
    logger.info("=== Performance Monitoring Demo ===")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
        db_path = temp_db.name

    try:
        db_config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=f"sqlite:///{db_path}",
            enable_analytics=True,
            health_check_interval=2,  # Frequent health checks
        )

        pool = EnterpriseConnectionPool(
            pool_id="performance_demo_pool",
            database_config=db_config,
            adapter_class=ProductionSQLiteAdapter,
            enable_analytics=True,
            health_check_interval=2,
        )

        await pool.initialize()

        # Setup test table
        await pool.execute_query(
            """
            CREATE TABLE perf_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                timestamp REAL
            )
        """
        )

        # Simulate workload with varying intensity
        logger.info("Simulating database workload...")

        for batch in range(5):
            batch_start = time.time()

            # Insert batch of data
            for i in range(10):
                await pool.execute_query(
                    "INSERT INTO perf_test (data, timestamp) VALUES (?, ?)",
                    (f"Batch {batch} Item {i}", time.time()),
                )

            # Query data
            await pool.execute_query("SELECT COUNT(*) as count FROM perf_test")

            batch_time = time.time() - batch_start
            logger.info(f"Batch {batch} completed in {batch_time:.3f}s")

            # Brief pause between batches
            await asyncio.sleep(0.5)

        # Wait for analytics to update
        await asyncio.sleep(3)

        # Get comprehensive analytics
        analytics = pool.get_analytics_summary()

        logger.info("Performance Analytics:")
        logger.info(f"  - Total queries: {analytics['metrics']['total_queries']}")
        logger.info(
            f"  - Average query time: {analytics['metrics']['avg_query_time']:.4f}s"
        )
        logger.info(
            f"  - Queries per second: {analytics['metrics']['queries_per_second']:.2f}"
        )
        logger.info(
            f"  - Health check successes: {analytics['metrics']['health_check_successes']}"
        )
        logger.info(
            f"  - Health check failures: {analytics['metrics']['health_check_failures']}"
        )

        # Show usage history
        if analytics["usage_history"]:
            logger.info("Recent usage history:")
            for usage in analytics["usage_history"][-3:]:  # Last 3 snapshots
                logger.info(
                    f"  - {usage['timestamp'][:19]}: {usage['active_connections']} connections, "
                    f"{usage['queries_per_second']:.2f} QPS"
                )

        return True

    finally:
        await pool.close()
        Path(db_path).unlink(missing_ok=True)


async def main():
    """Run all enterprise database pool demos."""
    logger.info("Starting Enterprise Database Pool Demo Suite")

    demos = [
        ("Basic Enterprise Pool", demo_basic_enterprise_pool),
        ("Pool Coordinator", demo_pool_coordinator),
        ("AsyncSQLDatabaseNode Enterprise", demo_async_sql_node_enterprise),
        ("Performance Monitoring", demo_performance_monitoring),
    ]

    results = {}

    for demo_name, demo_func in demos:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {demo_name}")
        logger.info("=" * 60)

        try:
            start_time = time.time()
            success = await demo_func()
            execution_time = time.time() - start_time

            results[demo_name] = {"success": success, "time": execution_time}

            logger.info(
                f"✅ {demo_name} completed successfully in {execution_time:.2f}s"
            )

        except Exception as e:
            results[demo_name] = {"success": False, "error": str(e)}
            logger.error(f"❌ {demo_name} failed: {e}")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("Demo Suite Summary")
    logger.info("=" * 60)

    successful = sum(1 for result in results.values() if result["success"])
    total = len(results)

    logger.info(f"Completed: {successful}/{total} demos successful")

    for demo_name, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        if result["success"]:
            logger.info(f"{status} {demo_name} ({result['time']:.2f}s)")
        else:
            logger.info(f"{status} {demo_name} - {result['error']}")

    if successful == total:
        logger.info("🎉 All enterprise database pool features working correctly!")
    else:
        logger.warning(f"⚠️  {total - successful} demos failed")

    return successful == total


if __name__ == "__main__":
    # Run the demo
    success = asyncio.run(main())
    exit(0 if success else 1)
