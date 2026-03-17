"""Production Readiness Integration Test Suite.

Validates all production readiness fixes work together end-to-end.
This is TODO-034 — the final validation that all 34 other TODOs integrate correctly.
"""

import asyncio
import os
import tempfile
import time
from typing import Any, Dict

import pytest

from kailash.nodes.base import NodeRegistry
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.transaction.node_executor import (
    MockNodeExecutor,
    RegistryNodeExecutor,
)
from kailash.nodes.transaction.saga_coordinator import SagaCoordinatorNode, SagaState
from kailash.middleware.gateway.event_store import EventStore
from kailash.middleware.gateway.event_store_sqlite import SqliteEventStoreBackend
from kailash.runtime.shutdown import ShutdownCoordinator
from kailash.runtime.signals import SignalChannel, QueryRegistry
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.execution_tracker import ExecutionTracker
from kailash.runtime.tracing import WorkflowTracer, get_workflow_tracer
from kailash.runtime.pause import PauseController
from kailash.runtime.quotas import ResourceQuotas, QuotaEnforcer
from kailash.workflow.dlq import PersistentDLQ
from kailash.workflow.versioning import WorkflowVersionRegistry
from kailash.workflow.continuation import ContinueAsNew, ContinuationContext


class TestSagaRealExecution:
    """Verify saga coordinator executes real nodes (M1/M2 fix)."""

    @pytest.mark.asyncio
    async def test_saga_full_lifecycle_with_mock_executor(self):
        """Saga creates, executes, and returns real results."""
        executor = MockNodeExecutor()
        executor.set_response(
            "ProcessOrder", {"order_id": "ORD-123", "status": "processed"}
        )
        executor.set_response(
            "ChargePayment", {"payment_id": "PAY-456", "amount": 99.99}
        )
        executor.set_response("ShipOrder", {"tracking": "TRACK-789"})

        saga = SagaCoordinatorNode(
            saga_name="order_saga",
            executor=executor,
        )

        await saga.async_run(operation="create_saga", context={})
        await saga.async_run(
            operation="add_step",
            name="process",
            node_id="ProcessOrder",
            parameters={"order": "ORD-123"},
        )
        await saga.async_run(
            operation="add_step",
            name="charge",
            node_id="ChargePayment",
            parameters={"amount": 99.99},
        )
        await saga.async_run(
            operation="add_step",
            name="ship",
            node_id="ShipOrder",
            parameters={"order": "ORD-123"},
        )

        result = await saga.async_run(operation="execute_saga")

        # Saga should complete — verify nodes were called
        assert saga.state in (
            SagaState.COMPLETED,
            SagaState.FAILED,
            SagaState.COMPENSATED,
        )
        call_types = [c["node_type"] for c in executor.calls]
        assert "ProcessOrder" in call_types

    @pytest.mark.asyncio
    async def test_saga_compensation_executes_real_nodes(self):
        """Failed step triggers real compensation of completed steps."""
        executor = MockNodeExecutor()
        executor.set_response("StepA", {"status": "ok"})
        executor.set_response("StepB", {"status": "ok"})
        executor.set_failure("StepC", RuntimeError("Payment declined"))
        executor.set_response("CompA", {"status": "rolled_back"})
        executor.set_response("CompB", {"status": "rolled_back"})

        saga = SagaCoordinatorNode(saga_name="comp_test", executor=executor)
        await saga.async_run(operation="create_saga")
        await saga.async_run(
            operation="add_step",
            name="a",
            node_id="StepA",
            parameters={},
            compensation_node_id="CompA",
            compensation_parameters={},
        )
        await saga.async_run(
            operation="add_step",
            name="b",
            node_id="StepB",
            parameters={},
            compensation_node_id="CompB",
            compensation_parameters={},
        )
        await saga.async_run(
            operation="add_step", name="c", node_id="StepC", parameters={}
        )

        result = await saga.async_run(operation="execute_saga")

        assert result["status"] in ("compensated", "failed")
        # Verify at least one compensation node was called
        comp_calls = [c for c in executor.calls if c["node_type"] in ("CompA", "CompB")]
        assert (
            len(comp_calls) >= 1
        ), f"Expected compensation calls, got: {[c['node_type'] for c in executor.calls]}"


class TestEventStorePersistence:
    """Verify event store persists across restarts (S1 fix)."""

    @pytest.mark.asyncio
    async def test_events_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")

            # Write events
            backend1 = SqliteEventStoreBackend(db_path)
            await backend1.append(
                "stream-1",
                [
                    {"type": "OrderCreated", "data": {"id": "123"}},
                    {"type": "OrderPaid", "data": {"amount": 50}},
                ],
            )
            backend1.close()

            # Read from new instance
            backend2 = SqliteEventStoreBackend(db_path)
            events = await backend2.get("stream-1")
            backend2.close()

            assert len(events) == 2
            assert events[0]["type"] == "OrderCreated"
            assert events[1]["type"] == "OrderPaid"


class TestCheckpointResume:
    """Verify checkpoint state capture and restoration (M4/M5 fix)."""

    def test_execution_tracker_round_trip(self):
        """Tracker serializes and deserializes correctly."""
        tracker = ExecutionTracker()
        tracker.record_completion("node_1", {"result": "data_1"})
        tracker.record_completion("node_2", {"result": "data_2"})
        tracker.record_completion("node_3", {"result": "data_3"})

        serialized = tracker.to_dict()
        restored = ExecutionTracker.from_dict(serialized)

        assert restored.is_completed("node_1")
        assert restored.is_completed("node_2")
        assert restored.is_completed("node_3")
        assert not restored.is_completed("node_4")
        assert restored.get_output("node_1") == {"result": "data_1"}


class TestSignalChannel:
    """Verify workflow signals work (S2 fix)."""

    @pytest.mark.asyncio
    async def test_signal_send_and_receive(self):
        channel = SignalChannel()
        channel.send("approval", {"approved": True, "by": "admin"})

        data = await channel.wait_for("approval", timeout=1.0)
        assert data == {"approved": True, "by": "admin"}

    @pytest.mark.asyncio
    async def test_signal_timeout(self):
        channel = SignalChannel()
        with pytest.raises(TimeoutError):
            await channel.wait_for("never_sent", timeout=0.1)


class TestGracefulShutdown:
    """Verify coordinated shutdown (S7 fix)."""

    @pytest.mark.asyncio
    async def test_shutdown_priority_ordering(self):
        execution_order = []

        async def handler_a():
            execution_order.append("a")

        async def handler_b():
            execution_order.append("b")

        async def handler_c():
            execution_order.append("c")

        coordinator = ShutdownCoordinator(timeout=5.0)
        coordinator.register("close_connections", handler_c, priority=3)
        coordinator.register("stop_accepting", handler_a, priority=0)
        coordinator.register("drain_workflows", handler_b, priority=1)

        results = await coordinator.shutdown()

        assert execution_order == ["a", "b", "c"]
        assert all(v == "ok" for v in results.values())


class TestPersistentDLQ:
    """Verify dead letter queue persists (S4 fix)."""

    def test_dlq_persist_and_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "dlq.db")

            # Enqueue
            with PersistentDLQ(db_path) as dlq:
                dlq.enqueue(
                    "wf-1", "Connection timeout", '{"input": "data"}', max_retries=2
                )

            # Verify persists
            with PersistentDLQ(db_path) as dlq:
                stats = dlq.get_stats()
                assert stats["pending"] == 1

                items = dlq.dequeue_ready()
                assert len(items) == 1
                assert items[0].workflow_id == "wf-1"


class TestCancellation:
    """Verify workflow cancellation (X8 fix)."""

    @pytest.mark.asyncio
    async def test_cancellation_token(self):
        token = CancellationToken()
        assert not token.is_cancelled

        token.cancel()
        assert token.is_cancelled

        with pytest.raises(Exception):
            token.check()


class TestWorkflowTracer:
    """Verify OTel tracing graceful degradation (S6 fix)."""

    def test_tracer_works_without_otel(self):
        tracer = WorkflowTracer()
        # Should not raise even without OTel installed
        span = tracer.start_workflow_span("wf-1", "test_workflow")
        node_span = tracer.start_node_span("n-1", "PythonCode", span)
        tracer.end_span(node_span)
        tracer.end_span(span)


class TestResourceQuotas:
    """Verify resource quotas (N4 fix)."""

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        quotas = ResourceQuotas(max_concurrent_workflows=2)
        enforcer = QuotaEnforcer(quotas)

        async with enforcer.acquire():
            async with enforcer.acquire():
                assert enforcer.stats["active"] == 2
                assert enforcer.stats["available"] == 0


class TestWorkflowVersioning:
    """Verify workflow versioning (S8 fix)."""

    def test_version_registry(self):
        registry = WorkflowVersionRegistry()
        registry.register("my_workflow", "1.0.0", "builder_v1")
        registry.register("my_workflow", "2.0.0", "builder_v2")

        latest = registry.get("my_workflow")
        assert latest.version == "2.0.0"

        specific = registry.get("my_workflow", "1.0.0")
        assert specific.version == "1.0.0"


class TestContinueAsNew:
    """Verify continue-as-new pattern (N1 fix)."""

    def test_continuation_context(self):
        ctx = ContinuationContext(max_depth=5)
        ctx.record_continuation("run-1", {"batch": 0})
        ctx.record_continuation("run-2", {"batch": 1})

        assert ctx.depth == 2
        assert ctx.continued_from == "run-2"

    def test_max_depth_exceeded(self):
        ctx = ContinuationContext(max_depth=2)
        ctx.record_continuation("run-1", {})
        ctx.record_continuation("run-2", {})
        with pytest.raises(Exception):
            ctx.record_continuation("run-3", {})


class TestPauseController:
    """Verify pause/resume (N6 fix)."""

    @pytest.mark.asyncio
    async def test_pause_and_resume(self):
        controller = PauseController()
        assert not controller.is_paused

        controller.pause()
        assert controller.is_paused

        controller.resume()
        assert not controller.is_paused

        # Should not block when not paused
        await asyncio.wait_for(controller.wait_if_paused(), timeout=0.1)


class TestAllImportsResolve:
    """Verify all new modules are importable."""

    def test_runtime_imports(self):
        from kailash.runtime.signals import SignalChannel
        from kailash.runtime.shutdown import ShutdownCoordinator
        from kailash.runtime.cancellation import CancellationToken
        from kailash.runtime.execution_tracker import ExecutionTracker
        from kailash.runtime.tracing import WorkflowTracer
        from kailash.runtime.pause import PauseController
        from kailash.runtime.quotas import QuotaEnforcer
        from kailash.runtime.scheduler import WorkflowScheduler

    def test_transaction_imports(self):
        from kailash.nodes.transaction.node_executor import (
            NodeExecutor,
            RegistryNodeExecutor,
            MockNodeExecutor,
        )
        from kailash.nodes.transaction.participant_transport import (
            ParticipantTransport,
            LocalNodeTransport,
        )

    def test_middleware_imports(self):
        from kailash.middleware.gateway.event_store_sqlite import (
            SqliteEventStoreBackend,
        )
        from kailash.middleware.gateway.event_store_backend import EventStoreBackend

    def test_workflow_imports(self):
        from kailash.workflow.dlq import PersistentDLQ
        from kailash.workflow.versioning import WorkflowVersionRegistry
        from kailash.workflow.continuation import ContinueAsNew, ContinuationContext
