"""
Unit tests for TrustedAgent and related classes.

Tests cover the intent of trust-enhanced agents:
- Trust Sandwich Pattern: VERIFY → EXECUTE → AUDIT
- Transparent BaseAgent delegation via __getattr__
- Constraint enforcement on tools
- Hierarchical delegation via TrustedSupervisorAgent
- Trust context management

Note: These tests use mocks for the underlying components.
Integration tests with real infrastructure are in tests/integration/trust/
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from kaizen.trust.chain import (
    ActionResult,
    AuditAnchor,
    CapabilityType,
    VerificationLevel,
    VerificationResult,
)
from kaizen.trust.exceptions import (
    ConstraintViolationError,
    TrustChainNotFoundError,
    TrustError,
    VerificationFailedError,
)
from kaizen.trust.execution_context import ExecutionContext, HumanOrigin
from kaizen.trust.trusted_agent import (
    TrustContext,
    TrustContextManager,
    TrustedAgent,
    TrustedAgentConfig,
    TrustedSupervisorAgent,
)


# Helper to create mock VerificationResult
def make_verification_result(
    valid: bool = True,
    reason: str = None,
    level: VerificationLevel = VerificationLevel.STANDARD,
):
    """Create a VerificationResult with correct fields."""
    return VerificationResult(
        valid=valid,
        level=level,
        reason=reason,
    )


# Helper to create mock AuditAnchor
def make_audit_anchor(
    id: str = "anchor-001",
    agent_id: str = "agent-001",
    action: str = "execute",
    result: ActionResult = ActionResult.SUCCESS,
    parent_anchor_id: str = None,
):
    """Create an AuditAnchor with correct fields."""
    return AuditAnchor(
        id=id,
        agent_id=agent_id,
        action=action,
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash="hash-001",
        result=result,
        signature="sig",
        parent_anchor_id=parent_anchor_id,
        context={},
    )


# Helper to create mock ExecutionContext for EATP compliance
def make_execution_context(
    human_id: str = "user-001",
    display_name: str = "Test User",
    agent_id: str = "agent-001",
):
    """Create an ExecutionContext for EATP-compliant tests.

    EATP requires all agent executions to have a human_origin.
    This helper creates a valid context for unit tests.
    """
    human_origin = HumanOrigin(
        human_id=human_id,
        display_name=display_name,
        auth_provider="test",
        session_id="test-session",
        authenticated_at=datetime.now(timezone.utc),
    )
    return ExecutionContext(
        human_origin=human_origin,
        trace_id=f"trace-{agent_id}",
    )


class TestTrustedAgentConfig:
    """Tests for TrustedAgentConfig dataclass."""

    def test_config_with_defaults(self):
        """Config initializes with sensible defaults for enterprise use."""
        config = TrustedAgentConfig(agent_id="agent-001")

        assert config.agent_id == "agent-001"
        assert config.verification_level == VerificationLevel.STANDARD
        assert config.audit_enabled is True
        assert config.fail_on_verification_failure is True
        assert config.auto_establish is False
        assert config.authority_id is None
        assert config.default_capabilities == []
        assert config.constraint_enforcement is True
        assert config.parent_anchor_tracking is True

    def test_config_with_custom_values(self):
        """Config accepts all customizable options."""
        config = TrustedAgentConfig(
            agent_id="custom-agent",
            verification_level=VerificationLevel.FULL,
            audit_enabled=False,
            fail_on_verification_failure=False,
            auto_establish=True,
            authority_id="org-enterprise",
            default_capabilities=["read", "analyze"],
            constraint_enforcement=False,
            parent_anchor_tracking=False,
        )

        assert config.agent_id == "custom-agent"
        assert config.verification_level == VerificationLevel.FULL
        assert config.audit_enabled is False
        assert config.fail_on_verification_failure is False
        assert config.auto_establish is True
        assert config.authority_id == "org-enterprise"
        assert config.default_capabilities == ["read", "analyze"]
        assert config.constraint_enforcement is False
        assert config.parent_anchor_tracking is False


class TestTrustContext:
    """Tests for TrustContext dataclass."""

    def test_context_captures_execution_state(self):
        """TrustContext captures all relevant execution information."""
        ctx = TrustContext(
            agent_id="agent-001",
            action="analyze_data",
            resource="database",
        )

        assert ctx.agent_id == "agent-001"
        assert ctx.action == "analyze_data"
        assert ctx.resource == "database"
        assert ctx.verification_result is None
        assert ctx.parent_anchor_id is None
        assert isinstance(ctx.start_time, datetime)
        assert ctx.effective_constraints == []
        assert ctx.metadata == {}

    def test_context_with_full_state(self):
        """TrustContext can hold complete execution state."""
        verification = make_verification_result(valid=True)

        ctx = TrustContext(
            agent_id="agent-001",
            action="analyze_data",
            resource="database",
            verification_result=verification,
            parent_anchor_id="anchor-parent",
            effective_constraints=["read_only"],
            metadata={"run_id": "run-123"},
        )

        assert ctx.verification_result.valid is True
        assert ctx.parent_anchor_id == "anchor-parent"
        assert "read_only" in ctx.effective_constraints
        assert ctx.metadata["run_id"] == "run-123"


class TestTrustedAgentTransparentDelegation:
    """Tests that TrustedAgent transparently delegates to BaseAgent."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = MagicMock()
        self.mock_trust_ops = AsyncMock()
        self.config = TrustedAgentConfig(agent_id="agent-001")

    def test_getattr_delegates_to_wrapped_agent(self):
        """All BaseAgent attributes accessible through TrustedAgent."""
        self.mock_agent.signature = MagicMock()
        self.mock_agent.config = MagicMock()
        self.mock_agent.to_workflow = MagicMock(return_value="workflow")

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        # Access BaseAgent attributes
        assert trusted.signature == self.mock_agent.signature
        assert trusted.config == self.mock_agent.config
        assert trusted.to_workflow() == "workflow"

    def test_agent_id_returns_config_agent_id(self):
        """agent_id property returns the trust agent ID, not BaseAgent's."""
        self.mock_agent.agent_id = "base-agent-id"

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        assert trusted.agent_id == "agent-001"

    def test_wrapped_agent_exposes_original(self):
        """wrapped_agent property provides access to the original agent."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        assert trusted.wrapped_agent is self.mock_agent

    def test_trust_operations_accessible(self):
        """trust_operations property provides access to TrustOperations."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        assert trusted.trust_operations is self.mock_trust_ops


class TestTrustSandwichPattern:
    """Tests for the core Trust Sandwich Pattern: VERIFY → EXECUTE → AUDIT."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = AsyncMock()
        self.mock_agent.execute_async = AsyncMock(return_value={"result": "success"})

        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(valid=True)
        )
        self.mock_trust_ops.audit = AsyncMock(return_value=make_audit_anchor())

        self.config = TrustedAgentConfig(agent_id="agent-001")

        # EATP: Create execution context for human traceability
        self.context = make_execution_context(agent_id="agent-001")

    @pytest.mark.asyncio
    async def test_execute_verifies_before_action(self):
        """VERIFY: Trust is checked before any action is performed."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        await trusted.execute_async(inputs={"question": "test?"}, context=self.context)

        # Verify was called before execute
        self.mock_trust_ops.verify.assert_called_once()
        call_args = self.mock_trust_ops.verify.call_args
        assert call_args.kwargs["agent_id"] == "agent-001"
        assert call_args.kwargs["action"] == "execute"

    @pytest.mark.asyncio
    async def test_execute_performs_action_on_verified_trust(self):
        """EXECUTE: Action is performed after successful verification."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        result = await trusted.execute_async(
            inputs={"question": "test?"}, context=self.context
        )

        self.mock_agent.execute_async.assert_called_once()
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_execute_records_audit_after_action(self):
        """AUDIT: Action is recorded in audit trail after execution."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        await trusted.execute_async(inputs={"question": "test?"}, context=self.context)

        # Audit was recorded
        self.mock_trust_ops.audit.assert_called_once()
        call_args = self.mock_trust_ops.audit.call_args
        assert call_args.kwargs["agent_id"] == "agent-001"
        assert call_args.kwargs["action"] == "execute"
        assert call_args.kwargs["result"] == ActionResult.SUCCESS

    @pytest.mark.asyncio
    async def test_execute_audits_on_failure(self):
        """AUDIT: Failures are recorded in audit trail."""
        self.mock_agent.execute_async.side_effect = RuntimeError("Execution failed")

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        with pytest.raises(RuntimeError, match="Execution failed"):
            await trusted.execute_async(inputs={}, context=self.context)

        # Audit recorded with FAILURE result
        call_args = self.mock_trust_ops.audit.call_args
        assert call_args.kwargs["result"] == ActionResult.FAILURE
        assert "error" in call_args.kwargs["context_data"]

    @pytest.mark.asyncio
    async def test_execute_blocks_on_verification_failure(self):
        """VERIFY: Verification failure blocks execution."""
        self.mock_trust_ops.verify.return_value = make_verification_result(
            valid=False,
            reason="Capability not found",
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,  # fail_on_verification_failure=True by default
        )

        with pytest.raises(VerificationFailedError):
            await trusted.execute_async(inputs={}, context=self.context)

        # Agent execution never called
        self.mock_agent.execute_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_allows_soft_failure_when_configured(self):
        """Soft failure mode allows execution despite verification failure."""
        self.mock_trust_ops.verify.return_value = make_verification_result(
            valid=False,
            reason="Capability not found",
        )

        soft_config = TrustedAgentConfig(
            agent_id="agent-001",
            fail_on_verification_failure=False,
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=soft_config,
        )

        # Should not raise, but verification still recorded
        result = await trusted.execute_async(inputs={})
        assert result == {"result": "success"}


class TestAuditChaining:
    """Tests for audit anchor chaining across related actions."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = AsyncMock()
        self.mock_agent.execute_async = AsyncMock(return_value={})

        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(valid=True)
        )

        self.anchor_count = 0

        def create_anchor(*args, **kwargs):
            self.anchor_count += 1
            return make_audit_anchor(
                id=f"anchor-{self.anchor_count:03d}",
                action=kwargs.get("action", "execute"),
                result=kwargs.get("result", ActionResult.SUCCESS),
                parent_anchor_id=kwargs.get("parent_anchor_id"),
            )

        self.mock_trust_ops.audit = AsyncMock(side_effect=create_anchor)

        self.config = TrustedAgentConfig(
            agent_id="agent-001",
            parent_anchor_tracking=True,
        )

        # EATP: Create execution context for human traceability
        self.context = make_execution_context(agent_id="agent-001")

    @pytest.mark.asyncio
    async def test_consecutive_actions_chain_anchors(self):
        """Consecutive actions link via parent_anchor_id."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        # First execution
        await trusted.execute_async(inputs={}, action="step_1", context=self.context)
        assert trusted.current_anchor_id == "anchor-001"

        # Second execution - should link to first
        await trusted.execute_async(inputs={}, action="step_2", context=self.context)

        # Second audit call should have parent_anchor_id
        second_call = self.mock_trust_ops.audit.call_args_list[1]
        assert second_call.kwargs["parent_anchor_id"] == "anchor-001"

    @pytest.mark.asyncio
    async def test_anchor_tracking_can_be_disabled(self):
        """Parent anchor tracking can be disabled."""
        no_tracking_config = TrustedAgentConfig(
            agent_id="agent-001",
            parent_anchor_tracking=False,
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=no_tracking_config,
        )

        await trusted.execute_async(inputs={}, action="step_1", context=self.context)
        await trusted.execute_async(inputs={}, action="step_2", context=self.context)

        # Second call should not have parent from tracking
        second_call = self.mock_trust_ops.audit.call_args_list[1]
        assert second_call.kwargs["parent_anchor_id"] is None


class TestAutoEstablishment:
    """Tests for automatic trust establishment when agent not found."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = AsyncMock()
        self.mock_agent.execute_async = AsyncMock(return_value={})

        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.audit = AsyncMock(return_value=make_audit_anchor())

        # EATP: Create execution context for human traceability
        self.context = make_execution_context(agent_id="agent-001")

    @pytest.mark.asyncio
    async def test_auto_establish_when_chain_not_found(self):
        """Auto-establishes trust when agent has no chain."""
        # First verify fails with not found, second succeeds
        self.mock_trust_ops.verify = AsyncMock(
            side_effect=[
                TrustChainNotFoundError(agent_id="agent-001"),
                make_verification_result(valid=True),
            ]
        )
        self.mock_trust_ops.establish = AsyncMock()

        config = TrustedAgentConfig(
            agent_id="agent-001",
            auto_establish=True,
            authority_id="org-enterprise",
            default_capabilities=["execute", "analyze"],
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=config,
        )

        await trusted.execute_async(inputs={}, context=self.context)

        # Establish was called
        self.mock_trust_ops.establish.assert_called_once()
        call_args = self.mock_trust_ops.establish.call_args
        assert call_args.kwargs["agent_id"] == "agent-001"
        assert call_args.kwargs["authority_id"] == "org-enterprise"

    @pytest.mark.asyncio
    async def test_auto_establish_fails_without_authority(self):
        """Auto-establishment fails if no authority configured."""
        self.mock_trust_ops.verify = AsyncMock(
            side_effect=TrustChainNotFoundError(agent_id="agent-001")
        )

        config = TrustedAgentConfig(
            agent_id="agent-001",
            auto_establish=True,
            authority_id=None,  # No authority
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=config,
        )

        with pytest.raises(TrustError, match="no authority_id configured"):
            await trusted.execute_async(inputs={}, context=self.context)

    @pytest.mark.asyncio
    async def test_raises_when_auto_establish_disabled(self):
        """Raises TrustChainNotFoundError when auto-establish disabled."""
        self.mock_trust_ops.verify = AsyncMock(
            side_effect=TrustChainNotFoundError(agent_id="agent-001")
        )

        config = TrustedAgentConfig(
            agent_id="agent-001",
            auto_establish=False,
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=config,
        )

        with pytest.raises(TrustChainNotFoundError):
            await trusted.execute_async(inputs={}, context=self.context)


class TestToolConstraintEnforcement:
    """Tests for enforcing trust chain constraints on tool usage."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = AsyncMock()
        self.mock_agent.execute_tool = AsyncMock(return_value={"output": "result"})

        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(valid=True)
        )
        self.mock_trust_ops.audit = AsyncMock(
            return_value=make_audit_anchor(action="use_tool:file_read")
        )

        self.config = TrustedAgentConfig(
            agent_id="agent-001",
            constraint_enforcement=True,
        )

    @pytest.mark.asyncio
    async def test_execute_tool_verifies_trust(self):
        """Tool execution verifies trust with tool-specific action."""
        self.mock_trust_ops.get_agent_constraints = AsyncMock(return_value=[])

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        await trusted.execute_tool("file_read", {"path": "/data"})

        # Verify called with tool action
        call_args = self.mock_trust_ops.verify.call_args
        assert call_args.kwargs["action"] == "use_tool:file_read"

    @pytest.mark.asyncio
    async def test_read_only_blocks_write_tools(self):
        """read_only constraint blocks write operations."""
        self.mock_trust_ops.get_agent_constraints = AsyncMock(
            return_value=["read_only"]
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        with pytest.raises(ConstraintViolationError) as exc_info:
            await trusted.execute_tool("file_write", {"path": "/data"})

        assert "read_only" in str(exc_info.value)
        assert "file_write" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_only_allows_read_tools(self):
        """read_only constraint allows read operations."""
        self.mock_trust_ops.get_agent_constraints = AsyncMock(
            return_value=["read_only"]
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        result = await trusted.execute_tool("file_read", {"path": "/data"})
        assert result == {"output": "result"}

    @pytest.mark.asyncio
    async def test_no_network_blocks_network_tools(self):
        """no_network constraint blocks network operations."""
        self.mock_trust_ops.get_agent_constraints = AsyncMock(
            return_value=["no_network"]
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        with pytest.raises(ConstraintViolationError) as exc_info:
            await trusted.execute_tool(
                "http_request", {"url": "https://api.example.com"}
            )

        assert "no_network" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_constraint_enforcement_can_be_disabled(self):
        """Constraint enforcement can be disabled."""
        self.mock_trust_ops.get_agent_constraints = AsyncMock(
            return_value=["read_only"]
        )

        no_enforce_config = TrustedAgentConfig(
            agent_id="agent-001",
            constraint_enforcement=False,
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=no_enforce_config,
        )

        # Should not check constraints, so write succeeds
        result = await trusted.execute_tool("file_write", {"path": "/data"})
        assert result == {"output": "result"}

        # get_agent_constraints never called
        self.mock_trust_ops.get_agent_constraints.assert_not_called()


class TestTrustedSupervisorAgent:
    """Tests for hierarchical delegation via TrustedSupervisorAgent."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = AsyncMock()
        self.mock_agent.execute_async = AsyncMock(return_value={})

        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(valid=True)
        )
        self.mock_trust_ops.audit = AsyncMock(
            return_value=make_audit_anchor(
                agent_id="supervisor-001",
                action="delegate_trust",
            )
        )

        # Mock delegation
        self.mock_delegation = MagicMock()
        self.mock_delegation.id = "delegation-001"
        self.mock_trust_ops.delegate = AsyncMock(return_value=self.mock_delegation)

        self.config = TrustedAgentConfig(agent_id="supervisor-001")

        # EATP: Create execution context for human traceability
        self.context = make_execution_context(agent_id="supervisor-001")

    @pytest.mark.asyncio
    async def test_delegate_to_worker(self):
        """Supervisor can delegate capabilities to worker."""
        supervisor = TrustedSupervisorAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        # EATP: delegate_to_worker now returns (delegation, worker_context) tuple
        delegation, worker_context = await supervisor.delegate_to_worker(
            worker_id="worker-001",
            task_id="task-q4-analysis",
            capabilities=["analyze_data"],
            additional_constraints=["q4_data_only"],
            context=self.context,
        )

        assert delegation.id == "delegation-001"
        # EATP: Verify worker context was created with proper delegation chain
        assert worker_context is not None
        assert "worker-001" in worker_context.delegation_chain

        # Delegation was called with correct params
        call_args = self.mock_trust_ops.delegate.call_args
        assert call_args.kwargs["delegator_id"] == "supervisor-001"
        assert call_args.kwargs["delegatee_id"] == "worker-001"
        assert call_args.kwargs["capabilities"] == ["analyze_data"]
        assert call_args.kwargs["additional_constraints"] == ["q4_data_only"]

    @pytest.mark.asyncio
    async def test_delegate_records_audit(self):
        """Delegation is recorded in audit trail."""
        supervisor = TrustedSupervisorAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        await supervisor.delegate_to_worker(
            worker_id="worker-001",
            task_id="task-001",
            capabilities=["analyze"],
            context=self.context,
        )

        # Audit recorded for delegation
        call_args = self.mock_trust_ops.audit.call_args
        assert call_args.kwargs["action"] == "delegate_trust"
        assert call_args.kwargs["resource"] == "worker-001"

    @pytest.mark.asyncio
    async def test_tracks_active_delegations(self):
        """Supervisor tracks active delegations to workers."""
        supervisor = TrustedSupervisorAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        await supervisor.delegate_to_worker(
            worker_id="worker-001",
            task_id="task-001",
            capabilities=["analyze"],
            context=self.context,
        )

        assert "worker-001" in supervisor._active_delegations
        assert "delegation-001" in supervisor._active_delegations["worker-001"]

    @pytest.mark.asyncio
    async def test_revoke_delegation(self):
        """Supervisor can revoke worker delegations."""
        self.mock_trust_ops.revoke_delegation = AsyncMock()

        supervisor = TrustedSupervisorAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        # First delegate
        await supervisor.delegate_to_worker(
            worker_id="worker-001",
            task_id="task-001",
            capabilities=["analyze"],
            context=self.context,
        )

        # Then revoke
        await supervisor.revoke_worker_delegation("delegation-001", "worker-001")

        self.mock_trust_ops.revoke_delegation.assert_called_once_with(
            "delegation-001", "worker-001"
        )

        # Delegation removed from tracking
        assert "delegation-001" not in supervisor._active_delegations.get(
            "worker-001", set()
        )

    @pytest.mark.asyncio
    async def test_create_worker_combines_creation_and_delegation(self):
        """create_worker creates trusted worker with delegated capabilities."""
        mock_worker_agent = AsyncMock()

        supervisor = TrustedSupervisorAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        # EATP: create_worker now returns (worker, worker_context) tuple
        worker, worker_context = await supervisor.create_worker(
            worker_agent=mock_worker_agent,
            worker_id="worker-001",
            capabilities=["analyze_data"],
            constraints=["department_only"],
            context=self.context,
        )

        # Worker is a TrustedAgent
        assert isinstance(worker, TrustedAgent)
        assert worker.agent_id == "worker-001"
        assert worker.wrapped_agent is mock_worker_agent

        # Delegation was created
        self.mock_trust_ops.delegate.assert_called_once()

        # EATP: Worker context was created
        assert worker_context is not None


class TestTrustContextManager:
    """Tests for TrustContextManager async context manager."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(valid=True)
        )
        self.mock_trust_ops.audit = AsyncMock(
            return_value=make_audit_anchor(action="analyze")
        )

    @pytest.mark.asyncio
    async def test_context_manager_verify(self):
        """Can verify actions within context."""
        async with TrustContextManager(self.mock_trust_ops, "agent-001") as ctx:
            result = await ctx.verify("analyze", "database")

            assert result.valid is True
            self.mock_trust_ops.verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_record_success(self):
        """Can record successful actions."""
        async with TrustContextManager(self.mock_trust_ops, "agent-001") as ctx:
            await ctx.verify("analyze")
            # EATP: parameter renamed from 'context' to 'audit_context'
            anchor_id = await ctx.record_success("analyze", audit_context={"rows": 100})

            assert anchor_id == "anchor-001"

            call_args = self.mock_trust_ops.audit.call_args
            assert call_args.kwargs["result"] == ActionResult.SUCCESS

    @pytest.mark.asyncio
    async def test_context_manager_record_failure(self):
        """Can record failed actions."""
        async with TrustContextManager(self.mock_trust_ops, "agent-001") as ctx:
            await ctx.verify("analyze")
            anchor_id = await ctx.record_failure(
                "analyze", "Database connection failed"
            )

            call_args = self.mock_trust_ops.audit.call_args
            assert call_args.kwargs["result"] == ActionResult.FAILURE
            # EATP: parameter renamed from 'context' to 'context_data'
            assert "error" in call_args.kwargs["context_data"]

    @pytest.mark.asyncio
    async def test_context_manager_auto_records_failure_on_exception(self):
        """Context manager auto-records failure when exception occurs."""
        with pytest.raises(RuntimeError):
            async with TrustContextManager(self.mock_trust_ops, "agent-001") as ctx:
                await ctx.verify("analyze")
                raise RuntimeError("Something went wrong")

        # Failure was recorded for pending action
        last_call = self.mock_trust_ops.audit.call_args
        assert last_call.kwargs["result"] == ActionResult.FAILURE

    @pytest.mark.asyncio
    async def test_context_manager_chains_anchors(self):
        """Consecutive recordings chain via parent_anchor_id."""
        # Return different anchor IDs for each call
        anchor_count = [0]

        def create_anchor(*args, **kwargs):
            anchor_count[0] += 1
            return make_audit_anchor(
                id=f"anchor-{anchor_count[0]:03d}",
                action=kwargs.get("action", "analyze"),
                result=kwargs.get("result", ActionResult.SUCCESS),
            )

        self.mock_trust_ops.audit = AsyncMock(side_effect=create_anchor)

        async with TrustContextManager(self.mock_trust_ops, "agent-001") as ctx:
            await ctx.verify("step_1")
            await ctx.record_success("step_1")

            await ctx.verify("step_2")
            await ctx.record_success("step_2")

        # Second audit should have parent_anchor_id
        second_call = self.mock_trust_ops.audit.call_args_list[1]
        assert second_call.kwargs["parent_anchor_id"] == "anchor-001"

    @pytest.mark.asyncio
    async def test_verify_raises_on_failure(self):
        """Verification failure raises VerificationFailedError."""
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(
                valid=False,
                reason="Not permitted",
            )
        )

        async with TrustContextManager(self.mock_trust_ops, "agent-001") as ctx:
            with pytest.raises(VerificationFailedError):
                await ctx.verify("forbidden_action")


class TestAuditDisabled:
    """Tests for behavior when audit is disabled."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = AsyncMock()
        self.mock_agent.execute_async = AsyncMock(return_value={"result": "ok"})

        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(valid=True)
        )

        self.config = TrustedAgentConfig(
            agent_id="agent-001",
            audit_enabled=False,
            # EATP: Disable strict context requirement for these tests
            fail_on_verification_failure=False,
        )

    @pytest.mark.asyncio
    async def test_no_audit_when_disabled(self):
        """No audit recorded when audit_enabled=False."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        await trusted.execute_async(inputs={})

        # Audit never called
        self.mock_trust_ops.audit.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_audit_returns_empty_when_disabled(self):
        """record_audit returns empty string when audit disabled."""
        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=self.config,
        )

        anchor_id = await trusted.record_audit("test_action")
        assert anchor_id == ""


class TestVerificationLevels:
    """Tests for different verification levels."""

    def setup_method(self):
        """Set up mock dependencies."""
        self.mock_agent = AsyncMock()
        self.mock_agent.execute_async = AsyncMock(return_value={})

        self.mock_trust_ops = AsyncMock()
        self.mock_trust_ops.verify = AsyncMock(
            return_value=make_verification_result(valid=True)
        )
        self.mock_trust_ops.audit = AsyncMock(return_value=make_audit_anchor())

        # EATP: Create execution context for human traceability
        self.context = make_execution_context(agent_id="agent-001")

    @pytest.mark.asyncio
    async def test_quick_verification_level(self):
        """QUICK verification level is passed to trust_ops."""
        config = TrustedAgentConfig(
            agent_id="agent-001",
            verification_level=VerificationLevel.QUICK,
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=config,
        )

        await trusted.execute_async(inputs={}, context=self.context)

        call_args = self.mock_trust_ops.verify.call_args
        assert call_args.kwargs["level"] == VerificationLevel.QUICK

    @pytest.mark.asyncio
    async def test_full_verification_level(self):
        """FULL verification level is passed to trust_ops."""
        config = TrustedAgentConfig(
            agent_id="agent-001",
            verification_level=VerificationLevel.FULL,
        )

        trusted = TrustedAgent(
            agent=self.mock_agent,
            trust_ops=self.mock_trust_ops,
            config=config,
        )

        await trusted.execute_async(inputs={}, context=self.context)

        call_args = self.mock_trust_ops.verify.call_args
        assert call_args.kwargs["level"] == VerificationLevel.FULL
