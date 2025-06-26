"""Integration tests for Durable Gateway with real services.

These tests use Docker services (PostgreSQL, Redis, Ollama) to test
the durable gateway with real data and workflows.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List

import httpx
import pytest
import pytest_asyncio

from kailash.middleware.gateway.checkpoint_manager import CheckpointManager, DiskStorage
from kailash.middleware.gateway.deduplicator import RequestDeduplicator
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.middleware.gateway.event_store import EventStore
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow, WorkflowBuilder

# Test configuration
TEST_PORT = 8001
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5434,  # Docker PostgreSQL port
    "database": "kailash_test",
    "user": "test_user",
    "password": "test_password",
}

OLLAMA_CONFIG = {
    "base_url": "http://localhost:11435",
    "model": "llama3.2:3b",  # Will use a small model for tests
}


class TestDurableGatewayIntegration:
    """Integration tests for Durable Gateway."""

    @pytest_asyncio.fixture
    async def postgres_setup(self):
        """Set up PostgreSQL test database."""
        # Create test database
        pool = WorkflowConnectionPool(
            name="test_setup",
            **POSTGRES_CONFIG,
            min_connections=1,
            max_connections=5,
        )

        await pool.process({"operation": "initialize"})

        # Create test tables
        conn = await pool.process({"operation": "acquire"})
        conn_id = conn["connection_id"]

        try:
            # Drop existing tables
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "DROP TABLE IF EXISTS orders CASCADE",
                    "fetch_mode": "one",
                }
            )

            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "DROP TABLE IF EXISTS order_items CASCADE",
                    "fetch_mode": "one",
                }
            )

            # Create orders table
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    CREATE TABLE orders (
                        order_id VARCHAR(50) PRIMARY KEY,
                        customer_name VARCHAR(100),
                        total_amount DECIMAL(10,2),
                        status VARCHAR(20),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """,
                    "fetch_mode": "one",
                }
            )

            # Create order items table
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    CREATE TABLE order_items (
                        item_id SERIAL PRIMARY KEY,
                        order_id VARCHAR(50) REFERENCES orders(order_id),
                        product_name VARCHAR(100),
                        quantity INTEGER,
                        price DECIMAL(10,2)
                    )
                """,
                    "fetch_mode": "one",
                }
            )

        finally:
            await pool.process({"operation": "release", "connection_id": conn_id})

        yield pool

        # Cleanup
        await pool.process({"operation": "stats"})  # Log final stats
        # Note: WorkflowConnectionPool cleanup happens via node lifecycle

    @pytest_asyncio.fixture
    async def gateway(self, postgres_setup):
        """Create durable gateway for testing."""
        # Create gateway with real storage backends
        checkpoint_manager = CheckpointManager(
            disk_storage=DiskStorage("/tmp/kailash_test_checkpoints"),
            retention_hours=1,
        )

        deduplicator = RequestDeduplicator(
            ttl_seconds=300,  # 5 minutes for testing
        )

        event_store = EventStore(
            batch_size=10,
            flush_interval_seconds=0.5,
        )

        gateway = DurableAPIGateway(
            title="Test Durable Gateway",
            enable_durability=True,
            checkpoint_manager=checkpoint_manager,
            deduplicator=deduplicator,
            event_store=event_store,
            durability_opt_in=False,  # Always use durability for tests
        )

        # Register test workflows
        await self._register_test_workflows(gateway, postgres_setup)

        # Start gateway in background
        gateway_task = asyncio.create_task(gateway.run_async())

        # Wait for startup
        await asyncio.sleep(1)

        yield gateway

        # Cleanup
        gateway_task.cancel()
        await gateway.close()

    async def _register_test_workflows(self, gateway, pool):
        """Register test workflows."""
        # 1. Order Processing Workflow
        order_workflow = await self._create_order_workflow(pool)
        gateway.register_workflow("order_processing", order_workflow)

        # 2. Data Analysis Workflow with LLM
        analysis_workflow = await self._create_analysis_workflow(pool)
        gateway.register_workflow("data_analysis", analysis_workflow)

        # 3. Long-Running Workflow
        long_workflow = await self._create_long_running_workflow()
        gateway.register_workflow("long_running", long_workflow)

    async def _create_order_workflow(self, pool) -> Workflow:
        """Create order processing workflow."""
        workflow = WorkflowBuilder("order_processor")

        # Validate order
        workflow.add_node(
            "validate_order",
            "PythonCodeNode",
            {
                "code": """
order = inputs["order"]
if not order.get("customer_name") or not order.get("items"):
    raise ValueError("Invalid order: missing customer_name or items")

total = sum(item["quantity"] * item["price"] for item in order["items"])
result = {
    "order_id": f"ORD-{inputs.get('request_id', 'unknown')[:8]}",
    "customer_name": order["customer_name"],
    "items": order["items"],
    "total_amount": total,
    "validated": True
}
"""
            },
        )

        # Save to database
        workflow.add_node(
            "save_order",
            "PythonCodeNode",
            {
                "code": """
import asyncio

pool = inputs["pool"]
order_data = inputs["order_data"]

# Acquire connection
conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    # Insert order
    await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            INSERT INTO orders (order_id, customer_name, total_amount, status)
            VALUES ($1, $2, $3, $4)
        ''',
        "params": [
            order_data["order_id"],
            order_data["customer_name"],
            order_data["total_amount"],
            "pending"
        ],
        "fetch_mode": "one"
    })

    # Insert items
    for item in order_data["items"]:
        await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": '''
                INSERT INTO order_items (order_id, product_name, quantity, price)
                VALUES ($1, $2, $3, $4)
            ''',
            "params": [
                order_data["order_id"],
                item["product_name"],
                item["quantity"],
                item["price"]
            ],
            "fetch_mode": "one"
        })

    result = {"saved": True, "order_id": order_data["order_id"]}

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # Process payment (simulated)
        workflow.add_node(
            "process_payment",
            "PythonCodeNode",
            {
                "code": """
import random
import asyncio

# Simulate payment processing
await asyncio.sleep(0.5)

# 90% success rate
success = random.random() < 0.9

result = {
    "payment_id": f"PAY-{inputs['order_data']['order_id']}",
    "success": success,
    "amount": inputs['order_data']['total_amount']
}
"""
            },
        )

        # Update order status
        workflow.add_node(
            "update_status",
            "PythonCodeNode",
            {
                "code": """
pool = inputs["pool"]
order_id = inputs["order_id"]
payment_result = inputs["payment_result"]

status = "completed" if payment_result["success"] else "payment_failed"

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": "UPDATE orders SET status = $1 WHERE order_id = $2",
        "params": [status, order_id],
        "fetch_mode": "one"
    })

    result = {"status_updated": True, "new_status": status}

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # Connect workflow
        workflow.add_connection("validate_order", "save_order", "result", "order_data")
        workflow.add_connection(
            "save_order", "process_payment", "result.order_id", "order_id"
        )
        workflow.add_connection(
            "validate_order", "process_payment", "result", "order_data"
        )
        workflow.add_connection(
            "process_payment", "update_status", "result", "payment_result"
        )
        workflow.add_connection(
            "save_order", "update_status", "result.order_id", "order_id"
        )

        return workflow.build()

    async def _create_analysis_workflow(self, pool) -> Workflow:
        """Create data analysis workflow with LLM."""
        workflow = WorkflowBuilder("data_analyzer")

        # Fetch data from database
        workflow.add_node(
            "fetch_data",
            "PythonCodeNode",
            {
                "code": """
pool = inputs["pool"]
query_type = inputs.get("query_type", "summary")

conn = await pool.process({"operation": "acquire"})
conn_id = conn["connection_id"]

try:
    if query_type == "summary":
        result = await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": '''
                SELECT
                    COUNT(*) as total_orders,
                    SUM(total_amount) as total_revenue,
                    AVG(total_amount) as avg_order_value,
                    MAX(total_amount) as max_order,
                    MIN(total_amount) as min_order
                FROM orders
                WHERE created_at >= NOW() - INTERVAL '7 days'
            ''',
            "fetch_mode": "one"
        })
    else:
        result = await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": '''
                SELECT
                    o.order_id,
                    o.customer_name,
                    o.total_amount,
                    o.status,
                    COUNT(oi.item_id) as item_count
                FROM orders o
                LEFT JOIN order_items oi ON o.order_id = oi.order_id
                GROUP BY o.order_id, o.customer_name, o.total_amount, o.status
                ORDER BY o.created_at DESC
                LIMIT 10
            ''',
            "fetch_mode": "all"
        })

    result = {"data": result["data"], "query_type": query_type}

finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn_id
    })
""",
                "inputs": {"pool": pool},
            },
        )

        # Analyze with LLM (using ollama)
        workflow.add_node(
            "llm_analysis",
            "LLMAgentNode",
            {
                "name": "analyzer",
                "model": "llama2",
                "api_base": OLLAMA_CONFIG["base_url"],
                "system_prompt": """You are a data analyst. Analyze the provided data and give insights.
Focus on:
1. Key trends or patterns
2. Potential issues or opportunities
3. Actionable recommendations
Keep your response concise and professional.""",
                "prompt": """Analyze this business data:

{{data}}

Provide 3-5 key insights.""",
                "temperature": 0.7,
                "max_tokens": 500,
            },
        )

        # Format report
        workflow.add_node(
            "format_report",
            "PythonCodeNode",
            {
                "code": """
from datetime import datetime

data = inputs["data"]
analysis = inputs["analysis"]

report = {
    "report_id": f"RPT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    "generated_at": datetime.now().isoformat(),
    "data_summary": data,
    "ai_insights": analysis.get("response", "No analysis available"),
    "status": "completed"
}

result = report
"""
            },
        )

        # Connect workflow
        workflow.add_connection("fetch_data", "llm_analysis", "result.data", "data")
        workflow.add_connection("fetch_data", "format_report", "result", "data")
        workflow.add_connection("llm_analysis", "format_report", "result", "analysis")

        return workflow.build()

    async def _create_long_running_workflow(self) -> Workflow:
        """Create long-running workflow for testing durability."""
        workflow = WorkflowBuilder("long_runner")

        # Stage 1: Initialize
        workflow.add_node(
            "initialize",
            "PythonCodeNode",
            {
                "code": """
import time

start_time = time.time()
total_steps = inputs.get("total_steps", 10)

result = {
    "task_id": f"TASK-{int(start_time)}",
    "total_steps": total_steps,
    "current_step": 0,
    "start_time": start_time,
    "status": "initialized"
}
"""
            },
        )

        # Stage 2: Process steps
        workflow.add_node(
            "process_steps",
            "PythonCodeNode",
            {
                "code": """
import asyncio
import random

task_data = inputs["task_data"]
checkpoint_interval = inputs.get("checkpoint_interval", 3)

results = []
for step in range(task_data["total_steps"]):
    # Simulate work
    await asyncio.sleep(0.2)

    # Random chance of "failure" for testing resume
    if random.random() < 0.1 and step > 5:
        raise Exception(f"Simulated failure at step {step}")

    step_result = {
        "step": step + 1,
        "value": random.randint(1, 100),
        "timestamp": asyncio.get_event_loop().time()
    }
    results.append(step_result)

    # Checkpoint periodically
    if (step + 1) % checkpoint_interval == 0:
        # In real implementation, would trigger checkpoint
        pass

result = {
    "task_id": task_data["task_id"],
    "completed_steps": len(results),
    "results": results,
    "status": "completed"
}
"""
            },
        )

        # Stage 3: Aggregate results
        workflow.add_node(
            "aggregate",
            "PythonCodeNode",
            {
                "code": """
import statistics

process_results = inputs["process_results"]
results = process_results["results"]

values = [r["value"] for r in results]

summary = {
    "task_id": process_results["task_id"],
    "total_steps": len(results),
    "sum": sum(values),
    "average": statistics.mean(values),
    "median": statistics.median(values),
    "min": min(values),
    "max": max(values),
    "status": "aggregated"
}

result = summary
"""
            },
        )

        # Connect workflow
        workflow.add_connection("initialize", "process_steps", "result", "task_data")
        workflow.add_connection(
            "process_steps", "aggregate", "result", "process_results"
        )

        return workflow.build()

    @pytest.mark.asyncio
    async def test_basic_request_durability(self, gateway):
        """Test basic request with checkpointing."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            # Submit order
            order_data = {
                "customer_name": "Test Customer",
                "items": [
                    {"product_name": "Widget A", "quantity": 2, "price": 10.99},
                    {"product_name": "Gadget B", "quantity": 1, "price": 25.50},
                ],
            }

            response = await client.post(
                "/order_processing/execute",
                json={"order": order_data},
                headers={"X-Request-ID": str(uuid.uuid4())},
            )

            assert response.status_code == 200
            result = response.json()

            # Check order was processed
            assert "order_id" in result
            assert result["status"] == "success"

            # Check durability status
            request_id = response.headers.get("X-Request-ID")
            status_response = await client.get(f"/durability/requests/{request_id}")
            assert status_response.status_code == 200

            status = status_response.json()
            assert status["state"] == "completed"
            assert status["checkpoints"] > 0

    @pytest.mark.asyncio
    async def test_request_deduplication(self, gateway):
        """Test request deduplication with idempotency key."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            idempotency_key = f"test-order-{uuid.uuid4()}"

            order_data = {
                "customer_name": "Duplicate Test",
                "items": [{"product_name": "Item X", "quantity": 1, "price": 50.00}],
            }

            # First request
            response1 = await client.post(
                "/order_processing/execute",
                json={"order": order_data},
                headers={"Idempotency-Key": idempotency_key},
            )

            assert response1.status_code == 200
            result1 = response1.json()

            # Duplicate request with same idempotency key
            response2 = await client.post(
                "/order_processing/execute",
                json={"order": order_data},
                headers={"Idempotency-Key": idempotency_key},
            )

            assert response2.status_code == 200
            result2 = response2.json()

            # Should return same result
            assert result1["order_id"] == result2["order_id"]

            # Check for cache header
            assert response2.headers.get("X-Cached-Response") == "true"

    @pytest.mark.asyncio
    async def test_long_running_with_checkpoints(self, gateway):
        """Test long-running workflow with checkpoints."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            # Start long-running task
            response = await client.post(
                "/long_running/execute",
                json={"total_steps": 20, "checkpoint_interval": 5},
                timeout=30.0,
            )

            if response.status_code == 200:
                result = response.json()
                assert result["status"] == "success"
                assert "summary" in result
                assert result["summary"]["total_steps"] == 20
            else:
                # If it failed, check we can get status
                request_id = response.headers.get("X-Request-ID")
                status_response = await client.get(f"/durability/requests/{request_id}")
                assert status_response.status_code == 200

                status = status_response.json()
                assert status["state"] in ["failed", "executing"]
                assert status["checkpoints"] > 0

    @pytest.mark.asyncio
    async def test_llm_analysis_workflow(self, gateway):
        """Test data analysis workflow with LLM integration."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            # First, create some test data
            for i in range(5):
                order_data = {
                    "customer_name": f"Customer {i}",
                    "items": [
                        {
                            "product_name": f"Product {j}",
                            "quantity": j + 1,
                            "price": 10.0 * (j + 1),
                        }
                        for j in range(3)
                    ],
                }

                await client.post(
                    "/order_processing/execute", json={"order": order_data}
                )

            # Run analysis
            response = await client.post(
                "/data_analysis/execute",
                json={"query_type": "summary"},
                timeout=60.0,  # LLM might take time
            )

            assert response.status_code == 200
            result = response.json()

            # Check report structure
            assert "report_id" in result
            assert "data_summary" in result
            assert "ai_insights" in result

            # Verify data was fetched
            summary = result["data_summary"]["data"]
            assert summary["total_orders"] >= 5
            assert summary["total_revenue"] > 0

    @pytest.mark.asyncio
    async def test_event_sourcing(self, gateway):
        """Test event sourcing and replay capability."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            # Execute a workflow
            order_data = {
                "customer_name": "Event Test",
                "items": [
                    {"product_name": "Event Item", "quantity": 1, "price": 99.99}
                ],
            }

            response = await client.post(
                "/order_processing/execute", json={"order": order_data}
            )

            request_id = response.headers.get("X-Request-ID")

            # Get events
            events_response = await client.get(
                f"/durability/requests/{request_id}/events"
            )
            assert events_response.status_code == 200

            events = events_response.json()
            assert events["event_count"] > 0

            # Check event types
            event_types = [e["event_type"] for e in events["events"]]
            assert "request.created" in event_types
            assert "request.started" in event_types
            assert "request.completed" in event_types

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, gateway):
        """Test gateway handles concurrent requests properly."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            # Submit multiple orders concurrently
            tasks = []
            for i in range(10):
                order_data = {
                    "customer_name": f"Concurrent Customer {i}",
                    "items": [
                        {
                            "product_name": f"Concurrent Item {i}",
                            "quantity": i + 1,
                            "price": 10.0 * (i + 1),
                        }
                    ],
                }

                task = client.post(
                    "/order_processing/execute", json={"order": order_data}
                )
                tasks.append(task)

            # Wait for all to complete
            responses = await asyncio.gather(*tasks)

            # All should succeed
            for response in responses:
                assert response.status_code == 200
                result = response.json()
                assert "order_id" in result

    @pytest.mark.asyncio
    async def test_checkpoint_recovery(self, gateway):
        """Test checkpoint storage and recovery."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            # Get durability stats before
            stats_before = await client.get("/durability/status")
            checkpoints_before = stats_before.json()["checkpoint_stats"]["save_count"]

            # Execute workflow
            response = await client.post(
                "/order_processing/execute",
                json={
                    "order": {
                        "customer_name": "Checkpoint Test",
                        "items": [
                            {"product_name": "Test", "quantity": 1, "price": 10.0}
                        ],
                    }
                },
            )

            # Get durability stats after
            stats_after = await client.get("/durability/status")
            checkpoints_after = stats_after.json()["checkpoint_stats"]["save_count"]

            # Should have created checkpoints
            assert checkpoints_after > checkpoints_before

    @pytest.mark.asyncio
    async def test_performance_metrics(self, gateway):
        """Test performance metrics collection."""
        async with httpx.AsyncClient(
            base_url=f"http://localhost:{TEST_PORT}"
        ) as client:
            # Execute several requests
            for i in range(5):
                await client.post(
                    "/order_processing/execute",
                    json={
                        "order": {
                            "customer_name": f"Metrics Test {i}",
                            "items": [
                                {"product_name": "Item", "quantity": 1, "price": 10.0}
                            ],
                        }
                    },
                )

            # Get performance projection
            projection_response = await client.get(
                "/durability/projections/performance_metrics"
            )
            assert projection_response.status_code == 200

            metrics = projection_response.json()["state"]
            assert metrics["total_requests"] >= 5
            assert metrics["completed_requests"] >= 5
            assert "total_duration_ms" in metrics
