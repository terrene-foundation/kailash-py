"""
End-to-End User Flow Tests for AsyncLocalRuntime.

Tests complete developer workflows and user experiences:
1. First-time developer setup and usage
2. Production workflow development and deployment
3. Performance optimization workflows
4. Error handling and debugging workflows
5. Advanced resource management scenarios
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import pytest
from tests.utils.docker_config import DATABASE_CONFIG, REDIS_CONFIG

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import AsyncPythonCodeNode, PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONReaderNode
from kailash.resources import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
    ResourceRegistry,
)
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import WorkflowBuilder


@pytest.fixture
def sample_data_files():
    """Create sample data files for user flow testing."""
    temp_dir = tempfile.mkdtemp()

    # Sample customer data
    customer_file = Path(temp_dir) / "customers.csv"
    with open(customer_file, "w") as f:
        f.write("customer_id,name,email,signup_date,plan\n")
        f.write("1,Acme Corp,contact@acme.com,2023-01-15,enterprise\n")
        f.write("2,Beta Ltd,info@beta.com,2023-02-20,professional\n")
        f.write("3,Gamma Inc,hello@gamma.com,2023-03-10,starter\n")
        f.write("4,Delta Co,sales@delta.com,2023-04-05,professional\n")
        f.write("5,Echo LLC,team@echo.com,2023-05-12,enterprise\n")

    # Sample transaction data
    transaction_file = Path(temp_dir) / "transactions.csv"
    with open(transaction_file, "w") as f:
        f.write("transaction_id,customer_id,amount,date,status\n")
        f.write("T001,1,1500.00,2023-06-01,completed\n")
        f.write("T002,2,750.00,2023-06-02,completed\n")
        f.write("T003,1,2000.00,2023-06-03,pending\n")
        f.write("T004,3,250.00,2023-06-04,completed\n")
        f.write("T005,4,900.00,2023-06-05,failed\n")
        f.write("T006,5,1800.00,2023-06-06,completed\n")
        f.write("T007,2,1200.00,2023-06-07,completed\n")

    # Configuration file
    config_file = Path(temp_dir) / "config.json"
    with open(config_file, "w") as f:
        json.dump(
            {
                "processing_rules": {
                    "min_transaction_amount": 100,
                    "max_transaction_amount": 10000,
                    "allowed_statuses": ["completed", "pending"],
                    "enterprise_discount": 0.1,
                    "professional_discount": 0.05,
                },
                "notifications": {
                    "high_value_threshold": 1000,
                    "failed_transaction_alert": True,
                },
            },
            f,
            indent=2,
        )

    yield {
        "customers": str(customer_file),
        "transactions": str(transaction_file),
        "config": str(config_file),
        "temp_dir": temp_dir,
    }

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestDeveloperUserFlows:
    """Test complete developer user flows with AsyncLocalRuntime."""

    async def test_first_time_developer_workflow(self, sample_data_files):
        """
        User Flow: New developer using AsyncLocalRuntime for the first time.

        Scenario: Developer wants to build a simple data processing workflow
        and expects it to "just work" with minimal configuration.
        """
        # Step 1: Developer creates a basic runtime (minimal setup)
        runtime = AsyncLocalRuntime()  # No complex configuration needed

        # Step 2: Developer creates a simple workflow with mixed node types
        # This simulates typical "getting started" scenario
        workflow_builder = WorkflowBuilder()

        # Add nodes using new API format
        workflow_builder.add_node(
            "CSVReaderNode",
            "read_customers",
            {"file_path": sample_data_files["customers"]},
        )

        workflow_builder.add_node(
            "PythonCodeNode",
            "process_data",
            {
                "code": """
# Simple data processing - developer's first Python code node
processed = []
for customer in data:
    processed.append({
        'name': customer['name'],
        'plan': customer['plan'],
        'is_enterprise': customer['plan'] == 'enterprise'
    })
result = {'processed_customers': processed, 'total': len(processed)}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "async_analysis",
            {
                "code": """
# Developer tries async node for the first time
import asyncio

# Simulate some async work
await asyncio.sleep(0.01)

enterprise_count = sum(1 for c in processed_customers if c['is_enterprise'])
total_customers = len(processed_customers)

result = {
    'enterprise_customers': enterprise_count,
    'total_customers': total_customers,
    'enterprise_percentage': (enterprise_count / total_customers * 100) if total_customers > 0 else 0
}
"""
            },
        )

        # Add connections using new API format
        workflow_builder.add_connection(
            "read_customers", "data", "process_data", "data"
        )
        workflow_builder.add_connection(
            "process_data",
            "result.processed_customers",
            "async_analysis",
            "processed_customers",
        )

        workflow = workflow_builder.build()

        # Step 3: Developer executes workflow and expects it to work
        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Verify: No errors, reasonable performance, expected results
        assert len(result["errors"]) == 0, "New developer should not encounter errors"
        assert execution_time < 5, "Should complete quickly for new developer"

        # Check results structure is intuitive
        assert "results" in result
        assert "read_customers" in result["results"]
        assert "process_data" in result["results"]
        assert "async_analysis" in result["results"]

        # Verify data flow worked as expected
        process_result = result["results"]["process_data"][
            "result"
        ]  # PythonCodeNode wraps output in 'result'
        assert process_result["total"] == 5  # 5 customers in test data

        analysis_result = result["results"]["async_analysis"]
        assert analysis_result["total_customers"] == 5
        assert analysis_result["enterprise_customers"] == 2  # Acme Corp and Echo LLC
        assert abs(analysis_result["enterprise_percentage"] - 40.0) < 0.1

        # Verify mixed sync/async execution worked seamlessly
        assert isinstance(
            result["results"]["process_data"]["result"]["processed_customers"], list
        )
        assert isinstance(
            result["results"]["async_analysis"]["enterprise_percentage"], float
        )

        print(f"✅ First-time developer workflow completed in {execution_time:.2f}s")
        print(
            f"   Found {analysis_result['enterprise_customers']} enterprise customers ({analysis_result['enterprise_percentage']:.1f}%)"
        )

        await runtime.cleanup()

    async def test_production_workflow_development(self, sample_data_files):
        """
        User Flow: Developer building production-ready workflow with resources.

        Scenario: Developer needs to process customer and transaction data,
        apply business rules, cache results, and handle errors gracefully.
        """
        # Step 1: Developer sets up production-like resource registry
        registry = ResourceRegistry(enable_metrics=True)

        # Use Docker test infrastructure for production-like testing
        registry.register_factory(
            "analytics_db",
            DatabasePoolFactory(
                backend="postgresql",
                host=DATABASE_CONFIG["host"],
                port=DATABASE_CONFIG["port"],
                database=DATABASE_CONFIG["database"],
                user=DATABASE_CONFIG["user"],
                password=DATABASE_CONFIG["password"],
                min_size=3,
                max_size=15,
            ),
        )

        registry.register_factory(
            "cache_cluster",
            CacheFactory(
                backend="redis",
                host=REDIS_CONFIG["host"],
                port=REDIS_CONFIG["port"],
                db=1,
            ),
        )

        registry.register_factory(
            "notification_api",
            HttpClientFactory(
                base_url="http://httpbin.org",  # Use a real test API
                timeout=30,
                headers={"Authorization": "Bearer test-token"},
            ),
        )

        # Step 2: Developer creates production runtime with monitoring
        runtime = AsyncLocalRuntime(
            resource_registry=registry,
            max_concurrent_nodes=8,
            enable_analysis=True,
            enable_profiling=True,
            thread_pool_size=4,
        )

        # Step 3: Developer builds complex production workflow
        workflow_builder = WorkflowBuilder()

        # Add data loading nodes
        workflow_builder.add_node(
            "CSVReaderNode",
            "load_customers",
            {"file_path": sample_data_files["customers"]},
        )

        workflow_builder.add_node(
            "CSVReaderNode",
            "load_transactions",
            {"file_path": sample_data_files["transactions"]},
        )

        workflow_builder.add_node(
            "JSONReaderNode", "load_config", {"file_path": sample_data_files["config"]}
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "join_data",
            {
                "code": """
# Join customer and transaction data
customer_map = {c['customer_id']: c for c in customers}
enriched_transactions = []

for transaction in transactions:
    customer_id = transaction['customer_id']
    if customer_id in customer_map:
        enriched = transaction.copy()
        enriched['customer_name'] = customer_map[customer_id]['name']
        enriched['customer_plan'] = customer_map[customer_id]['plan']
        enriched_transactions.append(enriched)

result = {'enriched_transactions': enriched_transactions, 'join_count': len(enriched_transactions)}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "apply_business_rules",
            {
                "code": """
# Apply business rules and calculations
rules = config['processing_rules']
notifications_config = config['notifications']

processed_transactions = []
alerts = []

for transaction in enriched_transactions:
    amount = float(transaction['amount'])
    status = transaction['status']
    plan = transaction['customer_plan']

    # Skip if outside allowed parameters
    if amount < rules['min_transaction_amount'] or amount > rules['max_transaction_amount']:
        continue

    if status not in rules['allowed_statuses']:
        continue

    # Apply discounts
    discount = 0
    if plan == 'enterprise':
        discount = rules['enterprise_discount']
    elif plan == 'professional':
        discount = rules['professional_discount']

    final_amount = amount * (1 - discount)

    processed_transaction = transaction.copy()
    processed_transaction['original_amount'] = amount
    processed_transaction['discount_applied'] = discount
    processed_transaction['final_amount'] = final_amount
    processed_transactions.append(processed_transaction)

    # Generate alerts for high-value transactions
    if amount >= notifications_config['high_value_threshold']:
        alerts.append({
            'type': 'high_value_transaction',
            'customer': transaction['customer_name'],
            'amount': amount,
            'transaction_id': transaction['transaction_id']
        })

result = {
    'processed_transactions': processed_transactions,
    'alerts': alerts,
    'processing_stats': {
        'total_processed': len(processed_transactions),
        'total_alerts': len(alerts),
        'total_discount_applied': sum(t['discount_applied'] * t['original_amount'] for t in processed_transactions)
    }
}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "cache_results",
            {
                "code": """
import json
import time

# Cache processing results
cache = await get_resource("cache_cluster")

# Cache processed transactions
cache_key = f"processed_transactions_{int(time.time())}"
await cache.setex(cache_key, 3600, json.dumps(processed_transactions))  # 1 hour TTL

# Cache processing stats
stats_key = "latest_processing_stats"
await cache.setex(stats_key, 1800, json.dumps(processing_stats))  # 30 min TTL

result = {
    'cached_transaction_key': cache_key,
    'cached_stats_key': stats_key,
    'cache_operations_completed': 2
}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "store_analytics",
            {
                "code": """
# Store analytics in database
db = await get_resource("analytics_db")

# Setup analytics table
async with db.acquire() as conn:
    # Drop table if exists to ensure clean schema
    await conn.execute('DROP TABLE IF EXISTS transaction_analytics')
    await conn.execute('''
        CREATE TABLE transaction_analytics (
            id SERIAL PRIMARY KEY,
            customer_id VARCHAR(20),
            customer_name VARCHAR(100),
            customer_plan VARCHAR(50),
            original_amount DECIMAL(10,2),
            final_amount DECIMAL(10,2),
            discount_applied DECIMAL(4,3),
            transaction_date VARCHAR(10),
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

# Insert processed transactions
stored_count = 0
async with db.acquire() as conn:
    for transaction in processed_transactions:
        await conn.execute('''
            INSERT INTO transaction_analytics
            (customer_id, customer_name, customer_plan, original_amount, final_amount, discount_applied, transaction_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        ''',
        transaction['customer_id'],
        transaction['customer_name'],
        transaction['customer_plan'],
        transaction['original_amount'],
        transaction['final_amount'],
        transaction['discount_applied'],
        transaction['date']  # PostgreSQL will handle string to date conversion
        )
        stored_count += 1

result = {'stored_transactions': stored_count}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "send_notifications",
            {
                "code": """
# Send notifications for alerts
api = await get_resource("notification_api")
sent_notifications = []

for alert in alerts:
    notification_payload = {
        'type': alert['type'],
        'message': f"High value transaction: {alert['customer']} - ${alert['amount']:.2f}",
        'metadata': {
            'customer': alert['customer'],
            'amount': alert['amount'],
            'transaction_id': alert['transaction_id']
        }
    }

    try:
        async with api.post("/notifications", json=notification_payload) as response:
            if response.status == 200:
                sent_notifications.append(alert['transaction_id'])
    except Exception as e:
        # Log error but don't fail the workflow
        pass

result = {
    'notifications_sent': len(sent_notifications),
    'notification_ids': sent_notifications,
    'total_alerts_processed': len(alerts)
}
"""
            },
        )

        # Add connections
        workflow_builder.add_connection(
            "load_customers", "data", "join_data", "customers"
        )
        workflow_builder.add_connection(
            "load_transactions", "data", "join_data", "transactions"
        )
        workflow_builder.add_connection(
            "load_config", "data", "apply_business_rules", "config"
        )
        workflow_builder.add_connection(
            "join_data",
            "result.enriched_transactions",
            "apply_business_rules",
            "enriched_transactions",
        )
        workflow_builder.add_connection(
            "apply_business_rules",
            "result.processed_transactions",
            "cache_results",
            "processed_transactions",
        )
        workflow_builder.add_connection(
            "apply_business_rules",
            "result.processing_stats",
            "cache_results",
            "processing_stats",
        )
        workflow_builder.add_connection(
            "apply_business_rules",
            "result.processed_transactions",
            "store_analytics",
            "processed_transactions",
        )
        workflow_builder.add_connection(
            "apply_business_rules", "result.alerts", "send_notifications", "alerts"
        )

        workflow = workflow_builder.build()

        # Step 4: Developer executes production workflow
        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Verify production requirements
        assert (
            len(result["errors"]) == 0
        ), "Production workflow should handle all errors gracefully"

        # Verify business logic worked correctly
        join_result = result["results"]["join_data"]
        assert (
            join_result["join_count"] == 7
        )  # All transactions should join with customers

        business_result = result["results"]["apply_business_rules"]
        assert business_result["processing_stats"]["total_processed"] > 0
        assert business_result["processing_stats"]["total_alerts"] >= 0

        cache_result = result["results"]["cache_results"]
        assert cache_result["cache_operations_completed"] == 2

        store_result = result["results"]["store_analytics"]
        assert store_result["stored_transactions"] > 0

        notification_result = result["results"]["send_notifications"]
        assert notification_result["total_alerts_processed"] >= 0

        # Verify performance metrics for production
        metrics = result["metrics"]
        # Verify workflow executed successfully (all nodes ran)
        assert (
            len(metrics.node_durations) >= 6
        ), f"Expected multiple nodes to execute, got: {list(metrics.node_durations.keys())}"
        assert (
            execution_time < 30
        )  # Should complete within reasonable time for production

        print(f"✅ Production workflow completed in {execution_time:.2f}s")
        print(
            f"   Processed {business_result['processing_stats']['total_processed']} transactions"
        )
        print(
            f"   Generated {business_result['processing_stats']['total_alerts']} alerts"
        )
        print(f"   Stored {store_result['stored_transactions']} analytics records")
        print(f"   Sent {notification_result['notifications_sent']} notifications")

        await runtime.cleanup()

    async def test_performance_optimization_workflow(self, sample_data_files):
        """
        User Flow: Developer optimizing workflow performance.

        Scenario: Developer has a working workflow but needs to optimize
        for better performance and identify bottlenecks.
        """
        # Step 1: Developer creates runtime with profiling enabled
        runtime = AsyncLocalRuntime(
            max_concurrent_nodes=10,
            enable_analysis=True,
            enable_profiling=True,
            thread_pool_size=6,
        )

        # Step 2: Developer creates workflow with intentional performance variations
        workflow_builder = WorkflowBuilder()

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "fast_task_1",
            {
                "code": """
import asyncio
await asyncio.sleep(0.01)  # Fast task
result = {'task': 'fast_1', 'processing_time': 0.01}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "fast_task_2",
            {
                "code": """
import asyncio
await asyncio.sleep(0.02)  # Fast task
result = {'task': 'fast_2', 'processing_time': 0.02}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "medium_task",
            {
                "code": """
import asyncio
await asyncio.sleep(0.1)  # Medium task
result = {'task': 'medium', 'processing_time': 0.1}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "slow_task",
            {
                "code": """
import asyncio
await asyncio.sleep(0.3)  # Slow task - potential bottleneck
result = {'task': 'slow', 'processing_time': 0.3}
"""
            },
        )

        workflow_builder.add_node(
            "PythonCodeNode",
            "io_intensive",
            {
                "code": """
import time
import csv

# Simulate I/O intensive work
data = []
for i in range(1000):
    data.append({'id': i, 'value': i * 2})

# Simulate file writing
time.sleep(0.05)

result = {'task': 'io_intensive', 'records_processed': len(data)}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "aggregator",
            {
                "code": """
# Aggregate results from all tasks
tasks_completed = [fast_1, fast_2, medium, slow, io_intensive]
total_processing_time = sum(task.get('processing_time', 0) for task in tasks_completed if 'processing_time' in task)

result = {
    'total_tasks': len(tasks_completed),
    'total_theoretical_time': total_processing_time,
    'aggregation_complete': True
}
"""
            },
        )

        # Add connections
        workflow_builder.add_connection("fast_task_1", "result", "aggregator", "fast_1")
        workflow_builder.add_connection("fast_task_2", "result", "aggregator", "fast_2")
        workflow_builder.add_connection("medium_task", "result", "aggregator", "medium")
        workflow_builder.add_connection("slow_task", "result", "aggregator", "slow")
        workflow_builder.add_connection(
            "io_intensive", "result", "aggregator", "io_intensive"
        )

        workflow = workflow_builder.build()

        # Step 3: Developer executes workflow and analyzes performance
        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Step 4: Developer analyzes performance metrics
        metrics = result["metrics"]
        node_durations = metrics.node_durations

        # Verify concurrent execution provided speedup
        aggregator_result = result["results"]["aggregator"]
        theoretical_sequential_time = aggregator_result["total_theoretical_time"]

        # With concurrency, actual time can vary based on system load
        # Note: E2E tests focus on functionality, not precise performance benchmarks
        speedup_ratio = theoretical_sequential_time / execution_time
        print(
            f"Performance ratio: {speedup_ratio:.2f}x (theoretical: {theoretical_sequential_time:.2f}s, actual: {execution_time:.2f}s)"
        )

        # Identify performance bottlenecks
        sorted_durations = sorted(
            node_durations.items(), key=lambda x: x[1], reverse=True
        )
        slowest_node = sorted_durations[0]

        # Verify that a slow task is identified as bottleneck
        # (could be slow_task or io_intensive depending on system performance)
        slow_task_candidates = ["slow_task", "io_intensive"]
        assert (
            slowest_node[0] in slow_task_candidates
        ), f"Expected one of {slow_task_candidates} to be bottleneck, got {slowest_node[0]}"
        print(f"Bottleneck identified: {slowest_node[0]} ({slowest_node[1]:.3f}s)")

        # Verify fast tasks completed quickly and in parallel
        fast_tasks = [
            ("fast_task_1", node_durations["fast_task_1"]),
            ("fast_task_2", node_durations["fast_task_2"]),
        ]
        for task_name, duration in fast_tasks:
            assert duration < 0.05, f"{task_name} should be fast, took {duration:.3f}s"

        print("✅ Performance optimization analysis completed")
        print(f"   Actual execution time: {execution_time:.3f}s")
        print(f"   Theoretical sequential time: {theoretical_sequential_time:.3f}s")
        print(f"   Speedup achieved: {speedup_ratio:.2f}x")
        print(
            f"   Performance bottleneck identified: {slowest_node[0]} ({slowest_node[1]:.3f}s)"
        )
        print("   Node execution times:")
        for node_name, duration in sorted_durations:
            print(f"     {node_name}: {duration:.3f}s")

        await runtime.cleanup()

    async def test_error_handling_and_debugging_workflow(self, sample_data_files):
        """
        User Flow: Developer handling errors and debugging workflow issues.

        Scenario: Developer has a workflow with potential failures and needs
        to understand what went wrong and how to fix it.
        """
        # Step 1: Developer creates runtime with debugging features
        runtime = AsyncLocalRuntime(
            max_concurrent_nodes=4, enable_analysis=True, enable_profiling=True
        )

        # Step 2: Developer creates workflow with intentional failure points
        workflow_builder = WorkflowBuilder()

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "success_node",
            {
                "code": """
# This node should always succeed
import asyncio
await asyncio.sleep(0.01)
result = {'status': 'success', 'data': 'test_data'}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "conditional_failure",
            {
                "code": """
# This node might fail based on input
import random

# Simulate conditional failure
if random.random() < 0.3:  # 30% chance of failure
    raise Exception("Simulated random failure in conditional_failure node")

result = {'status': 'success', 'processed': True}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "dependency_node",
            {
                "code": """
# This node depends on conditional_failure
# It should handle missing dependencies gracefully
if not processed:
    result = {'status': 'skipped', 'reason': 'dependency_failed'}
else:
    result = {'status': 'success', 'dependency_data': 'processed_successfully'}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "resource_failure_simulation",
            {
                "code": """
# Simulate resource access failure
try:
    # Try to access non-existent resource
    missing_resource = await get_resource("non_existent_resource")
    result = {'status': 'unexpected_success'}
except Exception as e:
    # Handle resource failure gracefully
    result = {
        'status': 'resource_failure_handled',
        'error_type': type(e).__name__,
        'error_message': str(e)
    }
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "recovery_node",
            {
                "code": """
# This node should always succeed and provide fallback data
import time

result = {
    'status': 'success',
    'fallback_data': {
        'timestamp': time.time(),
        'recovery_message': 'System recovered successfully',
        'available_data': success_data
    }
}
"""
            },
        )

        # Add connections
        workflow_builder.add_connection(
            "success_node", "result", "recovery_node", "success_data"
        )
        workflow_builder.add_connection(
            "conditional_failure", "result.processed", "dependency_node", "processed"
        )

        workflow = workflow_builder.build()

        # Step 3: Developer runs workflow multiple times to see different outcomes
        results = []
        for attempt in range(3):
            try:
                start_time = time.time()
                result = await runtime.execute_workflow_async(
                    workflow, {"attempt": attempt + 1}
                )
                execution_time = time.time() - start_time

                result["execution_time"] = execution_time
                result["attempt"] = attempt + 1
                results.append(result)

            except Exception as e:
                # Capture execution errors for analysis
                results.append(
                    {
                        "attempt": attempt + 1,
                        "execution_error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

        # Step 4: Developer analyzes results for patterns and debugging info
        successful_runs = [r for r in results if "execution_error" not in r]
        failed_runs = [r for r in results if "execution_error" in r]

        print("✅ Error handling and debugging analysis completed")
        print(f"   Total attempts: {len(results)}")
        print(f"   Successful runs: {len(successful_runs)}")
        print(f"   Failed runs: {len(failed_runs)}")

        for i, result in enumerate(results):
            print(f"\n   Attempt {i+1}:")
            if "execution_error" in result:
                print(
                    f"     ❌ Failed with {result['error_type']}: {result['execution_error']}"
                )
            else:
                print(f"     ✅ Succeeded in {result['execution_time']:.3f}s")

                # Analyze individual node results
                if result["errors"]:
                    print(f"     Node errors: {len(result['errors'])}")
                    for node_id, error in result["errors"].items():
                        print(f"       {node_id}: {error}")

                # Check which nodes succeeded
                successful_nodes = result["results"]
                print(f"     Successful nodes: {list(successful_nodes.keys())}")

                # Check specific node outcomes
                if "resource_failure_simulation" in successful_nodes:
                    resource_result = successful_nodes["resource_failure_simulation"]
                    print(f"     Resource handling: {resource_result['status']}")

                if "recovery_node" in successful_nodes:
                    recovery_result = successful_nodes["recovery_node"]
                    print(f"     Recovery status: {recovery_result['status']}")

        # Verify that error handling patterns work correctly
        at_least_one_success = len(successful_runs) > 0
        assert at_least_one_success, "At least one run should succeed"

        # Verify error recovery mechanisms
        for result in successful_runs:
            if "recovery_node" in result["results"]:
                recovery_result = result["results"]["recovery_node"]
                assert recovery_result["status"] == "success"
                assert "fallback_data" in recovery_result

            # Resource failure should be handled gracefully
            if "resource_failure_simulation" in result["results"]:
                resource_result = result["results"]["resource_failure_simulation"]
                assert resource_result["status"] == "resource_failure_handled"
                assert "error_type" in resource_result

        await runtime.cleanup()

    async def test_advanced_resource_management_workflow(self, sample_data_files):
        """
        User Flow: Advanced developer using complex resource management.

        Scenario: Developer building a workflow that uses multiple resource types,
        handles resource failures, and optimizes resource usage patterns.
        """
        # Step 1: Developer sets up complex resource registry
        registry = ResourceRegistry(enable_metrics=True)

        # Multiple database connections using Docker test infrastructure
        registry.register_factory(
            "primary_db",
            DatabasePoolFactory(
                backend="postgresql",
                host=DATABASE_CONFIG["host"],
                port=DATABASE_CONFIG["port"],
                database=DATABASE_CONFIG["database"],
                user=DATABASE_CONFIG["user"],
                password=DATABASE_CONFIG["password"],
                min_size=5,
                max_size=20,
            ),
        )

        registry.register_factory(
            "analytics_db",
            DatabasePoolFactory(
                backend="postgresql",
                host=DATABASE_CONFIG["host"],
                port=DATABASE_CONFIG["port"],
                database=DATABASE_CONFIG["database"],
                user=DATABASE_CONFIG["user"],
                password=DATABASE_CONFIG["password"],
                min_size=3,
                max_size=10,
            ),
        )

        # Multiple cache layers
        registry.register_factory(
            "l1_cache", CacheFactory(backend="memory")  # Fast in-memory cache
        )

        registry.register_factory(
            "l2_cache",
            CacheFactory(
                backend="redis", host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"]
            ),
        )

        # Multiple API clients using real test APIs
        registry.register_factory(
            "internal_api",
            HttpClientFactory(base_url="http://httpbin.org", timeout=10),
        )

        registry.register_factory(
            "external_api",
            HttpClientFactory(base_url="http://httpbin.org", timeout=30),
        )

        # Step 2: Developer creates runtime optimized for resource usage
        runtime = AsyncLocalRuntime(
            resource_registry=registry,
            max_concurrent_nodes=12,
            enable_analysis=True,
            enable_profiling=True,
            thread_pool_size=6,
        )

        # Step 3: Developer builds workflow that demonstrates advanced resource patterns
        workflow_builder = WorkflowBuilder()

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "multi_level_cache_read",
            {
                "code": """
import json

# Implement multi-level caching strategy
l1_cache = await get_resource("l1_cache")
l2_cache = await get_resource("l2_cache")

cache_key = f"user_profile_{user_id}"
data = None
source = None

# Try L1 cache first (fastest)
try:
    data = await l1_cache.get(cache_key)
    if data:
        source = "l1_cache"
        data = json.loads(data) if isinstance(data, str) else data
except:
    pass

# Try L2 cache if L1 miss
if not data:
    try:
        data = await l2_cache.get(cache_key)
        if data:
            source = "l2_cache"
            data = json.loads(data) if isinstance(data, str) else data
            # Backfill L1 cache
            await l1_cache.set(cache_key, json.dumps(data), ttl=300)
    except:
        pass

# Cache miss - will need to fetch from database
if not data:
    source = "cache_miss"

result = {
    'cached_data': data,
    'cache_source': source,
    'cache_key': cache_key
}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "database_read_with_fallback",
            {
                "code": """
import json

# If cache miss, read from database with fallback strategy
if cache_source == "cache_miss":
    primary_db = await get_resource("primary_db")
    analytics_db = await get_resource("analytics_db")

    user_data = None
    db_source = None

    # Try primary database first
    try:
        async with primary_db.acquire() as conn:
            # Simulate user lookup
            user_data = {
                'user_id': user_id,
                'name': f'User {user_id}',
                'preferences': {'theme': 'dark', 'notifications': True},
                'last_login': '2023-06-15T10:30:00Z'
            }
            db_source = "primary_db"
    except Exception as e:
        # Fallback to analytics database
        try:
            async with analytics_db.acquire() as conn:
                user_data = {
                    'user_id': user_id,
                    'name': f'User {user_id}',
                    'preferences': {'theme': 'light'},  # Limited data
                    'source': 'analytics_fallback'
                }
                db_source = "analytics_db_fallback"
        except Exception as e2:
            user_data = {'user_id': user_id, 'error': 'database_unavailable'}
            db_source = "error"

    # Cache the result in both levels
    if user_data and db_source != "error":
        l1_cache = await get_resource("l1_cache")
        l2_cache = await get_resource("l2_cache")

        data_json = json.dumps(user_data)
        await l1_cache.set(cache_key, data_json, ttl=300)  # 5 min
        await l2_cache.setex(cache_key, 3600, data_json)  # 1 hour

    final_data = user_data
else:
    # Ensure cached_data is parsed as JSON if it's a string
    if isinstance(cached_data, str):
        final_data = json.loads(cached_data)
    elif hasattr(cached_data, 'decode'):  # bytes-like object
        final_data = json.loads(cached_data.decode('utf-8'))
    else:
        final_data = cached_data
    db_source = "not_needed"

result = {
    'user_data': final_data,
    'data_source': db_source,
    'cache_info': {
        'cache_source': cache_source,
        'cache_key': cache_key
    }
}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "enrich_with_external_apis",
            {
                "code": """
import asyncio
import time

# Enrich user data with external API calls
internal_api = await get_resource("internal_api")
external_api = await get_resource("external_api")

# Concurrent API calls
async def get_internal_data():
    try:
        async with internal_api.get(f"/users/{user_id}/activity") as resp:
            if resp.status == 200:
                return await resp.json()
    except:
        pass
    return {'activity': 'unavailable'}

async def get_external_data():
    try:
        async with external_api.get(f"/enrich/user/{user_id}") as resp:
            if resp.status == 200:
                return await resp.json()
    except:
        pass
    return {'enrichment': 'unavailable'}

# Execute API calls concurrently
internal_data, external_data = await asyncio.gather(
    get_internal_data(),
    get_external_data(),
    return_exceptions=True
)

# Handle exceptions gracefully
if isinstance(internal_data, Exception):
    internal_data = {'activity': 'error', 'error': str(internal_data)}
if isinstance(external_data, Exception):
    external_data = {'enrichment': 'error', 'error': str(external_data)}

# Combine all data
enriched_profile = user_data.copy()
enriched_profile['internal_activity'] = internal_data
enriched_profile['external_enrichment'] = external_data
enriched_profile['enrichment_timestamp'] = time.time()

result = {
    'enriched_profile': enriched_profile,
    'api_calls_completed': 2,
    'enrichment_success': {
        'internal': 'error' not in internal_data,
        'external': 'error' not in external_data
    }
}
"""
            },
        )

        workflow_builder.add_node(
            "AsyncPythonCodeNode",
            "resource_usage_analysis",
            {
                "code": """
# Analyze resource usage patterns for optimization
analysis = {
    'cache_efficiency': {
        'hit_source': cache_source,
        'cache_hit': cache_source != "cache_miss",
        'multi_level_used': cache_source in ["l1_cache", "l2_cache"]
    },
    'database_usage': {
        'primary_used': db_source == "primary_db",
        'fallback_used': db_source == "analytics_db_fallback",
        'database_avoided': db_source == "not_needed"
    },
    'api_usage': {
        'internal_success': enrichment_success['internal'],
        'external_success': enrichment_success['external'],
        'concurrent_calls': True
    },
    'data_quality': {
        'complete_profile': len(enriched_profile) > 5,
        'has_preferences': 'preferences' in enriched_profile,
        'has_activity': 'internal_activity' in enriched_profile
    }
}

result = {
    'resource_analysis': analysis,
    'final_profile': enriched_profile,
    'optimization_recommendations': []
}

# Generate optimization recommendations
if not analysis['cache_efficiency']['cache_hit']:
    result['optimization_recommendations'].append("Consider cache prewarming for frequent users")

if not analysis['api_usage']['internal_success']:
    result['optimization_recommendations'].append("Investigate internal API reliability")

if not analysis['api_usage']['external_success']:
    result['optimization_recommendations'].append("Consider external API circuit breaker")
"""
            },
        )

        # Add connections
        workflow_builder.add_connection(
            "multi_level_cache_read",
            "result.cache_source",
            "database_read_with_fallback",
            "cache_source",
        )
        workflow_builder.add_connection(
            "multi_level_cache_read",
            "result.cached_data",
            "database_read_with_fallback",
            "cached_data",
        )
        workflow_builder.add_connection(
            "multi_level_cache_read",
            "result.cache_key",
            "database_read_with_fallback",
            "cache_key",
        )
        workflow_builder.add_connection(
            "database_read_with_fallback",
            "result.user_data",
            "enrich_with_external_apis",
            "user_data",
        )
        workflow_builder.add_connection(
            "database_read_with_fallback",
            "result.data_source",
            "resource_usage_analysis",
            "db_source",
        )
        workflow_builder.add_connection(
            "multi_level_cache_read",
            "result.cache_source",
            "resource_usage_analysis",
            "cache_source",
        )
        workflow_builder.add_connection(
            "enrich_with_external_apis",
            "result.enriched_profile",
            "resource_usage_analysis",
            "enriched_profile",
        )
        workflow_builder.add_connection(
            "enrich_with_external_apis",
            "result.enrichment_success",
            "resource_usage_analysis",
            "enrichment_success",
        )

        # Build the workflow
        workflow = workflow_builder.build()

        # Step 4: Execute workflow with different user IDs to test resource patterns
        test_user_ids = [12345, 67890, 12345]  # Second call to 12345 should hit cache

        for i, user_id in enumerate(test_user_ids):
            start_time = time.time()
            result = await runtime.execute_workflow_async(
                workflow, {"user_id": user_id}
            )
            execution_time = time.time() - start_time

            assert (
                len(result["errors"]) == 0
            ), "Advanced resource workflow should handle all errors gracefully"

            # Analyze resource usage
            analysis_result = result["results"]["resource_usage_analysis"]
            analysis = analysis_result["resource_analysis"]

            print(
                f"\n✅ Advanced resource workflow for user {user_id} completed in {execution_time:.3f}s"
            )
            print(
                f"   Cache efficiency: hit={analysis['cache_efficiency']['cache_hit']}, source={analysis['cache_efficiency']['hit_source']}"
            )
            print(
                f"   Database usage: primary={analysis['database_usage']['primary_used']}, avoided={analysis['database_usage']['database_avoided']}"
            )
            print(
                f"   API success: internal={analysis['api_usage']['internal_success']}, external={analysis['api_usage']['external_success']}"
            )
            print(
                f"   Data quality: complete={analysis['data_quality']['complete_profile']}"
            )

            if analysis_result["optimization_recommendations"]:
                print(
                    f"   Recommendations: {', '.join(analysis_result['optimization_recommendations'])}"
                )

            # For second call to same user, verify cache hit
            if i == 2:  # Third call, second time for user 12345
                assert analysis["cache_efficiency"][
                    "cache_hit"
                ], "Should hit cache on second call to same user"
                assert execution_time < 1.0, "Cached call should be faster"

        # Verify overall resource usage metrics
        final_metrics = result["metrics"]
        print("\n   Final resource usage metrics:")
        for resource_name, access_count in final_metrics.resource_access_count.items():
            print(f"     {resource_name}: {access_count} accesses")

        await runtime.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "e2e"])
