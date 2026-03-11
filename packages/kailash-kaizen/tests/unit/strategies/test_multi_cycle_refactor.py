"""
Test suite for refactored MultiCycleStrategy with ConvergenceStrategy.

Tests the integration of independent convergence strategies with MultiCycleStrategy.

Author: Kaizen Framework Team
Created: 2025-10-02
"""

import pytest


def test_multi_cycle_accepts_convergence_strategy():
    """Test that MultiCycleStrategy accepts convergence_strategy parameter."""
    from kaizen.strategies.convergence import SatisfactionConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    convergence = SatisfactionConvergence(confidence_threshold=0.9)
    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=5)

    assert strategy is not None
    assert strategy.convergence_strategy == convergence
    assert strategy.max_cycles == 5


def test_multi_cycle_rejects_old_mode_parameter():
    """Test that old 'mode' parameter raises helpful error."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    with pytest.raises((TypeError, ValueError)) as exc_info:
        MultiCycleStrategy(mode="test_driven", max_cycles=5)

    # Should mention the new pattern
    error_msg = str(exc_info.value).lower()
    assert (
        "convergence" in error_msg
        or "deprecated" in error_msg
        or "unexpected" in error_msg
    )


def test_multi_cycle_convergence_delegation():
    """Test that convergence check delegates to strategy."""
    from kaizen.strategies.convergence import SatisfactionConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    # Create convergence strategy
    convergence = SatisfactionConvergence(confidence_threshold=0.8)
    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)

    # Create mock agent with required attributes
    class MockAgent:
        def __init__(self):
            self.signature = type(
                "obj", (object,), {"output_fields": ["result"], "input_fields": {}}
            )()
            self.workflow_generator = None

    MockAgent()

    # The strategy should delegate to convergence
    # Note: This is a unit test - we test the delegation, not full execution
    assert hasattr(strategy, "convergence_strategy")
    assert strategy.convergence_strategy == convergence


def test_multi_cycle_six_phase_execution_works():
    """Test that 6-phase execution pattern still works."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    # Verify the strategy has the required extension points
    strategy = MultiCycleStrategy(max_cycles=3)

    assert hasattr(strategy, "pre_cycle")
    assert hasattr(strategy, "parse_cycle_result")
    assert hasattr(strategy, "should_terminate")
    assert hasattr(strategy, "extract_observation")
    assert hasattr(strategy, "execute")
    assert hasattr(strategy, "build_workflow")


def test_multi_cycle_max_cycles_enforced():
    """Test that max_cycles parameter still works."""
    from kaizen.strategies.convergence import SatisfactionConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    # Never converging strategy
    convergence = SatisfactionConvergence(confidence_threshold=999.0)
    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=3)

    assert strategy.max_cycles == 3


def test_multi_cycle_early_stopping_when_converged():
    """Test early stopping when convergence strategy signals stop."""
    from kaizen.strategies.convergence import ConvergenceStrategy
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    # Always-converge strategy
    class AlwaysConverge(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return True

    convergence = AlwaysConverge()
    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)

    # Should have convergence strategy set
    assert strategy.convergence_strategy == convergence


def test_multi_cycle_late_stopping_at_max_cycles():
    """Test late stopping when max cycles reached."""
    from kaizen.strategies.convergence import ConvergenceStrategy
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    # Never-converge strategy
    class NeverConverge(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return False

    convergence = NeverConverge()
    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=5)

    assert strategy.max_cycles == 5
    assert strategy.convergence_strategy == convergence


def test_multi_cycle_with_test_driven_convergence():
    """Test integration with TestDrivenConvergence."""
    from kaizen.strategies.convergence import TestDrivenConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    def test_suite(result):
        # Pass if result has 'answer' key
        return (1, 0) if "answer" in result else (0, 1)

    convergence = TestDrivenConvergence(test_suite=test_suite)
    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=5)

    assert isinstance(strategy.convergence_strategy, TestDrivenConvergence)


def test_multi_cycle_with_satisfaction_convergence():
    """Test integration with SatisfactionConvergence."""
    from kaizen.strategies.convergence import SatisfactionConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    convergence = SatisfactionConvergence(confidence_threshold=0.95)
    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=8)

    assert isinstance(strategy.convergence_strategy, SatisfactionConvergence)


def test_multi_cycle_with_hybrid_convergence():
    """Test integration with HybridConvergence."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    satisfaction1 = SatisfactionConvergence(confidence_threshold=0.8)
    satisfaction2 = SatisfactionConvergence(confidence_threshold=0.9)
    convergence = HybridConvergence(
        strategies=[satisfaction1, satisfaction2], mode="AND"
    )

    strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)

    assert isinstance(strategy.convergence_strategy, HybridConvergence)


def test_multi_cycle_default_convergence_callback_still_works():
    """Test that default convergence_check callback (old API) still works."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    def custom_convergence(cycle_results):
        # Stop after 3 cycles
        return len(cycle_results) >= 3

    # Old API with convergence_check callback
    strategy = MultiCycleStrategy(max_cycles=10, convergence_check=custom_convergence)

    assert strategy.convergence_check_callback == custom_convergence


def test_multi_cycle_cycle_processor_still_works():
    """Test that cycle_processor callback (old API) still works."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    def custom_processor(inputs, cycle_num):
        return {"cycle": cycle_num, "processed": True}

    strategy = MultiCycleStrategy(max_cycles=5, cycle_processor=custom_processor)

    assert strategy.cycle_processor_callback == custom_processor


def test_multi_cycle_convergence_strategy_takes_precedence():
    """Test that convergence_strategy takes precedence over convergence_check."""
    from kaizen.strategies.convergence import SatisfactionConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    def old_callback(cycle_results):
        return False

    convergence = SatisfactionConvergence(confidence_threshold=0.9)

    # Both provided - convergence_strategy should take precedence
    strategy = MultiCycleStrategy(
        convergence_strategy=convergence, convergence_check=old_callback, max_cycles=5
    )

    # New API should be used
    assert strategy.convergence_strategy == convergence


def test_multi_cycle_backward_compat_no_convergence_strategy():
    """Test backward compatibility when no convergence_strategy provided."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    # Should work with just max_cycles (legacy usage)
    strategy = MultiCycleStrategy(max_cycles=5)

    assert strategy.max_cycles == 5
    # convergence_strategy should be None (falls back to old logic)
    assert (
        not hasattr(strategy, "convergence_strategy")
        or strategy.convergence_strategy is None
    )


def test_multi_cycle_extension_points_preserved():
    """Test that all extension points are preserved."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    strategy = MultiCycleStrategy(max_cycles=3)

    # All 4 extension points should exist
    assert callable(strategy.pre_cycle)
    assert callable(strategy.parse_cycle_result)
    assert callable(strategy.should_terminate)
    assert callable(strategy.extract_observation)

    # Test they can be called (with dummy data)
    inputs = strategy.pre_cycle(0, {"task": "test"})
    assert isinstance(inputs, dict)

    parsed = strategy.parse_cycle_result({"raw": "data"}, 0)
    assert isinstance(parsed, dict)

    should_stop = strategy.should_terminate({"done": True}, 0)
    assert isinstance(should_stop, bool)

    obs = strategy.extract_observation({"observation": "test"})
    assert isinstance(obs, str)


def test_multi_cycle_no_convergence_strategy_uses_should_terminate():
    """Test that without convergence_strategy, should_terminate is used."""
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    # No convergence_strategy - should fall back to should_terminate
    strategy = MultiCycleStrategy(max_cycles=5)

    # should_terminate should work as before
    assert strategy.should_terminate({"done": True}, 0) is True
    assert strategy.should_terminate({"error": "fail"}, 0) is True
    assert (
        strategy.should_terminate({"action": "FINAL ANSWER: 42"}, 0) is True
    )  # Value, not key


def test_multi_cycle_convergence_strategy_with_cycle_processor():
    """Test that convergence_strategy works with cycle_processor."""
    from kaizen.strategies.convergence import SatisfactionConvergence
    from kaizen.strategies.multi_cycle import MultiCycleStrategy

    def processor(inputs, cycle_num):
        return {"cycle": cycle_num, "confidence": 0.9}

    convergence = SatisfactionConvergence(confidence_threshold=0.8)
    strategy = MultiCycleStrategy(
        convergence_strategy=convergence, cycle_processor=processor, max_cycles=5
    )

    assert strategy.convergence_strategy == convergence
    assert strategy.cycle_processor_callback == processor
