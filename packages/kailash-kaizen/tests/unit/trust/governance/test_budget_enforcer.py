"""
Tier 1 Unit Tests: ExternalAgentBudgetEnforcer

Tests budget enforcement logic in isolation (no database persistence).

Intent: Verify budget checks correctly enforce limits and track usage.
"""

from datetime import datetime

import pytest
from kailash.runtime import AsyncLocalRuntime
from kaizen.trust.governance import (
    BudgetCheckResult,
    ExternalAgentBudget,
    ExternalAgentBudgetEnforcer,
    ExternalAgentCostEstimator,
)


class TestBudgetCheckResult:
    """Test BudgetCheckResult dataclass."""

    def test_budget_check_result_allowed(self):
        """
        Intent: Verify allowed result has correct structure.

        Expected: allowed=True, reason=None, metadata populated.
        """
        result = BudgetCheckResult(
            allowed=True,
            remaining_budget_usd=50.0,
            remaining_executions=5000,
            degraded_mode=False,
            usage_percentage=0.50,
        )

        assert result.allowed is True
        assert result.reason is None
        assert result.remaining_budget_usd == 50.0
        assert result.remaining_executions == 5000
        assert result.degraded_mode is False
        assert result.usage_percentage == 0.50

    def test_budget_check_result_blocked(self):
        """
        Intent: Verify blocked result has reason.

        Expected: allowed=False, reason explains why.
        """
        result = BudgetCheckResult(
            allowed=False,
            reason="Monthly budget exceeded",
            remaining_budget_usd=0.0,
            usage_percentage=1.0,
        )

        assert result.allowed is False
        assert result.reason == "Monthly budget exceeded"
        assert result.remaining_budget_usd == 0.0


class TestExternalAgentBudget:
    """Test ExternalAgentBudget dataclass."""

    def test_budget_creation_with_defaults(self):
        """
        Intent: Verify budget can be created with sensible defaults.

        Expected: All required fields set, optional fields have defaults.
        """
        budget = ExternalAgentBudget(
            external_agent_id="test_agent", monthly_budget_usd=100.0
        )

        assert budget.external_agent_id == "test_agent"
        assert budget.monthly_budget_usd == 100.0
        assert budget.monthly_spent_usd == 0.0
        assert budget.monthly_execution_limit == 10000
        assert budget.monthly_execution_count == 0
        assert budget.warning_threshold == 0.80
        assert budget.degradation_threshold == 0.90
        assert budget.enforcement_mode == "hard"

    def test_budget_creation_with_daily_limits(self):
        """
        Intent: Verify daily limits can be configured.

        Expected: Daily budget and execution limits set correctly.
        """
        budget = ExternalAgentBudget(
            external_agent_id="test_agent",
            monthly_budget_usd=100.0,
            daily_budget_usd=10.0,
            daily_execution_limit=1000,
        )

        assert budget.daily_budget_usd == 10.0
        assert budget.daily_execution_limit == 1000
        assert budget.daily_spent_usd == 0.0
        assert budget.daily_execution_count == 0


@pytest.mark.asyncio
class TestExternalAgentBudgetEnforcer:
    """Test budget enforcer logic."""

    async def test_check_budget_allows_within_monthly_limit(self):
        """
        Intent: Verify budget check allows execution when within monthly limit.

        Setup: Budget $100, spent $50, estimate $10
        Expected: Allowed, remaining $50
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test", monthly_budget_usd=100.0, monthly_spent_usd=50.0
        )

        result = await enforcer.check_budget(budget, estimated_cost=10.0)

        assert result.allowed is True
        assert result.reason is None
        assert result.remaining_budget_usd == 50.0
        assert result.usage_percentage == pytest.approx(0.50, rel=0.01)
        assert result.degraded_mode is False

    async def test_check_budget_blocks_when_monthly_budget_exceeded(self):
        """
        Intent: Verify budget check blocks when monthly budget would be exceeded.

        Setup: Budget $100, spent $50, estimate $60 → would total $110
        Expected: Blocked with reason
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test", monthly_budget_usd=100.0, monthly_spent_usd=50.0
        )

        result = await enforcer.check_budget(budget, estimated_cost=60.0)

        assert result.allowed is False
        assert "Monthly budget would be exceeded" in result.reason
        assert "$110.00" in result.reason
        assert "$100.00" in result.reason
        assert result.remaining_budget_usd == 50.0

    async def test_check_budget_blocks_when_daily_budget_exceeded(self):
        """
        Intent: Verify daily budget enforcement prevents daily spikes.

        Setup: Daily budget $10, daily spent $8, estimate $5 → would total $13
        Expected: Blocked with daily budget reason
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=10.0,
            daily_budget_usd=10.0,
            daily_spent_usd=8.0,
        )

        result = await enforcer.check_budget(budget, estimated_cost=5.0)

        assert result.allowed is False
        assert "Daily budget would be exceeded" in result.reason
        assert "$13.00" in result.reason
        assert "$10.00" in result.reason

    async def test_check_budget_blocks_when_monthly_execution_limit_exceeded(self):
        """
        Intent: Verify execution count limits work independently of cost limits.

        Setup: Monthly limit 1000, count 999, estimate would make 1000
        Expected: Allowed (999 + 1 = 1000 is at limit but not exceeded)

        Setup: Monthly limit 1000, count 1000, estimate would make 1001
        Expected: Blocked
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        # At limit (should allow)
        budget_at_limit = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=1000.0,
            monthly_spent_usd=0.0,
            monthly_execution_limit=1000,
            monthly_execution_count=999,
        )

        result = await enforcer.check_budget(budget_at_limit, estimated_cost=0.01)
        assert result.allowed is True

        # Exceeding limit (should block)
        budget_exceeded = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=1000.0,
            monthly_spent_usd=0.0,
            monthly_execution_limit=1000,
            monthly_execution_count=1000,
        )

        result = await enforcer.check_budget(budget_exceeded, estimated_cost=0.01)
        assert result.allowed is False
        assert "Monthly execution limit would be exceeded" in result.reason
        assert "1001" in result.reason
        assert "1000" in result.reason

    async def test_check_budget_blocks_when_daily_execution_limit_exceeded(self):
        """
        Intent: Verify daily execution limits prevent daily spikes.

        Setup: Daily limit 100, count 100, estimate would make 101
        Expected: Blocked with daily execution reason
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=1000.0,
            monthly_spent_usd=0.0,
            monthly_execution_limit=10000,
            monthly_execution_count=0,
            daily_execution_limit=100,
            daily_execution_count=100,
        )

        result = await enforcer.check_budget(budget, estimated_cost=0.01)

        assert result.allowed is False
        assert "Daily execution limit would be exceeded" in result.reason
        assert "101" in result.reason
        assert "100" in result.reason

    async def test_check_budget_sets_degraded_mode_at_90_percent(self):
        """
        Intent: Verify degradation threshold triggers when usage >= 90%.

        Setup: Budget $100, spent $90 (90%), estimate $1
        Expected: Allowed but degraded_mode=True
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=90.0,
            degradation_threshold=0.90,
        )

        result = await enforcer.check_budget(budget, estimated_cost=1.0)

        assert result.allowed is True  # Still allowed
        assert result.degraded_mode is True  # But degraded
        assert result.usage_percentage == pytest.approx(0.90, rel=0.01)

    async def test_check_budget_triggers_warning_at_80_percent(self):
        """
        Intent: Verify warning threshold triggers when usage >= 80%.

        Setup: Budget $100, spent $80 (80%), estimate $1
        Expected: Allowed, warning_triggered=True
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=80.0,
            warning_threshold=0.80,
        )

        result = await enforcer.check_budget(budget, estimated_cost=1.0)

        assert result.allowed is True
        assert result.warning_triggered is True
        assert result.usage_percentage == pytest.approx(0.80, rel=0.01)

    async def test_check_budget_no_warning_below_threshold(self):
        """
        Intent: Verify no warning when usage < 80%.

        Setup: Budget $100, spent $79 (79%), estimate $1
        Expected: Allowed, warning_triggered=False
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=79.0,
            warning_threshold=0.80,
        )

        result = await enforcer.check_budget(budget, estimated_cost=1.0)

        assert result.allowed is True
        assert result.warning_triggered is False

    async def test_record_usage_updates_all_counters(self):
        """
        Intent: Verify record_usage updates monthly and daily counters.

        Setup: Budget with $50 monthly, $5 daily, 10 executions
        Action: Record $10 usage
        Expected: All counters incremented correctly
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=50.0,
            daily_spent_usd=5.0,
            monthly_execution_count=10,
            daily_execution_count=2,
        )

        updated = await enforcer.record_usage(
            budget, actual_cost=10.0, execution_success=True
        )

        assert updated.monthly_spent_usd == 60.0
        assert updated.daily_spent_usd == 15.0
        assert updated.monthly_execution_count == 11
        assert updated.daily_execution_count == 3

    async def test_record_usage_negative_cost_raises_error(self):
        """
        Intent: Verify negative costs are rejected.

        Expected: ValueError raised
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(external_agent_id="test", monthly_budget_usd=100.0)

        with pytest.raises(ValueError) as exc_info:
            await enforcer.record_usage(
                budget, actual_cost=-10.0, execution_success=True
            )

        assert "cannot be negative" in str(exc_info.value)

    async def test_record_usage_with_metadata(self):
        """
        Intent: Verify metadata can be attached to usage records.

        Expected: Metadata stored in budget
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(external_agent_id="test", monthly_budget_usd=100.0)

        metadata = {"execution_id": "exec-123", "duration_ms": 1500}

        updated = await enforcer.record_usage(
            budget, actual_cost=5.0, execution_success=True, metadata=metadata
        )

        assert "execution_id" in updated.metadata
        assert updated.metadata["execution_id"] == "exec-123"
        assert updated.metadata["duration_ms"] == 1500

    async def test_estimate_execution_cost_delegates_to_cost_estimator(self):
        """
        Intent: Verify cost estimation is delegated correctly.

        Expected: Cost matches ExternalAgentCostEstimator result
        """
        runtime = AsyncLocalRuntime()
        cost_estimator = ExternalAgentCostEstimator()
        enforcer = ExternalAgentBudgetEnforcer(
            runtime=runtime, cost_estimator=cost_estimator
        )

        cost = await enforcer.estimate_execution_cost(
            platform_type="copilot_studio",
            agent_name="hr_assistant",
            complexity="standard",
        )

        # Should match cost estimator directly
        expected_cost = cost_estimator.estimate_cost(
            "copilot_studio", "hr_assistant", complexity="standard"
        )

        assert cost == expected_cost

    async def test_check_budget_priority_order(self):
        """
        Intent: Verify checks are performed in correct order.

        Order: Monthly budget → Daily budget → Monthly executions → Daily executions

        Setup: Violate daily budget but monthly budget OK
        Expected: Daily budget error (not monthly)
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=1000.0,
            monthly_spent_usd=100.0,
            daily_budget_usd=10.0,
            daily_spent_usd=15.0,  # Already exceeded
        )

        result = await enforcer.check_budget(budget, estimated_cost=1.0)

        assert result.allowed is False
        assert "Daily budget" in result.reason  # Should fail on daily, not monthly

    async def test_check_budget_custom_thresholds(self):
        """
        Intent: Verify custom warning/degradation thresholds work.

        Setup: Warning at 70%, degradation at 80%
        Expected: Custom thresholds respected
        """
        runtime = AsyncLocalRuntime()
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)

        budget = ExternalAgentBudget(
            external_agent_id="test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=70.0,
            warning_threshold=0.70,
            degradation_threshold=0.80,
        )

        result = await enforcer.check_budget(budget, estimated_cost=1.0)

        assert result.allowed is True
        assert result.warning_triggered is True  # At 70%
        assert result.degraded_mode is False  # Below 80%


# Run tests with pytest -xvs tests/unit/trust/governance/test_budget_enforcer.py
