"""
Test suite for SatisfactionConvergence strategy.

Tests convergence based on confidence/satisfaction threshold.

Author: Kaizen Framework Team
Created: 2025-10-02
"""


def test_satisfaction_convergence_import():
    """Test that SatisfactionConvergence can be imported."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    assert SatisfactionConvergence is not None


def test_satisfaction_convergence_instantiate_default():
    """Test that SatisfactionConvergence can be instantiated with default threshold."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence()
    assert strategy is not None
    assert strategy.threshold == 0.9  # Default


def test_satisfaction_convergence_instantiate_custom_threshold():
    """Test that SatisfactionConvergence accepts custom threshold."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.75)
    assert strategy.threshold == 0.75


def test_satisfaction_convergence_is_convergence_strategy():
    """Test that SatisfactionConvergence is a ConvergenceStrategy."""
    from kaizen.strategies.convergence import (
        ConvergenceStrategy,
        SatisfactionConvergence,
    )

    strategy = SatisfactionConvergence()
    assert isinstance(strategy, ConvergenceStrategy)


def test_satisfaction_convergence_stops_when_threshold_met():
    """Test that convergence stops when confidence >= threshold."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.9)
    should_stop = strategy.should_stop({"confidence": 0.95}, {})

    assert should_stop is True


def test_satisfaction_convergence_continues_when_below_threshold():
    """Test that convergence continues when confidence < threshold."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.9)
    should_stop = strategy.should_stop({"confidence": 0.85}, {})

    assert should_stop is False


def test_satisfaction_convergence_exact_threshold():
    """Test exact threshold match."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.8)
    should_stop = strategy.should_stop({"confidence": 0.8}, {})

    assert should_stop is True  # >= includes equality


def test_satisfaction_convergence_tracks_last_confidence():
    """Test that strategy tracks last confidence value."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.9)

    # First check
    strategy.should_stop({"confidence": 0.7}, {})
    assert strategy.last_confidence == 0.7

    # Second check
    strategy.should_stop({"confidence": 0.95}, {})
    assert strategy.last_confidence == 0.95


def test_satisfaction_convergence_missing_confidence_key():
    """Test behavior when confidence key is missing (should default to 0.0)."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.5)
    should_stop = strategy.should_stop({"answer": "42"}, {})

    # Missing confidence defaults to 0.0, which is < 0.5
    assert should_stop is False
    assert strategy.last_confidence == 0.0


def test_satisfaction_convergence_get_reason_with_confidence():
    """Test that get_reason returns informative message."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.9)
    strategy.should_stop({"confidence": 0.95}, {})

    reason = strategy.get_reason()
    assert "0.95" in reason
    assert "0.9" in reason


def test_satisfaction_convergence_get_reason_without_check():
    """Test that get_reason works before any checks."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence()
    reason = strategy.get_reason()

    assert isinstance(reason, str)
    assert len(reason) > 0


def test_satisfaction_convergence_different_thresholds():
    """Test various threshold values."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    # Low threshold (0.5)
    strategy_low = SatisfactionConvergence(confidence_threshold=0.5)
    assert strategy_low.should_stop({"confidence": 0.6}, {}) is True
    assert strategy_low.should_stop({"confidence": 0.4}, {}) is False

    # High threshold (1.0)
    strategy_high = SatisfactionConvergence(confidence_threshold=1.0)
    assert strategy_high.should_stop({"confidence": 1.0}, {}) is True
    assert strategy_high.should_stop({"confidence": 0.99}, {}) is False

    # Mid threshold (0.75)
    strategy_mid = SatisfactionConvergence(confidence_threshold=0.75)
    assert strategy_mid.should_stop({"confidence": 0.8}, {}) is True
    assert strategy_mid.should_stop({"confidence": 0.7}, {}) is False


def test_satisfaction_convergence_zero_confidence():
    """Test edge case: zero confidence."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.0)
    should_stop = strategy.should_stop({"confidence": 0.0}, {})

    # 0.0 >= 0.0 is True
    assert should_stop is True


def test_satisfaction_convergence_progressive_improvement():
    """Test scenario: confidence progressively improves."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.9)

    # Cycle 1: Low confidence
    assert strategy.should_stop({"confidence": 0.5}, {}) is False

    # Cycle 2: Medium confidence
    assert strategy.should_stop({"confidence": 0.7}, {}) is False

    # Cycle 3: High but below threshold
    assert strategy.should_stop({"confidence": 0.85}, {}) is False

    # Cycle 4: Meets threshold
    assert strategy.should_stop({"confidence": 0.92}, {}) is True


def test_satisfaction_convergence_confidence_from_reflection():
    """Test that confidence could potentially come from reflection (future enhancement)."""
    from kaizen.strategies.convergence import SatisfactionConvergence

    strategy = SatisfactionConvergence(confidence_threshold=0.8)

    # Currently only checks result, not reflection
    # But architecture supports it for future
    should_stop = strategy.should_stop(
        {"confidence": 0.9}, {"alternative_confidence": 0.5}
    )

    assert should_stop is True  # Uses result confidence
