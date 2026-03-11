"""
Tests for TrustPolicy and TrustPolicyEngine - Policy-based trust evaluation.

Test Intent:
- Verify policies correctly evaluate trust requirements before agent actions
- Verify policy composition (AND, OR, NOT) works for complex requirements
- Verify built-in evaluators correctly check genesis, capabilities, constraints
- Verify policy engine caching improves performance while maintaining correctness
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from kaizen.trust.orchestration.exceptions import PolicyViolationError
from kaizen.trust.orchestration.execution_context import TrustExecutionContext
from kaizen.trust.orchestration.policy import (
    PolicyResult,
    PolicyType,
    TrustPolicy,
    TrustPolicyEngine,
)


class TestPolicyResult:
    """Test PolicyResult creation and properties."""

    def test_allowed_result(self):
        """Allowed result should indicate success."""
        result = PolicyResult(
            allowed=True,
            policy_name="test_policy",
            reason="Policy satisfied",
        )

        assert result.allowed is True
        assert result.policy_name == "test_policy"
        assert result.reason == "Policy satisfied"

    def test_denied_result(self):
        """Denied result should include reason."""
        result = PolicyResult(
            allowed=False,
            policy_name="require-read-cap",
            reason="Capability missing",
        )

        assert result.allowed is False
        assert result.policy_name == "require-read-cap"
        assert "Capability missing" in result.reason

    def test_allow_factory(self):
        """PolicyResult.allow() should create allowed result."""
        result = PolicyResult.allow("my_policy", "All checks passed")

        assert result.allowed is True
        assert result.policy_name == "my_policy"

    def test_deny_factory(self):
        """PolicyResult.deny() should create denied result."""
        result = PolicyResult.deny("my_policy", "Access denied")

        assert result.allowed is False
        assert result.reason == "Access denied"


class TestTrustPolicyCreation:
    """Test TrustPolicy factory methods."""

    def test_require_genesis_policy(self):
        """require_genesis creates REQUIRE_GENESIS policy."""
        policy = TrustPolicy.require_genesis()

        assert policy.policy_type == PolicyType.REQUIRE_GENESIS
        assert policy.policy_name == "require_genesis"

    def test_require_capability_policy(self):
        """require_capability creates REQUIRE_CAPABILITY policy."""
        policy = TrustPolicy.require_capability("admin_access")

        assert policy.policy_type == PolicyType.REQUIRE_CAPABILITY
        assert policy.policy_config["capability"] == "admin_access"
        assert "admin_access" in policy.policy_name

    def test_enforce_constraint_policy(self):
        """enforce_constraint creates ENFORCE_CONSTRAINT policy."""
        policy = TrustPolicy.enforce_constraint(
            constraint_type="max_records",
            constraint_value=1000,
        )

        assert policy.policy_type == PolicyType.ENFORCE_CONSTRAINT
        assert policy.policy_config["constraint_type"] == "max_records"
        assert policy.policy_config["constraint_value"] == 1000

    def test_require_delegation_policy(self):
        """require_delegation creates REQUIRE_DELEGATION policy."""
        policy = TrustPolicy.require_delegation(from_agent_id="trusted-supervisor")

        assert policy.policy_type == PolicyType.REQUIRE_DELEGATION
        assert policy.policy_config["from_agent_id"] == "trusted-supervisor"

    def test_verify_chain_integrity_policy(self):
        """verify_chain_integrity creates VERIFY_CHAIN_INTEGRITY policy."""
        policy = TrustPolicy.verify_chain_integrity()

        assert policy.policy_type == PolicyType.VERIFY_CHAIN_INTEGRITY

    def test_custom_policy(self):
        """Custom policies can be created with evaluators."""

        async def custom_eval(agent_id, context, trust_ops):
            return PolicyResult.allow("custom", "Custom passed")

        policy = TrustPolicy.custom(
            policy_name="custom-check",
            evaluator=custom_eval,
            config={"key": "value"},
        )

        assert policy.policy_type == PolicyType.CUSTOM
        assert policy.policy_name == "custom-check"
        assert policy.evaluator is not None


class TestPolicyComposition:
    """Test policy composition with AND, OR, NOT operations."""

    def test_and_composition(self):
        """AND composition requires all policies to pass."""
        policy1 = TrustPolicy.require_capability("read")
        policy2 = TrustPolicy.require_capability("write")

        combined = policy1.and_(policy2)

        assert "AND" in combined.policy_name
        assert combined.is_composed()

    def test_or_composition(self):
        """OR composition passes if any policy passes."""
        policy1 = TrustPolicy.require_capability("admin")
        policy2 = TrustPolicy.require_capability("superuser")

        combined = policy1.or_(policy2)

        assert "OR" in combined.policy_name
        assert combined.is_composed()

    def test_not_composition(self):
        """NOT composition inverts policy result."""
        policy = TrustPolicy.require_capability("guest")

        inverted = policy.not_()

        assert "NOT" in inverted.policy_name
        assert inverted.is_composed()

    def test_complex_composition(self):
        """Complex compositions can be built with multiple operators."""
        # (read AND write) OR admin
        read_write = TrustPolicy.require_capability("read").and_(
            TrustPolicy.require_capability("write")
        )
        admin = TrustPolicy.require_capability("admin")

        combined = read_write.or_(admin)

        assert "OR" in combined.policy_name
        assert "AND" in combined.policy_name


class TestTrustPolicyEngine:
    """Test TrustPolicyEngine evaluation."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(
            return_value=MagicMock(
                capability_attestations=[],
            )
        )
        mock.verify = AsyncMock(return_value=MagicMock(valid=True, reason=""))
        return mock

    @pytest.fixture
    def sample_context(self):
        """Create sample execution context."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="test-task",
            delegated_capabilities=["read_data", "analyze_data"],
            inherited_constraints={
                "max_records": 1000,
                "allowed_tables": ["users", "orders"],
            },
        )

    @pytest.fixture
    def engine(self, mock_trust_ops):
        """Create policy engine with mock trust ops."""
        return TrustPolicyEngine(trust_operations=mock_trust_ops)

    @pytest.mark.asyncio
    async def test_evaluate_require_genesis_passes(
        self, engine, sample_context, mock_trust_ops
    ):
        """REQUIRE_GENESIS passes when agent has trust chain."""
        mock_trust_ops.get_chain.return_value = MagicMock()  # Non-None
        policy = TrustPolicy.require_genesis()

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluate_require_genesis_fails(
        self, engine, sample_context, mock_trust_ops
    ):
        """REQUIRE_GENESIS fails when agent lacks trust chain."""
        mock_trust_ops.get_chain.return_value = None
        policy = TrustPolicy.require_genesis()

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is False
        assert "trust chain" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_evaluate_require_capability_passes(self, engine, sample_context):
        """REQUIRE_CAPABILITY passes when context has capability."""
        policy = TrustPolicy.require_capability("read_data")

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluate_require_capability_fails(self, engine, sample_context):
        """REQUIRE_CAPABILITY fails when context lacks capability."""
        policy = TrustPolicy.require_capability("admin_access")

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is False
        assert "admin_access" in result.reason

    @pytest.mark.asyncio
    async def test_evaluate_enforce_constraint_passes(self, engine, sample_context):
        """ENFORCE_CONSTRAINT passes when within limits."""
        policy = TrustPolicy.enforce_constraint(
            constraint_type="max_records",
            constraint_value=2000,  # Context has 1000, which is within 2000
        )

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluate_enforce_constraint_fails(self, engine, sample_context):
        """ENFORCE_CONSTRAINT fails when exceeding limits."""
        policy = TrustPolicy.enforce_constraint(
            constraint_type="max_records",
            constraint_value=500,  # Context has 1000, which exceeds 500
        )

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_evaluate_chain_integrity_passes(
        self, engine, sample_context, mock_trust_ops
    ):
        """VERIFY_CHAIN_INTEGRITY passes when chain is valid."""
        mock_trust_ops.verify.return_value = MagicMock(valid=True, reason="OK")
        policy = TrustPolicy.verify_chain_integrity()

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluate_chain_integrity_fails(
        self, engine, sample_context, mock_trust_ops
    ):
        """VERIFY_CHAIN_INTEGRITY fails when chain is invalid."""
        mock_trust_ops.verify.return_value = MagicMock(
            valid=False, reason="Chain broken"
        )
        policy = TrustPolicy.verify_chain_integrity()

        result = await engine.evaluate_policy(policy, "agent-001", sample_context)

        assert result.allowed is False


class TestPolicyEngineComposedEvaluation:
    """Test evaluation of composed policies."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(return_value=MagicMock())
        mock.verify = AsyncMock(return_value=MagicMock(valid=True))
        return mock

    @pytest.fixture
    def engine(self, mock_trust_ops):
        """Create policy engine."""
        return TrustPolicyEngine(trust_operations=mock_trust_ops)

    @pytest.mark.asyncio
    async def test_and_passes_when_both_pass(self, engine):
        """AND composition passes when both policies pass."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write"],
        )

        policy = TrustPolicy.require_capability("read").and_(
            TrustPolicy.require_capability("write")
        )

        result = await engine.evaluate_policy(policy, "agent", context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_and_fails_when_one_fails(self, engine):
        """AND composition fails when any policy fails."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],  # Missing write
        )

        policy = TrustPolicy.require_capability("read").and_(
            TrustPolicy.require_capability("write")
        )

        result = await engine.evaluate_policy(policy, "agent", context)

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_or_passes_when_one_passes(self, engine):
        """OR composition passes when any policy passes."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["admin"],  # Has admin, not superuser
        )

        policy = TrustPolicy.require_capability("admin").or_(
            TrustPolicy.require_capability("superuser")
        )

        result = await engine.evaluate_policy(policy, "agent", context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_or_fails_when_all_fail(self, engine):
        """OR composition fails when all policies fail."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],  # Neither admin nor superuser
        )

        policy = TrustPolicy.require_capability("admin").or_(
            TrustPolicy.require_capability("superuser")
        )

        result = await engine.evaluate_policy(policy, "agent", context)

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_not_inverts_result(self, engine):
        """NOT composition inverts policy result."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["user"],  # Not guest
        )

        # NOT guest (should pass when agent doesn't have guest capability)
        policy = TrustPolicy.require_capability("guest").not_()

        result = await engine.evaluate_policy(policy, "agent", context)

        assert result.allowed is True  # Inverted: not having guest is OK


class TestPolicyEngineRegistration:
    """Test policy registration and evaluation."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(return_value=MagicMock())
        mock.verify = AsyncMock(return_value=MagicMock(valid=True))
        return mock

    @pytest.fixture
    def engine(self, mock_trust_ops):
        """Create policy engine."""
        return TrustPolicyEngine(trust_operations=mock_trust_ops)

    @pytest.fixture
    def sample_context(self):
        """Create sample execution context."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write"],
        )

    @pytest.mark.asyncio
    async def test_register_and_evaluate_policy(self, engine, sample_context):
        """Registered policies are evaluated."""
        policy = TrustPolicy.require_capability("write")
        engine.register_policy(policy)

        result = await engine.evaluate_for_agent("agent-001", sample_context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_multiple_policies_evaluated(self, engine, sample_context):
        """Multiple policies are all evaluated."""
        engine.register_policy(TrustPolicy.require_capability("read"))
        engine.register_policy(TrustPolicy.require_capability("write"))

        result = await engine.evaluate_for_agent("agent-001", sample_context)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_no_policies_returns_allowed(self, engine, sample_context):
        """No registered policies returns allowed by default."""
        result = await engine.evaluate_for_agent("unregistered-agent", sample_context)

        assert result.allowed is True

    def test_list_policies(self, engine):
        """Can list registered policies."""
        engine.register_policy(TrustPolicy.require_capability("read"))
        engine.register_policy(TrustPolicy.require_genesis())

        policies = engine.list_policies()

        assert len(policies) == 2

    def test_unregister_policy(self, engine):
        """Can unregister policies."""
        policy = TrustPolicy.require_genesis()
        engine.register_policy(policy)

        removed = engine.unregister_policy(policy.policy_name)

        assert removed is True
        assert len(engine.list_policies()) == 0


class TestPolicyEngineCaching:
    """Test policy result caching."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock trust operations."""
        mock = MagicMock()
        mock.get_chain = AsyncMock(return_value=MagicMock())
        mock.verify = AsyncMock(return_value=MagicMock(valid=True))
        return mock

    @pytest.fixture
    def engine_with_cache(self, mock_trust_ops):
        """Create engine with caching enabled."""
        return TrustPolicyEngine(
            trust_operations=mock_trust_ops,
            cache_ttl_seconds=300,
            enable_cache=True,
        )

    @pytest.fixture
    def sample_context(self):
        """Create sample execution context."""
        return TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
        )

    @pytest.mark.asyncio
    async def test_cached_results_returned(self, engine_with_cache, sample_context):
        """Cached results should be returned on subsequent calls."""
        policy = TrustPolicy.require_capability("read")

        # First call
        result1 = await engine_with_cache.evaluate_policy(
            policy, "agent", sample_context
        )
        # Second call (should use cache)
        result2 = await engine_with_cache.evaluate_policy(
            policy, "agent", sample_context
        )

        assert result1.allowed == result2.allowed
        assert result1.allowed is True

    @pytest.mark.asyncio
    async def test_cache_stats(self, engine_with_cache, sample_context):
        """Cache stats should be tracked."""
        policy = TrustPolicy.require_capability("read")

        await engine_with_cache.evaluate_policy(policy, "agent", sample_context)
        await engine_with_cache.evaluate_policy(policy, "agent", sample_context)

        stats = engine_with_cache.get_cache_stats()
        assert stats["total_evaluations"] >= 2
        assert stats["cache_hits"] >= 1

    @pytest.mark.asyncio
    async def test_clear_cache(self, engine_with_cache, sample_context):
        """Cache can be cleared."""
        policy = TrustPolicy.require_capability("read")

        await engine_with_cache.evaluate_policy(policy, "agent", sample_context)
        count = engine_with_cache.clear_cache()

        assert count >= 1
        # After clearing, should re-evaluate
        result = await engine_with_cache.evaluate_policy(
            policy, "agent", sample_context
        )
        assert result.allowed is True
