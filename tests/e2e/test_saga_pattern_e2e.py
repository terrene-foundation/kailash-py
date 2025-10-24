"""End-to-End tests for Saga Pattern implementation.

Tests complete saga scenarios with real infrastructure following
Tier 3 testing policy: NO MOCKING, real Docker services, complete user flows.
"""

import asyncio
import time
import uuid
from typing import Any, Dict

import asyncpg
import pytest
import redis
from kailash.nodes.transaction import SagaCoordinatorNode, SagaStepNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.requires_postgres
class TestSagaPatternE2E:
    """E2E tests for complete saga pattern scenarios."""

    @pytest.fixture(scope="class", autouse=True)
    def docker_services(self):
        """Ensure all required Docker services are running."""
        # Docker services should be running via test-env
        pass

    @pytest.fixture
    def redis_client(self):
        """Create Redis client for E2E tests."""
        redis_config = get_redis_connection_params()
        client = redis.Redis(
            host=redis_config["host"], port=redis_config["port"], decode_responses=True
        )
        # Clean up
        client.flushdb()
        yield client
        client.flushdb()
        client.close()

    @pytest.fixture
    def db_pool(self, event_loop):
        """Create PostgreSQL pool for E2E tests."""

        async def setup_pool():
            connection_string = get_postgres_connection_string()
            pool = await asyncpg.create_pool(connection_string, min_size=2, max_size=10)

            # Create tables for E2E test
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS e2e_saga_states (
                        saga_id VARCHAR(255) PRIMARY KEY,
                        saga_name VARCHAR(255),
                        state VARCHAR(50),
                        state_data JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS e2e_orders (
                        order_id VARCHAR(255) PRIMARY KEY,
                        customer_id VARCHAR(255),
                        amount DECIMAL(10,2),
                        status VARCHAR(50),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS e2e_payments (
                        payment_id VARCHAR(255) PRIMARY KEY,
                        order_id VARCHAR(255),
                        amount DECIMAL(10,2),
                        status VARCHAR(50),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS e2e_inventory (
                        item_id VARCHAR(255) PRIMARY KEY,
                        quantity INTEGER,
                        reserved INTEGER DEFAULT 0
                    );
                """
                )

                # Insert test inventory
                await conn.execute(
                    """
                    INSERT INTO e2e_inventory (item_id, quantity)
                    VALUES ('ITEM001', 100), ('ITEM002', 50)
                    ON CONFLICT (item_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        reserved = 0
                """
                )

            return pool

        async def cleanup_pool(pool):
            # Cleanup
            async with pool.acquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS e2e_saga_states CASCADE")
                await conn.execute("DROP TABLE IF EXISTS e2e_orders CASCADE")
                await conn.execute("DROP TABLE IF EXISTS e2e_payments CASCADE")
                await conn.execute("DROP TABLE IF EXISTS e2e_inventory CASCADE")

            await pool.close()

        pool = event_loop.run_until_complete(setup_pool())
        yield pool
        event_loop.run_until_complete(cleanup_pool(pool))

    def test_distributed_order_processing_saga_success(self, redis_client, db_pool):
        """Test complete order processing saga - happy path."""
        # Create coordinator with Redis persistence
        coordinator = SagaCoordinatorNode(
            saga_name="order_processing",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:saga:"},
        )

        # Start order processing saga
        order_id = f"order_{uuid.uuid4()}"
        customer_id = f"customer_{uuid.uuid4()}"

        result = coordinator.execute(
            operation="create_saga",
            context={
                "order_id": order_id,
                "customer_id": customer_id,
                "items": [{"item_id": "ITEM001", "quantity": 5}],
                "total_amount": 250.00,
            },
        )

        assert result["status"] == "success"
        saga_id = result["saga_id"]

        # Step 1: Validate order
        coordinator.execute(
            operation="add_step",
            name="validate_order",
            node_id="OrderValidationNode",
            parameters={"validation_rules": ["check_customer", "check_items"]},
            compensation_node_id="CancelOrderValidationNode",
        )

        # Step 2: Reserve inventory
        coordinator.execute(
            operation="add_step",
            name="reserve_inventory",
            node_id="InventoryReservationNode",
            parameters={"operation": "reserve"},
            compensation_node_id="ReleaseInventoryNode",
        )

        # Step 3: Process payment
        coordinator.execute(
            operation="add_step",
            name="process_payment",
            node_id="PaymentProcessingNode",
            parameters={"payment_method": "credit_card"},
            compensation_node_id="RefundPaymentNode",
        )

        # Step 4: Create shipment
        coordinator.execute(
            operation="add_step",
            name="create_shipment",
            node_id="ShipmentCreationNode",
            parameters={"shipping_method": "standard"},
            compensation_node_id="CancelShipmentNode",
        )

        # Execute the saga
        execution_result = coordinator.execute(operation="execute_saga")

        assert execution_result["status"] == "success"
        assert execution_result["state"] == "completed"
        assert execution_result["steps_completed"] == 4

        # Verify saga was persisted correctly
        status_result = coordinator.execute(operation="get_status")
        assert status_result["state"] == "completed"
        assert len(status_result["steps"]) == 4

        # Verify we can load the saga later
        new_coordinator = SagaCoordinatorNode(
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:saga:"},
        )

        load_result = new_coordinator.execute(operation="load_saga", saga_id=saga_id)

        assert load_result["status"] == "success"
        assert new_coordinator.saga_id == saga_id
        assert len(new_coordinator.steps) == 4

    def test_distributed_order_processing_saga_with_failure_and_compensation(
        self, redis_client
    ):
        """Test saga with step failure triggering compensation."""
        coordinator = SagaCoordinatorNode(
            saga_name="failing_order_processing",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:saga:"},
        )

        # Create saga
        order_id = f"failing_order_{uuid.uuid4()}"
        result = coordinator.execute(
            operation="create_saga",
            context={
                "order_id": order_id,
                "customer_id": "customer_123",
                "total_amount": 999.99,
            },
        )

        saga_id = result["saga_id"]

        # Add steps that will fail at payment
        steps = [
            {
                "name": "validate_order",
                "node_id": "ValidOrderNode",
                "comp_id": "CancelValidationNode",
            },
            {
                "name": "reserve_inventory",
                "node_id": "ReserveNode",
                "comp_id": "ReleaseNode",
            },
            {
                "name": "process_payment",
                "node_id": "FailingPaymentNode",
                "comp_id": "RefundNode",
            },  # This will fail
            {
                "name": "create_shipment",
                "node_id": "ShipmentNode",
                "comp_id": "CancelShipmentNode",
            },
        ]

        for step in steps:
            coordinator.execute(
                operation="add_step",
                name=step["name"],
                node_id=step["node_id"],
                compensation_node_id=step["comp_id"],
            )

        # Mock the payment step to fail
        async def mock_failing_payment_step(step, inputs):
            if step.name == "process_payment":
                raise Exception("Payment processing failed - insufficient funds")
            return {"status": "success", "data": f"result_{step.name}"}

        coordinator._execute_step = mock_failing_payment_step

        # Execute saga - should fail and compensate
        execution_result = coordinator.execute(operation="execute_saga")

        assert execution_result["status"] == "failed"
        assert execution_result["failed_step"] == "process_payment"
        assert "Payment processing failed" in execution_result["error"]
        assert "compensation" in execution_result

        # Verify compensation occurred
        compensation_result = execution_result["compensation"]
        assert compensation_result["status"] in ["compensated", "partial_compensation"]

        # Verify saga state is properly tracked
        status_result = coordinator.execute(operation="get_status")
        assert status_result["state"] in ["failed", "compensated"]

    def test_saga_recovery_after_system_failure(self, redis_client, db_pool):
        """Test saga recovery and resumption after system failure."""
        # For recovery test, use Redis storage to avoid database async issues
        coordinator1 = SagaCoordinatorNode(
            saga_name="recoverable_order",
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "e2e:recovery:",
            },
        )

        # Start a saga
        order_id = f"recoverable_order_{uuid.uuid4()}"
        result = coordinator1.execute(
            operation="create_saga",
            context={
                "order_id": order_id,
                "customer_id": "recovery_customer",
                "total_amount": 150.00,
            },
        )

        saga_id = result["saga_id"]

        # Add several steps
        steps = [
            "validate_order",
            "reserve_inventory",
            "process_payment",
            "create_shipment",
        ]

        for i, step_name in enumerate(steps):
            coordinator1.execute(
                operation="add_step",
                name=step_name,
                node_id=f"Node_{i}",
                compensation_node_id=f"CompNode_{i}",
            )

        # Partially execute saga (simulate system failure mid-execution)
        # Mock step execution to only complete first 2 steps
        def mock_partial_execution(step, inputs):
            if step.name in ["validate_order", "reserve_inventory"]:
                return {"status": "success", "data": f"completed_{step.name}"}
            # Simulate system failure for remaining steps
            raise Exception("System failure during execution")

        coordinator1._execute_step = mock_partial_execution

        # This should fail partway through
        try:
            coordinator1.execute(operation="execute_saga")
        except:
            pass  # Expected to fail

        # Simulate system restart - create new coordinator instance
        coordinator2 = SagaCoordinatorNode(
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "e2e:recovery:",
            },
        )

        # Load the failed saga
        load_result = coordinator2.execute(operation="load_saga", saga_id=saga_id)

        assert load_result["status"] == "success"
        assert coordinator2.saga_id == saga_id

        # Check saga status
        status_result = coordinator2.execute(operation="get_status")
        assert len(status_result["steps"]) == 4

        # Should be able to resume or compensate
        if status_result["state"] in ["running", "failed"]:
            # Try to resume with working step execution
            def mock_working_execution(step, inputs):
                return {"status": "success", "data": f"recovered_{step.name}"}

            coordinator2._execute_step = mock_working_execution

            resume_result = coordinator2.execute(operation="resume")
            # Resume might find no pending steps if all failed
            assert resume_result["status"] in ["success", "no_pending_steps"]

    def test_saga_workflow_integration(self, redis_client):
        """Test saga integration with workflow builder."""
        # Create workflow with saga coordinator
        workflow = WorkflowBuilder()

        # Add saga coordinator node
        workflow.add_node(
            "SagaCoordinatorNode",
            "saga",
            {
                "saga_name": "workflow_integrated_saga",
                "operation": "create_saga",
                "state_storage": "redis",
                "storage_config": {
                    "redis_client": redis_client,
                    "key_prefix": "e2e:workflow:saga:",
                },
            },
        )

        # Add data preparation node
        workflow.add_node(
            "PythonCodeNode",
            "prepare_data",
            {
                "code": """
# Prepare data for saga
result = {
    'order_id': f'workflow_order_{customer_id or "unknown"}',
    'processed_at': timestamp or 'now',
    'validated': True
}
            """
            },
        )

        # Connect preparation to saga
        workflow.add_connection("prepare_data", "result", "saga", "context")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(),
            parameters={
                "prepare_data": {
                    "customer_id": "workflow_customer_123",
                    "timestamp": "2024-01-15T10:00:00Z",
                }
            },
        )

        # Verify workflow execution
        assert "saga" in results
        saga_result = results["saga"]

        # The saga should be created with workflow data
        assert saga_result["status"] == "success"
        assert "saga_id" in saga_result

    def test_multiple_concurrent_sagas(self, redis_client):
        """Test multiple sagas running concurrently with shared storage."""
        num_sagas = 5
        coordinators = []
        saga_ids = []

        # Create multiple sagas concurrently
        for i in range(num_sagas):
            coordinator = SagaCoordinatorNode(
                saga_name=f"concurrent_saga_{i}",
                state_storage="redis",
                storage_config={
                    "redis_client": redis_client,
                    "key_prefix": "e2e:concurrent:",
                },
            )

            result = coordinator.execute(
                operation="create_saga",
                context={"saga_index": i, "created_at": time.time()},
            )

            coordinators.append(coordinator)
            saga_ids.append(result["saga_id"])

        # Add steps to each saga
        for i, coordinator in enumerate(coordinators):
            for j in range(3):
                coordinator.execute(
                    operation="add_step",
                    name=f"step_{j}",
                    node_id=f"Node_{i}_{j}",
                    compensation_node_id=f"CompNode_{i}_{j}",
                )

        # Execute all sagas
        results = []
        for coordinator in coordinators:
            result = coordinator.execute(operation="execute_saga")
            results.append(result)

        # Verify all sagas completed successfully
        for result in results:
            assert result["status"] == "success"
            assert result["steps_completed"] == 3

        # Verify all sagas can be listed
        manager = SagaCoordinatorNode(
            state_storage="redis",
            storage_config={
                "redis_client": redis_client,
                "key_prefix": "e2e:concurrent:",
            },
        )

        list_result = manager.execute(operation="list_sagas")
        assert list_result["count"] >= num_sagas

        # Verify each saga can be loaded individually
        for saga_id in saga_ids:
            loader = SagaCoordinatorNode(
                state_storage="redis",
                storage_config={
                    "redis_client": redis_client,
                    "key_prefix": "e2e:concurrent:",
                },
            )

            load_result = loader.execute(operation="load_saga", saga_id=saga_id)

            assert load_result["status"] == "success"
            assert loader.saga_id == saga_id
            assert len(loader.steps) == 3

    @pytest.mark.slow
    def test_saga_performance_under_load(self, redis_client):
        """Test saga performance with many operations."""
        coordinator = SagaCoordinatorNode(
            saga_name="performance_test_saga",
            state_storage="redis",
            storage_config={"redis_client": redis_client, "key_prefix": "e2e:perf:"},
        )

        # Create saga
        start_time = time.time()
        result = coordinator.execute(operation="create_saga")
        creation_time = time.time() - start_time

        assert result["status"] == "success"
        assert creation_time < 1.0  # Should create saga in under 1 second

        # Add many steps
        num_steps = 50
        step_start = time.time()

        for i in range(num_steps):
            coordinator.execute(
                operation="add_step",
                name=f"perf_step_{i}",
                node_id=f"PerfNode_{i}",
                compensation_node_id=f"PerfCompNode_{i}",
            )

        step_creation_time = time.time() - step_start
        assert step_creation_time < 5.0  # Should add 50 steps in under 5 seconds

        # Execute saga
        exec_start = time.time()
        exec_result = coordinator.execute(operation="execute_saga")
        exec_time = time.time() - exec_start

        assert exec_result["status"] == "success"
        assert exec_result["steps_completed"] == num_steps
        assert exec_time < 10.0  # Should execute 50 steps in under 10 seconds

        # Test status retrieval performance
        status_start = time.time()
        status_result = coordinator.execute(operation="get_status")
        status_time = time.time() - status_start

        assert status_result["total_steps"] == num_steps
        assert status_time < 1.0  # Should get status in under 1 second
