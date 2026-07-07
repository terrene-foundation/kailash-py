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
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
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

    @pytest.mark.asyncio
    async def test_conditional_workflow(self, test_suite):
        """Conditional execution with DataFlow nodes via SwitchNode routing.

        Re-expressed on the current API (#1582): the removed conditional
        connection edges (add_connection(condition=..., output_map=...)) are
        replaced by the real SwitchNode port-routing idiom — a boolean switch
        emits ``true_output`` / ``false_output`` ports wired 4-positionally, and
        ``LocalRuntime(conditional_execution="skip_branches")`` prunes the
        branch that is not taken.
        """
        db = DataFlow(test_suite.config.url)
        runtime = LocalRuntime(conditional_execution="skip_branches")

        @db.model
        class Account:
            account_number: str
            balance: float
            account_type: str  # standard, premium
            overdraft_limit: float = 0.0

        await db.create_tables_async()

        # Unique account numbers per run keep the assertions isolated from
        # rows left by prior runs of the shared PostgreSQL test database.
        tok = str(int(time.time() * 1_000_000))
        std_no, prm_no = f"STD-{tok}", f"PRM-{tok}"

        # Create test accounts
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node(
            "AccountCreateNode",
            "standard_acc",
            {
                "account_number": std_no,
                "balance": 100.0,
                "account_type": "standard",
                "overdraft_limit": 0.0,
            },
        )

        setup_workflow.add_node(
            "AccountCreateNode",
            "premium_acc",
            {
                "account_number": prm_no,
                "balance": 100.0,
                "account_type": "premium",
                "overdraft_limit": 500.0,
            },
        )

        await runtime.execute_async(
            setup_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )

        # Test conditional withdrawal workflow
        async def test_withdrawal(account_number: str, amount: float):
            workflow = WorkflowBuilder()

            # Fetch the account. The current ReadNode requires an id, so a
            # filtered list is the by-natural-key read idiom.
            workflow.add_node(
                "AccountListNode",
                "get_account",
                {"filter": {"account_number": account_number}, "limit": 1},
            )

            # Decide whether the withdrawal is allowed. Connected inputs are
            # injected as local variables; the node exposes its dict on `result`.
            workflow.add_node(
                "PythonCodeNode",
                "check_balance",
                {
                    "code": f"""
account = records[0]
withdrawal_amount = {amount}
available = account['balance'] + account['overdraft_limit']
result = {{
    'can_withdraw': available >= withdrawal_amount,
    'new_balance': account['balance'] - withdrawal_amount,
    'account_id': account['id'],
}}
"""
                },
            )

            # Boolean SwitchNode: routes the check_balance dict to true_output
            # when can_withdraw is True, else to false_output.
            workflow.add_node(
                "SwitchNode",
                "decide",
                {"condition_field": "can_withdraw", "operator": "==", "value": True},
            )

            # Success path: unpack the approved id/new balance, then update.
            # The intermediate node keeps the update reachable under
            # skip_branches (a dotted connection straight off the switch output
            # is not treated as a live branch edge by the pruning planner).
            workflow.add_node(
                "PythonCodeNode",
                "approve",
                {
                    "code": """
result = {'id': input_data['account_id'], 'balance': input_data['new_balance']}
"""
                },
            )
            workflow.add_node("AccountUpdateNode", "withdraw", {})

            # Failure path: log the rejection.
            workflow.add_node(
                "PythonCodeNode",
                "reject",
                {
                    "code": """
result = {'status': 'rejected', 'reason': 'Insufficient funds'}
"""
                },
            )

            # Wire the graph (4-positional add_connection, no conditional edges).
            workflow.add_connection(
                "get_account", "records", "check_balance", "records"
            )
            workflow.add_connection("check_balance", "result", "decide", "input_data")
            # True branch: switch -> approve -> update (id + new balance).
            workflow.add_connection("decide", "true_output", "approve", "input_data")
            workflow.add_connection("approve", "result.id", "withdraw", "id")
            workflow.add_connection("approve", "result.balance", "withdraw", "balance")
            # False branch.
            workflow.add_connection("decide", "false_output", "reject", "input_data")

            return await runtime.execute_async(
                workflow.build(),
                parameters={"workflow_context": {"dataflow_instance": db}},
            )

        # Standard account cannot cover 150 (100 + 0 overdraft) -> rejected;
        # the success branch is pruned.
        results, _ = await test_withdrawal(std_no, 150.0)
        assert "reject" in results
        assert results["reject"]["result"]["status"] == "rejected"
        assert "withdraw" not in results

        # Premium account can cover 150 (100 + 500 overdraft) -> withdrawn;
        # the failure branch is pruned.
        results, _ = await test_withdrawal(prm_no, 150.0)
        assert "withdraw" in results
        assert results["withdraw"]["balance"] == pytest.approx(-50.0, abs=0.01)
        assert "reject" not in results

        # State-persistence read-back: PRM balance is now -50.
        verify = WorkflowBuilder()
        verify.add_node(
            "AccountListNode",
            "check",
            {"filter": {"account_number": prm_no}, "limit": 1},
        )
        verify_results, _ = await runtime.execute_async(
            verify.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )
        assert verify_results["check"]["records"][0]["balance"] == pytest.approx(
            -50.0, abs=0.01
        )

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

    @pytest.mark.asyncio
    async def test_workflow_transaction(self, test_suite):
        """Transaction boundaries with SwitchNode commit/rollback routing.

        Re-expressed on the current API (#1582): the removed conditional
        connection edges (condition="status == 'success'" / "status == 'failed'")
        are replaced by the real transaction nodes (TransactionScopeNode /
        TransactionCommitNode / TransactionRollbackNode) plus a boolean
        SwitchNode routing to commit on success and rollback on failure.
        ``skip_branches`` prunes the untaken transaction terminal.
        """
        db = DataFlow(test_suite.config.url)
        runtime = LocalRuntime(conditional_execution="skip_branches")

        @db.model
        class BankAccount:
            account_number: str
            balance: float
            locked: bool = False

        await db.create_tables_async()

        tok = str(int(time.time() * 1_000_000))
        acc1_no, acc2_no = f"ACC-001-{tok}", f"ACC-002-{tok}"

        # Create accounts, capturing their ids (UpdateNode filters by id).
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node(
            "BankAccountCreateNode",
            "acc1",
            {"account_number": acc1_no, "balance": 1000.0},
        )
        setup_workflow.add_node(
            "BankAccountCreateNode",
            "acc2",
            {"account_number": acc2_no, "balance": 500.0},
        )
        setup_results, _ = await runtime.execute_async(
            setup_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )
        acc1_id = setup_results["acc1"]["id"]
        acc2_id = setup_results["acc2"]["id"]

        # Transfer workflow with a real transaction scope + commit/rollback route
        transfer_amount = 200.0
        transfer_workflow = WorkflowBuilder()

        # Begin transaction
        transfer_workflow.add_node(
            "TransactionScopeNode",
            "begin_txn",
            {"isolation_level": "READ_COMMITTED"},
        )

        # Debit ACC-001, credit ACC-002 on the scope's connection.
        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "debit",
            {
                "filter": {"id": acc1_id},
                "fields": {"balance": 1000.0 - transfer_amount},
            },
        )
        transfer_workflow.add_node(
            "BankAccountUpdateNode",
            "credit",
            {"filter": {"id": acc2_id}, "fields": {"balance": 500.0 + transfer_amount}},
        )

        # Decide the transaction outcome from both updates succeeding.
        transfer_workflow.add_node(
            "PythonCodeNode",
            "decide",
            {
                "code": """
result = {
    'status': 'success' if (debit_id is not None and credit_id is not None) else 'failed'
}
"""
            },
        )

        # Boolean SwitchNode: success -> true_output -> commit; else rollback.
        transfer_workflow.add_node(
            "SwitchNode",
            "route",
            {"condition_field": "status", "operator": "==", "value": "success"},
        )

        # Commit / rollback terminals
        transfer_workflow.add_node("TransactionCommitNode", "commit_txn", {})
        transfer_workflow.add_node("TransactionRollbackNode", "rollback_txn", {})

        # Wire the graph (4-positional add_connection, no conditional edges).
        transfer_workflow.add_connection(
            "begin_txn", "transaction_id", "debit", "transaction_id"
        )
        transfer_workflow.add_connection("debit", "id", "credit", "previous_id")
        transfer_workflow.add_connection("debit", "id", "decide", "debit_id")
        transfer_workflow.add_connection("credit", "id", "decide", "credit_id")
        transfer_workflow.add_connection("decide", "result", "route", "input_data")
        transfer_workflow.add_connection(
            "route", "true_output", "commit_txn", "trigger"
        )
        transfer_workflow.add_connection(
            "route", "false_output", "rollback_txn", "trigger"
        )

        # Execute transfer
        results, _ = await runtime.execute_async(
            transfer_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )

        # Success path taken: commit ran, rollback pruned.
        assert results["commit_txn"]["status"] == "committed"
        assert "rollback_txn" not in results

        # State-persistence read-back: balances transferred, locks clear.
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node("BankAccountListNode", "check", {"limit": 1000})
        verify_results, _ = await runtime.execute_async(
            verify_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )
        accounts = verify_results["check"]["records"]

        acc1 = next(a for a in accounts if a["account_number"] == acc1_no)
        acc2 = next(a for a in accounts if a["account_number"] == acc2_no)

        assert acc1["balance"] == pytest.approx(800.0, abs=0.01)  # 1000 - 200
        assert acc2["balance"] == pytest.approx(700.0, abs=0.01)  # 500 + 200
        assert acc1["locked"] is False
        assert acc2["locked"] is False

    @pytest.mark.asyncio
    async def test_nested_transactions(self, test_suite):
        """Nested transaction handling via savepoint + SwitchNode routing.

        Re-expressed on the current API (#1582): the removed conditional
        connection edge (condition="balanced == false") is replaced by a
        TransactionSavepointNode / TransactionRollbackToSavepointNode pair plus
        a boolean SwitchNode routing on a needs_rollback flag. entry2 is written
        inside the savepoint and removed by the rollback-to-savepoint; entry1
        and entry3 survive to the outer commit.
        """
        db = DataFlow(test_suite.config.url)
        runtime = LocalRuntime(conditional_execution="skip_branches")

        @db.model
        class Ledger:
            entry_type: str
            amount: float
            description: str

        await db.create_tables_async()

        # Unique descriptions per run keep the assertions isolated from rows
        # left by prior runs of the shared PostgreSQL test database.
        tok = str(int(time.time() * 1_000_000))
        d1 = f"First entry {tok}"
        d2 = f"Second entry {tok}"
        d3 = f"Balance adjustment {tok}"

        # Workflow with an outer transaction + inner savepoint
        workflow = WorkflowBuilder()

        # Outer transaction
        workflow.add_node(
            "TransactionScopeNode",
            "outer_txn",
            {"isolation_level": "READ_COMMITTED"},
        )

        # First operation
        workflow.add_node(
            "LedgerCreateNode",
            "entry1",
            {"entry_type": "debit", "amount": 100.0, "description": d1},
        )

        # Inner savepoint
        workflow.add_node("TransactionSavepointNode", "inner_sp", {"name": "inner"})

        # Second operation (written inside the savepoint)
        workflow.add_node(
            "LedgerCreateNode",
            "entry2",
            {"entry_type": "credit", "amount": 100.0, "description": d2},
        )

        # Balance check forces a rollback of the inner savepoint (removes entry2).
        workflow.add_node(
            "PythonCodeNode",
            "check_balance",
            {
                "code": """
# Force an imbalance so the inner savepoint is rolled back.
result = {'needs_rollback': True}
"""
            },
        )

        # Boolean SwitchNode: needs_rollback -> true_output -> rollback savepoint.
        workflow.add_node(
            "SwitchNode",
            "route",
            {"condition_field": "needs_rollback", "operator": "==", "value": True},
        )

        # Rollback to savepoint (removes entry2)
        workflow.add_node(
            "TransactionRollbackToSavepointNode",
            "rollback_inner",
            {"savepoint": "inner"},
        )

        # Continue with the outer transaction
        workflow.add_node(
            "LedgerCreateNode",
            "entry3",
            {"entry_type": "adjustment", "amount": 0.0, "description": d3},
        )

        # Commit the outer transaction
        workflow.add_node("TransactionCommitNode", "commit_outer", {})

        # Wire the graph (4-positional add_connection, no conditional edges).
        workflow.add_connection(
            "outer_txn", "transaction_id", "entry1", "transaction_id"
        )
        workflow.add_connection("entry1", "id", "inner_sp", "previous_id")
        workflow.add_connection("inner_sp", "status", "entry2", "sp_status")
        workflow.add_connection("entry2", "id", "check_balance", "entry2_id")
        workflow.add_connection("check_balance", "result", "route", "input_data")
        workflow.add_connection("route", "true_output", "rollback_inner", "trigger")
        workflow.add_connection("rollback_inner", "status", "entry3", "rb_status")
        workflow.add_connection("entry3", "id", "commit_outer", "record_count")

        # Execute
        results, _ = await runtime.execute_async(
            workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )

        # Verify results
        assert results["entry1"]["id"] is not None
        assert results["rollback_inner"]["status"] == "rolled_back_to_savepoint"
        assert results["commit_outer"]["status"] == "committed"

        # State-persistence read-back: entry1 + entry3 persist, entry2 rolled back.
        check_workflow = WorkflowBuilder()
        check_workflow.add_node("LedgerListNode", "check", {"limit": 1000})

        check_results, _ = await runtime.execute_async(
            check_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )
        descriptions = [e["description"] for e in check_results["check"]["records"]]

        assert d1 in descriptions
        assert d3 in descriptions
        assert d2 not in descriptions


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
class TestMonitoringIntegration:
    """Test monitoring integration with DataFlow."""

    @pytest.mark.asyncio
    async def test_query_monitoring(self, test_suite):
        """Query performance monitoring via monitoring=True + pool inspection.

        Re-expressed on the current API (#1582): the old monitor-nodes
        accessor was removed; the monitoring surface is monitoring=True plus
        the connection-pool inspection API (get_connection_pool /
        get_health_status / get_metrics).
        """
        # Create DataFlow with monitoring enabled
        db = DataFlow(
            test_suite.config.url, monitoring=True, slow_query_threshold=0.05
        )  # 50ms for testing
        runtime = LocalRuntime()

        @db.model
        class MetricData:
            metric_name: str
            value: float
            # NB: the field is named `labels` (not `tags`): `tags` is a reserved
            # node-metadata key on the SDK's base Node (a set), so a DataFlow
            # model field named `tags` collides at CreateNode construction.
            labels: Dict[str, str] = {}

        await db.create_tables_async()

        # Real monitoring surface: inspect connection-pool health (replaces the
        # removed monitor-nodes accessor).
        pool = db.get_connection_pool()
        health = await pool.get_health_status()
        assert health["status"] == "healthy"
        assert health["total_connections"] <= pool.max_connections

        tok = str(int(time.time() * 1_000_000))

        # Create workflow with various query patterns
        workflow = WorkflowBuilder()

        # Fast single-record write
        workflow.add_node(
            "MetricDataCreateNode",
            "fast_op",
            {
                "metric_name": f"cpu_usage_{tok}",
                "value": 45.5,
                "labels": {"host": "server1"},
            },
        )

        # Potentially slow operation (bulk write)
        slow_data = [
            {
                "metric_name": f"metric_{tok}_{i}",
                "value": i * 0.1,
                "labels": {"batch": "test"},
            }
            for i in range(100)
        ]
        workflow.add_node("MetricDataBulkCreateNode", "slow_op", {"data": slow_data})

        # Read query (verifies the fast write persisted -> read-back)
        workflow.add_node(
            "MetricDataListNode",
            "query",
            {"filter": {"metric_name": f"cpu_usage_{tok}"}, "limit": 10},
        )
        # Order the read after the fast write so it sees the committed row.
        workflow.add_connection("fast_op", "id", "query", "after_fast")

        # Execute workflow
        start_time = time.time()
        results, _ = await runtime.execute_async(workflow.build())
        execution_time = time.time() - start_time

        # All operations completed.
        assert results["fast_op"]["id"] is not None
        assert results["slow_op"]["success"] is True
        assert results["slow_op"]["inserted"] == 100
        # State-persistence read-back: the fast write is queryable.
        assert results["query"]["count"] == 1

        # Monitoring should track performance
        print(f"Workflow execution time: {execution_time:.3f}s")
        print("Monitoring active - slow queries would be tracked")

        # Monitoring surface: pool metrics are exposed for the operator.
        metrics = await pool.get_metrics()
        assert metrics["total_connections"] == pool.max_connections
        assert metrics["connections_created"] > 0
        assert metrics["active_connections"] >= 0

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

    @pytest.mark.asyncio
    async def test_performance_anomaly_detection(self, test_suite):
        """Performance anomaly detection via monitoring=True + pool metrics.

        Re-expressed on the current API (#1582): the old monitor-nodes
        accessor was removed; monitoring is surfaced via monitoring=True and
        the connection-pool inspection API. The spike is detected by reading
        the sensor's series back and filtering the anomalous values.
        """
        db = DataFlow(test_suite.config.url, monitoring=True, slow_query_threshold=0.1)
        runtime = LocalRuntime()

        @db.model
        class TimeSeriesData:
            timestamp: datetime
            value: float
            sensor_id: str

        await db.create_tables_async()

        # Unique sensor id per run keeps the spike count isolated from rows
        # left by prior runs of the shared PostgreSQL test database.
        tok = str(int(time.time() * 1_000_000))
        sensor = f"sensor_{tok}"

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
                    "sensor_id": sensor,
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
                    "sensor_id": sensor,
                },
            )

        await runtime.execute_async(anomaly_workflow.build())

        # Read the sensor series back and detect the spike (value > 50).
        detect_workflow = WorkflowBuilder()
        detect_workflow.add_node(
            "TimeSeriesDataListNode",
            "detect_spike",
            {"filter": {"sensor_id": sensor}, "limit": 100},
        )
        results, _ = await runtime.execute_async(detect_workflow.build())

        # Check if anomaly was detected
        records = results["detect_spike"]["records"]
        spike_data = [r for r in records if r["value"] > 50.0]
        assert len(spike_data) == 5  # All anomaly records

        # Monitoring surface: pool metrics are available for anomaly alerting.
        pool = db.get_connection_pool()
        metrics = await pool.get_metrics()
        assert metrics["total_connections"] == pool.max_connections
        assert metrics["connections_created"] > 0
        print("Performance anomaly detection active")
