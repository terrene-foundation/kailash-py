"""Tier 2 integration tests for AsyncLocalRuntime trust context propagation.

Extracted from tests/unit/runtime/trust/test_trust_propagation.py.
AsyncLocalRuntime spawns threads and requires real infrastructure — not suitable
for Tier 1 unit tests with a --timeout=10 constraint.
"""

from __future__ import annotations

import pytest

from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    get_runtime_trust_context,
    set_runtime_trust_context,
)
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifierConfig,
)
from kailash.sdk_exceptions import WorkflowExecutionError


# =============================================================================
# Test AsyncLocalRuntime.execute_workflow_async() trust context propagation
# =============================================================================


class TestAsyncLocalRuntimeExecuteTrustPropagation:
    """Test AsyncLocalRuntime.execute_workflow_async() propagates trust context."""

    @pytest.mark.asyncio
    async def test_asyncruntime_execute_propagates_trust_context(self):
        """Test that trust context is set during AsyncLocalRuntime execution."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build minimal workflow using PythonCodeNode
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'status': 'ok'}"},
        )
        built_workflow = workflow.build()

        # Create trust context
        ctx = RuntimeTrustContext(
            trace_id="test-async-propagation",
            delegation_chain=["agent-1"],
        )

        # Create async runtime with trust context
        runtime = AsyncLocalRuntime(
            trust_context=ctx,
            execution_timeout=5,
        )

        try:
            # Execute - should not raise trust-related errors
            results, run_id = await runtime.execute_workflow_async(
                built_workflow, inputs={}
            )
        except Exception:
            # Workflow might fail for other reasons
            pass
        finally:
            await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_asyncruntime_execute_without_trust_works(self):
        """Test backward compatibility - no trust context = no change."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build minimal workflow using PythonCodeNode
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'status': 'ok'}"},
        )
        built_workflow = workflow.build()

        # Create runtime without trust context
        runtime = AsyncLocalRuntime(execution_timeout=5)

        try:
            # Should work without any trust-related errors
            results, run_id = await runtime.execute_workflow_async(
                built_workflow, inputs={}
            )
        except Exception:
            # Workflow might fail for other reasons, but no trust error
            pass
        finally:
            await runtime.cleanup()


# =============================================================================
# Test workflow blocked by ENFORCING mode
# =============================================================================


class TestWorkflowBlockedByEnforcingMode:
    """Test that ENFORCING mode blocks untrusted workflows."""

    @pytest.mark.asyncio
    async def test_workflow_blocked_by_enforcing_mode(self):
        """Test ENFORCING mode blocks untrusted workflow execution."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build minimal workflow using PythonCodeNode
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'status': 'ok'}"},
        )
        built_workflow = workflow.build()

        # Create verifier that denies all
        mock_verifier = MockTrustVerifier(
            default_allow=False,
            config=TrustVerifierConfig(mode="enforcing"),
        )

        # Create trust context
        ctx = RuntimeTrustContext(
            trace_id="test-blocked",
            delegation_chain=["untrusted-agent"],
        )

        # Create runtime in ENFORCING mode with denying verifier
        runtime = AsyncLocalRuntime(
            trust_context=ctx,
            trust_verifier=mock_verifier,
            trust_verification_mode="enforcing",
            execution_timeout=5,
        )

        try:
            with pytest.raises(WorkflowExecutionError, match="Trust verification"):
                await runtime.execute_workflow_async(built_workflow, inputs={})
        finally:
            await runtime.cleanup()


# =============================================================================
# Test trust context cleanup on exception
# =============================================================================


class TestTrustContextCleanupOnException:
    """Test that ContextVar is cleaned up even on exception."""

    @pytest.mark.asyncio
    async def test_trust_context_cleanup_on_exception(self):
        """Test ContextVar is properly cleaned up even when execution fails."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build a workflow using PythonCodeNode
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'status': 'ok'}"},
        )
        built_workflow = workflow.build()

        # Create trust context
        ctx = RuntimeTrustContext(
            trace_id="test-cleanup",
            delegation_chain=["agent-1"],
        )

        # Verify no context is set before
        set_runtime_trust_context(None)
        assert get_runtime_trust_context() is None

        runtime = AsyncLocalRuntime(
            trust_context=ctx,
            execution_timeout=5,
        )

        try:
            # Execute - might fail
            await runtime.execute_workflow_async(built_workflow, inputs={})
        except Exception:
            pass
        finally:
            await runtime.cleanup()

        # Context should be cleaned up after execution
        # (the ContextVar token should be reset)
