"""
Budget interrupt handler.

Automatically triggers interrupt when cost budget is exceeded.
"""

import logging

from ..manager import InterruptManager
from ..types import InterruptMode, InterruptSource

logger = logging.getLogger(__name__)


class BudgetInterruptHandler:
    """
    Automatically interrupt when budget exceeded.

    Tracks cumulative cost and triggers GRACEFUL interrupt at budget limit.
    """

    def __init__(
        self,
        interrupt_manager: InterruptManager,
        budget_usd: float,
        warning_threshold: float = 0.8,
    ):
        """
        Initialize budget handler.

        Args:
            interrupt_manager: InterruptManager to trigger interrupts
            budget_usd: Maximum cost budget in USD
            warning_threshold: Fraction of budget at which to warn (0.8 = 80%)
        """
        self.interrupt_manager = interrupt_manager
        self.budget_usd = budget_usd
        self.warning_threshold = warning_threshold
        self._current_cost_usd = 0.0
        self._warned = False

    def track_cost(self, cost_usd: float) -> None:
        """
        Track cost from operation.

        Call this after each operation that incurs cost (LLM call, tool use).

        Args:
            cost_usd: Cost of operation in USD
        """
        self._current_cost_usd += cost_usd

        logger.debug(
            f"Cost tracked: ${cost_usd:.4f} "
            f"(total: ${self._current_cost_usd:.4f} / ${self.budget_usd:.4f})"
        )

        # Check warning threshold
        if not self._warned and self._current_cost_usd >= (
            self.budget_usd * self.warning_threshold
        ):
            remaining = self.budget_usd - self._current_cost_usd
            logger.warning(
                f"Budget warning: ${remaining:.4f} remaining "
                f"(${self.budget_usd:.4f} total)"
            )
            self._warned = True

        # Check budget exceeded
        if self._current_cost_usd >= self.budget_usd:
            if not self.interrupt_manager.is_interrupted():
                self.interrupt_manager.request_interrupt(
                    mode=InterruptMode.GRACEFUL,
                    source=InterruptSource.BUDGET,
                    message=f"Budget exceeded (${self._current_cost_usd:.4f} / ${self.budget_usd:.4f})",
                    metadata={
                        "budget_usd": self.budget_usd,
                        "spent_usd": self._current_cost_usd,
                        "overage_usd": self._current_cost_usd - self.budget_usd,
                    },
                )

    def get_current_cost(self) -> float:
        """
        Get current cost.

        Returns:
            Current cost in USD
        """
        return self._current_cost_usd

    def get_remaining_budget(self) -> float:
        """
        Get remaining budget.

        Returns:
            Remaining budget in USD (may be negative if exceeded)
        """
        return self.budget_usd - self._current_cost_usd

    def get_budget_usage_percent(self) -> float:
        """
        Get budget usage percentage.

        Returns:
            Percentage of budget used (0-100+)
        """
        return (self._current_cost_usd / self.budget_usd) * 100.0

    def reset(self) -> None:
        """
        Reset cost tracking.

        Use when starting new execution or after checkpoint.
        """
        self._current_cost_usd = 0.0
        self._warned = False
        logger.debug("Budget handler reset")


# Export all public types
__all__ = [
    "BudgetInterruptHandler",
]
