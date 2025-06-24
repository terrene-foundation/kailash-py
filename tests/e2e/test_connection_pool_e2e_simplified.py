"""Simplified E2E tests for WorkflowConnectionPool focused on essential functionality."""

import asyncio
import os
import random
import time
import uuid
from typing import Any, Dict, List

import pytest

from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool


@pytest.mark.e2e
@pytest.mark.asyncio
class TestConnectionPoolE2ESimplified:
    """Simplified E2E tests demonstrating real-world usage patterns."""

    @pytest.fixture
    def db_config(self):
        """Database configuration for E2E testing."""
        return {
            "name": "e2e_pool",
            "database_type": "postgresql",
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5433)),
            "database": os.getenv("POSTGRES_DB", "kailash_test"),
            "user": os.getenv("POSTGRES_USER", "admin"),
            "password": os.getenv("POSTGRES_PASSWORD", "admin"),
            "min_connections": 3,
            "max_connections": 10,
            "health_threshold": 70,
            "pre_warm": True,
        }

    async def test_simple_ecommerce_workflow(self, db_config):
        """
        Simplified e-commerce workflow demonstrating:
        - Connection pooling for high-throughput operations
        - Concurrent order processing
        - Transaction handling
        """
        pool = WorkflowConnectionPool(**db_config)
        await pool.process({"operation": "initialize"})

        # Setup simple schema
        setup_conn = await pool.process({"operation": "acquire"})
        conn_id = setup_conn["connection_id"]

        # Create simplified tables (separately for asyncpg)
        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn_id,
                "query": """
                CREATE TABLE IF NOT EXISTS simple_products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    price DECIMAL(10,2),
                    stock INT DEFAULT 0
                )
            """,
                "fetch_mode": "one",
            }
        )

        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn_id,
                "query": """
                CREATE TABLE IF NOT EXISTS simple_orders (
                    id SERIAL PRIMARY KEY,
                    product_id INT,
                    quantity INT,
                    total DECIMAL(10,2),
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """,
                "fetch_mode": "one",
            }
        )

        # Insert sample products
        products = [
            ("Laptop", 999.99, 20),
            ("Mouse", 29.99, 100),
            ("Keyboard", 79.99, 50),
        ]

        for name, price, stock in products:
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    INSERT INTO simple_products (name, price, stock)
                    VALUES ($1, $2::decimal, $3::int)
                """,
                    "params": [name, price, stock],
                    "fetch_mode": "one",
                }
            )

        await pool.process({"operation": "release", "connection_id": conn_id})

        # Process concurrent orders
        async def process_order(order_num: int):
            """Simulate order processing."""
            try:
                # Acquire connection
                conn = await pool.process({"operation": "acquire"})
                conn_id = conn["connection_id"]

                # Select random product
                products = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "SELECT * FROM simple_products WHERE stock > 0",
                        "fetch_mode": "all",
                    }
                )

                if not products["data"]:
                    return {"order": order_num, "status": "no_stock"}

                product = random.choice(products["data"])
                quantity = random.randint(1, min(3, product["stock"]))
                total = float(product["price"]) * quantity

                # Create order and update stock (simplified transaction)
                order_result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO simple_orders (product_id, quantity, total, status)
                        VALUES ($1::int, $2::int, $3::decimal, 'confirmed')
                        RETURNING id
                    """,
                        "params": [product["id"], quantity, total],
                        "fetch_mode": "one",
                    }
                )

                # Update stock
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        UPDATE simple_products
                        SET stock = stock - $2::int
                        WHERE id = $1::int
                    """,
                        "params": [product["id"], quantity],
                        "fetch_mode": "one",
                    }
                )

                # Release connection
                await pool.process({"operation": "release", "connection_id": conn_id})

                return {
                    "order": order_num,
                    "order_id": order_result["data"]["id"],
                    "product": product["name"],
                    "quantity": quantity,
                    "total": total,
                    "status": "success",
                }

            except Exception as e:
                return {"order": order_num, "status": "error", "error": str(e)}

        # Run concurrent orders
        num_orders = 30
        start_time = time.time()

        tasks = [process_order(i) for i in range(num_orders)]
        results = await asyncio.gather(*tasks)

        elapsed_time = time.time() - start_time

        # Analyze results
        successful = [r for r in results if r.get("status") == "success"]
        no_stock = [r for r in results if r.get("status") == "no_stock"]
        errors = [r for r in results if r.get("status") == "error"]

        # Get final stats
        stats_conn = await pool.process({"operation": "acquire"})
        final_stats = await pool.process(
            {
                "operation": "execute",
                "connection_id": stats_conn["connection_id"],
                "query": """
                SELECT
                    COUNT(*) as total_orders,
                    SUM(total) as revenue,
                    AVG(total) as avg_order_value
                FROM simple_orders
                WHERE status = 'confirmed'
            """,
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": stats_conn["connection_id"]}
        )

        pool_stats = await pool.process({"operation": "stats"})

        # Cleanup
        cleanup_conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS simple_orders CASCADE",
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS simple_products CASCADE",
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": cleanup_conn["connection_id"]}
        )

        await pool._cleanup()

        # Assertions
        assert len(successful) > 0  # At least some orders should succeed
        assert (
            pool_stats["queries"]["executed"] > num_orders * 2
        )  # Multiple queries per order
        assert pool_stats["connections"]["created"] <= db_config["max_connections"]
        assert elapsed_time < num_orders * 0.5  # Benefit from concurrent processing

        print(
            f"""
E-commerce Workflow Results:
- Total Orders: {num_orders}
- Successful: {len(successful)}
- No Stock: {len(no_stock)}
- Errors: {len(errors)}
- Total Revenue: ${final_stats['data']['revenue'] or 0:.2f}
- Avg Order Value: ${final_stats['data']['avg_order_value'] or 0:.2f}
- Execution Time: {elapsed_time:.2f}s
- Queries Executed: {pool_stats['queries']['executed']}
- Pool Efficiency: {pool_stats['queries']['executed'] / pool_stats['connections']['created']:.1f} queries/connection
        """
        )

    async def test_iot_sensor_processing(self, db_config):
        """
        IoT sensor data processing demonstrating:
        - High-frequency data ingestion
        - Real-time aggregation
        - Alert generation
        """
        pool = WorkflowConnectionPool(**db_config)
        await pool.process({"operation": "initialize"})

        # Setup schema
        setup_conn = await pool.process({"operation": "acquire"})

        # Create tables separately
        await pool.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": """
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id SERIAL PRIMARY KEY,
                    sensor_id VARCHAR(50),
                    value FLOAT,
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """,
                "fetch_mode": "one",
            }
        )

        await pool.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": """
                CREATE INDEX IF NOT EXISTS idx_sensor_time
                ON sensor_data(sensor_id, timestamp DESC)
            """,
                "fetch_mode": "one",
            }
        )

        await pool.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": """
                CREATE TABLE IF NOT EXISTS sensor_alerts (
                    id SERIAL PRIMARY KEY,
                    sensor_id VARCHAR(50),
                    alert_type VARCHAR(50),
                    value FLOAT,
                    threshold FLOAT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """,
                "fetch_mode": "one",
            }
        )

        await pool.process(
            {"operation": "release", "connection_id": setup_conn["connection_id"]}
        )

        # Simulate sensor data streams
        sensors = [f"sensor_{i}" for i in range(10)]
        alert_threshold = 80.0

        async def process_sensor_reading(reading_id: int):
            """Process a single sensor reading."""
            sensor_id = random.choice(sensors)
            value = random.uniform(20.0, 100.0)

            conn = await pool.process({"operation": "acquire"})
            conn_id = conn["connection_id"]

            try:
                # Insert reading
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO sensor_data (sensor_id, value)
                        VALUES ($1, $2::float)
                    """,
                        "params": [sensor_id, value],
                        "fetch_mode": "one",
                    }
                )

                # Check if alert needed
                if value > alert_threshold:
                    await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            INSERT INTO sensor_alerts (sensor_id, alert_type, value, threshold)
                            VALUES ($1, 'high_value', $2::float, $3::float)
                        """,
                            "params": [sensor_id, value, alert_threshold],
                            "fetch_mode": "one",
                        }
                    )

                # Get recent average (last 10 readings)
                avg_result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        SELECT AVG(value) as avg_value
                        FROM (
                            SELECT value
                            FROM sensor_data
                            WHERE sensor_id = $1
                            ORDER BY timestamp DESC
                            LIMIT 10
                        ) recent
                    """,
                        "params": [sensor_id],
                        "fetch_mode": "one",
                    }
                )

                await pool.process({"operation": "release", "connection_id": conn_id})

                return {
                    "reading_id": reading_id,
                    "sensor_id": sensor_id,
                    "value": value,
                    "alert": value > alert_threshold,
                    "recent_avg": (
                        avg_result["data"]["avg_value"] if avg_result["data"] else None
                    ),
                }

            except Exception as e:
                await pool.process({"operation": "release", "connection_id": conn_id})
                raise

        # Simulate concurrent sensor readings
        num_readings = 100
        start_time = time.time()

        tasks = [process_sensor_reading(i) for i in range(num_readings)]
        results = await asyncio.gather(*tasks)

        elapsed_time = time.time() - start_time

        # Analyze results
        alerts_generated = sum(1 for r in results if r.get("alert"))

        # Get summary stats
        stats_conn = await pool.process({"operation": "acquire"})
        summary = await pool.process(
            {
                "operation": "execute",
                "connection_id": stats_conn["connection_id"],
                "query": """
                SELECT
                    COUNT(DISTINCT sensor_id) as active_sensors,
                    COUNT(*) as total_readings,
                    AVG(value) as avg_value,
                    MIN(value) as min_value,
                    MAX(value) as max_value
                FROM sensor_data
            """,
                "fetch_mode": "one",
            }
        )

        alert_summary = await pool.process(
            {
                "operation": "execute",
                "connection_id": stats_conn["connection_id"],
                "query": "SELECT COUNT(*) as alert_count FROM sensor_alerts",
                "fetch_mode": "one",
            }
        )

        await pool.process(
            {"operation": "release", "connection_id": stats_conn["connection_id"]}
        )

        pool_stats = await pool.process({"operation": "stats"})

        # Cleanup
        cleanup_conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS sensor_alerts CASCADE",
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS sensor_data CASCADE",
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": cleanup_conn["connection_id"]}
        )

        await pool._cleanup()

        # Assertions
        assert summary["data"]["total_readings"] == num_readings
        assert summary["data"]["active_sensors"] == len(sensors)
        assert alert_summary["data"]["alert_count"] == alerts_generated
        assert pool_stats["connections"]["created"] <= db_config["max_connections"]
        readings_per_second = num_readings / elapsed_time
        assert readings_per_second > 10  # Should handle at least 10 readings/second

        print(
            f"""
IoT Sensor Processing Results:
- Total Readings: {num_readings}
- Active Sensors: {summary['data']['active_sensors']}
- Alerts Generated: {alerts_generated}
- Avg Sensor Value: {summary['data']['avg_value']:.2f}
- Min/Max Values: {summary['data']['min_value']:.2f} / {summary['data']['max_value']:.2f}
- Processing Rate: {readings_per_second:.1f} readings/second
- Execution Time: {elapsed_time:.2f}s
- Pool Efficiency: {pool_stats['queries']['executed'] / pool_stats['connections']['created']:.1f} queries/connection
        """
        )


if __name__ == "__main__":
    # Run tests directly
    import sys

    test = TestConnectionPoolE2ESimplified()

    # Create config directly without using fixture
    config = {
        "name": "e2e_pool",
        "database_type": "postgresql",
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5433)),
        "database": os.getenv("POSTGRES_DB", "kailash_test"),
        "user": os.getenv("POSTGRES_USER", "admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "admin"),
        "min_connections": 3,
        "max_connections": 10,
        "health_threshold": 70,
        "pre_warm": True,
    }

    async def run_all():
        print("Running simplified E2E tests...\\n")

        try:
            print("1. Simple E-commerce Workflow Test")
            await test.test_simple_ecommerce_workflow(config)

            print("\\n2. IoT Sensor Processing Test")
            await test.test_iot_sensor_processing(config)

            print("\\n✅ All E2E tests completed successfully!")
        except Exception as e:
            print(f"\\n❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    asyncio.run(run_all())
