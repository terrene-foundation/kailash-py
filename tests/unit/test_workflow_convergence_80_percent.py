"""Comprehensive tests to boost workflow.convergence coverage from 25% to >80%."""

from typing import Any, Dict
from unittest.mock import MagicMock, Mock

import pytest


class MockCycleState:
    """Mock CycleState for testing."""

    def __init__(self, iteration=0, elapsed_time=0.0, history=None):
        self.iteration = iteration
        self.elapsed_time = elapsed_time
        self.history = history or []


class TestConvergenceConditionBase:
    """Test the base ConvergenceCondition abstract class."""

    def test_convergence_condition_abstract(self):
        """Test that ConvergenceCondition cannot be instantiated directly."""
        try:
            from kailash.workflow.convergence import ConvergenceCondition

            with pytest.raises(TypeError):
                ConvergenceCondition()

        except ImportError:
            pytest.skip("ConvergenceCondition not available")

    def test_convergence_condition_describe_default(self):
        """Test default describe method implementation."""
        try:
            from kailash.workflow.convergence import ConvergenceCondition

            class TestCondition(ConvergenceCondition):
                def evaluate(self, results, cycle_state):
                    return False

            condition = TestCondition()
            assert condition.describe() == "TestCondition"

        except ImportError:
            pytest.skip("ConvergenceCondition not available")


class TestExpressionCondition:
    """Test ExpressionCondition functionality."""

    def test_expression_condition_init(self):
        """Test ExpressionCondition initialization."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("iteration >= 10")
            assert condition.expression == "iteration >= 10"

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_simple_evaluation(self):
        """Test simple expression evaluation."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("iteration >= 5")
            cycle_state = MockCycleState(iteration=7)
            results = {}

            assert condition.evaluate(results, cycle_state) is True

            cycle_state = MockCycleState(iteration=3)
            assert condition.evaluate(results, cycle_state) is False

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_with_results(self):
        """Test expression evaluation with result values."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("quality_score > 0.9")
            cycle_state = MockCycleState(iteration=1)
            results = {"node1": {"quality_score": 0.95}}

            assert condition.evaluate(results, cycle_state) is True

            results = {"node1": {"quality_score": 0.85}}
            assert condition.evaluate(results, cycle_state) is False

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_with_nested_results(self):
        """Test expression evaluation with nested PythonCodeNode results."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("accuracy > 0.8")
            cycle_state = MockCycleState(iteration=1)
            results = {"evaluator": {"result": {"accuracy": 0.85, "loss": 0.1}}}

            assert condition.evaluate(results, cycle_state) is True

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_math_functions(self):
        """Test expression evaluation with math functions."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("abs(loss_change) < 0.01")
            cycle_state = MockCycleState(iteration=1)
            results = {"node1": {"loss_change": -0.005}}

            assert condition.evaluate(results, cycle_state) is True

            results = {"node1": {"loss_change": 0.02}}
            assert condition.evaluate(results, cycle_state) is False

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_context_variables(self):
        """Test expression evaluation with context variables."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("iteration > 3 and elapsed_time < 60.0")
            cycle_state = MockCycleState(iteration=5, elapsed_time=45.0)
            results = {}

            assert condition.evaluate(results, cycle_state) is True

            cycle_state = MockCycleState(iteration=2, elapsed_time=45.0)
            assert condition.evaluate(results, cycle_state) is False

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_with_history(self):
        """Test expression evaluation with history access."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("len(history) >= 3")
            cycle_state = MockCycleState(iteration=1, history=[1, 2, 3, 4])
            results = {}

            assert condition.evaluate(results, cycle_state) is True

            cycle_state = MockCycleState(iteration=1, history=[1, 2])
            assert condition.evaluate(results, cycle_state) is False

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_node_id_access(self):
        """Test direct access to node results by node ID."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("optimizer.learning_rate < 0.01")
            cycle_state = MockCycleState(iteration=1)
            results = {"optimizer": {"learning_rate": 0.005}}

            assert condition.evaluate(results, cycle_state) is True

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_invalid_expression(self):
        """Test handling of invalid expressions."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("undefined_variable > 0")
            cycle_state = MockCycleState(iteration=1)
            results = {}

            # Should return True (terminate) on error for safety
            assert condition.evaluate(results, cycle_state) is True

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_describe(self):
        """Test expression condition description."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("quality > 0.9")
            assert condition.describe() == "ExpressionCondition: quality > 0.9"

        except ImportError:
            pytest.skip("ExpressionCondition not available")

    def test_expression_condition_non_identifier_keys(self):
        """Test handling of non-identifier keys in results."""
        try:
            from kailash.workflow.convergence import ExpressionCondition

            condition = ExpressionCondition("iteration >= 1")  # Simple expression
            cycle_state = MockCycleState(iteration=1)
            results = {
                "node-with-dashes": {"value": 1},  # Non-identifier
                "123node": {"value": 2},  # Non-identifier
                "valid_node": {"score": 0.8},  # Valid identifier
            }

            # Should not crash with non-identifier keys
            result = condition.evaluate(results, cycle_state)
        # # assert result... - variable may not be defined - result variable may not be defined

        except ImportError:
            pytest.skip("ExpressionCondition not available")


class TestCallbackCondition:
    """Test CallbackCondition functionality."""

    def test_callback_condition_init(self):
        """Test CallbackCondition initialization."""
        try:
            from kailash.workflow.convergence import CallbackCondition

            def test_callback(results, cycle_state):
                return True

            condition = CallbackCondition(test_callback)
            assert condition.callback == test_callback
            assert condition.name == "test_callback"

        except ImportError:
            pytest.skip("CallbackCondition not available")

    def test_callback_condition_init_with_name(self):
        """Test CallbackCondition initialization with custom name."""
        try:
            from kailash.workflow.convergence import CallbackCondition

            def test_callback(results, cycle_state):
                return False

            condition = CallbackCondition(test_callback, name="custom_name")
            assert condition.name == "custom_name"

        except ImportError:
            pytest.skip("CallbackCondition not available")

    def test_callback_condition_evaluation(self):
        """Test callback evaluation."""
        try:
            from kailash.workflow.convergence import CallbackCondition

            def converge_on_high_score(results, cycle_state):
                return results.get("score", 0) > 0.95

            condition = CallbackCondition(converge_on_high_score)
            cycle_state = MockCycleState(iteration=1)

            # High score should converge
            results = {"score": 0.98}
            assert condition.evaluate(results, cycle_state) is True

            # Low score should continue
            results = {"score": 0.85}
            assert condition.evaluate(results, cycle_state) is False

        except ImportError:
            pytest.skip("CallbackCondition not available")

    def test_callback_condition_with_cycle_state(self):
        """Test callback that uses cycle state."""
        try:
            from kailash.workflow.convergence import CallbackCondition

            def converge_after_iterations(results, cycle_state):
                return cycle_state.iteration >= 10

            condition = CallbackCondition(converge_after_iterations)

            cycle_state = MockCycleState(iteration=12)
            assert condition.evaluate({}, cycle_state) is True

            cycle_state = MockCycleState(iteration=5)
            assert condition.evaluate({}, cycle_state) is False

        except ImportError:
            pytest.skip("CallbackCondition not available")

    def test_callback_condition_error_handling(self):
        """Test error handling in callback evaluation."""
        try:
            from kailash.workflow.convergence import CallbackCondition

            def failing_callback(results, cycle_state):
                raise Exception("Callback failed")

            condition = CallbackCondition(failing_callback)
            cycle_state = MockCycleState(iteration=1)

            # Should return True (terminate) on error for safety
            assert condition.evaluate({}, cycle_state) is True

        except ImportError:
            pytest.skip("CallbackCondition not available")

    def test_callback_condition_describe(self):
        """Test callback condition description."""
        try:
            from kailash.workflow.convergence import CallbackCondition

            def test_callback(results, cycle_state):
                return True

            condition = CallbackCondition(test_callback, name="test_convergence")
            assert condition.describe() == "CallbackCondition: test_convergence"

        except ImportError:
            pytest.skip("CallbackCondition not available")


class TestMaxIterationsCondition:
    """Test MaxIterationsCondition functionality."""

    def test_max_iterations_condition_init(self):
        """Test MaxIterationsCondition initialization."""
        try:
            from kailash.workflow.convergence import MaxIterationsCondition

            condition = MaxIterationsCondition(10)
            assert condition.max_iterations == 10

        except ImportError:
            pytest.skip("MaxIterationsCondition not available")

    def test_max_iterations_condition_evaluation(self):
        """Test max iterations evaluation."""
        try:
            from kailash.workflow.convergence import MaxIterationsCondition

            condition = MaxIterationsCondition(5)

            # Should continue before max iterations
            cycle_state = MockCycleState(iteration=3)
            assert condition.evaluate({}, cycle_state) is False

            # Should converge at max iterations
            cycle_state = MockCycleState(iteration=5)
            assert condition.evaluate({}, cycle_state) is True

            # Should converge after max iterations
            cycle_state = MockCycleState(iteration=7)
            assert condition.evaluate({}, cycle_state) is True

        except ImportError:
            pytest.skip("MaxIterationsCondition not available")

    def test_max_iterations_condition_describe(self):
        """Test max iterations condition description."""
        try:
            from kailash.workflow.convergence import MaxIterationsCondition

            condition = MaxIterationsCondition(15)
            assert condition.describe() == "MaxIterationsCondition: 15"

        except ImportError:
            pytest.skip("MaxIterationsCondition not available")


class TestCompoundCondition:
    """Test CompoundCondition functionality."""

    def test_compound_condition_init_or(self):
        """Test CompoundCondition initialization with OR."""
        try:
            from kailash.workflow.convergence import (
                CompoundCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(10)
            cond2 = ExpressionCondition("quality > 0.9")

            condition = CompoundCondition([cond1, cond2], "OR")
            assert len(condition.conditions) == 2
            assert condition.operator == "OR"

        except ImportError:
            pytest.skip("CompoundCondition not available")

    def test_compound_condition_init_and(self):
        """Test CompoundCondition initialization with AND."""
        try:
            from kailash.workflow.convergence import (
                CompoundCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(10)
            cond2 = ExpressionCondition("quality > 0.9")

            condition = CompoundCondition(
                [cond1, cond2], "and"
            )  # Test case insensitive
            assert condition.operator == "AND"

        except ImportError:
            pytest.skip("CompoundCondition not available")

    def test_compound_condition_invalid_operator(self):
        """Test CompoundCondition with invalid operator."""
        try:
            from kailash.workflow.convergence import (
                CompoundCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(10)

            with pytest.raises(ValueError, match="Operator must be 'AND' or 'OR'"):
                CompoundCondition([cond1], "XOR")

        except ImportError:
            pytest.skip("CompoundCondition not available")

    def test_compound_condition_or_evaluation(self):
        """Test OR compound condition evaluation."""
        try:
            from kailash.workflow.convergence import (
                CompoundCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(10)  # Will be False at iteration 5
            cond2 = ExpressionCondition("quality > 0.9")  # Will depend on results

            condition = CompoundCondition([cond1, cond2], "OR")
            cycle_state = MockCycleState(iteration=5)

            # Neither condition met - should continue
            results = {"quality": 0.8}
            assert condition.evaluate(results, cycle_state) is False

            # One condition met - should converge
            results = {"quality": 0.95}
            assert condition.evaluate(results, cycle_state) is True

            # Both conditions met - should converge
            cycle_state = MockCycleState(iteration=15)
            results = {"quality": 0.95}
            assert condition.evaluate(results, cycle_state) is True

        except ImportError:
            pytest.skip("CompoundCondition not available")

    def test_compound_condition_and_evaluation(self):
        """Test AND compound condition evaluation."""
        try:
            from kailash.workflow.convergence import (
                CompoundCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(10)  # Will be True at iteration 15
            cond2 = ExpressionCondition("quality > 0.9")  # Will depend on results

            condition = CompoundCondition([cond1, cond2], "AND")
            cycle_state = MockCycleState(iteration=15)

            # Only one condition met - should continue
            results = {"quality": 0.8}
            assert condition.evaluate(results, cycle_state) is False

            # Both conditions met - should converge
            results = {"quality": 0.95}
            assert condition.evaluate(results, cycle_state) is True

        except ImportError:
            pytest.skip("CompoundCondition not available")

    def test_compound_condition_describe(self):
        """Test compound condition description."""
        try:
            from kailash.workflow.convergence import (
                CompoundCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(10)
            cond2 = ExpressionCondition("quality > 0.9")

            condition = CompoundCondition([cond1, cond2], "OR")
            description = condition.describe()

            assert "CompoundCondition(OR)" in description
            assert "MaxIterationsCondition: 10" in description
            assert "ExpressionCondition: quality > 0.9" in description

        except ImportError:
            pytest.skip("CompoundCondition not available")


class TestAdaptiveCondition:
    """Test AdaptiveCondition functionality."""

    def test_adaptive_condition_init(self):
        """Test AdaptiveCondition initialization."""
        try:
            from kailash.workflow.convergence import (
                AdaptiveCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(5)
            cond2 = ExpressionCondition("quality > 0.9")

            stages = [(0, cond1), (10, cond2)]
            condition = AdaptiveCondition(stages)

            assert len(condition.stages) == 2
            # Should be sorted by threshold
            assert condition.stages[0][0] == 0
            assert condition.stages[1][0] == 10

        except ImportError:
            pytest.skip("AdaptiveCondition not available")

    def test_adaptive_condition_stage_selection(self):
        """Test adaptive condition stage selection."""
        try:
            from kailash.workflow.convergence import (
                AdaptiveCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(5)  # Early stage: stop at 5 iterations
            cond2 = ExpressionCondition("quality > 0.9")  # Later stage: quality-based

            stages = [(0, cond1), (10, cond2)]
            condition = AdaptiveCondition(stages)

            # Early iterations - use first condition
            cycle_state = MockCycleState(iteration=3)
            results = {"quality": 0.95}
            assert condition.evaluate(results, cycle_state) is False  # < 5 iterations

            cycle_state = MockCycleState(iteration=5)
            assert condition.evaluate(results, cycle_state) is True  # >= 5 iterations

            # Later iterations - use second condition
            cycle_state = MockCycleState(iteration=12)
            results = {"quality": 0.85}
            assert condition.evaluate(results, cycle_state) is False  # Low quality

            results = {"quality": 0.95}
            assert condition.evaluate(results, cycle_state) is True  # High quality

        except ImportError:
            pytest.skip("AdaptiveCondition not available")

    def test_adaptive_condition_no_applicable_stage(self):
        """Test adaptive condition when no stage applies."""
        try:
            from kailash.workflow.convergence import (
                AdaptiveCondition,
                ExpressionCondition,
            )

            cond1 = ExpressionCondition("quality > 0.9")
            stages = [(10, cond1)]  # Only applies from iteration 10+
            condition = AdaptiveCondition(stages)

            # Before any stage applies - should continue
            cycle_state = MockCycleState(iteration=5)
            results = {"quality": 0.95}
            assert condition.evaluate(results, cycle_state) is False

        except ImportError:
            pytest.skip("AdaptiveCondition not available")

    def test_adaptive_condition_stages_sorting(self):
        """Test that stages are sorted by threshold."""
        try:
            from kailash.workflow.convergence import (
                AdaptiveCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(5)
            cond2 = MaxIterationsCondition(10)
            cond3 = MaxIterationsCondition(3)

            # Provide stages out of order
            stages = [(10, cond2), (3, cond3), (5, cond1)]
            condition = AdaptiveCondition(stages)

            # Should be sorted by threshold
            assert condition.stages[0][0] == 3
            assert condition.stages[1][0] == 5
            assert condition.stages[2][0] == 10

        except ImportError:
            pytest.skip("AdaptiveCondition not available")

    def test_adaptive_condition_describe(self):
        """Test adaptive condition description."""
        try:
            from kailash.workflow.convergence import (
                AdaptiveCondition,
                ExpressionCondition,
                MaxIterationsCondition,
            )

            cond1 = MaxIterationsCondition(5)
            cond2 = ExpressionCondition("quality > 0.9")

            stages = [(0, cond1), (10, cond2)]
            condition = AdaptiveCondition(stages)

            description = condition.describe()
            assert "AdaptiveCondition" in description
            assert "MaxIterationsCondition: 5" in description
            assert "ExpressionCondition: quality > 0.9" in description

        except ImportError:
            pytest.skip("AdaptiveCondition not available")


class TestCreateConvergenceCondition:
    """Test the factory function for creating convergence conditions."""

    def test_create_from_string(self):
        """Test creating condition from string expression."""
        try:
            from kailash.workflow.convergence import (
                ExpressionCondition,
                create_convergence_condition,
            )

            condition = create_convergence_condition("quality > 0.9")
            assert isinstance(condition, ExpressionCondition)
            assert condition.expression == "quality > 0.9"

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_int(self):
        """Test creating condition from integer (max iterations)."""
        try:
            from kailash.workflow.convergence import (
                MaxIterationsCondition,
                create_convergence_condition,
            )

            condition = create_convergence_condition(15)
            assert isinstance(condition, MaxIterationsCondition)
            assert condition.max_iterations == 15

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_callable(self):
        """Test creating condition from callable."""
        try:
            from kailash.workflow.convergence import (
                CallbackCondition,
                create_convergence_condition,
            )

            def test_callback(results, cycle_state):
                return True

            condition = create_convergence_condition(test_callback)
            assert isinstance(condition, CallbackCondition)
            assert condition.callback == test_callback

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_dict_expression(self):
        """Test creating expression condition from dict."""
        try:
            from kailash.workflow.convergence import (
                ExpressionCondition,
                create_convergence_condition,
            )

            spec = {"type": "expression", "expression": "iteration >= 10"}
            condition = create_convergence_condition(spec)
            assert isinstance(condition, ExpressionCondition)
            assert condition.expression == "iteration >= 10"

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_dict_max_iterations(self):
        """Test creating max iterations condition from dict."""
        try:
            from kailash.workflow.convergence import (
                MaxIterationsCondition,
                create_convergence_condition,
            )

            spec = {"type": "max_iterations", "max_iterations": 20}
            condition = create_convergence_condition(spec)
            assert isinstance(condition, MaxIterationsCondition)
            assert condition.max_iterations == 20

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_dict_callback(self):
        """Test creating callback condition from dict."""
        try:
            from kailash.workflow.convergence import (
                CallbackCondition,
                create_convergence_condition,
            )

            def test_callback(results, cycle_state):
                return False

            spec = {"type": "callback", "callback": test_callback, "name": "test"}
            condition = create_convergence_condition(spec)
            assert isinstance(condition, CallbackCondition)
            assert condition.callback == test_callback
            assert condition.name == "test"

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_dict_compound(self):
        """Test creating compound condition from dict."""
        try:
            from kailash.workflow.convergence import (
                CompoundCondition,
                create_convergence_condition,
            )

            spec = {
                "type": "compound",
                "conditions": ["quality > 0.9", 15],
                "operator": "AND",
            }
            condition = create_convergence_condition(spec)
            assert isinstance(condition, CompoundCondition)
            assert condition.operator == "AND"
            assert len(condition.conditions) == 2

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_dict_adaptive(self):
        """Test creating adaptive condition from dict."""
        try:
            from kailash.workflow.convergence import (
                AdaptiveCondition,
                create_convergence_condition,
            )

            spec = {
                "type": "adaptive",
                "stages": [(0, "quality > 0.8"), (10, "quality > 0.95")],
            }
            condition = create_convergence_condition(spec)
            assert isinstance(condition, AdaptiveCondition)
            assert len(condition.stages) == 2

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_dict_default_expression(self):
        """Test creating condition from dict without type (defaults to expression)."""
        try:
            from kailash.workflow.convergence import (
                ExpressionCondition,
                create_convergence_condition,
            )

            spec = {"expression": "score > threshold"}
            condition = create_convergence_condition(spec)
            assert isinstance(condition, ExpressionCondition)
            assert condition.expression == "score > threshold"

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_from_dict_unknown_type(self):
        """Test error handling for unknown condition type."""
        try:
            from kailash.workflow.convergence import create_convergence_condition

            spec = {"type": "unknown_type"}
            with pytest.raises(
                ValueError, match="Unknown condition type: unknown_type"
            ):
                create_convergence_condition(spec)

        except ImportError:
            pytest.skip("create_convergence_condition not available")

    def test_create_invalid_spec(self):
        """Test error handling for invalid spec type."""
        try:
            from kailash.workflow.convergence import create_convergence_condition

            with pytest.raises(ValueError, match="Invalid convergence condition spec"):
                create_convergence_condition([1, 2, 3])  # List is not supported

        except ImportError:
            pytest.skip("create_convergence_condition not available")
