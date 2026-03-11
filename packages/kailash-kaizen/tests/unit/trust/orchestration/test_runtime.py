"""
Tests for TrustAwareOrchestrationRuntime - Trust-aware workflow execution.

Test Intent:
- Verify trust is verified before agent task execution (pre-execution check)
- Verify actions are audited after execution (post-execution audit)
- Verify trust context propagates correctly through delegation chains
- Verify parallel workflow execution maintains trust boundaries
- Verify policy violations prevent task execution and are properly reported
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from kaizen.trust.orchestration.exceptions import (
    PolicyViolationError,
    TrustVerificationFailedError,
)
from kaizen.trust.orchestration.execution_context import (
    DelegationEntry,
    TrustExecutionContext,
)
from kaizen.trust.orchestration.policy import (
    PolicyResult,
    TrustPolicy,
    TrustPolicyEngine,
)
from kaizen.trust.orchestration.runtime import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
    TrustedTaskResult,
    TrustedWorkflowStatus,
)


class TestTrustAwareRuntimeConfig:
    """Test runtime configuration."""

    def test_default_config(self):
        """Default config should have sensible defaults."""
        config = TrustAwareRuntimeConfig()

        assert config.max_concurrent_agents == 10
        assert config.verify_before_execution is True
        assert config.audit_after_execution is True
        assert config.enable_policy_engine is True

    def test_custom_config(self):
        """Custom config values should be respected."""
        config = TrustAwareRuntimeConfig(
            max_concurrent_agents=5,
            verify_before_execution=False,
            audit_after_execution=False,
            enable_policy_engine=False,
        )

        assert config.max_concurrent_agents == 5
        assert config.verify_before_execution is False


class TestTrustedTaskResult:
    """Test task execution results."""

    def test_successful_result(self):
        """Successful result should contain output."""
        result = TrustedTaskResult(
            task_id="task-001",
            agent_id="agent-001",
            success=True,
            result={"data": "output"},
            verification_time_ms=10.5,
            execution_time_ms=150.5,
        )

        assert result.success is True
        assert result.result["data"] == "output"
        assert result.error is None

    def test_failed_result(self):
        """Failed result should contain error information."""
        result = TrustedTaskResult(
            task_id="task-001",
            agent_id="agent-001",
            success=False,
            error="Task execution failed",
            execution_time_ms=50.0,
        )

        assert result.success is False
        assert result.error == "Task execution failed"


class TestTrustedWorkflowStatus:
    """Test workflow execution status."""

    def test_workflow_status(self):
        """Workflow status should track execution state."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="workflow",
            delegated_capabilities=["read"],
        )

        status = TrustedWorkflowStatus(
            workflow_id="workflow-001",
            context=context,
            total_tasks=5,
            completed_tasks=3,
            failed_tasks=2,
        )

        assert status.total_tasks == 5
        assert status.completed_tasks == 3
        assert status.failed_tasks == 2


class TestTrustAwareOrchestrationRuntime:
    """Test trust-aware runtime initialization."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(
            return_value=MagicMock(
                capability_attestations=[],
            )
        )
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
        mock.audit = AsyncMock(return_value=MagicMock(anchor_id="audit-001"))
        mock.delegate = AsyncMock()
        return mock

    @pytest.fixture
    def mock_agent_registry(self):
        """Create mock agent registry."""
        mock = MagicMock()
        mock.get_agent = AsyncMock(
            return_value=MagicMock(
                agent_id="agent-001",
                capabilities=["read", "write"],
            )
        )
        return mock

    @pytest.fixture
    def runtime(self, mock_trust_ops, mock_agent_registry):
        """Create trust-aware runtime."""
        return TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
            agent_registry=mock_agent_registry,
            config=TrustAwareRuntimeConfig(),
        )

    def test_runtime_initialization(self, runtime):
        """Runtime should initialize with policy engine."""
        assert runtime.policy_engine is not None
        assert runtime.is_running is False

    @pytest.mark.asyncio
    async def test_runtime_start_stop(self, runtime):
        """Runtime should start and stop."""
        await runtime.start()
        assert runtime.is_running is True

        await runtime.shutdown()
        assert runtime.is_running is False


class TestTrustVerification:
    """Test pre-execution trust verification."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(
            return_value=MagicMock(
                capability_attestations=[],
            )
        )
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
        mock.audit = AsyncMock(return_value=MagicMock(anchor_id="audit-001"))
        return mock

    @pytest.fixture
    def runtime(self, mock_trust_ops):
        """Create trust-aware runtime."""
        return TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
        )

    @pytest.fixture
    def context_with_read(self):
        """Context with read capability."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read_data"],
        )

    @pytest.mark.asyncio
    async def test_verify_agent_trust_passes(
        self, runtime, context_with_read, mock_trust_ops
    ):
        """Verification passes when agent has valid trust chain."""
        result = await runtime.verify_agent_trust(
            agent_id="agent-001",
            context=context_with_read,
            action="read_data",
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_verify_agent_trust_fails_no_chain(
        self, runtime, context_with_read, mock_trust_ops
    ):
        """Verification fails when agent lacks trust chain."""
        mock_trust_ops.get_chain.return_value = None

        result = await runtime.verify_agent_trust(
            agent_id="agent-001",
            context=context_with_read,
            action="read_data",
        )

        assert result.allowed is False
        assert "trust chain" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_verify_uses_policy_engine(self, mock_trust_ops):
        """Policy engine is used when enabled in config."""
        runtime = TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
            config=TrustAwareRuntimeConfig(enable_policy_engine=True),
        )

        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
        )

        # Register a policy that will fail
        runtime.register_policy(TrustPolicy.require_capability("admin"))

        result = await runtime.verify_agent_trust(
            agent_id="agent-001",
            context=context,
            action="read",
        )

        assert result.allowed is False


class TestDelegation:
    """Test trust delegation between agents."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.delegate = AsyncMock()
        return mock

    @pytest.fixture
    def runtime(self, mock_trust_ops):
        """Create trust-aware runtime."""
        return TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
        )

    @pytest.fixture
    def supervisor_context(self):
        """Create supervisor context with full capabilities."""
        return TrustExecutionContext.create(
            parent_agent_id="root-supervisor",
            task_id="main-workflow",
            delegated_capabilities=["read", "write", "delete", "admin"],
        )

    @pytest.mark.asyncio
    async def test_create_delegation_succeeds(self, runtime, supervisor_context):
        """Delegation from supervisor to worker should succeed."""
        entry = await runtime.create_delegation(
            supervisor_id="root-supervisor",
            worker_id="worker-001",
            task_id="subtask-001",
            capabilities=["read", "write"],
            context=supervisor_context,
        )

        assert entry.delegator_id == "root-supervisor"
        assert entry.delegatee_id == "worker-001"
        assert set(entry.capabilities) == {"read", "write"}

    @pytest.mark.asyncio
    async def test_create_delegation_records_in_trust_store(
        self, runtime, supervisor_context, mock_trust_ops
    ):
        """Delegation should be recorded in trust store."""
        await runtime.create_delegation(
            supervisor_id="root-supervisor",
            worker_id="worker-001",
            task_id="subtask-001",
            capabilities=["read"],
            context=supervisor_context,
        )

        mock_trust_ops.delegate.assert_called()


class TestTrustedTaskExecution:
    """Test task execution with trust verification."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(
            return_value=MagicMock(
                capability_attestations=[],
            )
        )
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
        mock.audit = AsyncMock(return_value=MagicMock(anchor_id="audit-001"))
        return mock

    @pytest.fixture
    def runtime(self, mock_trust_ops):
        """Create trust-aware runtime."""
        return TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
        )

    @pytest.fixture
    def context(self):
        """Create execution context."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="workflow",
            delegated_capabilities=["analyze"],
        )

    @pytest.mark.asyncio
    async def test_execute_trusted_task_verifies_first(self, runtime, context):
        """Task execution should verify trust before running."""
        task_executed = False

        async def task_executor(task):
            nonlocal task_executed
            task_executed = True
            return {"result": "success"}

        result = await runtime.execute_trusted_task(
            agent_id="agent-001",
            task="analyze data",
            context=context,
            executor=task_executor,
        )

        assert task_executed is True
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_trusted_task_raises_on_trust_failure(
        self, runtime, mock_trust_ops
    ):
        """Task should raise if trust verification fails."""
        mock_trust_ops.get_chain.return_value = None  # No trust chain

        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="workflow",
            delegated_capabilities=["analyze"],
        )

        async def task_executor(task):
            return {"result": "success"}

        with pytest.raises(TrustVerificationFailedError):
            await runtime.execute_trusted_task(
                agent_id="agent-001",
                task="do something",
                context=context,
                executor=task_executor,
            )

    @pytest.mark.asyncio
    async def test_execute_trusted_task_records_audit(
        self, runtime, context, mock_trust_ops
    ):
        """Task execution should record audit entry."""

        async def task_executor(task):
            return {"result": "done"}

        await runtime.execute_trusted_task(
            agent_id="agent-001",
            task="analyze",
            context=context,
            executor=task_executor,
        )

        # Audit should be recorded after execution
        mock_trust_ops.audit.assert_called()

    @pytest.mark.asyncio
    async def test_execute_task_handles_executor_error(self, runtime, context):
        """Task execution should handle executor errors gracefully."""

        async def failing_executor(task):
            raise ValueError("Task failed")

        result = await runtime.execute_trusted_task(
            agent_id="agent-001",
            task="failing task",
            context=context,
            executor=failing_executor,
        )

        assert result.success is False
        assert "Task failed" in result.error


class TestTrustedWorkflowExecution:
    """Test multi-task workflow execution with trust."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(
            return_value=MagicMock(
                capability_attestations=[],
            )
        )
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
        mock.audit = AsyncMock(return_value=MagicMock(anchor_id="audit-001"))
        return mock

    @pytest.fixture
    def runtime(self, mock_trust_ops):
        """Create trust-aware runtime."""
        return TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
        )

    @pytest.fixture
    def context(self):
        """Create execution context with multiple capabilities."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="workflow",
            delegated_capabilities=["read", "analyze", "report"],
        )

    @pytest.mark.asyncio
    async def test_execute_workflow_multiple_tasks(self, runtime, context):
        """Workflow should execute all tasks in sequence."""
        tasks_executed = []

        async def task_executor(agent_id, task):
            tasks_executed.append(task)
            return {"result": f"done: {task}"}

        def agent_selector(task):
            return "agent-001"

        status = await runtime.execute_trusted_workflow(
            tasks=["task1", "task2", "task3"],
            context=context,
            agent_selector=agent_selector,
            task_executor=task_executor,
        )

        assert status.total_tasks == 3
        assert status.completed_tasks == 3
        assert status.failed_tasks == 0
        assert tasks_executed == ["task1", "task2", "task3"]

    @pytest.mark.asyncio
    async def test_workflow_tracks_failures(self, runtime, context):
        """Workflow should track task failures."""

        async def sometimes_failing_executor(agent_id, task):
            if task == "fail-task":
                raise ValueError("Intentional failure")
            return {"result": "success"}

        def agent_selector(task):
            return "agent-001"

        status = await runtime.execute_trusted_workflow(
            tasks=["task1", "fail-task", "task3"],
            context=context,
            agent_selector=agent_selector,
            task_executor=sometimes_failing_executor,
        )

        assert status.total_tasks == 3
        assert status.completed_tasks == 2  # task1 and task3
        assert status.failed_tasks == 1  # fail-task


class TestParallelWorkflowExecution:
    """Test parallel task execution with trust."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(
            return_value=MagicMock(
                capability_attestations=[],
            )
        )
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
        mock.audit = AsyncMock(return_value=MagicMock(anchor_id="audit-001"))
        return mock

    @pytest.fixture
    def runtime(self, mock_trust_ops):
        """Create trust-aware runtime with parallel support."""
        return TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
            config=TrustAwareRuntimeConfig(max_concurrent_agents=5),
        )

    @pytest.fixture
    def context(self):
        """Create execution context."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="parallel-workflow",
            delegated_capabilities=["read", "process", "analyze"],
        )

    @pytest.mark.asyncio
    async def test_execute_parallel_workflow(self, runtime, context):
        """Parallel workflow should execute groups concurrently."""
        execution_order = []

        async def task_executor(agent_id, task):
            execution_order.append(task)
            await asyncio.sleep(0.01)  # Simulate work
            return {"result": f"done: {task}"}

        # Define task groups (tasks per agent)
        task_groups = {
            "agent-1": ["task-1a", "task-1b"],
            "agent-2": ["task-2a"],
        }

        status = await runtime.execute_parallel_trusted_workflow(
            task_groups=task_groups,
            context=context,
            task_executor=task_executor,
        )

        assert status.total_tasks == 3
        assert status.completed_tasks == 3


class TestRuntimeConfiguration:
    """Test runtime behavior with different configurations."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(
            return_value=MagicMock(
                capability_attestations=[],
            )
        )
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
        mock.audit = AsyncMock(return_value=MagicMock(anchor_id="audit-001"))
        return mock

    @pytest.mark.asyncio
    async def test_skip_verification_when_disabled(self, mock_trust_ops):
        """Verification can be skipped when disabled in config."""
        mock_trust_ops.get_chain.return_value = None  # Would normally fail

        runtime = TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
            config=TrustAwareRuntimeConfig(verify_before_execution=False),
        )

        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="workflow",
            delegated_capabilities=["cap"],
        )

        task_executed = False

        async def executor(task):
            nonlocal task_executed
            task_executed = True
            return {}

        result = await runtime.execute_trusted_task(
            agent_id="agent-001",
            task="task",
            context=context,
            executor=executor,
        )

        # Task should execute even without trust chain when verification disabled
        assert task_executed is True
        assert result.success is True

    @pytest.mark.asyncio
    async def test_skip_audit_when_disabled(self, mock_trust_ops):
        """Audit can be skipped when disabled in config."""
        runtime = TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
            config=TrustAwareRuntimeConfig(audit_after_execution=False),
        )

        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="workflow",
            delegated_capabilities=["cap"],
        )

        async def executor(task):
            return {}

        await runtime.execute_trusted_task(
            agent_id="agent-001",
            task="task",
            context=context,
            executor=executor,
        )

        # Audit should not be called when disabled
        mock_trust_ops.audit.assert_not_called()


class TestRuntimeMetrics:
    """Test runtime metrics collection."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(return_value=MagicMock())
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
        mock.audit = AsyncMock(return_value=MagicMock(anchor_id="audit-001"))
        return mock

    @pytest.fixture
    def runtime(self, mock_trust_ops):
        """Create trust-aware runtime."""
        return TrustAwareOrchestrationRuntime(
            trust_operations=mock_trust_ops,
        )

    @pytest.fixture
    def context(self):
        """Create execution context."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="workflow",
            delegated_capabilities=["analyze"],
        )

    @pytest.mark.asyncio
    async def test_metrics_tracked(self, runtime, context):
        """Runtime should track execution metrics."""

        async def executor(task):
            return {"result": "done"}

        await runtime.execute_trusted_task(
            agent_id="agent-001",
            task="task",
            context=context,
            executor=executor,
        )

        metrics = runtime.get_metrics()
        assert metrics["total_executions"] >= 1
        assert metrics["total_verifications"] >= 1
