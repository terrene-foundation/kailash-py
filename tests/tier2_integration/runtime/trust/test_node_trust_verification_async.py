"""Tier 2 integration tests for AsyncLocalRuntime node-level trust verification.

Extracted from tests/unit/runtime/trust/test_node_trust_verification.py.
AsyncLocalRuntime spawns threads and requires real infrastructure — not suitable
for Tier 1 unit tests with a --timeout=10 constraint.
"""

from __future__ import annotations

import logging

import pytest

from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
)
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifierConfig,
)


# =============================================================================
# Test node-level trust in AsyncLocalRuntime execution paths
# =============================================================================


class TestAsyncLocalRuntimeNodeTrustEnforcing:
    """Test that AsyncLocalRuntime blocks node execution in ENFORCING mode."""

    @pytest.mark.asyncio
    async def test_enforcing_blocks_denied_node(self):
        """AsyncLocalRuntime should raise for denied nodes in ENFORCING mode."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["PythonCodeNode"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        ctx = RuntimeTrustContext(
            trace_id="test-async-enforce",
            verification_mode=TrustVerificationMode.ENFORCING,
            delegation_chain=["agent-1"],
        )

        runtime = AsyncLocalRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
            trust_context=ctx,
        )

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "code_node",
            {"code": "result = 42", "validate_security": False},
        )
        workflow = builder.build()

        with pytest.raises(Exception, match="Trust verification denied"):
            await runtime.execute_workflow_async(workflow, inputs={})

    @pytest.mark.asyncio
    async def test_enforcing_allows_permitted_node(self):
        """AsyncLocalRuntime should allow execution of permitted nodes."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        ctx = RuntimeTrustContext(
            trace_id="test-async-allow",
            verification_mode=TrustVerificationMode.ENFORCING,
            delegation_chain=["agent-1"],
        )

        runtime = AsyncLocalRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
            trust_context=ctx,
        )

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "code_node",
            {"code": "result = 42", "validate_security": False},
        )
        workflow = builder.build()

        results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        assert "code_node" in results
        assert results["code_node"]["result"] == 42


class TestAsyncLocalRuntimeNodeTrustPermissive:
    """Test AsyncLocalRuntime PERMISSIVE mode."""

    @pytest.mark.asyncio
    async def test_permissive_allows_denied_node(self):
        """PERMISSIVE mode should allow execution even when node is denied."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["PythonCodeNode"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        ctx = RuntimeTrustContext(
            trace_id="test-async-permissive",
            verification_mode=TrustVerificationMode.PERMISSIVE,
            delegation_chain=["agent-1"],
        )

        runtime = AsyncLocalRuntime(
            trust_verification_mode="permissive",
            trust_verifier=verifier,
            trust_context=ctx,
        )

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "code_node",
            {"code": "result = 42", "validate_security": False},
        )
        workflow = builder.build()

        results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        assert "code_node" in results
        assert results["code_node"]["result"] == 42


class TestAsyncLocalRuntimeNodeTrustDisabled:
    """Test AsyncLocalRuntime disabled mode has zero overhead."""

    @pytest.mark.asyncio
    async def test_disabled_mode_no_overhead(self):
        """DISABLED mode (default) should execute normally."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "code_node",
            {"code": "result = 42", "validate_security": False},
        )
        workflow = builder.build()

        results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        assert "code_node" in results
        assert results["code_node"]["result"] == 42


# =============================================================================
# Backward compatibility — async half only
# =============================================================================


class TestNodeTrustBackwardCompatibilityAsync:
    """Async portion of backward compatibility tests (uses AsyncLocalRuntime)."""

    @pytest.mark.asyncio
    async def test_default_async_runtime_no_trust_overhead(self):
        """Default AsyncLocalRuntime should have zero trust overhead."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        runtime = AsyncLocalRuntime()
        assert runtime._trust_verification_mode == TrustVerificationMode.DISABLED

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "code_node",
            {"code": "result = 'hello'", "validate_security": False},
        )
        workflow = builder.build()

        results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        assert results["code_node"]["result"] == "hello"
