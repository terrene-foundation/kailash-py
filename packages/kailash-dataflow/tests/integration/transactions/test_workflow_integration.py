"""
Integration Tests: Workflow Integration

Tests DataFlow integration with Kailash workflows.
Focuses on data flow between nodes, transactions, and monitoring.
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict

import pytest
from dataflow import DataFlow

from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestWorkflowDataFlow:
    """Test data flow between DataFlow nodes in workflows."""

    @pytest.mark.asyncio
    async def test_node_chaining(self, test_suite, runtime):
        """Test chaining DataFlow nodes with data flow."""
        dataflow = DataFlow(test_suite.config.url)

        @dataflow.model
        class Order:
            order_number: str
            customer_id: int
            total: float = 0.0
            status: str = "pending"

        @dataflow.model
        class OrderItem:
            order_id: int
            product_name: str
            quantity: int
            unit_price: float

        # Create workflow with chained operations
        workflow = WorkflowBuilder()

        # Create order
        workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {
                "order_number": "ORD-2024-001",
                "customer_id": 123,
                "status": "processing",
            },
        )

        # Add order items — order_id is fed at runtime via connection from
        # create_order.id (flat DataFlow node params; connection populates order_id)
        workflow.add_node(
            "OrderItemCreateNode",
            "add_item_1",
            {
                "product_name": "Widget A",
                "quantity": 2,
                "unit_price": 29.99,
            },
        )

        workflow.add_node(
            "OrderItemCreateNode",
            "add_item_2",
            {
                "product_name": "Widget B",
                "quantity": 1,
                "unit_price": 49.99,
            },
        )

        # Calculate total
        workflow.add_node(
            "PythonCodeNode",
            "calculate_total",
            {
                "code": """
# Connected inputs are injected as direct local variables; the node exposes a
# single output port named `result`. DataFlow create nodes return the flat
# record, so each item field is connected individually.
result = (q1 * p1) + (q2 * p2)
"""
            },
        )

        # Update order with total — id and total arrive via connection (flat
        # DataFlow params auto-map: top-level id -> filter, total/status -> fields)
        workflow.add_node(
            "OrderUpdateNode",
            "update_total",
            {
                "status": "completed",
            },
        )

        # Connect nodes with data flow.
        # API: add_connection(from_node, from_output, to_node, to_input).
        # DataFlow nodes return the flat created/updated record; connect the
        # individual fields the downstream node needs.
        workflow.add_connection("create_order", "id", "add_item_1", "order_id")
        workflow.add_connection("create_order", "id", "add_item_2", "order_id")
        workflow.add_connection("add_item_1", "quantity", "calculate_total", "q1")
        workflow.add_connection("add_item_1", "unit_price", "calculate_total", "p1")
        workflow.add_connection("add_item_2", "quantity", "calculate_total", "q2")
        workflow.add_connection("add_item_2", "unit_price", "calculate_total", "p2")
        workflow.add_connection("calculate_total", "result", "update_total", "total")
        workflow.add_connection("create_order", "id", "update_total", "id")

        # Execute workflow
        results, _ = await runtime.execute_async(workflow.build())

        # Verify each node produced a persisted record (create/update nodes
        # return the flat row with its primary key).
        assert results["create_order"]["id"] is not None
        assert results["add_item_1"]["id"] is not None
        assert results["add_item_2"]["id"] is not None
        assert results["update_total"]["id"] == results["create_order"]["id"]

        # Check final order state via a read-back (state-persistence verification).
        verify = WorkflowBuilder()
        verify.add_node(
            "OrderReadNode",
            "read_order",
            {"conditions": {"id": results["create_order"]["id"]}},
        )
        verify_results, _ = await runtime.execute_async(verify.build())
        order = verify_results["read_order"]
        expected_total = (2 * 29.99) + (1 * 49.99)
        assert order["total"] == pytest.approx(expected_total, 0.01)
        assert order["status"] == "completed"

    @pytest.mark.xfail(
        strict=True,
        reason="Conditional connection routing (add_connection(condition=..., "
        "output_map=...) and SwitchNode true/false-path kwargs) is not part of the "
        "current WorkflowBuilder API — add_connection is 4-positional "
        "(from_node, from_output, to_node, to_input) with no conditional edges. "
        "Faithful porting to the current SwitchNode port-routing idiom is a "
        "redesign, not a stale-API fix — deferred per #1582.",
    )
    @pytest.mark.asyncio
    async def test_conditional_workflow(self, test_suite, runtime):
        """Test conditional execution with DataFlow nodes."""
        dataflow = DataFlow(test_suite.config.url)

        @dataflow.model
        class Account:
            account_number: str
            balance: float
            account_type: str  # standard, premium
            overdraft_limit: float = 0.0

        # Create test accounts
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node(
            "AccountCreateNode",
            "standard_acc",
            {
                "account_number": "STD-001",
                "balance": 100.0,
                "account_type": "standard",
                "overdraft_limit": 0.0,
            },
        )

        setup_workflow.add_node(
            "AccountCreateNode",
            "premium_acc",
            {
                "account_number": "PRM-001",
                "balance": 100.0,
                "account_type": "premium",
                "overdraft_limit": 500.0,
            },
        )

        await runtime.execute_async(setup_workflow.build())

        # Test conditional withdrawal workflow
        async def test_withdrawal(account_number: str, amount: float):
            workflow = WorkflowBuilder()

            # Get account
            workflow.add_node(
                "AccountReadNode",
                "get_account",
                {"conditions": {"account_number": account_number}},
            )

            # Check if withdrawal is allowed
            workflow.add_node(
                "PythonCodeNode",
                "check_balance",
                {
                    "code": f"""
account = inputs['account']
withdrawal_amount = {amount}

available = account['balance'] + account['overdraft_limit']
can_withdraw = available >= withdrawal_amount

outputs = {{
    'can_withdraw': can_withdraw,
    'new_balance': account['balance'] - withdrawal_amount,
    'account_id': account['id']
}}
"""
                },
            )

            # Conditional execution using SwitchNode
            workflow.add_node("SwitchNode", "decide", {"condition": ":can_withdraw"})

            # Success path: Update balance
            workflow.add_node(
                "AccountUpdateNode",
                "withdraw",
                {
                    "conditions": {"id": ":account_id"},
                    "updates": {"balance": ":new_balance"},
                },
            )

            # Failure path: Log rejection
            workflow.add_node(
                "PythonCodeNode",
                "reject",
                {
                    "code": """
outputs = {
    'status': 'rejected',
    'reason': 'Insufficient funds'
}
"""
                },
            )

            # Connect workflow
            workflow.add_connection("get_account", "check_balance", "output", "account")
            workflow.add_connection(
                "check_balance", "decide", output_map={"can_withdraw": "can_withdraw"}
            )
            workflow.add_connection(
                "decide",
                "withdraw",
                condition="true",
                output_map={"account_id": "account_id", "new_balance": "new_balance"},
            )
            workflow.add_connection("decide", "reject", condition="false")

            return await runtime.execute_async(workflow.build())

        # Test standard account (should fail for 150)
        results, _ = await test_withdrawal("STD-001", 150.0)
        assert "reject" in results
        assert results["reject"]["output"]["status"] == "rejected"

        # Test premium account (should succeed for 150)
        results, _ = await test_withdrawal("PRM-001", 150.0)
        assert "withdraw" in results
        assert results["withdraw"]["status"] == "success"
        assert results["withdraw"]["output"]["balance"] == -50.0

    @pytest.mark.asyncio
    async def test_parallel_execution(self, test_suite, runtime):
        """Test parallel execution of DataFlow nodes."""
        dataflow = DataFlow(test_suite.config.url)

        @dataflow.model
        class Task:
            name: str
            status: str = "pending"
            duration_ms: int = 0

        # Create workflow with parallel operations
        workflow = WorkflowBuilder()

        # Create multiple tasks in parallel
        task_count = 10
        for i in range(task_count):
            workflow.add_node(
                "TaskCreateNode",
                f"task_{i}",
                {"name": f"Parallel Task {i}", "status": "running"},
            )

        # Aggregate the parallel task ids in a summarize node. Each task's
        # primary key is connected as a direct input variable (t0..tN); the
        # node exposes its output under the single `result` port.
        summary_code = (
            "ids = [" + ", ".join(f"t{i}" for i in range(task_count)) + "]\n"
            "result = {\n"
            "    'total_tasks': len(ids),\n"
            "    'all_successful': all(i is not None for i in ids),\n"
            "}\n"
        )
        workflow.add_node("PythonCodeNode", "summarize", {"code": summary_code})

        # Connect all task ids to the summarize node (fan-in).
        for i in range(task_count):
            workflow.add_connection(f"task_{i}", "id", "summarize", f"t{i}")

        # Execute and measure time
        start_time = time.time()
        results, _ = await runtime.execute_async(workflow.build())
        execution_time = time.time() - start_time

        # Verify parallel execution — all task records were created and their
        # ids fanned into the summary.
        assert results["summarize"]["result"]["total_tasks"] == task_count
        assert results["summarize"]["result"]["all_successful"]

        # Should be faster than sequential (rough estimate)
        assert execution_time < task_count * 0.5  # Less than 500ms per task


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestTransactionManagement:
    """Test transaction management in workflows."""

    @pytest.mark.xfail(
        strict=True,
        reason="The transaction-node routing here relies on conditional connection "
        "edges (add_connection(node, target, condition=\"status == 'success'\") and "
        "\"status == 'failed'\" rollback branches) that are not part of the current "
        "WorkflowBuilder API — add_connection is 4-positional with no conditional "
        "edges. The Begin/Commit/RollbackTransactionNode primitives work post-fix, "
        "but the commit/rollback branching contract is a redesign — deferred per #1582.",
    )
    @pytest.mark.asyncio
    async def test_workflow_transaction(self, test_suite, runtime):
        """Test transaction boundaries in workflows."""
        dataflow = DataFlow(test_suite.config.url)

        @dataflow.model
        class BankAccount:
            account_number: str
            balance: float
            locked: bool = False

        # Create accounts
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node(
            "BankAccountCreateNode",
            "acc1",
            {"account_number": "ACC-001", "balance": 1000.0},
        )
        setup_workflow.add_node(
            "BankAccountCreateNode",
            "acc2",
            {"account_number": "ACC-002", "balance": 500.0},
        )

        await runtime.execute_async(setup_workflow.build())

        # Transfer workflow with transaction
        transfer_workflow = WorkflowBuilder()

        # Begin transaction
        transfer_workflow.add_node(
            "BeginTransactionNode", "begin_txn", {"isolation_level": "read_committed"}
        )

        # Lock accounts
        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "lock_from",
            {"conditions": {"account_number": "ACC-001"}, "updates": {"locked": True}},
        )

        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "lock_to",
            {"conditions": {"account_number": "ACC-002"}, "updates": {"locked": True}},
        )

        # Transfer amount
        transfer_amount = 200.0
        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "debit",
            {
                "conditions": {"account_number": "ACC-001"},
                "updates": {"balance": f"balance - {transfer_amount}"},
            },
        )

        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "credit",
            {
                "conditions": {"account_number": "ACC-002"},
                "updates": {"balance": f"balance + {transfer_amount}"},
            },
        )

        # Unlock accounts
        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "unlock_from",
            {"conditions": {"account_number": "ACC-001"}, "updates": {"locked": False}},
        )

        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "unlock_to",
            {"conditions": {"account_number": "ACC-002"}, "updates": {"locked": False}},
        )

        # Commit transaction
        transfer_workflow.add_node("CommitTransactionNode", "commit_txn", {})

        # Rollback node (for error cases)
        transfer_workflow.add_node("RollbackTransactionNode", "rollback_txn", {})

        # Connect success path
        transfer_workflow.add_connection("begin_txn", "lock_from")
        transfer_workflow.add_connection("begin_txn", "lock_to")
        transfer_workflow.add_connection(
            "lock_from", "debit", condition="status == 'success'"
        )
        transfer_workflow.add_connection(
            "lock_to", "credit", condition="status == 'success'"
        )
        transfer_workflow.add_connection("debit", "unlock_from")
        transfer_workflow.add_connection("credit", "unlock_to")
        transfer_workflow.add_connection("unlock_from", "commit_txn")
        transfer_workflow.add_connection("unlock_to", "commit_txn")

        # Connect rollback paths
        for node in ["lock_from", "lock_to", "debit", "credit"]:
            transfer_workflow.add_connection(
                node, "rollback_txn", condition="status == 'failed'"
            )

        # Execute transfer
        results, _ = await runtime.execute_async(transfer_workflow.build())

        # Verify transaction completed
        if "commit_txn" in results:
            assert results["commit_txn"]["status"] == "success"

            # Check final balances
            verify_workflow = WorkflowBuilder()
            verify_workflow.add_node("BankAccountListNode", "check", {})

            verify_results, _ = await runtime.execute_async(verify_workflow.build())
            accounts = verify_results["check"]["output"]

            acc1 = next(a for a in accounts if a["account_number"] == "ACC-001")
            acc2 = next(a for a in accounts if a["account_number"] == "ACC-002")

            assert acc1["balance"] == 800.0  # 1000 - 200
            assert acc2["balance"] == 700.0  # 500 + 200
            assert acc1["locked"] is False
            assert acc2["locked"] is False

    @pytest.mark.xfail(
        strict=True,
        reason="Savepoint/nested-transaction routing here relies on a conditional "
        'connection edge (add_connection(..., condition="balanced == false")) that '
        "is not part of the current WorkflowBuilder API — add_connection is "
        "4-positional with no conditional edges. Begin/Commit/RollbackTransactionNode "
        "with savepoint_name work post-fix, but the conditional rollback-to-savepoint "
        "branching contract is a redesign — deferred per #1582.",
    )
    @pytest.mark.asyncio
    async def test_nested_transactions(self, test_suite, runtime):
        """Test nested transaction handling."""
        dataflow = DataFlow(test_suite.config.url)

        @dataflow.model
        class Ledger:
            entry_type: str
            amount: float
            description: str

        # Workflow with nested transactions
        workflow = WorkflowBuilder()

        # Outer transaction
        workflow.add_node(
            "BeginTransactionNode",
            "outer_txn",
            {"isolation_level": "read_committed", "savepoint_name": "outer"},
        )

        # First operation
        workflow.add_node(
            "LedgerCreateNode",
            "entry1",
            {"entry_type": "debit", "amount": 100.0, "description": "First entry"},
        )

        # Inner transaction (savepoint)
        workflow.add_node(
            "BeginTransactionNode", "inner_txn", {"savepoint_name": "inner"}
        )

        # Second operation
        workflow.add_node(
            "LedgerCreateNode",
            "entry2",
            {"entry_type": "credit", "amount": 100.0, "description": "Second entry"},
        )

        # Simulate error in inner transaction
        workflow.add_node(
            "PythonCodeNode",
            "check_balance",
            {
                "code": """
# Simulate balance check
entries = inputs.get('entries', [])
debit_total = sum(e['amount'] for e in entries if e['entry_type'] == 'debit')
credit_total = sum(e['amount'] for e in entries if e['entry_type'] == 'credit')

# Force error for testing
outputs = {
    'balanced': False,  # Force rollback
    'difference': debit_total - credit_total
}
"""
            },
        )

        # Rollback to savepoint
        workflow.add_node(
            "RollbackTransactionNode", "rollback_inner", {"savepoint_name": "inner"}
        )

        # Continue with outer transaction
        workflow.add_node(
            "LedgerCreateNode",
            "entry3",
            {
                "entry_type": "adjustment",
                "amount": 0.0,
                "description": "Balance adjustment",
            },
        )

        # Commit outer transaction
        workflow.add_node("CommitTransactionNode", "commit_outer", {})

        # Connect workflow
        workflow.add_connection("outer_txn", "entry1")
        workflow.add_connection("entry1", "inner_txn")
        workflow.add_connection("inner_txn", "entry2")
        workflow.add_connection("entry2", "check_balance")
        workflow.add_connection(
            "check_balance", "rollback_inner", condition="balanced == false"
        )
        workflow.add_connection("rollback_inner", "entry3")
        workflow.add_connection("entry3", "commit_outer")

        # Execute
        results, _ = await runtime.execute_async(workflow.build())

        # Verify results
        assert results["entry1"]["status"] == "success"
        assert results["rollback_inner"]["status"] == "success"
        assert results["commit_outer"]["status"] == "success"

        # Check final state - entry2 should be rolled back
        check_workflow = WorkflowBuilder()
        check_workflow.add_node("LedgerListNode", "check", {})

        check_results, _ = await runtime.execute_async(check_workflow.build())
        entries = check_results["check"]["output"]

        assert len(entries) == 2  # Only entry1 and entry3
        assert any(e["description"] == "First entry" for e in entries)
        assert any(e["description"] == "Balance adjustment" for e in entries)
        assert not any(e["description"] == "Second entry" for e in entries)


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
class TestMonitoringIntegration:
    """Test monitoring integration with DataFlow."""

    @pytest.mark.xfail(
        strict=True,
        reason="db.get_monitor_nodes() is not part of the current DataFlow API — "
        "no such method exists in packages/kailash-dataflow/src (only stale docs/"
        "examples reference it). Monitoring is surfaced via monitoring=True + the "
        "connection-pool inspection API (get_connection_pool / get_metrics). "
        "Deferred monitor-node contract — see #1582.",
    )
    @pytest.mark.asyncio
    async def test_query_monitoring(self, test_suite):
        """Test query performance monitoring."""
        # Create DataFlow with monitoring enabled
        db = DataFlow(
            test_suite.config.url, monitoring=True, slow_query_threshold=0.05
        )  # 50ms for testing
        runtime = LocalRuntime()

        @db.model
        class MetricData:
            metric_name: str
            value: float
            tags: Dict[str, str] = {}

        # Get monitor nodes
        monitors = db.get_monitor_nodes()
        assert monitors is not None
        assert "transaction" in monitors
        assert "metrics" in monitors

        # Create workflow with various query patterns
        workflow = WorkflowBuilder()

        # Fast query
        workflow.add_node(
            "MetricDataCreateNode",
            "fast_op",
            {"metric_name": "cpu_usage", "value": 45.5, "tags": {"host": "server1"}},
        )

        # Potentially slow query (bulk operation)
        slow_data = [
            {"metric_name": f"metric_{i}", "value": i * 0.1, "tags": {"batch": "test"}}
            for i in range(100)
        ]

        workflow.add_node("MetricDataBulkCreateNode", "slow_op", {"records": slow_data})

        # Complex aggregation query
        workflow.add_node(
            "SQLDatabaseNode",
            "complex_query",
            {
                "connection_string": db.config.database.get_connection_url(
                    db.config.environment
                ),
                "query": """
                SELECT
                    metric_name,
                    AVG(value) as avg_value,
                    COUNT(*) as count,
                    MAX(value) as max_value,
                    MIN(value) as min_value
                FROM metricdata
                GROUP BY metric_name
                HAVING COUNT(*) > 0
                ORDER BY avg_value DESC
                LIMIT 10
            """,
            },
        )

        # Execute workflow
        start_time = time.time()
        results, _ = await runtime.execute_async(workflow.build())
        execution_time = time.time() - start_time

        # All operations should complete
        assert results["fast_op"]["status"] == "success"
        assert results["slow_op"]["status"] == "success"
        assert results["complex_query"]["status"] == "success"

        # Monitoring should track performance
        # In production, slow queries would be logged
        print(f"Workflow execution time: {execution_time:.3f}s")
        print("Monitoring active - slow queries would be tracked")

        # Check if transaction monitor detected any issues
        transaction_monitor = monitors["transaction"]
        # In real implementation, we'd check monitor metrics

    @pytest.mark.asyncio
    async def test_connection_pool_monitoring(self, test_suite):
        """Test connection pool health monitoring."""
        db = DataFlow(test_suite.config.url, monitoring=True)
        runtime = LocalRuntime()

        @db.model
        class LoadTest:
            request_id: str
            timestamp: datetime

        # Create high load scenario
        workflows = []
        for batch in range(5):
            workflow = WorkflowBuilder()

            for i in range(20):
                workflow.add_node(
                    "LoadTestCreateNode",
                    f"req_{i}",
                    {
                        "request_id": f"batch_{batch}_req_{i}",
                        "timestamp": datetime.now().isoformat(),
                    },
                )

            workflows.append(workflow.build())

        # Execute concurrently
        tasks = [runtime.execute_async(w) for w in workflows]
        await asyncio.gather(*tasks)

        # Check pool health. get_connection_pool() returns a protocol-satisfying
        # deterministic pool adapter (dataflow.testing.mock_helpers.
        # MockConnectionPool) — NOT a unittest.mock — exposing the real
        # connection-pool inspection surface (get_health_status / get_metrics /
        # max_connections) per rules/testing.md § "Protocol Adapters".
        pool = db.get_connection_pool()
        health = await pool.get_health_status()

        assert health["status"] == "healthy"
        assert health["active_connections"] >= 0
        assert health["total_connections"] <= pool.max_connections

        # Get pool metrics — assert on the keys the current pool surface exposes.
        metrics = await pool.get_metrics()

        assert metrics["connections_created"] > 0
        assert metrics["connections_reused"] > 0
        assert metrics["active_connections"] >= 0
        assert metrics["total_connections"] == pool.max_connections

        print(f"Pool metrics: {metrics}")

    @pytest.mark.xfail(
        strict=True,
        reason="db.get_monitor_nodes() is not part of the current DataFlow API — "
        "no such method exists in packages/kailash-dataflow/src (only stale docs/"
        "examples reference it). Performance-anomaly monitor nodes were never "
        "shipped on the current surface. Deferred monitor-node contract — see #1582.",
    )
    @pytest.mark.asyncio
    async def test_performance_anomaly_detection(self, test_suite):
        """Test performance anomaly detection."""
        db = DataFlow(test_suite.config.url, monitoring=True, slow_query_threshold=0.1)
        runtime = LocalRuntime()

        @db.model
        class TimeSeriesData:
            timestamp: datetime
            value: float
            sensor_id: str

        monitors = db.get_monitor_nodes()

        # Normal operations to establish baseline
        normal_workflow = WorkflowBuilder()

        base_time = datetime.now()
        for i in range(10):
            normal_workflow.add_node(
                "TimeSeriesDataCreateNode",
                f"normal_{i}",
                {
                    "timestamp": base_time.isoformat(),
                    "value": 20.0 + (i * 0.1),
                    "sensor_id": "sensor_001",
                },
            )

        await runtime.execute_async(normal_workflow.build())

        # Introduce anomaly (unusual pattern)
        anomaly_workflow = WorkflowBuilder()

        # Sudden spike in values
        for i in range(5):
            anomaly_workflow.add_node(
                "TimeSeriesDataCreateNode",
                f"anomaly_{i}",
                {
                    "timestamp": datetime.now().isoformat(),
                    "value": 100.0 + (i * 10),  # Much higher than normal
                    "sensor_id": "sensor_001",
                },
            )

        # Complex query that might be slow
        anomaly_workflow.add_node(
            "TimeSeriesDataListNode",
            "detect_spike",
            {"filter": {"sensor_id": "sensor_001", "value": {"$gt": 50.0}}},
        )

        results, _ = await runtime.execute_async(anomaly_workflow.build())

        # Check if anomaly was detected
        spike_data = results["detect_spike"]["output"]
        assert len(spike_data) == 5  # All anomaly records

        # In production, PerformanceAnomalyNode would alert on this
        if "anomaly" in monitors:
            print("Performance anomaly detection active")
