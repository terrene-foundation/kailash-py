"""Unit tests for CARE-039: Node-level trust verification in runtime execution.

Tests verify that _verify_node_trust() is called before every node execution
in both LocalRuntime and AsyncLocalRuntime, covering:
- ENFORCING mode blocks denied nodes with WorkflowExecutionError
- PERMISSIVE mode logs warnings but allows denied nodes
- DISABLED mode (default) never calls verification
- Backward compatibility: no trust context = no verification overhead
- High-risk node types (BashCommand, HttpRequest, etc.) are verified
- Both async and sync execution paths in LocalRuntime
- AsyncLocalRuntime async node path and sync-in-thread path

These are Tier 1 unit tests - mocking is allowed.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.runtime.base import BaseRuntime
from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
    runtime_trust_context,
    set_runtime_trust_context,
)
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.workflow import Workflow


class ConcreteRuntime(BaseRuntime):
    """Concrete implementation for testing abstract base."""

    def execute(self, workflow: Workflow, **kwargs):
        return {}, "test-run-id"


# =============================================================================
# Test _verify_node_trust base method directly
# =============================================================================


class TestVerifyNodeTrustDisabled:
    """Test _verify_node_trust returns True when DISABLED."""

    @pytest.mark.asyncio
    async def test_disabled_mode_returns_true(self):
        """DISABLED mode should always return True without calling verifier."""
        runtime = ConcreteRuntime(trust_verification_mode="disabled")
        result = await runtime._verify_node_trust("node-1", "BashCommand")
        assert result is True

    @pytest.mark.asyncio
    async def test_disabled_mode_with_context_returns_true(self):
        """DISABLED mode returns True even with trust context."""
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["agent-1"],
        )
        runtime = ConcreteRuntime(trust_verification_mode="disabled")
        result = await runtime._verify_node_trust("node-1", "BashCommand", ctx)
        assert result is True


class TestVerifyNodeTrustNoVerifier:
    """Test _verify_node_trust returns True when no verifier configured."""

    @pytest.mark.asyncio
    async def test_no_verifier_returns_true(self):
        """Should return True when mode is ENFORCING but no verifier set."""
        runtime = ConcreteRuntime(trust_verification_mode="enforcing")
        result = await runtime._verify_node_trust("node-1", "BashCommand")
        assert result is True


class TestVerifyNodeTrustEnforcing:
    """Test ENFORCING mode blocks denied nodes."""

    @pytest.mark.asyncio
    async def test_enforcing_blocks_denied_node(self):
        """ENFORCING mode should return False for denied node types."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["agent-1"],
        )
        result = await runtime._verify_node_trust("node-1", "BashCommand", ctx)
        assert result is False

    @pytest.mark.asyncio
    async def test_enforcing_allows_permitted_node(self):
        """ENFORCING mode should return True for allowed node types."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["agent-1"],
        )
        result = await runtime._verify_node_trust("node-1", "HttpRequest", ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_enforcing_blocks_denied_agent(self):
        """ENFORCING mode should return False for denied agents."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["blocked-agent"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["blocked-agent"],
        )
        result = await runtime._verify_node_trust("node-1", "PythonCode", ctx)
        assert result is False

    @pytest.mark.asyncio
    async def test_enforcing_logs_error_on_denial(self, caplog):
        """ENFORCING mode should log ERROR when denying a node."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["agent-1"],
        )
        with caplog.at_level(logging.ERROR):
            result = await runtime._verify_node_trust("node-1", "BashCommand", ctx)

        assert result is False
        assert any("ENFORCING" in msg for msg in caplog.messages)
        assert any("BashCommand" in msg for msg in caplog.messages)


class TestVerifyNodeTrustPermissive:
    """Test PERMISSIVE mode logs but allows denied nodes."""

    @pytest.mark.asyncio
    async def test_permissive_allows_denied_node(self):
        """PERMISSIVE mode should return True even for denied nodes."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="permissive",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["agent-1"],
        )
        result = await runtime._verify_node_trust("node-1", "BashCommand", ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_permissive_logs_warning_on_denial(self, caplog):
        """PERMISSIVE mode should log WARNING when node would be denied."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="permissive",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["agent-1"],
        )
        with caplog.at_level(logging.WARNING):
            result = await runtime._verify_node_trust("node-1", "BashCommand", ctx)

        assert result is True
        assert any("PERMISSIVE" in msg for msg in caplog.messages)
        assert any("BashCommand" in msg for msg in caplog.messages)


# =============================================================================
# Test node-level trust in LocalRuntime execution paths
# =============================================================================


class TestLocalRuntimeNodeTrustEnforcing:
    """Test that LocalRuntime blocks node execution in ENFORCING mode."""

    def test_enforcing_blocks_denied_node_in_workflow(self):
        """LocalRuntime should raise WorkflowExecutionError for denied nodes."""
        from kailash.nodes.code.python import PythonCodeNode
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["PythonCodeNode"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        ctx = RuntimeTrustContext(
            trace_id="test-enforce",
            verification_mode=TrustVerificationMode.ENFORCING,
            delegation_chain=["agent-1"],
        )

        runtime = LocalRuntime(
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

        with pytest.raises(
            Exception, match="Trust verification denied execution of node"
        ):
            runtime.execute(workflow)

    def test_enforcing_allows_permitted_node_in_workflow(self):
        """LocalRuntime should allow execution of permitted nodes."""
        from kailash.nodes.code.python import PythonCodeNode
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        ctx = RuntimeTrustContext(
            trace_id="test-allow",
            verification_mode=TrustVerificationMode.ENFORCING,
            delegation_chain=["agent-1"],
        )

        runtime = LocalRuntime(
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

        results, run_id = runtime.execute(workflow)
        assert "code_node" in results
        assert results["code_node"]["result"] == 42


class TestLocalRuntimeNodeTrustPermissive:
    """Test that LocalRuntime logs but allows in PERMISSIVE mode."""

    def test_permissive_allows_denied_node(self, caplog):
        """PERMISSIVE mode should allow execution even when node is denied."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["PythonCodeNode"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        ctx = RuntimeTrustContext(
            trace_id="test-permissive",
            verification_mode=TrustVerificationMode.PERMISSIVE,
            delegation_chain=["agent-1"],
        )

        runtime = LocalRuntime(
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

        with caplog.at_level(logging.WARNING):
            results, run_id = runtime.execute(workflow)

        assert "code_node" in results
        assert results["code_node"]["result"] == 42


class TestLocalRuntimeNodeTrustDisabled:
    """Test that disabled mode has zero overhead."""

    def test_disabled_mode_no_overhead(self):
        """DISABLED mode (default) should execute normally without trust checks."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        runtime = LocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "code_node",
            {"code": "result = 42", "validate_security": False},
        )
        workflow = builder.build()

        results, run_id = runtime.execute(workflow)
        assert "code_node" in results
        assert results["code_node"]["result"] == 42


class TestLocalRuntimeNodeTrustMultipleNodes:
    """Test trust verification across multiple nodes in a workflow."""

    def test_enforcing_blocks_at_first_denied_node(self):
        """Should fail at the first denied node, not executing subsequent nodes."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["PythonCodeNode"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        ctx = RuntimeTrustContext(
            trace_id="test-multi",
            verification_mode=TrustVerificationMode.ENFORCING,
            delegation_chain=["agent-1"],
        )

        runtime = LocalRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
            trust_context=ctx,
        )

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "node_a",
            {"code": "result = 1", "validate_security": False},
        )
        builder.add_node(
            "PythonCodeNode",
            "node_b",
            {"code": "result = 2", "validate_security": False},
        )
        builder.connect("node_a", "node_b")
        workflow = builder.build()

        with pytest.raises(Exception, match="Trust verification denied"):
            runtime.execute(workflow)


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
# Test high-risk node types specifically
# =============================================================================


class TestHighRiskNodeTrustVerification:
    """Verify that all high-risk node types trigger trust verification."""

    HIGH_RISK_TYPES = [
        "BashCommand",
        "HttpRequest",
        "DatabaseQuery",
        "FileWrite",
        "CodeExecution",
        "PythonCode",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("node_type", HIGH_RISK_TYPES)
    async def test_enforcing_blocks_each_high_risk_type(self, node_type):
        """Each high-risk node type should be blocked when denied."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=[node_type],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test-high-risk",
            delegation_chain=["agent-1"],
        )
        result = await runtime._verify_node_trust("node-1", node_type, ctx)
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("node_type", HIGH_RISK_TYPES)
    async def test_permissive_allows_each_high_risk_type(self, node_type):
        """Each high-risk node type should be allowed in PERMISSIVE mode."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=[node_type],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="permissive",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test-high-risk-permissive",
            delegation_chain=["agent-1"],
        )
        result = await runtime._verify_node_trust("node-1", node_type, ctx)
        assert result is True


# =============================================================================
# Test agent ID extraction from trust context
# =============================================================================


class TestNodeTrustAgentIdExtraction:
    """Test that agent ID is correctly extracted from delegation chain."""

    @pytest.mark.asyncio
    async def test_agent_id_from_delegation_chain(self):
        """Should use last agent in delegation chain for verification."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["blocked-agent"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=["root-agent", "blocked-agent"],
        )
        result = await runtime._verify_node_trust("node-1", "PythonCode", ctx)
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_agent_when_no_chain(self):
        """Should use 'unknown' when delegation chain is empty."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["unknown"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        ctx = RuntimeTrustContext(
            trace_id="test",
            delegation_chain=[],
        )
        result = await runtime._verify_node_trust("node-1", "PythonCode", ctx)
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_agent_when_no_context(self):
        """Should use 'unknown' when no trust context provided."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["unknown"],
            config=TrustVerifierConfig(mode="enforcing"),
        )
        runtime = ConcreteRuntime(
            trust_verification_mode="enforcing",
            trust_verifier=verifier,
        )
        result = await runtime._verify_node_trust("node-1", "PythonCode", None)
        assert result is False


# =============================================================================
# Backward compatibility
# =============================================================================


class TestNodeTrustBackwardCompatibility:
    """Ensure existing workflows work without any trust configuration."""

    def test_default_runtime_no_trust_overhead(self):
        """Default LocalRuntime should have zero trust overhead."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        runtime = LocalRuntime()
        assert runtime._trust_verification_mode == TrustVerificationMode.DISABLED
        assert runtime._trust_verifier is None
        assert runtime._trust_context is None

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "code_node",
            {"code": "result = 'hello'", "validate_security": False},
        )
        workflow = builder.build()

        results, run_id = runtime.execute(workflow)
        assert results["code_node"]["result"] == "hello"

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
