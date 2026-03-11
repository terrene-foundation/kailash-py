"""
External Agent Budget Enforcer.

Extends Kaizen's BudgetEnforcer with multi-dimensional budget tracking for external agents:
- Monthly and daily budget limits (USD)
- Monthly and daily execution count limits
- Warning and degradation thresholds
- Soft vs hard enforcement modes

Integrates with DataFlow for persistent budget state.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from kaizen.trust.governance.cost_estimator import ExternalAgentCostEstimator

logger = logging.getLogger(__name__)


@dataclass
class ExternalAgentBudget:
    """
    Multi-dimensional budget configuration for external agents.

    Budgets can be enforced at multiple levels:
    - Monthly budget (primary limit)
    - Daily budget (spike prevention)
    - Execution count limits (non-monetary)

    Attributes:
        external_agent_id: Unique identifier for external agent
        monthly_budget_usd: Monthly spending limit (USD)
        monthly_spent_usd: Current month spending (USD)
        monthly_execution_limit: Max executions per month
        monthly_execution_count: Current month execution count
        daily_budget_usd: Daily spending limit (USD), None for unlimited
        daily_spent_usd: Today's spending (USD)
        daily_execution_limit: Max executions per day, None for unlimited
        daily_execution_count: Today's execution count
        cost_per_execution: Estimated cost per invocation (USD)
        warning_threshold: Warn when usage >= this percentage (0.0-1.0)
        degradation_threshold: Degrade when usage >= this percentage (0.0-1.0)
        enforcement_mode: "hard" (block) or "soft" (warn only)
        last_reset_monthly: Timestamp of last monthly reset
        last_reset_daily: Timestamp of last daily reset
    """

    external_agent_id: str
    monthly_budget_usd: float
    monthly_spent_usd: float = 0.0
    monthly_execution_limit: int = 10000
    monthly_execution_count: int = 0
    daily_budget_usd: float | None = None
    daily_spent_usd: float = 0.0
    daily_execution_limit: int | None = None
    daily_execution_count: int = 0
    cost_per_execution: float = 0.05
    warning_threshold: float = 0.80  # 80%
    degradation_threshold: float = 0.90  # 90%
    enforcement_mode: str = "hard"  # "hard" or "soft"
    last_reset_monthly: datetime | None = None
    last_reset_daily: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetCheckResult:
    """
    Result of budget check operation.

    Attributes:
        allowed: Whether execution is allowed
        reason: Human-readable reason if not allowed
        remaining_budget_usd: Remaining monthly budget (USD), None if unlimited
        remaining_daily_budget_usd: Remaining daily budget (USD), None if unlimited
        remaining_executions: Remaining monthly executions, None if unlimited
        remaining_daily_executions: Remaining daily executions, None if unlimited
        degraded_mode: Whether system is in degraded mode (near limit)
        usage_percentage: Current usage percentage (0.0-1.0)
        warning_triggered: Whether warning threshold exceeded
        metadata: Additional context information
    """

    allowed: bool
    reason: str | None = None
    remaining_budget_usd: float | None = None
    remaining_daily_budget_usd: float | None = None
    remaining_executions: int | None = None
    remaining_daily_executions: int | None = None
    degraded_mode: bool = False
    usage_percentage: float = 0.0
    warning_triggered: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ExternalAgentBudgetEnforcer:
    """
    Budget enforcement for external agent executions.

    Provides multi-dimensional budget checking and tracking:
    - Pre-execution budget validation
    - Post-execution usage recording
    - Degradation threshold monitoring
    - Warning alerts

    Integrates with DataFlow for persistent state management.

    Examples:
        >>> from dataflow import DataFlow
        >>> db = DataFlow(database_type="sqlite", database_config={"database": ":memory:"})
        >>> runtime = AsyncLocalRuntime()
        >>> enforcer = ExternalAgentBudgetEnforcer(runtime=runtime, db=db)
        >>>
        >>> # Check budget before execution
        >>> budget = ExternalAgentBudget(
        ...     external_agent_id="copilot_hr",
        ...     monthly_budget_usd=100.0,
        ...     monthly_spent_usd=50.0
        ... )
        >>> result = await enforcer.check_budget(budget, estimated_cost=10.0)
        >>> if result.allowed:
        ...     print("Execution allowed")
        >>> else:
        ...     print(f"Blocked: {result.reason}")
        >>>
        >>> # Record actual usage
        >>> await enforcer.record_usage(budget, actual_cost=9.5, execution_success=True)
    """

    def __init__(
        self,
        runtime: AsyncLocalRuntime,
        db: Any | None = None,
        cost_estimator: ExternalAgentCostEstimator | None = None,
    ):
        """
        Initialize budget enforcer.

        Args:
            runtime: AsyncLocalRuntime for workflow execution
            db: Optional DataFlow instance for persistence
            cost_estimator: Optional cost estimator (creates default if None)
        """
        self.runtime = runtime
        self.db = db
        self.cost_estimator = cost_estimator or ExternalAgentCostEstimator()

    async def check_budget(
        self, budget: ExternalAgentBudget, estimated_cost: float
    ) -> BudgetCheckResult:
        """
        Check if execution is allowed within budget constraints.

        Checks in order:
        1. Monthly budget (USD)
        2. Daily budget (USD) if configured
        3. Monthly execution limit
        4. Daily execution limit if configured
        5. Degradation threshold (triggers alert but allows execution)

        Args:
            budget: Current budget configuration and state
            estimated_cost: Estimated cost for this execution (USD)

        Returns:
            BudgetCheckResult with allowed status and metadata

        Examples:
            >>> budget = ExternalAgentBudget(
            ...     external_agent_id="test",
            ...     monthly_budget_usd=100.0,
            ...     monthly_spent_usd=50.0
            ... )
            >>> result = await enforcer.check_budget(budget, estimated_cost=60.0)
            >>> result.allowed
            False
            >>> result.reason
            'Monthly budget would be exceeded: $110.00 > $100.00'
        """
        # Check monthly budget (USD)
        projected_monthly = budget.monthly_spent_usd + estimated_cost
        if projected_monthly > budget.monthly_budget_usd:
            return BudgetCheckResult(
                allowed=False,
                reason=(
                    f"Monthly budget would be exceeded: "
                    f"${projected_monthly:.2f} > ${budget.monthly_budget_usd:.2f}"
                ),
                remaining_budget_usd=budget.monthly_budget_usd
                - budget.monthly_spent_usd,
                usage_percentage=budget.monthly_spent_usd / budget.monthly_budget_usd,
            )

        # Check daily budget (USD) if configured
        if budget.daily_budget_usd is not None:
            projected_daily = budget.daily_spent_usd + estimated_cost
            if projected_daily > budget.daily_budget_usd:
                return BudgetCheckResult(
                    allowed=False,
                    reason=(
                        f"Daily budget would be exceeded: "
                        f"${projected_daily:.2f} > ${budget.daily_budget_usd:.2f}"
                    ),
                    remaining_daily_budget_usd=budget.daily_budget_usd
                    - budget.daily_spent_usd,
                    usage_percentage=budget.daily_spent_usd / budget.daily_budget_usd,
                )

        # Check monthly execution limit
        projected_executions = budget.monthly_execution_count + 1
        if projected_executions > budget.monthly_execution_limit:
            return BudgetCheckResult(
                allowed=False,
                reason=(
                    f"Monthly execution limit would be exceeded: "
                    f"{projected_executions} > {budget.monthly_execution_limit}"
                ),
                remaining_executions=budget.monthly_execution_limit
                - budget.monthly_execution_count,
                usage_percentage=budget.monthly_execution_count
                / budget.monthly_execution_limit,
            )

        # Check daily execution limit if configured
        if budget.daily_execution_limit is not None:
            projected_daily_executions = budget.daily_execution_count + 1
            if projected_daily_executions > budget.daily_execution_limit:
                return BudgetCheckResult(
                    allowed=False,
                    reason=(
                        f"Daily execution limit would be exceeded: "
                        f"{projected_daily_executions} > {budget.daily_execution_limit}"
                    ),
                    remaining_daily_executions=budget.daily_execution_limit
                    - budget.daily_execution_count,
                    usage_percentage=budget.daily_execution_count
                    / budget.daily_execution_limit,
                )

        # Calculate usage percentage (based on monthly budget)
        usage_percentage = budget.monthly_spent_usd / budget.monthly_budget_usd

        # Check warning threshold
        warning_triggered = usage_percentage >= budget.warning_threshold

        # Check degradation threshold
        degraded_mode = usage_percentage >= budget.degradation_threshold
        if degraded_mode:
            logger.warning(
                f"Degradation threshold exceeded for {budget.external_agent_id}: "
                f"{usage_percentage:.1%} >= {budget.degradation_threshold:.1%}"
            )
            await self._trigger_degradation_alert(budget, usage_percentage)

        # Execution allowed
        return BudgetCheckResult(
            allowed=True,
            reason=None,
            remaining_budget_usd=budget.monthly_budget_usd - budget.monthly_spent_usd,
            remaining_daily_budget_usd=(
                budget.daily_budget_usd - budget.daily_spent_usd
                if budget.daily_budget_usd
                else None
            ),
            remaining_executions=budget.monthly_execution_limit
            - budget.monthly_execution_count,
            remaining_daily_executions=(
                budget.daily_execution_limit - budget.daily_execution_count
                if budget.daily_execution_limit
                else None
            ),
            degraded_mode=degraded_mode,
            usage_percentage=usage_percentage,
            warning_triggered=warning_triggered,
        )

    async def record_usage(
        self,
        budget: ExternalAgentBudget,
        actual_cost: float,
        execution_success: bool,
        metadata: dict[str, Any] | None = None,
    ) -> ExternalAgentBudget:
        """
        Record actual usage after execution.

        Updates all budget counters:
        - monthly_spent_usd
        - daily_spent_usd
        - monthly_execution_count
        - daily_execution_count

        Args:
            budget: Budget to update
            actual_cost: Actual execution cost (USD)
            execution_success: Whether execution succeeded
            metadata: Optional execution metadata

        Returns:
            Updated budget object

        Raises:
            ValueError: If actual_cost is negative

        Examples:
            >>> budget = ExternalAgentBudget(
            ...     external_agent_id="test",
            ...     monthly_budget_usd=100.0,
            ...     monthly_spent_usd=50.0
            ... )
            >>> updated = await enforcer.record_usage(budget, actual_cost=10.0, execution_success=True)
            >>> updated.monthly_spent_usd
            60.0
            >>> updated.monthly_execution_count
            1
        """
        if actual_cost < 0:
            raise ValueError(f"Actual cost cannot be negative: {actual_cost}")

        # Update budget counters
        budget.monthly_spent_usd += actual_cost
        budget.daily_spent_usd += actual_cost
        budget.monthly_execution_count += 1
        budget.daily_execution_count += 1

        # Add metadata
        if metadata:
            budget.metadata.update(metadata)

        # Log usage
        logger.info(
            f"Usage recorded for {budget.external_agent_id}: "
            f"cost=${actual_cost:.4f}, "
            f"monthly_total=${budget.monthly_spent_usd:.2f}/{budget.monthly_budget_usd:.2f}, "
            f"executions={budget.monthly_execution_count}/{budget.monthly_execution_limit}, "
            f"success={execution_success}"
        )

        # Persist to database if configured
        if self.db:
            await self._persist_budget(budget)

        return budget

    async def estimate_execution_cost(
        self,
        platform_type: str,
        agent_name: str,
        complexity: str = "standard",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> float:
        """
        Estimate cost for external agent execution.

        Delegates to ExternalAgentCostEstimator.

        Args:
            platform_type: Platform type (copilot_studio, custom_rest_api, etc.)
            agent_name: Agent name
            complexity: Complexity level (simple, standard, complex)
            input_tokens: Optional input token count
            output_tokens: Optional output token count

        Returns:
            Estimated cost in USD

        Examples:
            >>> cost = await enforcer.estimate_execution_cost(
            ...     "copilot_studio",
            ...     "hr_assistant",
            ...     complexity="standard"
            ... )
            >>> cost
            0.06
        """
        return self.cost_estimator.estimate_cost(
            platform_type=platform_type,
            agent_name=agent_name,
            complexity=complexity,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def _trigger_degradation_alert(
        self, budget: ExternalAgentBudget, usage_percentage: float
    ) -> None:
        """
        Trigger degradation alert when threshold exceeded.

        Args:
            budget: Budget configuration
            usage_percentage: Current usage percentage
        """
        alert_data = {
            "external_agent_id": budget.external_agent_id,
            "usage_percentage": usage_percentage,
            "degradation_threshold": budget.degradation_threshold,
            "remaining_budget_usd": budget.monthly_budget_usd
            - budget.monthly_spent_usd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.warning(f"Degradation alert: {alert_data}")

        # TODO: Integrate with webhook service for notifications
        # await webhook_service.trigger("budget_degradation", alert_data)

    async def _persist_budget(self, budget: ExternalAgentBudget) -> None:
        """
        Persist budget state to database.

        Args:
            budget: Budget to persist
        """
        if not self.db:
            return

        # Create workflow to update budget
        workflow = WorkflowBuilder()

        # Use DataFlow UpdateNode (assuming schema exists)
        # Note: Actual implementation depends on DataFlow schema registration
        workflow.add_node(
            "UpdateExternalAgentBudgetNode",
            "update_budget",
            {
                "external_agent_id": budget.external_agent_id,
                "monthly_spent_usd": budget.monthly_spent_usd,
                "daily_spent_usd": budget.daily_spent_usd,
                "monthly_execution_count": budget.monthly_execution_count,
                "daily_execution_count": budget.daily_execution_count,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
            logger.debug(
                f"Budget persisted for {budget.external_agent_id}: "
                f"monthly=${budget.monthly_spent_usd:.2f}"
            )
        except Exception as e:
            logger.error(f"Failed to persist budget: {e}")
            # Don't fail the operation if persistence fails


# Export all public types
__all__ = [
    "ExternalAgentBudgetEnforcer",
    "ExternalAgentBudget",
    "BudgetCheckResult",
]
