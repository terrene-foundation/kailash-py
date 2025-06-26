"""Example demonstrating Phase 2 intelligent query routing and adaptive pooling.

This example shows how to use:
1. QueryRouterNode for intelligent query routing
2. Adaptive pool sizing based on workload
3. Pattern learning for optimization
4. Prepared statement caching
"""

import asyncio
import logging
from datetime import datetime

from kailash.core.local_runtime import LocalRuntime
from kailash.nodes.data.query_router import QueryRouterNode
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def simulate_workload(router, workload_type: str, duration_seconds: int = 30):
    """Simulate different workload patterns."""
    logger.info(f"Starting {workload_type} workload for {duration_seconds} seconds")

    start_time = datetime.now()
    query_count = 0
    errors = 0

    while (datetime.now() - start_time).total_seconds() < duration_seconds:
        try:
            if workload_type == "read_heavy":
                # 90% reads, 10% writes
                if query_count % 10 < 9:
                    result = await router.process(
                        {
                            "query": "SELECT * FROM products WHERE category = $1 AND price < $2",
                            "parameters": ["electronics", 1000],
                        }
                    )
                else:
                    result = await router.process(
                        {
                            "query": "UPDATE products SET views = views + 1 WHERE id = $1",
                            "parameters": [query_count],
                        }
                    )

            elif workload_type == "write_heavy":
                # 30% reads, 70% writes
                if query_count % 10 < 3:
                    result = await router.process(
                        {
                            "query": "SELECT stock FROM inventory WHERE product_id = $1",
                            "parameters": [query_count % 100],
                        }
                    )
                else:
                    result = await router.process(
                        {
                            "query": "INSERT INTO orders (user_id, product_id, quantity) VALUES ($1, $2, $3)",
                            "parameters": [query_count % 50, query_count % 100, 1],
                        }
                    )

            elif workload_type == "mixed_complex":
                # Mix of simple and complex queries
                query_type = query_count % 4

                if query_type == 0:
                    # Simple read
                    result = await router.process(
                        {
                            "query": "SELECT * FROM users WHERE id = $1",
                            "parameters": [query_count],
                        }
                    )
                elif query_type == 1:
                    # Complex read with JOIN
                    result = await router.process(
                        {
                            "query": """
                            SELECT u.name, COUNT(o.id) as order_count, SUM(o.total) as total_spent
                            FROM users u
                            LEFT JOIN orders o ON u.id = o.user_id
                            WHERE u.created_at > $1
                            GROUP BY u.id, u.name
                            HAVING COUNT(o.id) > 0
                        """,
                            "parameters": ["2024-01-01"],
                        }
                    )
                elif query_type == 2:
                    # Bulk insert
                    result = await router.process(
                        {
                            "query": """
                            INSERT INTO events (user_id, event_type, metadata)
                            VALUES ($1, $2, $3), ($4, $5, $6), ($7, $8, $9)
                        """,
                            "parameters": [
                                1,
                                "page_view",
                                "{}",
                                2,
                                "click",
                                "{}",
                                3,
                                "purchase",
                                "{}",
                            ],
                        }
                    )
                else:
                    # Transaction
                    session_id = f"session_{query_count}"

                    # BEGIN
                    await router.process({"query": "BEGIN", "session_id": session_id})

                    # Multiple operations
                    await router.process(
                        {
                            "query": "UPDATE inventory SET stock = stock - $1 WHERE product_id = $2",
                            "parameters": [1, query_count % 100],
                            "session_id": session_id,
                        }
                    )

                    await router.process(
                        {
                            "query": "INSERT INTO order_items (order_id, product_id, quantity) VALUES ($1, $2, $3)",
                            "parameters": [query_count, query_count % 100, 1],
                            "session_id": session_id,
                        }
                    )

                    # COMMIT
                    result = await router.process(
                        {"query": "COMMIT", "session_id": session_id}
                    )

            query_count += 1

            # Vary the rate
            if workload_type == "mixed_complex":
                await asyncio.sleep(0.05)  # 20 QPS
            else:
                await asyncio.sleep(0.01)  # 100 QPS

        except Exception as e:
            logger.error(f"Query error: {e}")
            errors += 1

    logger.info(
        f"Completed {workload_type} workload: {query_count} queries, {errors} errors"
    )
    return query_count, errors


async def main():
    """Demonstrate Phase 2 intelligent routing features."""
    runtime = LocalRuntime()

    # Create connection pool with all Phase 2 features enabled
    pool = WorkflowConnectionPool(
        name="adaptive_pool",
        database_type="postgresql",
        host="localhost",
        port=5432,
        database="test_db",
        user="postgres",
        password="postgres",
        min_connections=3,
        max_connections=20,
        adaptive_sizing=True,  # Enable adaptive pool sizing
        enable_query_routing=True,  # Enable pattern tracking
        health_threshold=60,
    )

    # Create query router with caching and pattern learning
    router = QueryRouterNode(
        name="smart_router",
        connection_pool="adaptive_pool",
        enable_read_write_split=True,  # Route reads to any connection
        cache_size=500,  # Cache up to 500 prepared statements
        pattern_learning=True,  # Learn query patterns
        health_threshold=50.0,
    )

    # Register nodes
    runtime.register_node("adaptive_pool", pool)
    runtime.register_node("smart_router", router)

    try:
        # Initialize pool
        logger.info("Initializing adaptive connection pool...")
        init_result = await pool.process({"operation": "initialize"})
        logger.info(f"Pool initialized: {init_result}")

        # Create schema for demo
        await setup_demo_schema(pool)

        # Simulate different workloads to demonstrate adaptive behavior

        # 1. Start with read-heavy workload
        logger.info("\n=== Phase 1: Read-Heavy Workload ===")
        await simulate_workload(router, "read_heavy", duration_seconds=20)

        # Check pool status
        pool_status = await pool.process({"operation": "stats"})
        logger.info(f"Pool stats after read-heavy: {pool_status['current_state']}")

        # Check router metrics
        router_metrics = await router.get_metrics()
        logger.info(f"Router metrics: {router_metrics['router_metrics']}")
        logger.info(f"Cache stats: {router_metrics['cache_stats']}")

        # 2. Switch to write-heavy workload
        logger.info("\n=== Phase 2: Write-Heavy Workload ===")
        await simulate_workload(router, "write_heavy", duration_seconds=20)

        # Pool should adapt to different workload
        pool_status = await pool.process({"operation": "stats"})
        logger.info(f"Pool stats after write-heavy: {pool_status['current_state']}")

        # 3. Complex mixed workload
        logger.info("\n=== Phase 3: Mixed Complex Workload ===")
        await simulate_workload(router, "mixed_complex", duration_seconds=30)

        # Final statistics
        logger.info("\n=== Final Statistics ===")

        # Pool statistics
        pool_stats = await pool.process({"operation": "stats"})
        logger.info("Connection Pool Statistics:")
        logger.info(
            f"  Total connections: {pool_stats['current_state']['total_connections']}"
        )
        logger.info(f"  Pool efficiency: {pool_stats['performance']}")
        logger.info(f"  Health status: {pool_stats['health']}")

        # Router statistics
        router_metrics = await router.get_metrics()
        logger.info("\nQuery Router Statistics:")
        logger.info(
            f"  Queries routed: {router_metrics['router_metrics']['queries_routed']}"
        )
        logger.info(
            f"  Average routing time: {router_metrics['router_metrics']['avg_routing_time_ms']:.2f}ms"
        )
        logger.info(
            f"  Cache hit rate: {router_metrics['cache_stats']['hit_rate']:.2%}"
        )

        # Pattern learning insights
        if pool.query_pattern_tracker:
            logger.info("\nPattern Learning Insights:")

            # Get workload forecast
            forecast = pool.query_pattern_tracker.get_workload_forecast(
                horizon_minutes=5
            )
            logger.info(f"  Expected QPS next 5 min: {forecast['historical_qps']:.1f}")
            logger.info(f"  Recommended pool size: {forecast['recommended_pool_size']}")

            # Top query patterns
            patterns = []
            for (
                fingerprint,
                executions,
            ) in pool.query_pattern_tracker.execution_by_fingerprint.items():
                if len(executions) > 5:
                    pattern = pool.query_pattern_tracker.get_pattern(fingerprint)
                    if pattern:
                        patterns.append(
                            {
                                "query": fingerprint,
                                "frequency": pattern.frequency,
                                "avg_time": pattern.avg_execution_time,
                            }
                        )

            patterns.sort(key=lambda p: p["frequency"], reverse=True)
            logger.info(f"  Top query patterns: {len(patterns)}")
            for i, pattern in enumerate(patterns[:5]):
                logger.info(
                    f"    {i+1}. {pattern['query'][:50]}... "
                    f"({pattern['frequency']:.1f} qpm, {pattern['avg_time']:.1f}ms)"
                )

        # Adaptive controller history
        if pool.adaptive_controller:
            history = pool.adaptive_controller.get_adjustment_history()
            if history:
                logger.info("\nAdaptive Pool Adjustments:")
                for adjustment in history[-5:]:
                    logger.info(
                        f"  {adjustment['timestamp']}: {adjustment['action']} "
                        f"from {adjustment['from_size']} to {adjustment['to_size']} "
                        f"- {adjustment['reason']}"
                    )

    except Exception as e:
        logger.error(f"Error in demo: {e}")
        raise

    finally:
        # Cleanup
        logger.info("\nCleaning up...")
        await cleanup_demo_schema(pool)
        await pool._cleanup()


async def setup_demo_schema(pool):
    """Create demo tables."""
    conn_result = await pool.process({"operation": "acquire"})
    conn_id = conn_result["connection_id"]

    try:
        # Create tables
        queries = [
            "DROP TABLE IF EXISTS order_items CASCADE",
            "DROP TABLE IF EXISTS orders CASCADE",
            "DROP TABLE IF EXISTS inventory CASCADE",
            "DROP TABLE IF EXISTS products CASCADE",
            "DROP TABLE IF EXISTS events CASCADE",
            "DROP TABLE IF EXISTS users CASCADE",
            """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                category VARCHAR(50),
                price DECIMAL(10, 2),
                views INTEGER DEFAULT 0
            )
            """,
            """
            CREATE TABLE inventory (
                product_id INTEGER PRIMARY KEY REFERENCES products(id),
                stock INTEGER DEFAULT 0
            )
            """,
            """
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                total DECIMAL(10, 2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(id),
                product_id INTEGER REFERENCES products(id),
                quantity INTEGER DEFAULT 1
            )
            """,
            """
            CREATE TABLE events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                event_type VARCHAR(50),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Insert sample data
            "INSERT INTO users (name, email) SELECT 'User ' || i, 'user' || i || '@example.com' FROM generate_series(1, 100) i",
            "INSERT INTO products (name, category, price) SELECT 'Product ' || i, CASE WHEN i % 3 = 0 THEN 'electronics' WHEN i % 3 = 1 THEN 'clothing' ELSE 'books' END, (random() * 1000)::decimal(10,2) FROM generate_series(1, 200) i",
            "INSERT INTO inventory (product_id, stock) SELECT id, (random() * 100)::integer FROM products",
            "INSERT INTO orders (user_id, total) SELECT (random() * 99 + 1)::integer, (random() * 500)::decimal(10,2) FROM generate_series(1, 500) i",
        ]

        for query in queries:
            await pool.process(
                {"operation": "execute", "connection_id": conn_id, "query": query}
            )

    finally:
        await pool.process({"operation": "release", "connection_id": conn_id})


async def cleanup_demo_schema(pool):
    """Clean up demo tables."""
    try:
        conn_result = await pool.process({"operation": "acquire"})
        conn_id = conn_result["connection_id"]

        queries = [
            "DROP TABLE IF EXISTS order_items CASCADE",
            "DROP TABLE IF EXISTS orders CASCADE",
            "DROP TABLE IF EXISTS inventory CASCADE",
            "DROP TABLE IF EXISTS products CASCADE",
            "DROP TABLE IF EXISTS events CASCADE",
            "DROP TABLE IF EXISTS users CASCADE",
        ]

        for query in queries:
            await pool.process(
                {"operation": "execute", "connection_id": conn_id, "query": query}
            )

        await pool.process({"operation": "release", "connection_id": conn_id})
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
