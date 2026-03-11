"""
Test suite for HybridConvergence strategy.

Tests convergence by composing multiple strategies with AND/OR logic.

Author: Kaizen Framework Team
Created: 2025-10-02
"""


def test_hybrid_convergence_import():
    """Test that HybridConvergence can be imported."""
    from kaizen.strategies.convergence import HybridConvergence

    assert HybridConvergence is not None


def test_hybrid_convergence_instantiate():
    """Test that HybridConvergence can be instantiated with strategies list."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2])
    assert hybrid is not None
    assert len(hybrid.strategies) == 2


def test_hybrid_convergence_is_convergence_strategy():
    """Test that HybridConvergence is a ConvergenceStrategy."""
    from kaizen.strategies.convergence import ConvergenceStrategy, HybridConvergence

    hybrid = HybridConvergence(strategies=[])
    assert isinstance(hybrid, ConvergenceStrategy)


def test_hybrid_convergence_and_mode_all_converge():
    """Test AND mode: all strategies must converge."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="AND")

    # Both thresholds met (0.95 >= 0.8 and 0.95 >= 0.9)
    should_stop = hybrid.should_stop({"confidence": 0.95}, {})
    assert should_stop is True


def test_hybrid_convergence_and_mode_some_converge():
    """Test AND mode: fails if only some converge."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="AND")

    # Only first threshold met (0.85 >= 0.8 but 0.85 < 0.9)
    should_stop = hybrid.should_stop({"confidence": 0.85}, {})
    assert should_stop is False


def test_hybrid_convergence_and_mode_none_converge():
    """Test AND mode: fails if none converge."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="AND")

    # No thresholds met
    should_stop = hybrid.should_stop({"confidence": 0.5}, {})
    assert should_stop is False


def test_hybrid_convergence_or_mode_all_converge():
    """Test OR mode: succeeds if all converge."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="OR")

    # Both thresholds met
    should_stop = hybrid.should_stop({"confidence": 0.95}, {})
    assert should_stop is True


def test_hybrid_convergence_or_mode_some_converge():
    """Test OR mode: succeeds if any converge."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="OR")

    # Only first threshold met
    should_stop = hybrid.should_stop({"confidence": 0.85}, {})
    assert should_stop is True


def test_hybrid_convergence_or_mode_none_converge():
    """Test OR mode: fails if none converge."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="OR")

    # No thresholds met
    should_stop = hybrid.should_stop({"confidence": 0.5}, {})
    assert should_stop is False


def test_hybrid_convergence_tracks_individual_results():
    """Test that hybrid tracks individual strategy results."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="AND")
    hybrid.should_stop({"confidence": 0.85}, {})

    assert len(hybrid.last_results) == 2
    assert hybrid.last_results[0] is True  # 0.85 >= 0.8
    assert hybrid.last_results[1] is False  # 0.85 < 0.9


def test_hybrid_convergence_get_reason_with_results():
    """Test that get_reason returns informative message."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="AND")
    hybrid.should_stop({"confidence": 0.95}, {})

    reason = hybrid.get_reason()
    assert "2/2" in reason  # All 2 converged
    assert "AND" in reason


def test_hybrid_convergence_get_reason_without_results():
    """Test that get_reason works before any checks."""
    from kaizen.strategies.convergence import HybridConvergence

    hybrid = HybridConvergence(strategies=[])
    reason = hybrid.get_reason()

    assert isinstance(reason, str)
    assert len(reason) > 0


def test_hybrid_convergence_three_strategies():
    """Test with three strategies."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.7)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy3 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2, strategy3], mode="AND")

    # All three met (0.95 >= all thresholds)
    assert hybrid.should_stop({"confidence": 0.95}, {}) is True

    # Only two met (0.85 >= 0.7, 0.85 >= 0.8, but 0.85 < 0.9)
    assert hybrid.should_stop({"confidence": 0.85}, {}) is False


def test_hybrid_convergence_five_strategies():
    """Test with five strategies."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategies = [
        SatisfactionConvergence(confidence_threshold=0.5),
        SatisfactionConvergence(confidence_threshold=0.6),
        SatisfactionConvergence(confidence_threshold=0.7),
        SatisfactionConvergence(confidence_threshold=0.8),
        SatisfactionConvergence(confidence_threshold=0.9),
    ]

    hybrid_and = HybridConvergence(strategies=strategies, mode="AND")
    hybrid_or = HybridConvergence(strategies=strategies, mode="OR")

    # AND: All must converge (0.95 >= all)
    assert hybrid_and.should_stop({"confidence": 0.95}, {}) is True

    # AND: Not all converge (0.75 doesn't meet 0.8, 0.9)
    assert hybrid_and.should_stop({"confidence": 0.75}, {}) is False

    # OR: Any can converge (0.55 >= 0.5)
    assert hybrid_or.should_stop({"confidence": 0.55}, {}) is True

    # OR: None converge
    assert hybrid_or.should_stop({"confidence": 0.3}, {}) is False


def test_hybrid_convergence_mixed_strategy_types():
    """Test mixing different convergence strategy types."""
    from kaizen.strategies.convergence import (
        HybridConvergence,
        SatisfactionConvergence,
        TestDrivenConvergence,
    )

    def simple_test_suite(result):
        # Pass if result has 'answer' key
        return (1, 0) if "answer" in result else (0, 1)

    satisfaction = SatisfactionConvergence(confidence_threshold=0.8)
    test_driven = TestDrivenConvergence(test_suite=simple_test_suite)

    hybrid = HybridConvergence(strategies=[satisfaction, test_driven], mode="AND")

    # Both conditions met
    should_stop = hybrid.should_stop({"confidence": 0.9, "answer": "42"}, {})
    assert should_stop is True

    # Only satisfaction met
    should_stop = hybrid.should_stop({"confidence": 0.9}, {})
    assert should_stop is False

    # Only test_driven met
    should_stop = hybrid.should_stop({"confidence": 0.5, "answer": "42"}, {})
    assert should_stop is False


def test_hybrid_convergence_invalid_mode_defaults_to_and():
    """Test that invalid mode defaults to AND."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    hybrid = HybridConvergence(strategies=[strategy1, strategy2], mode="INVALID")

    # Should behave like AND (both must converge)
    assert hybrid.should_stop({"confidence": 0.85}, {}) is False
    assert hybrid.should_stop({"confidence": 0.95}, {}) is True


def test_hybrid_convergence_empty_strategies():
    """Test edge case: empty strategies list."""
    from kaizen.strategies.convergence import HybridConvergence

    hybrid_and = HybridConvergence(strategies=[], mode="AND")
    hybrid_or = HybridConvergence(strategies=[], mode="OR")

    # AND: all([]) = True (vacuous truth)
    assert hybrid_and.should_stop({}, {}) is True

    # OR: any([]) = False (no elements)
    assert hybrid_or.should_stop({}, {}) is False


def test_hybrid_convergence_default_mode():
    """Test that default mode is AND."""
    from kaizen.strategies.convergence import HybridConvergence, SatisfactionConvergence

    strategy1 = SatisfactionConvergence(confidence_threshold=0.8)
    strategy2 = SatisfactionConvergence(confidence_threshold=0.9)

    # No mode specified - should default to AND
    hybrid = HybridConvergence(strategies=[strategy1, strategy2])

    # Should behave like AND
    assert hybrid.should_stop({"confidence": 0.85}, {}) is False
    assert hybrid.should_stop({"confidence": 0.95}, {}) is True
