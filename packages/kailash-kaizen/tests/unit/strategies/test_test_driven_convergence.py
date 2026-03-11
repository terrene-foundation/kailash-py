"""
Test suite for TestDrivenConvergence strategy.

Tests convergence based on test suite results (stop when all tests pass).

Author: Kaizen Framework Team
Created: 2025-10-02
"""

import pytest


def test_test_driven_convergence_import():
    """Test that TestDrivenConvergence can be imported."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    assert TestDrivenConvergence is not None


def test_test_driven_convergence_instantiate():
    """Test that TestDrivenConvergence can be instantiated with test suite."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    def dummy_test_suite(result):
        return (5, 0)  # 5 passed, 0 failed

    strategy = TestDrivenConvergence(test_suite=dummy_test_suite)
    assert strategy is not None
    assert strategy.test_suite == dummy_test_suite


def test_test_driven_convergence_is_convergence_strategy():
    """Test that TestDrivenConvergence is a ConvergenceStrategy."""
    from kaizen.strategies.convergence import ConvergenceStrategy, TestDrivenConvergence

    def dummy_test_suite(result):
        return (0, 0)

    strategy = TestDrivenConvergence(test_suite=dummy_test_suite)
    assert isinstance(strategy, ConvergenceStrategy)


def test_test_driven_convergence_stops_when_all_tests_pass():
    """Test that convergence stops when all tests pass."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    def passing_test_suite(result):
        return (10, 0)  # 10 passed, 0 failed

    strategy = TestDrivenConvergence(test_suite=passing_test_suite)
    should_stop = strategy.should_stop({"answer": "42"}, {})

    assert should_stop is True


def test_test_driven_convergence_continues_when_tests_fail():
    """Test that convergence continues when tests fail."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    def failing_test_suite(result):
        return (5, 3)  # 5 passed, 3 failed

    strategy = TestDrivenConvergence(test_suite=failing_test_suite)
    should_stop = strategy.should_stop({"answer": "wrong"}, {})

    assert should_stop is False


def test_test_driven_convergence_tracks_last_results():
    """Test that strategy tracks last test results."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    call_count = [0]

    def dynamic_test_suite(result):
        call_count[0] += 1
        if call_count[0] == 1:
            return (3, 2)  # First call: failures
        else:
            return (5, 0)  # Second call: all pass

    strategy = TestDrivenConvergence(test_suite=dynamic_test_suite)

    # First call - failures
    strategy.should_stop({}, {})
    assert strategy.last_results == (3, 2)

    # Second call - all pass
    strategy.should_stop({}, {})
    assert strategy.last_results == (5, 0)


def test_test_driven_convergence_get_reason_with_results():
    """Test that get_reason returns informative message."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    def test_suite(result):
        return (12, 0)

    strategy = TestDrivenConvergence(test_suite=test_suite)
    strategy.should_stop({}, {})

    reason = strategy.get_reason()
    assert "12" in reason
    assert "pass" in reason.lower()


def test_test_driven_convergence_get_reason_without_results():
    """Test that get_reason works before any tests run."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    def test_suite(result):
        return (0, 0)

    strategy = TestDrivenConvergence(test_suite=test_suite)
    reason = strategy.get_reason()

    assert isinstance(reason, str)
    assert len(reason) > 0


def test_test_driven_convergence_zero_tests():
    """Test edge case: zero tests."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    def empty_test_suite(result):
        return (0, 0)

    strategy = TestDrivenConvergence(test_suite=empty_test_suite)
    should_stop = strategy.should_stop({}, {})

    # Zero tests, zero failures -> should converge
    assert should_stop is True


def test_test_driven_convergence_all_tests_fail_initially():
    """Test scenario: all tests fail initially, then pass."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    results_sequence = [
        (0, 10),  # All fail
        (5, 5),  # Half pass
        (8, 2),  # Most pass
        (10, 0),  # All pass
    ]
    call_index = [0]

    def improving_test_suite(result):
        idx = call_index[0]
        call_index[0] += 1
        return results_sequence[idx]

    strategy = TestDrivenConvergence(test_suite=improving_test_suite)

    # Cycle 1: All fail
    assert strategy.should_stop({}, {}) is False

    # Cycle 2: Half pass
    assert strategy.should_stop({}, {}) is False

    # Cycle 3: Most pass
    assert strategy.should_stop({}, {}) is False

    # Cycle 4: All pass
    assert strategy.should_stop({}, {}) is True


def test_test_driven_convergence_passes_result_to_test_suite():
    """Test that result is passed to test suite callable."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    captured_result = [None]

    def capturing_test_suite(result):
        captured_result[0] = result
        return (5, 0)

    strategy = TestDrivenConvergence(test_suite=capturing_test_suite)
    test_result = {"code": "def foo(): pass", "output": "success"}

    strategy.should_stop(test_result, {})

    assert captured_result[0] == test_result


def test_test_driven_convergence_multiple_cycles():
    """Test multiple convergence checks in sequence."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    call_history = []

    def history_tracking_test_suite(result):
        call_history.append(result)
        # Converge on 3rd call
        if len(call_history) < 3:
            return (2, 1)
        else:
            return (3, 0)

    strategy = TestDrivenConvergence(test_suite=history_tracking_test_suite)

    # Cycle 1
    assert strategy.should_stop({"cycle": 1}, {}) is False
    # Cycle 2
    assert strategy.should_stop({"cycle": 2}, {}) is False
    # Cycle 3
    assert strategy.should_stop({"cycle": 3}, {}) is True

    assert len(call_history) == 3


def test_test_driven_convergence_test_suite_required():
    """Test that test_suite parameter is required."""
    from kaizen.strategies.convergence import TestDrivenConvergence

    # Should raise TypeError if test_suite not provided
    with pytest.raises(TypeError):
        TestDrivenConvergence()
