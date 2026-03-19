# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Spend tracking for EATP financial constraint enforcement.

Tracks cumulative spend per agent against financial constraint limits.
Supports periodic budget resets and threshold-based warnings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BudgetPeriod(Enum):
    """Budget reset period."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    NONE = "none"  # No automatic reset


class BudgetStatusLevel(Enum):
    """Budget status level."""

    OK = "ok"
    WARNING = "warning"  # Approaching limit
    EXCEEDED = "exceeded"  # Over limit


@dataclass
class SpendEvent:
    """Record of a spend event."""

    agent_id: str
    amount: float
    currency: str
    action: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetStatus:
    """Current budget status for an agent."""

    agent_id: str
    level: BudgetStatusLevel
    spent: float
    limit: float
    remaining: float
    currency: str
    utilization_pct: float
    period: BudgetPeriod
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    warning_threshold_pct: float = 80.0


@dataclass
class AgentBudget:
    """Budget configuration and state for an agent."""

    agent_id: str
    limit: float
    currency: str = "USD"
    period: BudgetPeriod = BudgetPeriod.DAILY
    warning_threshold_pct: float = 80.0
    spent: float = 0.0
    period_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    events: List[SpendEvent] = field(default_factory=list)


class SpendTracker:
    """Tracks cumulative spend per agent against financial limits.

    Provides budget management with automatic period resets,
    threshold warnings, and detailed spend history.

    Example:
        >>> tracker = SpendTracker()
        >>> tracker.set_budget("agent-001", limit=1000.0, currency="USD", period=BudgetPeriod.DAILY)
        >>> tracker.record_spend("agent-001", amount=250.0, currency="USD", action="purchase")
        >>> status = tracker.check_budget("agent-001")
        >>> print(f"Spent: ${status.spent}, Remaining: ${status.remaining}")
    """

    def __init__(self):
        """Initialize spend tracker."""
        self._budgets: Dict[str, AgentBudget] = {}

    def set_budget(
        self,
        agent_id: str,
        limit: float,
        currency: str = "USD",
        period: BudgetPeriod = BudgetPeriod.DAILY,
        warning_threshold_pct: float = 80.0,
    ) -> None:
        """Set budget for an agent.

        Args:
            agent_id: Agent to set budget for
            limit: Maximum spend amount per period
            currency: Currency code (e.g., "USD")
            period: Budget reset period
            warning_threshold_pct: Percentage at which to warn (0-100)
        """
        self._budgets[agent_id] = AgentBudget(
            agent_id=agent_id,
            limit=limit,
            currency=currency,
            period=period,
            warning_threshold_pct=warning_threshold_pct,
        )

    def record_spend(
        self,
        agent_id: str,
        amount: float,
        currency: str = "USD",
        action: str = "spend",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BudgetStatus:
        """Record a spend event for an agent.

        Args:
            agent_id: Agent making the spend
            amount: Amount spent
            currency: Currency of the spend
            action: Action that triggered the spend
            metadata: Additional context

        Returns:
            Updated BudgetStatus after recording

        Raises:
            ValueError: If agent has no budget configured
        """
        budget = self._budgets.get(agent_id)
        if budget is None:
            raise ValueError(f"No budget configured for agent '{agent_id}'. Call set_budget() first.")

        # Check for period reset
        self._check_period_reset(budget)

        event = SpendEvent(
            agent_id=agent_id,
            amount=amount,
            currency=currency,
            action=action,
            metadata=metadata or {},
        )
        budget.events.append(event)
        budget.spent += amount

        logger.info(
            f"[SPEND] agent={agent_id} amount={amount} {currency} "
            f"action={action} total_spent={budget.spent}/{budget.limit}"
        )

        return self.check_budget(agent_id)

    def check_budget(self, agent_id: str) -> BudgetStatus:
        """Check current budget status for an agent.

        Args:
            agent_id: Agent to check

        Returns:
            Current BudgetStatus

        Raises:
            ValueError: If agent has no budget configured
        """
        budget = self._budgets.get(agent_id)
        if budget is None:
            raise ValueError(f"No budget configured for agent '{agent_id}'")

        # Check for period reset
        self._check_period_reset(budget)

        remaining = max(0.0, budget.limit - budget.spent)
        utilization = (budget.spent / budget.limit * 100) if budget.limit > 0 else 0.0

        if budget.spent >= budget.limit:
            level = BudgetStatusLevel.EXCEEDED
        elif utilization >= budget.warning_threshold_pct:
            level = BudgetStatusLevel.WARNING
        else:
            level = BudgetStatusLevel.OK

        period_end = self._compute_period_end(budget)

        return BudgetStatus(
            agent_id=agent_id,
            level=level,
            spent=budget.spent,
            limit=budget.limit,
            remaining=remaining,
            currency=budget.currency,
            utilization_pct=utilization,
            period=budget.period,
            period_start=budget.period_start,
            period_end=period_end,
            warning_threshold_pct=budget.warning_threshold_pct,
        )

    def reset_budget(self, agent_id: str, period: Optional[BudgetPeriod] = None) -> None:
        """Reset an agent's budget.

        Args:
            agent_id: Agent to reset
            period: Optionally change the period
        """
        budget = self._budgets.get(agent_id)
        if budget is None:
            raise ValueError(f"No budget configured for agent '{agent_id}'")

        budget.spent = 0.0
        budget.period_start = datetime.now(timezone.utc)
        if period is not None:
            budget.period = period

        logger.info(f"[SPEND] Budget reset for agent={agent_id}")

    def get_spend_history(
        self,
        agent_id: str,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SpendEvent]:
        """Get spend history for an agent.

        Args:
            agent_id: Agent to query
            since: Only return events after this time
            limit: Maximum events to return

        Returns:
            List of SpendEvents, most recent first
        """
        budget = self._budgets.get(agent_id)
        if budget is None:
            return []

        events = budget.events
        if since:
            events = [e for e in events if e.timestamp >= since]

        return sorted(events, key=lambda e: e.timestamp, reverse=True)[:limit]

    def would_exceed(self, agent_id: str, amount: float) -> bool:
        """Check if a spend would exceed the budget.

        Args:
            agent_id: Agent to check
            amount: Proposed spend amount

        Returns:
            True if the spend would exceed the budget
        """
        budget = self._budgets.get(agent_id)
        if budget is None:
            return False

        self._check_period_reset(budget)
        return (budget.spent + amount) > budget.limit

    def _check_period_reset(self, budget: AgentBudget) -> None:
        """Check if budget period has elapsed and reset if so."""
        if budget.period == BudgetPeriod.NONE:
            return

        now = datetime.now(timezone.utc)
        period_end = self._compute_period_end(budget)

        if period_end and now >= period_end:
            logger.info(
                f"[SPEND] Auto-resetting budget for agent={budget.agent_id} (period={budget.period.value} elapsed)"
            )
            budget.spent = 0.0
            budget.period_start = now
            # Keep events for history but reset cumulative

    def _compute_period_end(self, budget: AgentBudget) -> Optional[datetime]:
        """Compute when the current budget period ends."""
        start = budget.period_start

        if budget.period == BudgetPeriod.DAILY:
            return start + timedelta(days=1)
        elif budget.period == BudgetPeriod.WEEKLY:
            return start + timedelta(weeks=1)
        elif budget.period == BudgetPeriod.MONTHLY:
            return start + timedelta(days=30)
        elif budget.period == BudgetPeriod.YEARLY:
            return start + timedelta(days=365)

        return None


__all__ = [
    "SpendTracker",
    "SpendEvent",
    "BudgetStatus",
    "BudgetStatusLevel",
    "BudgetPeriod",
    "AgentBudget",
]
