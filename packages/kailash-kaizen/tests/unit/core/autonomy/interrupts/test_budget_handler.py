"""
Unit tests for BudgetInterruptHandler.

Tests cost tracking, budget monitoring, and interrupt triggering.
"""

from kaizen.core.autonomy.interrupts.handlers.budget import BudgetInterruptHandler
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.types import InterruptMode, InterruptSource


class TestBudgetHandlerInit:
    """Test BudgetInterruptHandler initialization"""

    def test_init_default(self):
        """Test default initialization"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        assert handler.interrupt_manager is manager
        assert handler.budget_usd == 10.0
        assert handler.warning_threshold == 0.8
        assert handler._current_cost_usd == 0.0
        assert handler._warned is False

    def test_init_custom_warning_threshold(self):
        """Test initialization with custom warning threshold"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=5.0, warning_threshold=0.9)

        assert handler.budget_usd == 5.0
        assert handler.warning_threshold == 0.9


class TestCostTracking:
    """Test cost tracking functionality"""

    def test_track_cost_accumulates(self):
        """Test track_cost() accumulates costs"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        handler.track_cost(1.5)
        assert handler.get_current_cost() == 1.5

        handler.track_cost(2.0)
        assert handler.get_current_cost() == 3.5

        handler.track_cost(0.5)
        assert handler.get_current_cost() == 4.0

    def test_track_cost_triggers_warning(self):
        """Test tracking cost triggers warning at threshold"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(
            manager, budget_usd=10.0, warning_threshold=0.8
        )

        # Track below threshold
        handler.track_cost(7.0)
        assert not handler._warned

        # Track to threshold (8.0 = 0.8 * 10.0)
        handler.track_cost(1.5)  # Total = 8.5
        assert handler._warned

    def test_track_cost_triggers_interrupt(self):
        """Test tracking cost triggers interrupt when budget exceeded"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        # Track to budget limit
        handler.track_cost(10.5)

        # Should trigger interrupt
        assert manager.is_interrupted()

        # Verify interrupt details
        reason = manager._interrupt_reason
        assert reason is not None
        assert reason.mode == InterruptMode.GRACEFUL
        assert reason.source == InterruptSource.BUDGET
        assert "budget" in reason.message.lower()
        assert "exceeded" in reason.message.lower()
        assert reason.metadata["budget_usd"] == 10.0
        assert reason.metadata["spent_usd"] == 10.5
        assert reason.metadata["overage_usd"] == 0.5

    def test_track_cost_no_duplicate_interrupts(self):
        """Test tracking cost doesn't trigger duplicate interrupts"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        # Exceed budget
        handler.track_cost(11.0)

        assert manager.is_interrupted()
        original_reason = manager._interrupt_reason

        # Track more cost
        handler.track_cost(5.0)

        # Should keep original interrupt (idempotent)
        assert manager._interrupt_reason == original_reason


class TestBudgetQueries:
    """Test budget query methods"""

    def test_get_current_cost(self):
        """Test get_current_cost() returns tracked cost"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        assert handler.get_current_cost() == 0.0

        handler.track_cost(3.5)
        assert handler.get_current_cost() == 3.5

    def test_get_remaining_budget(self):
        """Test get_remaining_budget() calculation"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        assert handler.get_remaining_budget() == 10.0

        handler.track_cost(3.0)
        assert handler.get_remaining_budget() == 7.0

        handler.track_cost(5.0)
        assert handler.get_remaining_budget() == 2.0

    def test_get_remaining_budget_negative_when_exceeded(self):
        """Test remaining budget can be negative when exceeded"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        handler.track_cost(12.0)

        assert handler.get_remaining_budget() == -2.0

    def test_get_budget_usage_percent(self):
        """Test get_budget_usage_percent() calculation"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        assert handler.get_budget_usage_percent() == 0.0

        handler.track_cost(5.0)
        assert handler.get_budget_usage_percent() == 50.0

        handler.track_cost(3.0)
        assert handler.get_budget_usage_percent() == 80.0

        handler.track_cost(4.0)  # Total = 12.0
        assert handler.get_budget_usage_percent() == 120.0


class TestReset:
    """Test reset functionality"""

    def test_reset_clears_cost(self):
        """Test reset() clears cost tracking"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(manager, budget_usd=10.0)

        handler.track_cost(5.0)
        assert handler.get_current_cost() == 5.0
        assert handler._warned is False

        handler.track_cost(4.0)  # Triggers warning at 9.0 (90%)
        assert handler._warned is True

        # Reset
        handler.reset()

        # Should clear everything
        assert handler.get_current_cost() == 0.0
        assert handler._warned is False
        assert handler.get_remaining_budget() == 10.0
        assert handler.get_budget_usage_percent() == 0.0

    def test_reset_preserves_budget_config(self):
        """Test reset() preserves budget configuration"""
        manager = InterruptManager()
        handler = BudgetInterruptHandler(
            manager, budget_usd=10.0, warning_threshold=0.7
        )

        handler.track_cost(8.0)
        handler.reset()

        # Budget config should remain unchanged
        assert handler.budget_usd == 10.0
        assert handler.warning_threshold == 0.7
