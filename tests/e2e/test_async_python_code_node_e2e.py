"""End-to-end tests for AsyncPythonCodeNode with durable gateway.

This test demonstrates AsyncPythonCodeNode working in a real-world scenario
with database operations, async processing, and durable request handling.
"""

import asyncio
import json
import tempfile
import threading
import time

import httpx
import pytest
import pytest_asyncio
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager, DiskStorage
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.workflow import WorkflowBuilder

# Test configuration
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5434,
    "database": "kailash_test",
    "user": "test_user",
    "password": "test_password",
}


class TestAsyncPythonCodeNodeE2E:
    """E2E tests for AsyncPythonCodeNode."""

    @pytest_asyncio.fixture
    async def test_database(self):
        """Set up test database."""
        pool = WorkflowConnectionPool(
            name="async_test_db",
            **POSTGRES_CONFIG,
            min_connections=2,
            max_connections=5,
        )

        await pool.process({"operation": "initialize"})

        conn = await pool.process({"operation": "acquire"})
        conn_id = conn["connection_id"]

        try:
            # Create simple test table
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "DROP TABLE IF EXISTS async_test_data CASCADE",
                    "fetch_mode": "one",
                }
            )

            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": """
                    CREATE TABLE async_test_data (
                        id VARCHAR(50) PRIMARY KEY,
                        data JSONB NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                    "fetch_mode": "one",
                }
            )

            # Insert test data
            test_records = [
                {"id": "test_1", "value": 100, "category": "A"},
                {"id": "test_2", "value": 200, "category": "B"},
                {"id": "test_3", "value": 300, "category": "A"},
            ]

            for record in test_records:
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "INSERT INTO async_test_data (id, data) VALUES ($1, $2)",
                        "params": [record["id"], json.dumps(record)],
                        "fetch_mode": "one",
                    }
                )

        finally:
            await pool.process({"operation": "release", "connection_id": conn_id})

        yield pool

        await pool._cleanup()

    @pytest_asyncio.fixture
    async def async_gateway(self, test_database):
        """Set up durable gateway with async workflows."""
        temp_dir = tempfile.mkdtemp()

        # Create gateway with disk-based checkpointing
        checkpoint_manager = CheckpointManager(
            disk_storage=DiskStorage(temp_dir),
            retention_hours=48,
            compression_enabled=True,
        )

        gateway = DurableAPIGateway(
            title="AsyncPythonCodeNode E2E Gateway",
            enable_durability=True,
            checkpoint_manager=checkpoint_manager,
            durability_opt_in=False,
        )

        # Register async workflow
        workflow = await self._create_async_workflow(test_database)
        gateway.register_workflow("async_processor", workflow)

        # Start gateway in background thread with dynamic port
        import socket

        # Get a free port dynamically
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        server_thread = threading.Thread(
            target=lambda: gateway.run(host="localhost", port=port), daemon=True
        )
        server_thread.start()

        # Wait for gateway to be ready with health check polling
        import asyncio
        from datetime import datetime

        start_time = datetime.now()
        gateway_ready = False

        while (datetime.now() - start_time).total_seconds() < 10.0:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://localhost:{port}/health", timeout=1.0
                    )
                    if response.status_code == 200:
                        gateway_ready = True
                        break
            except (httpx.ConnectError, httpx.TimeoutException):
                # Gateway not ready yet
                pass

            await asyncio.sleep(0.1)

        if not gateway_ready:
            pytest.fail("Gateway failed to start within 10 seconds")

        gateway._test_port = port

        yield gateway

        # Cleanup
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    async def _create_async_workflow(self, pool) -> WorkflowBuilder:
        """Create workflow with AsyncPythonCodeNode."""
        workflow = WorkflowBuilder()
        workflow.name = "async_data_processor"

        # Data fetching with async operations
        workflow.add_node(
            "AsyncPythonCodeNode",
            "fetch_data",
            {
                "code": """
import asyncio
import json
import asyncpg

# Connect to database
conn = await asyncpg.connect(
    host="localhost",
    port=5434,
    database="kailash_test",
    user="test_user",
    password="test_password"
)

try:
    # Fetch data with category filter
    rows = await conn.fetch(
        "SELECT id, data, status, created_at FROM async_test_data WHERE data->>'category' = $1",
        category
    )

    # Convert to records
    records = []
    for row in rows:
        record = {
            "id": row[0],
            "data": row[1],
            "status": row[2],
            "created_at": str(row[3])
        }
        records.append(record)

    result = {"result": {"records": records, "count": len(records)}}

finally:
    await conn.close()
"""
            },
        )

        # Async data processing
        workflow.add_node(
            "AsyncPythonCodeNode",
            "process_data",
            {
                "code": """
import asyncio
import json

# Process records from previous step
records = fetch_result["records"]

# Simulate async processing
async def process_record(record):
    # Simulate some async work
    await asyncio.sleep(0.01)

    # Parse JSON data if it's a string
    data = record["data"]
    if isinstance(data, str):
        data = json.loads(data)
    value = data.get("value", 0)

    # Apply transformation
    processed = {
        "id": record["id"],
        "original_value": value,
        "processed_value": value * multiplier,
        "category": data.get("category"),
        "processing_time": 0.01
    }

    return processed

# Process all records concurrently
tasks = [process_record(record) for record in records]
processed_records = await asyncio.gather(*tasks)

# Calculate summary statistics
total_original = sum(r["original_value"] for r in processed_records)
total_processed = sum(r["processed_value"] for r in processed_records)

result = {"result": {
    "processed_records": processed_records,
    "summary": {
        "record_count": len(processed_records),
        "total_original": total_original,
        "total_processed": total_processed,
        "multiplier": multiplier
    }
}}
"""
            },
        )

        # Store results back to database
        workflow.add_node(
            "AsyncPythonCodeNode",
            "store_results",
            {
                "code": """
import asyncio
import json
import uuid
import asyncpg

# Connect to database
conn = await asyncpg.connect(
    host="localhost",
    port=5434,
    database="kailash_test",
    user="test_user",
    password="test_password"
)

try:
    # Store processing results
    processing_result = process_result
    result_id = f"result_{uuid.uuid4().hex[:12]}"

    # Insert processing result
    await conn.execute(
        "INSERT INTO async_test_data (id, data, status) VALUES ($1, $2, 'completed')",
        result_id, json.dumps(processing_result)
    )

    # Update status of original records
    for record in processing_result["processed_records"]:
        await conn.execute(
            "UPDATE async_test_data SET status = 'processed' WHERE id = $1",
            record["id"]
        )

    result = {"result": {
        "result_id": result_id,
        "records_updated": len(processing_result["processed_records"]),
        "success": True
    }}

finally:
    await conn.close()
"""
            },
        )

        # Connect workflow nodes
        workflow.add_connection("fetch_data", "result", "process_data", "fetch_result")
        workflow.add_connection(
            "process_data", "result", "store_results", "process_result"
        )

        return workflow.build()

    @pytest.mark.asyncio
    async def test_async_workflow_execution(self, async_gateway, test_database):
        """Test complete async workflow execution."""
        port = async_gateway._test_port

        # Execute workflow with inputs (pool is available in global context)
        workflow_inputs = {
            "fetch_data": {"category": "A"},
            "process_data": {"multiplier": 1.5},
            "store_results": {},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{port}/async_processor/execute",
                json={"inputs": workflow_inputs},
                timeout=30.0,
            )

            assert response.status_code == 200
            result = response.json()

            # Verify workflow execution
            assert "outputs" in result
            assert "store_results" in result["outputs"]

            store_result = result["outputs"]["store_results"]["result"]
            assert store_result["success"] is True
            assert store_result["records_updated"] == 2  # Category A has 2 records

            # Verify intermediate results
            process_result = result["outputs"]["process_data"]["result"]
            assert process_result["summary"]["record_count"] == 2
            assert process_result["summary"]["multiplier"] == 1.5

            print("Async workflow completed successfully:")
            print(f"  - Records processed: {store_result['records_updated']}")
            print(f"  - Result ID: {store_result['result_id']}")

    @pytest.mark.asyncio
    async def test_async_error_handling(self, async_gateway, test_database):
        """Test async error handling in workflow."""
        port = async_gateway._test_port

        # Execute with invalid category to trigger empty results
        workflow_inputs = {
            "fetch_data": {
                "category": "Z",  # Non-existent category
            },
            "process_data": {"multiplier": 2.0},
            "store_results": {},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{port}/async_processor/execute",
                json={"inputs": workflow_inputs},
                timeout=30.0,
            )

            assert response.status_code == 200
            result = response.json()

            # Should handle empty results gracefully
            store_result = result["outputs"]["store_results"]["result"]
            assert store_result["success"] is True
            assert store_result["records_updated"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_async_requests(self, async_gateway, test_database):
        """Test concurrent async workflow executions."""
        port = async_gateway._test_port

        # Create multiple concurrent requests
        async def execute_workflow(category, multiplier):
            workflow_inputs = {
                "fetch_data": {"category": category},
                "process_data": {"multiplier": multiplier},
                "store_results": {},
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://localhost:{port}/async_processor/execute",
                    json={"inputs": workflow_inputs},
                    timeout=30.0,
                )
                return response

        # Execute multiple workflows concurrently
        tasks = [
            execute_workflow("A", 2.0),
            execute_workflow("B", 3.0),
            execute_workflow("A", 1.5),
        ]

        responses = await asyncio.gather(*tasks)

        # All should succeed
        for response in responses:
            assert response.status_code == 200
            result = response.json()
            assert result["outputs"]["store_results"]["result"]["success"] is True

        print(f"Completed {len(responses)} concurrent async workflows successfully")
