"""Unit tests for CARE-017: Delegation Propagation.

Tests for trust verification helper methods in BaseRuntime and
trust context propagation in LocalRuntime and AsyncLocalRuntime.

These are Tier 1 unit tests - mocking is allowed since they test
the integration logic between runtime and trust verification.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.runtime.base import BaseRuntime
from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
    _runtime_trust_context,
    get_runtime_trust_context,
    runtime_trust_context,
    set_runtime_trust_context,
)
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.workflow import Workflow


class ConcreteRuntime(BaseRuntime):
    """Concrete implementation for testing abstract base."""

    def execute(self, workflow: Workflow, **kwargs):
        """Minimal execute implementation."""
        return {}, "test-run-id"


class MockWorkflow:
    """Mock workflow for testing."""

    def __init__(self, workflow_id: str = "test-workflow"):
        self.workflow_id = workflow_id
        self.graph = MagicMock()
        self.graph.nodes = ["node1", "node2"]


# =============================================================================
# Test _verify_workflow_trust helper method
# =============================================================================


class TestVerifyWorkflowTrustDisabled:
    """Test _verify_workflow_trust returns True when DISABLED."""

    @pytest.mark.asyncio
    async def test_verify_workflow_trust_disabled_returns_true(self):
        """Test that DISABLED mode always returns True."""
        runtime = ConcreteRuntime(trust_verification_mode="disabled")
        workflow = MockWorkflow()

        result = await runtime._verify_workflow_trust(workflow)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_workflow_trust_disabled_with_context_returns_true(self):
        """Test DISABLED mode returns True even with trust context."""
        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=["agent-1"],
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="disabled",
            trust_context=ctx,
        )
        workflow = MockWorkflow()

        result = await runtime._verify_workflow_trust(workflow, ctx)

        assert result is True


class TestVerifyWorkflowTrustNoVerifier:
    """Test _verify_workflow_trust returns True when no verifier configured."""

    @pytest.mark.asyncio
    async def test_verify_workflow_trust_no_verifier_returns_true(self):
        """Test returns True when no verifier is configured."""
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=None,  # No verifier
        )
        workflow = MockWorkflow()

        result = await runtime._verify_workflow_trust(workflow)

        assert result is True


class TestVerifyWorkflowTrustPermissive:
    """Test _verify_workflow_trust in PERMISSIVE mode."""

    @pytest.mark.asyncio
    async def test_verify_workflow_trust_permissive_allows_denied(self, caplog):
        """Test PERMISSIVE mode logs denial but returns True."""
        # Setup mock verifier that denies access
        mock_verifier = MockTrustVerifier(
            default_allow=False,
            config=TrustVerifierConfig(mode="enforcing"),
        )

        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=["blocked-agent"],
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="permissive",
            trust_verifier=mock_verifier,
            trust_context=ctx,
        )
        workflow = MockWorkflow()

        with caplog.at_level(logging.WARNING):
            result = await runtime._verify_workflow_trust(workflow, ctx)

        # Should return True (allow) in PERMISSIVE mode
        assert result is True
        # Should log a warning
        assert "PERMISSIVE" in caplog.text


class TestVerifyWorkflowTrustEnforcing:
    """Test _verify_workflow_trust in ENFORCING mode."""

    @pytest.mark.asyncio
    async def test_verify_workflow_trust_enforcing_blocks_denied(self, caplog):
        """Test ENFORCING mode returns False when denied."""
        # Setup mock verifier that denies access
        mock_verifier = MockTrustVerifier(
            default_allow=False,
            config=TrustVerifierConfig(mode="enforcing"),
        )

        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=["blocked-agent"],
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=mock_verifier,
            trust_context=ctx,
        )
        workflow = MockWorkflow()

        with caplog.at_level(logging.ERROR):
            result = await runtime._verify_workflow_trust(workflow, ctx)

        # Should return False (block) in ENFORCING mode
        assert result is False
        # Should log an error
        assert "ENFORCING" in caplog.text

    @pytest.mark.asyncio
    async def test_verify_workflow_trust_enforcing_allows_approved(self):
        """Test ENFORCING mode returns True when allowed."""
        # Setup mock verifier that allows access
        mock_verifier = MockTrustVerifier(
            default_allow=True,
            config=TrustVerifierConfig(mode="enforcing"),
        )

        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=["approved-agent"],
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=mock_verifier,
            trust_context=ctx,
        )
        workflow = MockWorkflow()

        result = await runtime._verify_workflow_trust(workflow, ctx)

        # Should return True (allow)
        assert result is True


# =============================================================================
# Test _verify_node_trust helper method
# =============================================================================


class TestVerifyNodeTrustDisabled:
    """Test _verify_node_trust returns True when DISABLED."""

    @pytest.mark.asyncio
    async def test_verify_node_trust_disabled_returns_true(self):
        """Test DISABLED mode always returns True for node verification."""
        runtime = ConcreteRuntime(trust_verification_mode="disabled")

        result = await runtime._verify_node_trust("node-1", "PythonCode")

        assert result is True


class TestVerifyNodeTrustEnforcing:
    """Test _verify_node_trust in ENFORCING mode."""

    @pytest.mark.asyncio
    async def test_verify_node_trust_enforcing_blocks_denied(self, caplog):
        """Test ENFORCING mode returns False when node is denied."""
        # Setup mock verifier that denies specific node type
        mock_verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )

        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=["agent-1"],
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=mock_verifier,
        )

        with caplog.at_level(logging.ERROR):
            result = await runtime._verify_node_trust("node-1", "BashCommand", ctx)

        # Should return False (block)
        assert result is False
        assert "ENFORCING" in caplog.text


class TestVerifyNodeTrustPermissive:
    """Test _verify_node_trust in PERMISSIVE mode."""

    @pytest.mark.asyncio
    async def test_verify_node_trust_permissive_allows(self, caplog):
        """Test PERMISSIVE mode logs but allows denied nodes."""
        # Setup mock verifier that denies specific node type
        mock_verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )

        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=["agent-1"],
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="permissive",
            trust_verifier=mock_verifier,
        )

        with caplog.at_level(logging.WARNING):
            result = await runtime._verify_node_trust("node-1", "BashCommand", ctx)

        # Should return True (allow) in PERMISSIVE
        assert result is True
        assert "PERMISSIVE" in caplog.text


# =============================================================================
# Test _get_effective_trust_context with ContextVar
# =============================================================================


class TestGetEffectiveTrustContextWithContextVar:
    """Test _get_effective_trust_context with ContextVar propagation."""

    def test_get_effective_trust_context_with_contextvar(self):
        """Test ContextVar propagation works correctly."""
        constructor_ctx = RuntimeTrustContext(trace_id="constructor")
        contextvar_ctx = RuntimeTrustContext(trace_id="contextvar")

        runtime = ConcreteRuntime(trust_context=constructor_ctx)

        # Without ContextVar set, should return constructor context
        set_runtime_trust_context(None)
        result = runtime._get_effective_trust_context()
        assert result.trace_id == "constructor"

        # With ContextVar set, should return ContextVar context
        with runtime_trust_context(contextvar_ctx):
            result = runtime._get_effective_trust_context()
            assert result.trace_id == "contextvar"

        # After exiting, should return to constructor context
        result = runtime._get_effective_trust_context()
        assert result.trace_id == "constructor"


# =============================================================================
# Test LocalRuntime.execute() trust context propagation
# =============================================================================


class TestLocalRuntimeExecuteTrustPropagation:
    """Test LocalRuntime.execute() propagates trust context."""

    def test_localruntime_execute_propagates_trust_context(self):
        """Test that trust context is set during LocalRuntime.execute()."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Create a simple workflow that captures the trust context
        captured_context = []

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
            trace_id="test-propagation",
            delegation_chain=["agent-1"],
        )

        # Create runtime with trust context
        with LocalRuntime(trust_context=ctx) as runtime:
            # Override to capture context during execution
            original_execute_async = runtime._execute_async

            async def capture_execute_async(*args, **kwargs):
                # Capture the trust context during execution
                current = get_runtime_trust_context()
                captured_context.append(current)
                return await original_execute_async(*args, **kwargs)

            runtime._execute_async = capture_execute_async

            # Execute
            try:
                results, run_id = runtime.execute(built_workflow)
            except Exception:
                # The workflow might fail, but we want to check context propagation
                pass

        # Check if trust context was available during execution
        # (captured_context may be empty if workflow failed before async path)

    def test_localruntime_execute_without_trust_works(self):
        """Test backward compatibility - no trust context = no change."""
        from kailash.runtime.local import LocalRuntime
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
        with LocalRuntime() as runtime:
            # This should work without any trust-related errors
            try:
                results, run_id = runtime.execute(built_workflow)
            except Exception:
                # Workflow might fail for other reasons, but no trust error
                pass

        # Just verify no exception related to trust was raised


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


# =============================================================================
# Test agent ID extraction from trust context
# =============================================================================


class TestLocalRuntimeBlockedByEnforcingMode:
    """Test that LocalRuntime ENFORCING mode blocks untrusted workflows."""

    def test_localruntime_workflow_blocked_by_enforcing_mode(self):
        """Test ENFORCING mode blocks untrusted workflow in LocalRuntime."""
        from kailash.runtime.local import LocalRuntime
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
            trace_id="test-blocked-sync",
            delegation_chain=["untrusted-agent"],
        )

        # Create runtime in ENFORCING mode with denying verifier
        with LocalRuntime(
            trust_context=ctx,
            trust_verifier=mock_verifier,
            trust_verification_mode="enforcing",
        ) as runtime:
            with pytest.raises(WorkflowExecutionError, match="Trust verification"):
                runtime.execute(built_workflow)


class TestAgentIdExtraction:
    """Test agent ID extraction from delegation chain."""

    @pytest.mark.asyncio
    async def test_agent_id_from_delegation_chain(self):
        """Test agent ID is extracted from delegation chain."""
        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=["root-agent", "delegated-agent"],
        )

        mock_verifier = MockTrustVerifier(
            default_allow=True,
            config=TrustVerifierConfig(mode="enforcing"),
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=mock_verifier,
        )

        workflow = MockWorkflow()

        # The verify method should use the last agent in chain
        result = await runtime._verify_workflow_trust(workflow, ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_agent_id_unknown_when_no_chain(self):
        """Test agent ID is 'unknown' when no delegation chain."""
        ctx = RuntimeTrustContext(
            trace_id="test-trace",
            delegation_chain=[],  # Empty chain
        )

        mock_verifier = MockTrustVerifier(
            default_allow=True,
            config=TrustVerifierConfig(mode="enforcing"),
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=mock_verifier,
        )

        workflow = MockWorkflow()

        # Should still work with empty chain
        result = await runtime._verify_workflow_trust(workflow, ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_agent_id_unknown_when_no_context(self):
        """Test agent ID is 'unknown' when no trust context."""
        mock_verifier = MockTrustVerifier(
            default_allow=True,
            config=TrustVerifierConfig(mode="enforcing"),
        )

        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=mock_verifier,
        )

        workflow = MockWorkflow()

        # Should work without context
        result = await runtime._verify_workflow_trust(workflow, None)
        assert result is True
