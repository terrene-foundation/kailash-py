"""Convergence condition system for cycle termination in workflows."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kailash.workflow.cycle_state import CycleState

logger = logging.getLogger(__name__)


class ConvergenceCondition(ABC):
    """Base class for cycle convergence conditions."""

    @abstractmethod
    def evaluate(self, results: dict[str, Any], cycle_state: "CycleState") -> bool:
        """Evaluate if cycle should terminate.

        Args:
            results: Current iteration results from nodes
            cycle_state: Current cycle state with history

        Returns:
            True if cycle should terminate, False to continue
        """
        raise NotImplementedError

    def describe(self) -> str:
        """Describe the convergence condition for logging."""
        return self.__class__.__name__


class ExpressionCondition(ConvergenceCondition):
    """Expression-based convergence condition.

    Examples:
        - "quality_score > 0.9"
        - "iteration >= 10"
        - "abs(loss_improvement) < 0.001"
    """

    def __init__(self, expression: str):
        """Initialize with expression string.

        Args:
            expression: Python expression to evaluate
        """
        self.expression = expression

    def evaluate(self, results: dict[str, Any], cycle_state: "CycleState") -> bool:
        """Evaluate expression with results and cycle state context."""
        # Create evaluation context
        context = {
            "results": results,
            "iteration": cycle_state.iteration,
            "history": cycle_state.history,
            "elapsed_time": cycle_state.elapsed_time,
            # Add common math functions
            "abs": abs,
            "min": min,
            "max": max,
            "sum": sum,
            "len": len,
            "all": all,
            "any": any,
        }

        # Add all result values to top-level context for easier access
        for node_id, node_result in results.items():
            if isinstance(node_id, str) and node_id.isidentifier():
                context[node_id] = node_result

                # Also extract scalar values from node results for convenience
                if isinstance(node_result, dict):
                    # Check if this is a PythonCodeNode result with 'result' key
                    if "result" in node_result and isinstance(
                        node_result["result"], dict
                    ):
                        # Extract from nested result
                        for key, value in node_result["result"].items():
                            if isinstance(key, str) and key.isidentifier():
                                if isinstance(value, (int, float, str, bool)):
                                    context[key] = value
                    else:
                        # Extract from top level
                        for key, value in node_result.items():
                            if isinstance(key, str) and key.isidentifier():
                                # Only add scalar values to avoid conflicts
                                if isinstance(value, (int, float, str, bool)):
                                    context[key] = value

        try:
            # Safe evaluation with restricted builtins
            logger.debug(f"Evaluating expression: {self.expression}")
            logger.debug(f"Context variables: {list(context.keys())}")
            logger.debug(
                f"should_continue value: {context.get('should_continue', 'NOT FOUND')}"
            )
            result = eval(self.expression, {"__builtins__": {}}, context)
            logger.debug(f"Expression result: {result} -> {bool(result)}")
            return bool(result)
        except Exception as e:
            logger.warning(
                f"Expression evaluation failed: {e}. Expression: {self.expression}"
            )
            # On error, terminate cycle for safety
            return True

    def describe(self) -> str:
        """Describe the expression condition."""
        return f"ExpressionCondition: {self.expression}"


class CallbackCondition(ConvergenceCondition):
    """Callback-based convergence condition for complex logic."""

    def __init__(
        self,
        callback: Callable[[dict[str, Any], "CycleState"], bool],
        name: str | None = None,
    ):
        """Initialize with callback function.

        Args:
            callback: Function that takes (results, cycle_state) and returns bool
            name: Optional name for the callback
        """
        self.callback = callback
        self.name = name or callback.__name__

    def evaluate(self, results: dict[str, Any], cycle_state: "CycleState") -> bool:
        """Evaluate callback with results and cycle state."""
        try:
            return self.callback(results, cycle_state)
        except Exception as e:
            logger.warning(f"Callback evaluation failed: {e}. Callback: {self.name}")
            # On error, terminate cycle for safety
            return True

    def describe(self) -> str:
        """Describe the callback condition."""
        return f"CallbackCondition: {self.name}"


class MaxIterationsCondition(ConvergenceCondition):
    """Simple iteration limit condition."""

    def __init__(self, max_iterations: int):
        """Initialize with maximum iteration count.

        Args:
            max_iterations: Maximum number of iterations allowed
        """
        self.max_iterations = max_iterations

    def evaluate(self, results: dict[str, Any], cycle_state: "CycleState") -> bool:
        """Check if maximum iterations reached."""
        return cycle_state.iteration >= self.max_iterations

    def describe(self) -> str:
        """Describe the iteration limit."""
        return f"MaxIterationsCondition: {self.max_iterations}"


class CompoundCondition(ConvergenceCondition):
    """Combine multiple conditions with AND/OR logic."""

    def __init__(self, conditions: list[ConvergenceCondition], operator: str = "OR"):
        """Initialize with list of conditions.

        Args:
            conditions: List of convergence conditions
            operator: "AND" or "OR" to combine conditions
        """
        self.conditions = conditions
        self.operator = operator.upper()
        if self.operator not in ["AND", "OR"]:
            raise ValueError("Operator must be 'AND' or 'OR'")

    def evaluate(self, results: dict[str, Any], cycle_state: "CycleState") -> bool:
        """Evaluate all conditions with specified operator."""
        evaluations = [cond.evaluate(results, cycle_state) for cond in self.conditions]

        if self.operator == "AND":
            return all(evaluations)
        else:  # OR
            return any(evaluations)

    def describe(self) -> str:
        """Describe the compound condition."""
        conditions_desc = [cond.describe() for cond in self.conditions]
        return f"CompoundCondition({self.operator}): [{', '.join(conditions_desc)}]"


class AdaptiveCondition(ConvergenceCondition):
    """Adaptive convergence that changes based on iteration progress."""

    def __init__(self, stages: list[tuple[int, ConvergenceCondition]]):
        """Initialize with stages of conditions.

        Args:
            stages: List of (iteration_threshold, condition) tuples
                   Conditions are applied when iteration >= threshold
        """
        self.stages = sorted(stages, key=lambda x: x[0])

    def evaluate(self, results: dict[str, Any], cycle_state: "CycleState") -> bool:
        """Evaluate condition based on current iteration stage."""
        current_iteration = cycle_state.iteration

        # Find the appropriate condition for current iteration
        active_condition = None
        for threshold, condition in reversed(self.stages):
            if current_iteration >= threshold:
                active_condition = condition
                break

        if active_condition:
            return active_condition.evaluate(results, cycle_state)

        # No condition applies yet, continue
        return False

    def describe(self) -> str:
        """Describe the adaptive condition."""
        stages_desc = [(t, c.describe()) for t, c in self.stages]
        return f"AdaptiveCondition: {stages_desc}"


def create_convergence_condition(
    spec: str | int | Callable | dict,
) -> ConvergenceCondition:
    """Factory function to create convergence conditions from various specs.

    Args:
        spec: Can be:
            - str: Expression condition
            - int: Max iterations condition
            - Callable: Callback condition
            - Dict: Complex condition specification

    Returns:
        ConvergenceCondition instance
    """
    if isinstance(spec, str):
        return ExpressionCondition(spec)
    elif isinstance(spec, int):
        return MaxIterationsCondition(spec)
    elif callable(spec):
        return CallbackCondition(spec)
    elif isinstance(spec, dict):
        cond_type = spec.get("type", "expression")

        if cond_type == "expression":
            return ExpressionCondition(spec["expression"])
        elif cond_type == "max_iterations":
            return MaxIterationsCondition(spec["max_iterations"])
        elif cond_type == "callback":
            return CallbackCondition(spec["callback"], spec.get("name"))
        elif cond_type == "compound":
            conditions = [create_convergence_condition(c) for c in spec["conditions"]]
            return CompoundCondition(conditions, spec.get("operator", "OR"))
        elif cond_type == "adaptive":
            stages = [(t, create_convergence_condition(c)) for t, c in spec["stages"]]
            return AdaptiveCondition(stages)
        else:
            raise ValueError(f"Unknown condition type: {cond_type}")
    else:
        raise ValueError(f"Invalid convergence condition spec: {spec}")
