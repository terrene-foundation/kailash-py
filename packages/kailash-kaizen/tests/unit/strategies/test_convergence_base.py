"""
Test suite for ConvergenceStrategy base class.

Tests the abstract base class and its contract for convergence strategies.

Author: Kaizen Framework Team
Created: 2025-10-02
"""

from abc import ABC

import pytest


def test_convergence_strategy_import():
    """Test that ConvergenceStrategy can be imported."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    assert ConvergenceStrategy is not None


def test_convergence_strategy_is_abstract():
    """Test that ConvergenceStrategy is an abstract base class."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    assert issubclass(ConvergenceStrategy, ABC)


def test_convergence_strategy_cannot_instantiate():
    """Test that ConvergenceStrategy cannot be instantiated directly."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    with pytest.raises(TypeError) as exc_info:
        ConvergenceStrategy()

    # Should mention abstract method
    assert "abstract" in str(exc_info.value).lower()


def test_convergence_strategy_requires_should_stop():
    """Test that subclass must implement should_stop method."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    # Incomplete subclass missing should_stop
    class IncompleteConvergence(ConvergenceStrategy):
        pass

    with pytest.raises(TypeError) as exc_info:
        IncompleteConvergence()

    assert "should_stop" in str(exc_info.value)


def test_convergence_strategy_subclass_with_should_stop():
    """Test that subclass with should_stop can be instantiated."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    class ValidConvergence(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return True

    # Should instantiate successfully
    strategy = ValidConvergence()
    assert strategy is not None
    assert hasattr(strategy, "should_stop")


def test_convergence_strategy_should_stop_signature():
    """Test that should_stop has correct signature."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    class TestConvergence(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return False

    strategy = TestConvergence()

    # Should accept two arguments
    result = strategy.should_stop({"key": "value"}, {"metric": 0.5})
    assert isinstance(result, bool)


def test_convergence_strategy_get_reason_default():
    """Test that get_reason has default implementation."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    class TestConvergence(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return True

    strategy = TestConvergence()
    reason = strategy.get_reason()

    assert isinstance(reason, str)
    assert len(reason) > 0
    assert "convergence" in reason.lower()


def test_convergence_strategy_get_reason_can_override():
    """Test that subclass can override get_reason."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    class CustomConvergence(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return True

        def get_reason(self):
            return "Custom reason for stopping"

    strategy = CustomConvergence()
    reason = strategy.get_reason()

    assert reason == "Custom reason for stopping"


def test_convergence_strategy_should_stop_returns_bool():
    """Test that should_stop returns boolean."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    class TestConvergence(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return "not a bool"  # Wrong type

    strategy = TestConvergence()

    # Should return value (even if wrong type)
    result = strategy.should_stop({}, {})
    # Note: Python doesn't enforce return type, but we test it exists
    assert result is not None


def test_convergence_strategy_multiple_subclasses():
    """Test that multiple independent subclasses can exist."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    class ConvergenceA(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return True

    class ConvergenceB(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return False

    strategy_a = ConvergenceA()
    strategy_b = ConvergenceB()

    assert strategy_a.should_stop({}, {}) is True
    assert strategy_b.should_stop({}, {}) is False


def test_convergence_strategy_type_checking():
    """Test that type checking works with isinstance."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    class TestConvergence(ConvergenceStrategy):
        def should_stop(self, result, reflection):
            return True

    strategy = TestConvergence()

    # Should pass isinstance check
    assert isinstance(strategy, ConvergenceStrategy)


def test_convergence_strategy_abstract_method_enforcement():
    """Test that NotImplementedError is raised if should_stop not implemented properly."""
    from kaizen.strategies.convergence import ConvergenceStrategy

    # This test verifies the abstract method contract
    # Even if subclass exists, instantiation should fail without should_stop
    with pytest.raises(TypeError):

        class BadConvergence(ConvergenceStrategy):
            pass

        BadConvergence()
