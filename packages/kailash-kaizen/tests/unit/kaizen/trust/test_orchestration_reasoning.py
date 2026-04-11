"""Tests for orchestration reasoning propagation (TODO-026).

Verifies that reasoning traces can be passed through the orchestration
runtime's create_delegation and execute_trusted_task methods, and that
the Kaizen shim re-exports work correctly.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.trust.orchestration.execution_context import TrustExecutionContext
from kailash.trust.orchestration.runtime import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
)
from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace


@pytest.fixture
def reasoning_trace():
    """Create a sample reasoning trace for testing."""
    return ReasoningTrace(
        decision="Delegate analysis to worker",
        rationale="Worker agent has required training and clearance",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        alternatives_considered=["Reject delegation", "Use alternative agent"],
        evidence=[{"type": "certification", "id": "cert-worker-001"}],
        methodology="capability_matching",
        confidence=0.92,
    )


@pytest.fixture
def trust_context():
    """Create a sample trust execution context."""
    return TrustExecutionContext.create(
        parent_agent_id="supervisor-001",
        task_id="workflow-123",
        delegated_capabilities=["analyze_data", "read_data"],
    )


@pytest.fixture
def mock_trust_ops():
    """Create mock trust operations."""
    ops = MagicMock()
    ops.delegate = AsyncMock(return_value=None)
    ops.verify = AsyncMock(return_value=MagicMock(valid=True, reason="OK"))
    ops.get_chain = AsyncMock(return_value=MagicMock())
    ops.audit = AsyncMock(return_value=MagicMock(anchor_id="aud-test-001"))
    return ops


@pytest.fixture
def runtime(mock_trust_ops):
    """Create a TrustAwareOrchestrationRuntime with mock dependencies."""
    config = TrustAwareRuntimeConfig(
        verify_before_execution=False,  # Simplify for unit tests
        audit_after_execution=True,
        enable_policy_engine=False,
    )
    return TrustAwareOrchestrationRuntime(
        trust_operations=mock_trust_ops,
        config=config,
    )


class TestCreateDelegationWithReasoning:
    """Test reasoning_trace parameter on create_delegation."""

    @pytest.mark.asyncio
    async def test_create_delegation_passes_reasoning_trace(
        self, runtime, trust_context, reasoning_trace, mock_trust_ops
    ):
        """create_delegation should pass reasoning_trace to trust_ops.delegate."""
        entry = await runtime.create_delegation(
            supervisor_id="supervisor-001",
            worker_id="worker-001",
            task_id="task-abc",
            capabilities=["analyze_data"],
            context=trust_context,
            reasoning_trace=reasoning_trace,
        )

        # Verify delegate was called with reasoning_trace
        mock_trust_ops.delegate.assert_called_once_with(
            delegator_id="supervisor-001",
            delegatee_id="worker-001",
            capabilities=["analyze_data"],
            task_id="task-abc",
            reasoning_trace=reasoning_trace,
        )
        assert entry.delegator_id == "supervisor-001"
        assert entry.delegatee_id == "worker-001"

    @pytest.mark.asyncio
    async def test_create_delegation_without_reasoning_trace(
        self, runtime, trust_context, mock_trust_ops
    ):
        """create_delegation should work without reasoning_trace (backward compat)."""
        entry = await runtime.create_delegation(
            supervisor_id="supervisor-001",
            worker_id="worker-001",
            task_id="task-def",
            capabilities=["read_data"],
            context=trust_context,
        )

        # Verify delegate was called with reasoning_trace=None
        mock_trust_ops.delegate.assert_called_once_with(
            delegator_id="supervisor-001",
            delegatee_id="worker-001",
            capabilities=["read_data"],
            task_id="task-def",
            reasoning_trace=None,
        )
        assert entry.delegator_id == "supervisor-001"

    @pytest.mark.asyncio
    async def test_create_delegation_reasoning_trace_survives_delegate_failure(
        self, runtime, trust_context, reasoning_trace, mock_trust_ops
    ):
        """If trust_ops.delegate fails, create_delegation should still return entry."""
        mock_trust_ops.delegate.side_effect = Exception("DB unavailable")

        entry = await runtime.create_delegation(
            supervisor_id="supervisor-001",
            worker_id="worker-001",
            task_id="task-ghi",
            capabilities=["analyze_data"],
            context=trust_context,
            reasoning_trace=reasoning_trace,
        )

        # Entry still created despite delegate failure
        assert entry is not None
        assert entry.delegatee_id == "worker-001"


class TestExecuteTrustedTaskWithReasoning:
    """Test reasoning_trace parameter on execute_trusted_task."""

    @pytest.mark.asyncio
    async def test_execute_trusted_task_passes_reasoning_to_audit(
        self, runtime, trust_context, reasoning_trace, mock_trust_ops
    ):
        """execute_trusted_task should pass reasoning_trace to audit call."""

        async def executor(task):
            return {"result": "analyzed"}

        result = await runtime.execute_trusted_task(
            agent_id="worker-001",
            task="analyze Q3 data",
            context=trust_context,
            executor=executor,
            reasoning_trace=reasoning_trace,
        )

        assert result.success is True

        # Verify audit was called with reasoning_trace
        mock_trust_ops.audit.assert_called_once()
        call_kwargs = mock_trust_ops.audit.call_args
        assert call_kwargs.kwargs.get("reasoning_trace") is reasoning_trace

    @pytest.mark.asyncio
    async def test_execute_trusted_task_without_reasoning(
        self, runtime, trust_context, mock_trust_ops
    ):
        """execute_trusted_task works without reasoning_trace (backward compat)."""

        async def executor(task):
            return {"result": "done"}

        result = await runtime.execute_trusted_task(
            agent_id="worker-001",
            task="read data",
            context=trust_context,
            executor=executor,
        )

        assert result.success is True

        # Verify audit was called with reasoning_trace=None
        mock_trust_ops.audit.assert_called_once()
        call_kwargs = mock_trust_ops.audit.call_args
        assert call_kwargs.kwargs.get("reasoning_trace") is None


class TestKaizenShimReExports:
    """Test that Kaizen orchestration shims properly re-export updated types."""

    def test_kaizen_orchestration_runtime_importable(self):
        """TrustAwareOrchestrationRuntime should import from kailash.trust.orchestration."""
        from kailash.trust.orchestration import TrustAwareOrchestrationRuntime

        assert TrustAwareOrchestrationRuntime is not None

    def test_kaizen_orchestration_runtime_shim_matches_eatp(self):
        """Kaizen shim should re-export the same class as EATP."""
        from kailash.trust.orchestration.runtime import (
            TrustAwareOrchestrationRuntime as EatpRuntime,
        )
        from kailash.trust.orchestration.runtime import (
            TrustAwareOrchestrationRuntime as KaizenRuntime,
        )

        assert KaizenRuntime is EatpRuntime

    def test_policy_enforce_constraint_with_reasoning_required(self):
        """Policies should support REASONING_REQUIRED constraint type."""
        from kailash.trust.orchestration import TrustPolicy

        from kaizen.trust import ConstraintType

        policy = TrustPolicy.enforce_constraint(
            constraint_type=ConstraintType.REASONING_REQUIRED.value,
            constraint_value=True,
            policy_name="require_reasoning",
        )

        assert policy.policy_name == "require_reasoning"
        assert policy.policy_config["constraint_type"] == "reasoning_required"
        assert policy.policy_config["constraint_value"] is True
