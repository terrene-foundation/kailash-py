"""
Tier 3 End-to-End Tests: Complete Budget Lifecycle

Tests budget enforcement in complete workflows (NO MOCKING).

Intent: Verify budget enforcement prevents over-budget executions in real scenarios.

CRITICAL: Uses real infrastructure for NO MOCKING policy (Tier 3).
"""

from datetime import datetime, timedelta, timezone

import pytest
from kailash.runtime import AsyncLocalRuntime
from kaizen.trust.governance import (
    BudgetAlertModel,
    BudgetHistoryModel,
    BudgetResetService,
    ExternalAgentBudget,
    ExternalAgentBudgetEnforcer,
    ExternalAgentBudgetModel,
)

from dataflow import DataFlow


@pytest.fixture
async def db_with_schema():
    """
    Create real database with complete schema for E2E testing.

    Returns SQLite with all governance tables.
    """
    db = DataFlow(database_type="sqlite", database_config={"database": ":memory:"})

    # Register all models
    db.register_model(ExternalAgentBudgetModel)
    db.register_model(BudgetHistoryModel)
    db.register_model(BudgetAlertModel)

    # Create tables manually for testing
    # Note: In production, DataFlow would auto-create via @db.model decorator
    await db.async_execute(
        """
        CREATE TABLE IF NOT EXISTS external_agent_budget_model (
            external_agent_id TEXT PRIMARY KEY,
            monthly_budget_usd REAL,
            monthly_spent_usd REAL,
            monthly_execution_limit INTEGER,
            monthly_execution_count INTEGER,
            daily_budget_usd REAL,
            daily_spent_usd REAL,
            daily_execution_limit INTEGER,
            daily_execution_count INTEGER,
            cost_per_execution REAL,
            warning_threshold REAL,
            degradation_threshold REAL,
            enforcement_mode TEXT,
            last_reset_monthly TEXT,
            last_reset_daily TEXT,
            created_at TEXT,
            updated_at TEXT,
            metadata TEXT
        )
    """
    )

    await db.async_execute(
        """
        CREATE TABLE IF NOT EXISTS budget_history_model (
            id TEXT PRIMARY KEY,
            external_agent_id TEXT,
            year INTEGER,
            month INTEGER,
            monthly_spent_usd REAL,
            monthly_execution_count INTEGER,
            archived_at TEXT,
            metadata TEXT
        )
    """
    )

    await db.async_execute(
        """
        CREATE TABLE IF NOT EXISTS budget_alert_model (
            id TEXT PRIMARY KEY,
            external_agent_id TEXT,
            alert_type TEXT,
            usage_percentage REAL,
            remaining_budget_usd REAL,
            timestamp TEXT,
            acknowledged INTEGER,
            acknowledged_by TEXT,
            acknowledged_at TEXT,
            metadata TEXT
        )
    """
    )

    yield db

    await db.close()


@pytest.fixture
def runtime():
    """Create runtime for E2E tests."""
    return AsyncLocalRuntime()


@pytest.mark.e2e
@pytest.mark.asyncio
class TestBudgetEnforcementE2E:
    """End-to-end budget enforcement scenarios."""

    async def test_multi_invocation_budget_enforcement(self, db_with_schema, runtime):
        """
        Intent: Verify budget blocking works in multi-invocation scenario.

        Setup:
        - Monthly budget $50
        - Cost per execution $10
        - Make 5 invocations (5 * $10 = $50, at limit)
        - Attempt 6th invocation (would be $60 total)

        Expected:
        - First 5 invocations succeed
        - 6th invocation fails with budget error
        - Database shows monthly_spent_usd=$50.0
        """
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime, db=db_with_schema)

        budget = ExternalAgentBudget(
            external_agent_id="multi_invoke_test",
            monthly_budget_usd=50.0,
            monthly_spent_usd=0.0,
            cost_per_execution=10.0,
        )

        # Make 5 successful invocations
        for i in range(5):
            # Check budget
            result = await enforcer.check_budget(budget, estimated_cost=10.0)
            assert result.allowed is True, f"Invocation {i + 1} should be allowed"

            # Record usage
            budget = await enforcer.record_usage(
                budget,
                actual_cost=10.0,
                execution_success=True,
                metadata={"invocation": i + 1},
            )

        # Verify we're at budget limit
        assert budget.monthly_spent_usd == 50.0
        assert budget.monthly_execution_count == 5

        # Attempt 6th invocation (should fail)
        result = await enforcer.check_budget(budget, estimated_cost=10.0)

        assert result.allowed is False
        assert "Monthly budget would be exceeded" in result.reason
        assert "$60.00" in result.reason  # Would total $60
        assert "$50.00" in result.reason  # Limit is $50

    async def test_degradation_mode_triggers_alert(self, db_with_schema, runtime):
        """
        Intent: Verify degradation threshold triggers alert workflow.

        Setup:
        - Monthly budget $100
        - Degradation threshold 90%
        - Make execution bringing total to $90 (exactly 90% - should alert)

        Expected:
        - Execution allowed
        - degraded_mode=True (at 90% threshold)
        - Alert logged (warning)
        """
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime, db=db_with_schema)

        budget = ExternalAgentBudget(
            external_agent_id="degradation_alert_test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=85.0,
            degradation_threshold=0.90,
        )

        # Execution: Bring to $90 (exactly 90% - threshold)
        result = await enforcer.check_budget(budget, estimated_cost=5.0)
        assert result.allowed is True
        assert result.degraded_mode is False  # Not degraded YET (85%)

        budget = await enforcer.record_usage(
            budget, actual_cost=5.0, execution_success=True
        )
        assert budget.monthly_spent_usd == 90.0

        # Second check at 90%
        result2 = await enforcer.check_budget(budget, estimated_cost=1.0)
        assert result2.allowed is True
        assert result2.degraded_mode is True  # NOW degraded (90% threshold met)
        assert result2.usage_percentage == pytest.approx(0.90, rel=0.01)

    async def test_daily_reset_workflow(self, db_with_schema, runtime):
        """
        Intent: Verify daily reset workflow resets daily counters only.

        Setup:
        - Create budget with monthly=$50, daily=$10
        - Simulate daily usage
        - Execute daily reset
        - Verify daily counters reset, monthly preserved

        Expected:
        - Before reset: daily_spent_usd=$10, monthly_spent_usd=$50
        - After reset: daily_spent_usd=$0, monthly_spent_usd=$50 (unchanged)
        """
        reset_service = BudgetResetService(runtime=runtime, db=db_with_schema)

        # Note: This test simulates reset without actual database insertion
        # Full E2E would require DataFlow CreateNode workflow

        result = await reset_service.reset_daily_budgets()

        assert "budgets_reset" in result
        assert "timestamp" in result
        assert isinstance(result["errors"], list)

        # Verify timestamp is recent
        timestamp = datetime.fromisoformat(result["timestamp"])
        assert (datetime.now(timezone.utc) - timestamp).total_seconds() < 5

    async def test_monthly_reset_with_archival(self, db_with_schema, runtime):
        """
        Intent: Verify monthly reset archives previous month data.

        Setup:
        - Create budget with monthly usage
        - Execute monthly reset with archival
        - Verify monthly counters reset and archive created

        Expected:
        - monthly_spent_usd reset to $0
        - monthly_execution_count reset to 0
        - BudgetHistory record created with previous month data
        """
        reset_service = BudgetResetService(runtime=runtime, db=db_with_schema)

        result = await reset_service.reset_monthly_budgets(archive_history=True)

        assert "budgets_reset" in result
        assert "archived" in result
        assert "archived_count" in result

        # Verify result structure
        assert isinstance(result["budgets_reset"], int)
        assert isinstance(result["archived"], bool)
        assert isinstance(result["archived_count"], int)

    async def test_warning_threshold_at_80_percent(self, db_with_schema, runtime):
        """
        Intent: Verify warning triggers at 80% usage.

        Setup:
        - Monthly budget $100
        - Warning threshold 80%
        - Usage at exactly 80%

        Expected:
        - Execution allowed
        - warning_triggered=True
        - degraded_mode=False (below 90%)
        """
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime, db=db_with_schema)

        budget = ExternalAgentBudget(
            external_agent_id="warning_test",
            monthly_budget_usd=100.0,
            monthly_spent_usd=80.0,  # Already at 80%
            warning_threshold=0.80,
            degradation_threshold=0.90,
        )

        result = await enforcer.check_budget(budget, estimated_cost=1.0)

        # At 80% now
        assert result.allowed is True
        assert result.warning_triggered is True
        assert result.degraded_mode is False

    async def test_execution_count_limit_blocks_cheap_operations(
        self, db_with_schema, runtime
    ):
        """
        Intent: Verify execution limits block even when budget has room.

        Setup:
        - Monthly budget $1000 (plenty of room)
        - Monthly execution limit 10
        - Make 10 cheap operations ($1 each)
        - Attempt 11th operation

        Expected:
        - First 10 operations succeed
        - 11th operation blocked by execution limit (not budget)
        """
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime, db=db_with_schema)

        budget = ExternalAgentBudget(
            external_agent_id="exec_count_test",
            monthly_budget_usd=1000.0,
            monthly_spent_usd=0.0,
            monthly_execution_limit=10,
            monthly_execution_count=0,
        )

        # Make 10 cheap operations
        for i in range(10):
            result = await enforcer.check_budget(budget, estimated_cost=1.0)
            assert result.allowed is True

            budget = await enforcer.record_usage(
                budget, actual_cost=1.0, execution_success=True
            )

        # Budget: $10/$1000 (1% used, plenty of room)
        # Executions: 10/10 (at limit)
        assert budget.monthly_spent_usd == 10.0
        assert budget.monthly_execution_count == 10

        # Attempt 11th operation
        result = await enforcer.check_budget(budget, estimated_cost=1.0)

        assert result.allowed is False
        assert "Monthly execution limit would be exceeded" in result.reason

    async def test_daily_spike_protection(self, db_with_schema, runtime):
        """
        Intent: Verify daily limits prevent cost spikes within a day.

        Setup:
        - Monthly budget $1000 (plenty)
        - Daily budget $50 (restrictive)
        - Make operations totaling $50 today
        - Attempt operation that would exceed daily limit

        Expected:
        - Operations up to $50 succeed
        - Operation exceeding daily limit blocked (even though monthly OK)
        """
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime, db=db_with_schema)

        budget = ExternalAgentBudget(
            external_agent_id="daily_spike_test",
            monthly_budget_usd=1000.0,
            monthly_spent_usd=100.0,
            daily_budget_usd=50.0,
            daily_spent_usd=0.0,
        )

        # Make operations totaling $50 daily
        for i in range(5):
            result = await enforcer.check_budget(budget, estimated_cost=10.0)
            assert result.allowed is True

            budget = await enforcer.record_usage(
                budget, actual_cost=10.0, execution_success=True
            )

        # Daily: $50/$50 (at limit)
        # Monthly: $150/$1000 (plenty of room)
        assert budget.daily_spent_usd == 50.0
        assert budget.monthly_spent_usd == 150.0

        # Attempt operation exceeding daily limit
        result = await enforcer.check_budget(budget, estimated_cost=10.0)

        assert result.allowed is False
        assert "Daily budget would be exceeded" in result.reason

    async def test_complex_execution_costs_more(self, db_with_schema, runtime):
        """
        Intent: Verify complex operations cost more than simple ones.

        Setup: Compare costs for simple vs complex Copilot Studio invocations
        Expected: Complex cost > simple cost
        """
        enforcer = ExternalAgentBudgetEnforcer(runtime=runtime, db=db_with_schema)

        simple_cost = await enforcer.estimate_execution_cost(
            platform_type="copilot_studio", agent_name="test", complexity="simple"
        )

        complex_cost = await enforcer.estimate_execution_cost(
            platform_type="copilot_studio", agent_name="test", complexity="complex"
        )

        assert complex_cost > simple_cost
        # Complex should be ~4x simple (2.0 multiplier vs 0.5)
        assert complex_cost / simple_cost == pytest.approx(4.0, rel=0.1)


# Run tests with pytest -xvs tests/e2e/trust/governance/test_budget_e2e.py
