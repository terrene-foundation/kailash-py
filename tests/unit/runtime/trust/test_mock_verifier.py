"""Unit tests for MockTrustVerifier (CARE-016).

Tests for MockTrustVerifier - a testing utility for verification without Kaizen backend.
These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import pytest
from kailash.runtime.trust.context import RuntimeTrustContext
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)


class TestMockVerifierDefaultBehavior:
    """Test MockTrustVerifier default behavior."""

    @pytest.mark.asyncio
    async def test_mock_verifier_default_allow(self):
        """Test MockTrustVerifier allows by default when default_allow=True."""
        verifier = MockTrustVerifier(default_allow=True)

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="any-agent",
        )

        assert result.allowed is True
        assert "allowed" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_mock_verifier_default_deny(self):
        """Test MockTrustVerifier denies by default when default_allow=False."""
        verifier = MockTrustVerifier(default_allow=False)

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="any-agent",
        )

        assert result.allowed is False
        assert "denied" in result.reason.lower()


class TestMockVerifierDeniedLists:
    """Test MockTrustVerifier with denied agents and nodes."""

    @pytest.mark.asyncio
    async def test_mock_verifier_denied_agents(self):
        """Test MockTrustVerifier denies specific agents."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["bad-agent", "blocked-agent"],
        )

        # Denied agent should be blocked
        result_denied = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="bad-agent",
        )
        assert result_denied.allowed is False
        assert "bad-agent" in result_denied.reason

        # Other agents should be allowed
        result_allowed = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="good-agent",
        )
        assert result_allowed.allowed is True

    @pytest.mark.asyncio
    async def test_mock_verifier_denied_nodes(self):
        """Test MockTrustVerifier denies specific node types."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_nodes=["BashCommand", "FileWrite"],
        )

        # Denied node type should be blocked
        result_denied = await verifier.verify_node_access(
            node_id="node-1",
            node_type="BashCommand",
            agent_id="any-agent",
        )
        assert result_denied.allowed is False
        assert "BashCommand" in result_denied.reason

        # Other node types should be allowed
        result_allowed = await verifier.verify_node_access(
            node_id="node-2",
            node_type="HttpRequest",
            agent_id="any-agent",
        )
        assert result_allowed.allowed is True

    @pytest.mark.asyncio
    async def test_mock_verifier_denied_agent_takes_precedence(self):
        """Test denied agent blocks even allowed node types."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["blocked-agent"],
            denied_nodes=["BashCommand"],
        )

        # Denied agent trying to use allowed node type
        result = await verifier.verify_node_access(
            node_id="node-1",
            node_type="HttpRequest",  # Not in denied_nodes
            agent_id="blocked-agent",  # In denied_agents
        )
        assert result.allowed is False
        assert "blocked-agent" in result.reason


class TestMockVerifierNoBackendRequired:
    """Test MockTrustVerifier works without Kaizen backend."""

    @pytest.mark.asyncio
    async def test_mock_verifier_no_backend_required(self):
        """Test MockTrustVerifier works standalone without any backend."""
        # MockTrustVerifier should work without any external dependencies
        verifier = MockTrustVerifier(default_allow=True)

        # All verification methods should work
        wf_result = await verifier.verify_workflow_access(
            workflow_id="wf-1",
            agent_id="agent-1",
        )
        assert wf_result.allowed is True

        node_result = await verifier.verify_node_access(
            node_id="node-1",
            node_type="TestNode",
            agent_id="agent-1",
        )
        assert node_result.allowed is True

        res_result = await verifier.verify_resource_access(
            resource="/test/file.txt",
            action="read",
            agent_id="agent-1",
        )
        assert res_result.allowed is True


class TestMockVerifierModes:
    """Test MockTrustVerifier mode behavior."""

    @pytest.mark.asyncio
    async def test_mock_verifier_permissive_mode_allows_denied(self):
        """Test PERMISSIVE mode allows normally denied operations."""
        config = TrustVerifierConfig(mode="permissive")
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["blocked-agent"],
            config=config,
        )

        # Blocked agent in PERMISSIVE mode should be allowed (with warning reason)
        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="blocked-agent",
        )

        assert result.allowed is True
        assert "PERMISSIVE" in result.reason

    @pytest.mark.asyncio
    async def test_mock_verifier_enforcing_mode_blocks(self):
        """Test ENFORCING mode blocks denied operations."""
        config = TrustVerifierConfig(mode="enforcing")
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["blocked-agent"],
            config=config,
        )

        # Blocked agent in ENFORCING mode should be denied
        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="blocked-agent",
        )

        assert result.allowed is False
        assert "blocked-agent" in result.reason

    @pytest.mark.asyncio
    async def test_mock_verifier_disabled_mode_allows_all(self):
        """Test DISABLED mode allows all operations."""
        config = TrustVerifierConfig(mode="disabled")
        verifier = MockTrustVerifier(
            default_allow=False,  # Even with default deny
            denied_agents=["blocked-agent"],  # And denied agents
            config=config,
        )

        # Even blocked agent should be allowed when disabled
        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="blocked-agent",
        )

        assert result.allowed is True
        assert "disabled" in result.reason.lower()


class TestMockVerifierAccessMethods:
    """Test all MockTrustVerifier verification methods."""

    @pytest.mark.asyncio
    async def test_mock_verifier_workflow_access(self):
        """Test verify_workflow_access method."""
        verifier = MockTrustVerifier(default_allow=True)

        result = await verifier.verify_workflow_access(
            workflow_id="workflow-123",
            agent_id="agent-456",
        )

        assert result.allowed is True
        assert isinstance(result, VerificationResult)

    @pytest.mark.asyncio
    async def test_mock_verifier_node_access(self):
        """Test verify_node_access method."""
        verifier = MockTrustVerifier(default_allow=True)

        result = await verifier.verify_node_access(
            node_id="node-789",
            node_type="PythonCode",
            agent_id="agent-456",
        )

        assert result.allowed is True
        assert isinstance(result, VerificationResult)

    @pytest.mark.asyncio
    async def test_mock_verifier_resource_access(self):
        """Test verify_resource_access method."""
        verifier = MockTrustVerifier(default_allow=True)

        result = await verifier.verify_resource_access(
            resource="/data/sensitive.json",
            action="write",
            agent_id="agent-456",
        )

        assert result.allowed is True
        assert isinstance(result, VerificationResult)


class TestMockVerifierWithTrustContext:
    """Test MockTrustVerifier with RuntimeTrustContext."""

    @pytest.mark.asyncio
    async def test_mock_verifier_propagates_trace_id(self):
        """Test trace_id from RuntimeTrustContext is propagated."""
        verifier = MockTrustVerifier(default_allow=True)
        trust_ctx = RuntimeTrustContext(trace_id="mock-trace-123")

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="agent-1",
            trust_context=trust_ctx,
        )

        assert result.trace_id == "mock-trace-123"

    @pytest.mark.asyncio
    async def test_mock_verifier_node_with_context(self):
        """Test verify_node_access with RuntimeTrustContext."""
        verifier = MockTrustVerifier(default_allow=True)
        trust_ctx = RuntimeTrustContext(trace_id="node-trace-456")

        result = await verifier.verify_node_access(
            node_id="node-1",
            node_type="BashCommand",
            agent_id="agent-1",
            trust_context=trust_ctx,
        )

        assert result.trace_id == "node-trace-456"

    @pytest.mark.asyncio
    async def test_mock_verifier_resource_with_context(self):
        """Test verify_resource_access with RuntimeTrustContext."""
        verifier = MockTrustVerifier(default_allow=True)
        trust_ctx = RuntimeTrustContext(trace_id="resource-trace-789")

        result = await verifier.verify_resource_access(
            resource="/data/file.txt",
            action="read",
            agent_id="agent-1",
            trust_context=trust_ctx,
        )

        assert result.trace_id == "resource-trace-789"


class TestMockVerifierEdgeCases:
    """Test MockTrustVerifier edge cases."""

    @pytest.mark.asyncio
    async def test_mock_verifier_empty_denied_lists(self):
        """Test with empty denied lists."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=[],
            denied_nodes=[],
        )

        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="any-agent",
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_mock_verifier_none_denied_lists(self):
        """Test with None for denied lists (default)."""
        verifier = MockTrustVerifier(default_allow=True)

        result = await verifier.verify_node_access(
            node_id="node-1",
            node_type="AnyNode",
            agent_id="any-agent",
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_mock_verifier_multiple_denied_agents(self):
        """Test with multiple denied agents."""
        verifier = MockTrustVerifier(
            default_allow=True,
            denied_agents=["agent-a", "agent-b", "agent-c"],
        )

        # All denied agents should be blocked
        for agent_id in ["agent-a", "agent-b", "agent-c"]:
            result = await verifier.verify_workflow_access(
                workflow_id="test-wf",
                agent_id=agent_id,
            )
            assert result.allowed is False

        # Unlisted agent should be allowed
        result = await verifier.verify_workflow_access(
            workflow_id="test-wf",
            agent_id="agent-d",
        )
        assert result.allowed is True
