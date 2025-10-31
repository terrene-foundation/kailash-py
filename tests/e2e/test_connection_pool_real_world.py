"""Real-world E2E tests for WorkflowConnectionPool.

These tests simulate complete real-world applications and use cases,
testing the pool in the context of actual business workflows.
"""

import asyncio
import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest
from kailash import Workflow
from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.runtime import LocalRuntime


@pytest.mark.e2e
@pytest.mark.asyncio
class TestConnectionPoolRealWorld:
    """Real-world E2E tests simulating production applications."""

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
            "max_connections": 15,
            "health_threshold": 70,
            "pre_warm": True,
        }

    async def test_ecommerce_order_processing_system(self, db_config):
        """
        Real-world test: E-commerce order processing system.

        Simulates:
        - Order placement with inventory checks
        - Payment processing
        - Shipping updates
        - Analytics queries
        - Concurrent user sessions
        """
        pool = WorkflowConnectionPool(**db_config)

        # Initialize database schema
        await self._setup_ecommerce_schema(pool)

        # Simulate multiple concurrent customer orders
        async def process_customer_order(customer_id: int):
            """Process a complete customer order workflow."""
            order_id = str(uuid.uuid4())
            items = []

            # 1. Browse products and check inventory
            conn = await pool.process({"operation": "acquire"})
            conn_id = conn["connection_id"]

            try:
                # Get available products
                products = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        SELECT p.id, p.name, p.price, i.quantity
                        FROM products p
                        JOIN inventory i ON p.id = i.product_id
                        WHERE i.quantity > 0
                        ORDER BY RANDOM()
                        LIMIT 10
                    """,
                        "fetch_mode": "all",
                    }
                )

                # Select random items
                if products["data"]:
                    num_items = random.randint(1, 3)
                    for _ in range(num_items):
                        product = random.choice(products["data"])
                        quantity = random.randint(1, min(3, product["quantity"]))
                        items.append(
                            {
                                "product_id": product["id"],
                                "name": product["name"],
                                "price": float(product["price"]),
                                "quantity": quantity,
                            }
                        )

                # 2. Create order with transaction
                order_result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO orders (id, customer_id, status, total_amount)
                        VALUES ($1::uuid, $2::int, 'pending', $3::decimal)
                        RETURNING id, created_at
                    """,
                        "params": [
                            order_id,
                            customer_id,
                            sum(item["price"] * item["quantity"] for item in items),
                        ],
                        "fetch_mode": "one",
                    }
                )

                # 3. Add order items and update inventory
                for item in items:
                    # Add order item
                    await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                            VALUES ($1::uuid, $2::int, $3::int, $4::decimal)
                        """,
                            "params": [
                                order_id,
                                item["product_id"],
                                item["quantity"],
                                item["price"],
                            ],
                            "fetch_mode": "one",
                        }
                    )

                    # Update inventory
                    inventory_result = await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            UPDATE inventory
                            SET quantity = quantity - $2::int,
                                last_updated = NOW()
                            WHERE product_id = $1::int AND quantity >= $2::int
                            RETURNING quantity
                        """,
                            "params": [item["product_id"], item["quantity"]],
                            "fetch_mode": "one",
                        }
                    )

                    if not inventory_result["data"]:
                        # Inventory check failed, rollback
                        raise Exception(
                            f"Insufficient inventory for product {item['product_id']}"
                        )

                # 4. Process payment (simulated)
                payment_status = "success" if random.random() > 0.1 else "failed"

                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO payments (order_id, amount, status, payment_method)
                        VALUES ($1::uuid, $2::decimal, $3, $4)
                    """,
                        "params": [
                            order_id,
                            sum(item["price"] * item["quantity"] for item in items),
                            payment_status,
                            random.choice(
                                ["credit_card", "debit_card", "paypal", "apple_pay"]
                            ),
                        ],
                        "fetch_mode": "one",
                    }
                )

                # 5. Update order status
                final_status = (
                    "confirmed" if payment_status == "success" else "cancelled"
                )
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        UPDATE orders
                        SET status = $2, updated_at = NOW()
                        WHERE id = $1::uuid
                    """,
                        "params": [order_id, final_status],
                        "fetch_mode": "one",
                    }
                )

                # 6. Analytics query - customer lifetime value
                if random.random() > 0.7:  # 30% of sessions check analytics
                    analytics = await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            SELECT
                                COUNT(*) as total_orders,
                                SUM(total_amount) as lifetime_value,
                                AVG(total_amount) as avg_order_value
                            FROM orders
                            WHERE customer_id = $1::int
                            AND status = 'confirmed'
                        """,
                            "params": [customer_id],
                            "fetch_mode": "one",
                        }
                    )

                return {
                    "customer_id": customer_id,
                    "order_id": order_id,
                    "status": final_status,
                    "items": len(items),
                    "total": sum(item["price"] * item["quantity"] for item in items),
                }

            finally:
                await pool.process({"operation": "release", "connection_id": conn_id})

        # Initialize pool
        await pool.process({"operation": "initialize"})

        # Simulate concurrent customers
        num_customers = 50
        start_time = time.time()

        tasks = [process_customer_order(i) for i in range(num_customers)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_time = time.time() - start_time

        # Analyze results
        successful_orders = [
            r for r in results if isinstance(r, dict) and r.get("status") == "confirmed"
        ]
        failed_orders = [
            r for r in results if isinstance(r, dict) and r.get("status") == "cancelled"
        ]
        errors = [r for r in results if isinstance(r, Exception)]

        # Generate business metrics
        conn = await pool.process({"operation": "acquire"})
        metrics = await pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": """
                WITH order_stats AS (
                    SELECT
                        COUNT(*) as total_orders,
                        COUNT(CASE WHEN status = 'confirmed' THEN 1 END) as confirmed_orders,
                        SUM(CASE WHEN status = 'confirmed' THEN total_amount ELSE 0 END) as revenue,
                        AVG(CASE WHEN status = 'confirmed' THEN total_amount END) as avg_order_value
                    FROM orders
                    WHERE created_at > NOW() - INTERVAL '1 hour'
                ),
                inventory_stats AS (
                    SELECT COUNT(*) as low_stock_items
                    FROM inventory
                    WHERE quantity < 10
                )
                SELECT * FROM order_stats, inventory_stats
            """,
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": conn["connection_id"]}
        )

        # Get pool stats
        pool_stats = await pool.process({"operation": "stats"})

        # Cleanup
        await self._cleanup_ecommerce_schema(pool)
        await pool._cleanup()

        # Assertions
        assert len(successful_orders) >= num_customers * 0.8  # 80% success rate
        assert pool_stats["connections"]["created"] <= db_config["max_connections"]
        assert elapsed_time < num_customers * 0.5  # Efficient processing

        print(
            f"""
E-commerce Order Processing Results:
- Total Customers: {num_customers}
- Successful Orders: {len(successful_orders)}
- Failed Orders: {len(failed_orders)}
- Errors: {len(errors)}
- Total Revenue: ${metrics['data']['revenue']:.2f}
- Avg Order Value: ${metrics['data']['avg_order_value']:.2f}
- Processing Time: {elapsed_time:.2f}s
- Throughput: {num_customers / elapsed_time:.1f} orders/second
- Connection Efficiency: {pool_stats['queries']['executed'] / pool_stats['connections']['created']:.1f} queries/connection
        """
        )

    async def test_iot_sensor_data_pipeline(self, db_config):
        """
        Real-world test: IoT sensor data ingestion and analysis pipeline.

        Simulates:
        - High-frequency sensor data ingestion
        - Real-time anomaly detection
        - Data aggregation and rollups
        - Alert generation
        """
        pool = WorkflowConnectionPool(**db_config)

        # Setup IoT schema
        await self._setup_iot_schema(pool)

        # Initialize pool
        await pool.process({"operation": "initialize"})

        # Simulate sensor data streams
        async def sensor_data_stream(sensor_id: str, sensor_type: str):
            """Simulate continuous sensor data stream."""
            conn = await pool.process({"operation": "acquire"})
            conn_id = conn["connection_id"]

            readings = []
            anomalies_detected = 0

            try:
                # Generate batch of readings
                for _ in range(100):  # 100 readings per sensor
                    # Generate realistic sensor data
                    if sensor_type == "temperature":
                        value = 20 + random.gauss(0, 2)  # Normal around 20°C
                        if random.random() < 0.05:  # 5% anomaly rate
                            value = 35 + random.random() * 10  # Anomaly
                            anomalies_detected += 1
                    elif sensor_type == "humidity":
                        value = 50 + random.gauss(0, 10)  # Normal around 50%
                        value = max(0, min(100, value))  # Clamp to 0-100
                    else:  # pressure
                        value = 1013 + random.gauss(0, 5)  # Normal atmospheric pressure

                    readings.append((sensor_id, value, sensor_type))

                # Batch insert readings
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO sensor_readings (sensor_id, value, reading_type)
                        SELECT
                            unnest($1::text[]),
                            unnest($2::float[]),
                            unnest($3::text[])
                    """,
                        "params": [
                            [r[0] for r in readings],
                            [r[1] for r in readings],
                            [r[2] for r in readings],
                        ],
                        "fetch_mode": "one",
                    }
                )

                # Check for anomalies using window functions
                anomaly_check = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        WITH recent_stats AS (
                            SELECT
                                sensor_id,
                                AVG(value) as avg_value,
                                STDDEV(value) as std_value
                            FROM sensor_readings
                            WHERE sensor_id = $1
                            AND timestamp > NOW() - INTERVAL '5 minutes'
                            GROUP BY sensor_id
                        ),
                        latest_readings AS (
                            SELECT value
                            FROM sensor_readings
                            WHERE sensor_id = $1
                            ORDER BY timestamp DESC
                            LIMIT 10
                        )
                        SELECT
                            COUNT(*) as anomaly_count
                        FROM latest_readings l, recent_stats s
                        WHERE ABS(l.value - s.avg_value) > 3 * s.std_value
                    """,
                        "params": [sensor_id],
                        "fetch_mode": "one",
                    }
                )

                # Generate alerts if needed
                if anomaly_check["data"] and anomaly_check["data"]["anomaly_count"] > 2:
                    await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            INSERT INTO alerts (sensor_id, alert_type, severity, message)
                            VALUES ($1, 'anomaly', 'high', $2)
                        """,
                            "params": [
                                sensor_id,
                                f"Multiple anomalies detected for {sensor_type} sensor",
                            ],
                            "fetch_mode": "one",
                        }
                    )

                # Perform aggregation
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO sensor_aggregates (sensor_id, period, avg_value, min_value, max_value, sample_count)
                        SELECT
                            sensor_id,
                            date_trunc('minute', NOW()) as period,
                            AVG(value),
                            MIN(value),
                            MAX(value),
                            COUNT(*)
                        FROM sensor_readings
                        WHERE sensor_id = $1
                        AND timestamp > date_trunc('minute', NOW())
                        AND timestamp <= date_trunc('minute', NOW()) + INTERVAL '1 minute'
                        GROUP BY sensor_id
                        ON CONFLICT (sensor_id, period) DO UPDATE
                        SET avg_value = EXCLUDED.avg_value,
                            min_value = EXCLUDED.min_value,
                            max_value = EXCLUDED.max_value,
                            sample_count = EXCLUDED.sample_count
                    """,
                        "params": [sensor_id],
                        "fetch_mode": "one",
                    }
                )

                return {
                    "sensor_id": sensor_id,
                    "readings": len(readings),
                    "anomalies": anomalies_detected,
                    "success": True,
                }

            finally:
                await pool.process({"operation": "release", "connection_id": conn_id})

        # Simulate multiple sensors
        sensors = (
            [(f"temp_{i}", "temperature") for i in range(10)]
            + [(f"humidity_{i}", "humidity") for i in range(5)]
            + [(f"pressure_{i}", "pressure") for i in range(5)]
        )

        start_time = time.time()

        # Process all sensors concurrently
        tasks = [
            sensor_data_stream(sensor_id, sensor_type)
            for sensor_id, sensor_type in sensors
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_time = time.time() - start_time

        # Analyze results
        successful = [r for r in results if isinstance(r, dict) and r.get("success")]
        total_readings = sum(r.get("readings", 0) for r in successful)
        total_anomalies = sum(r.get("anomalies", 0) for r in successful)

        # Get system metrics
        conn = await pool.process({"operation": "acquire"})
        system_metrics = await pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": """
                SELECT
                    (SELECT COUNT(*) FROM sensor_readings) as total_readings,
                    (SELECT COUNT(*) FROM alerts) as total_alerts,
                    (SELECT COUNT(DISTINCT sensor_id) FROM sensor_readings) as active_sensors,
                    (SELECT pg_size_pretty(pg_total_relation_size('sensor_readings'))) as table_size
            """,
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": conn["connection_id"]}
        )

        # Pool stats
        pool_stats = await pool.process({"operation": "stats"})

        # Cleanup
        await self._cleanup_iot_schema(pool)
        await pool._cleanup()

        # Assertions
        assert len(successful) == len(
            sensors
        )  # All sensors should process successfully
        assert total_readings == len(sensors) * 100  # Each sensor sends 100 readings
        assert pool_stats["queries"]["error_rate"] < 0.01  # Less than 1% error rate

        print(
            f"""
IoT Sensor Pipeline Results:
- Total Sensors: {len(sensors)}
- Successful Streams: {len(successful)}
- Total Readings: {total_readings}
- Anomalies Detected: {total_anomalies}
- Alerts Generated: {system_metrics['data']['total_alerts']}
- Processing Time: {elapsed_time:.2f}s
- Ingestion Rate: {total_readings / elapsed_time:.0f} readings/second
- Data Volume: {system_metrics['data']['table_size']}
- Query Performance: {pool_stats['performance']['avg_acquisition_time_ms']:.2f}ms avg acquisition
        """
        )

    async def test_financial_transaction_system(self, db_config):
        """
        Real-world test: Financial transaction processing with ACID guarantees.

        Simulates:
        - Account transfers with strict consistency
        - Balance checks and overdraft protection
        - Transaction history and audit trails
        - Regulatory reporting queries
        """
        pool = WorkflowConnectionPool(**db_config)

        # Setup financial schema
        await self._setup_financial_schema(pool)

        # Initialize pool
        await pool.process({"operation": "initialize"})

        # Create test accounts
        num_accounts = 20
        initial_balance = 10000.0

        conn = await pool.process({"operation": "acquire"})
        for i in range(num_accounts):
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn["connection_id"],
                    "query": """
                    INSERT INTO accounts (account_number, balance, account_type, status)
                    VALUES ($1, $2::decimal, $3, 'active')
                """,
                    "params": [
                        f"ACC{i:06d}",
                        initial_balance,
                        random.choice(["checking", "savings"]),
                    ],
                    "fetch_mode": "one",
                }
            )
        await pool.process(
            {"operation": "release", "connection_id": conn["connection_id"]}
        )

        # Process financial transactions
        async def process_transaction(transaction_id: int):
            """Process a financial transaction with full ACID guarantees."""
            # Random source and destination accounts
            source_acc = f"ACC{random.randint(0, num_accounts-1):06d}"
            dest_acc = f"ACC{random.randint(0, num_accounts-1):06d}"
            while dest_acc == source_acc:
                dest_acc = f"ACC{random.randint(0, num_accounts-1):06d}"

            amount = round(random.uniform(10, 1000), 2)

            conn = await pool.process({"operation": "acquire"})
            conn_id = conn["connection_id"]

            try:
                # Start transaction
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "BEGIN",
                        "fetch_mode": "one",
                    }
                )

                # Lock accounts in consistent order to prevent deadlocks
                accounts = sorted([source_acc, dest_acc])

                # Check source balance with lock
                balance_check = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        SELECT account_number, balance
                        FROM accounts
                        WHERE account_number = ANY($1::text[])
                        ORDER BY account_number
                        FOR UPDATE
                    """,
                        "params": [accounts],
                        "fetch_mode": "all",
                    }
                )

                # Find source balance
                source_balance = next(
                    (
                        acc["balance"]
                        for acc in balance_check["data"]
                        if acc["account_number"] == source_acc
                    ),
                    None,
                )

                if source_balance is None or float(source_balance) < amount:
                    # Insufficient funds - rollback
                    await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": "ROLLBACK",
                            "fetch_mode": "one",
                        }
                    )

                    # Log failed transaction
                    await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            INSERT INTO transactions (source_account, dest_account, amount, status, error_reason)
                            VALUES ($1, $2, $3::decimal, 'failed', 'insufficient_funds')
                        """,
                            "params": [source_acc, dest_acc, amount],
                            "fetch_mode": "one",
                        }
                    )

                    return {"status": "failed", "reason": "insufficient_funds"}

                # Perform transfer
                # Debit source
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        UPDATE accounts
                        SET balance = balance - $2::decimal,
                            last_transaction = NOW()
                        WHERE account_number = $1
                    """,
                        "params": [source_acc, amount],
                        "fetch_mode": "one",
                    }
                )

                # Credit destination
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        UPDATE accounts
                        SET balance = balance + $2::decimal,
                            last_transaction = NOW()
                        WHERE account_number = $1
                    """,
                        "params": [dest_acc, amount],
                        "fetch_mode": "one",
                    }
                )

                # Record transaction
                txn_result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO transactions (source_account, dest_account, amount, status)
                        VALUES ($1, $2, $3::decimal, 'completed')
                        RETURNING id, timestamp
                    """,
                        "params": [source_acc, dest_acc, amount],
                        "fetch_mode": "one",
                    }
                )

                # Add audit trail entries
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        INSERT INTO audit_trail (transaction_id, event_type, account_number, amount, balance_after)
                        VALUES
                            ($1::int, 'debit', $2, $3::decimal,
                             (SELECT balance FROM accounts WHERE account_number = $2)),
                            ($1::int, 'credit', $4, $3::decimal,
                             (SELECT balance FROM accounts WHERE account_number = $4))
                    """,
                        "params": [
                            txn_result["data"]["id"],
                            source_acc,
                            amount,
                            dest_acc,
                        ],
                        "fetch_mode": "one",
                    }
                )

                # Commit transaction
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "COMMIT",
                        "fetch_mode": "one",
                    }
                )

                return {
                    "status": "completed",
                    "transaction_id": txn_result["data"]["id"],
                    "amount": amount,
                }

            except Exception as e:
                # Rollback on any error
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "ROLLBACK",
                        "fetch_mode": "one",
                    }
                )
                raise
            finally:
                await pool.process({"operation": "release", "connection_id": conn_id})

        # Simulate concurrent transactions
        num_transactions = 200
        start_time = time.time()

        tasks = [process_transaction(i) for i in range(num_transactions)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_time = time.time() - start_time

        # Analyze results
        completed = [
            r for r in results if isinstance(r, dict) and r.get("status") == "completed"
        ]
        failed = [
            r for r in results if isinstance(r, dict) and r.get("status") == "failed"
        ]
        errors = [r for r in results if isinstance(r, Exception)]

        # Verify financial consistency
        conn = await pool.process({"operation": "acquire"})
        consistency_check = await pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": """
                WITH account_totals AS (
                    SELECT SUM(balance) as total_balance
                    FROM accounts
                ),
                transaction_stats AS (
                    SELECT
                        COUNT(*) as total_transactions,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                        SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END) as total_volume
                    FROM transactions
                ),
                audit_stats AS (
                    SELECT COUNT(DISTINCT transaction_id) as audited_transactions
                    FROM audit_trail
                )
                SELECT
                    a.total_balance,
                    t.*,
                    au.audited_transactions
                FROM account_totals a, transaction_stats t, audit_stats au
            """,
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": conn["connection_id"]}
        )

        # Pool stats
        pool_stats = await pool.process({"operation": "stats"})

        # Cleanup
        await self._cleanup_financial_schema(pool)
        await pool._cleanup()

        # Assertions
        expected_balance = num_accounts * initial_balance  # Should remain constant
        actual_balance = float(consistency_check["data"]["total_balance"])
        assert (
            abs(actual_balance - expected_balance) < 0.01
        )  # Financial consistency maintained
        assert consistency_check["data"]["completed"] == len(
            completed
        )  # Transaction count matches
        assert pool_stats["queries"]["error_rate"] < 0.02  # Low error rate

        print(
            f"""
Financial Transaction System Results:
- Total Transactions: {num_transactions}
- Completed: {len(completed)}
- Failed (Insufficient Funds): {len(failed)}
- Errors: {len(errors)}
- Transaction Volume: ${consistency_check['data']['total_volume']:.2f}
- Processing Time: {elapsed_time:.2f}s
- TPS: {len(completed) / elapsed_time:.1f} transactions/second
- Balance Consistency: {'✓ MAINTAINED' if abs(actual_balance - expected_balance) < 0.01 else '✗ VIOLATED'}
- Audit Coverage: {consistency_check['data']['audited_transactions']/max(1, consistency_check['data']['completed'])*100:.1f}%
        """
        )

    # Helper methods for schema setup/cleanup
    async def _setup_ecommerce_schema(self, pool):
        """Setup e-commerce database schema."""
        # Initialize pool first
        await pool.process({"operation": "initialize"})

        conn = await pool.process({"operation": "acquire"})
        conn_id = conn["connection_id"]

        # Create tables
        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn_id,
                "query": """
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    price DECIMAL(10,2),
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS inventory (
                    product_id INT PRIMARY KEY REFERENCES products(id),
                    quantity INT NOT NULL DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id UUID PRIMARY KEY,
                    customer_id INT NOT NULL,
                    status VARCHAR(50),
                    total_amount DECIMAL(10,2),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    id SERIAL PRIMARY KEY,
                    order_id UUID REFERENCES orders(id),
                    product_id INT REFERENCES products(id),
                    quantity INT NOT NULL,
                    unit_price DECIMAL(10,2)
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    order_id UUID REFERENCES orders(id),
                    amount DECIMAL(10,2),
                    status VARCHAR(50),
                    payment_method VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """,
                "fetch_mode": "one",
            }
        )

        # Insert sample products
        products = [
            ("Laptop", 999.99, 50),
            ("Mouse", 29.99, 200),
            ("Keyboard", 79.99, 150),
            ("Monitor", 299.99, 75),
            ("Headphones", 149.99, 100),
            ("Webcam", 89.99, 80),
            ("USB Hub", 39.99, 120),
            ("Desk Lamp", 49.99, 90),
            ("Phone Stand", 19.99, 200),
            ("Cable Organizer", 14.99, 250),
        ]

        for name, price, quantity in products:
            result = await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "INSERT INTO products (name, price) VALUES ($1, $2::decimal) RETURNING id",
                    "params": [name, price],
                    "fetch_mode": "one",
                }
            )

            if result["success"] and result["data"]:
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "INSERT INTO inventory (product_id, quantity) VALUES ($1::int, $2::int)",
                        "params": [result["data"]["id"], quantity],
                        "fetch_mode": "one",
                    }
                )

        await pool.process({"operation": "release", "connection_id": conn_id})

    async def _cleanup_ecommerce_schema(self, pool):
        """Cleanup e-commerce schema."""
        conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": """
                DROP TABLE IF EXISTS payments CASCADE;
                DROP TABLE IF EXISTS order_items CASCADE;
                DROP TABLE IF EXISTS orders CASCADE;
                DROP TABLE IF EXISTS inventory CASCADE;
                DROP TABLE IF EXISTS products CASCADE;
            """,
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": conn["connection_id"]}
        )

    async def _setup_iot_schema(self, pool):
        """Setup IoT database schema."""
        await pool.process({"operation": "initialize"})
        conn = await pool.process({"operation": "acquire"})
        conn_id = conn["connection_id"]

        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn_id,
                "query": """
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id SERIAL PRIMARY KEY,
                    sensor_id VARCHAR(50) NOT NULL,
                    value FLOAT NOT NULL,
                    reading_type VARCHAR(50),
                    timestamp TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_sensor_timestamp
                ON sensor_readings(sensor_id, timestamp DESC);

                CREATE TABLE IF NOT EXISTS sensor_aggregates (
                    sensor_id VARCHAR(50),
                    period TIMESTAMP,
                    avg_value FLOAT,
                    min_value FLOAT,
                    max_value FLOAT,
                    sample_count INT,
                    PRIMARY KEY (sensor_id, period)
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id SERIAL PRIMARY KEY,
                    sensor_id VARCHAR(50),
                    alert_type VARCHAR(50),
                    severity VARCHAR(20),
                    message TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """,
                "fetch_mode": "one",
            }
        )

        await pool.process({"operation": "release", "connection_id": conn_id})

    async def _cleanup_iot_schema(self, pool):
        """Cleanup IoT schema."""
        conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": """
                DROP TABLE IF EXISTS alerts CASCADE;
                DROP TABLE IF EXISTS sensor_aggregates CASCADE;
                DROP TABLE IF EXISTS sensor_readings CASCADE;
            """,
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": conn["connection_id"]}
        )

    async def _setup_financial_schema(self, pool):
        """Setup financial database schema."""
        await pool.process({"operation": "initialize"})
        conn = await pool.process({"operation": "acquire"})
        conn_id = conn["connection_id"]

        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn_id,
                "query": """
                CREATE TABLE IF NOT EXISTS accounts (
                    account_number VARCHAR(20) PRIMARY KEY,
                    balance DECIMAL(15,2) NOT NULL DEFAULT 0,
                    account_type VARCHAR(20),
                    status VARCHAR(20),
                    last_transaction TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    source_account VARCHAR(20),
                    dest_account VARCHAR(20),
                    amount DECIMAL(15,2) NOT NULL,
                    status VARCHAR(20),
                    error_reason VARCHAR(100),
                    timestamp TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS audit_trail (
                    id SERIAL PRIMARY KEY,
                    transaction_id INT,
                    event_type VARCHAR(20),
                    account_number VARCHAR(20),
                    amount DECIMAL(15,2),
                    balance_after DECIMAL(15,2),
                    timestamp TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_txn_timestamp ON transactions(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_txn ON audit_trail(transaction_id);
            """,
                "fetch_mode": "one",
            }
        )

        await pool.process({"operation": "release", "connection_id": conn_id})

    async def _cleanup_financial_schema(self, pool):
        """Cleanup financial schema."""
        conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": conn["connection_id"],
                "query": """
                DROP TABLE IF EXISTS audit_trail CASCADE;
                DROP TABLE IF EXISTS transactions CASCADE;
                DROP TABLE IF EXISTS accounts CASCADE;
            """,
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": conn["connection_id"]}
        )


if __name__ == "__main__":
    # Run tests directly
    import sys

    test = TestConnectionPoolRealWorld()
    config = test.db_config()

    async def run_all():
        print("Running real-world E2E tests...\n")

        try:
            print("1. E-commerce Order Processing System")
            await test.test_ecommerce_order_processing_system(config)

            print("\n2. IoT Sensor Data Pipeline")
            await test.test_iot_sensor_data_pipeline(config)

            print("\n3. Financial Transaction System")
            await test.test_financial_transaction_system(config)

            print("\n✅ All real-world tests completed successfully!")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    asyncio.run(run_all())
