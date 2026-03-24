"""
Convergence checking nodes for cyclic workflows.

This module provides specialized nodes for detecting convergence in cyclic workflows,
eliminating the need for custom convergence logic in every workflow. These nodes
implement common convergence patterns and can be easily configured for different
scenarios.

Design Philosophy:
    Convergence detection is a critical pattern in cyclic workflows. This module
    provides declarative convergence checking that replaces imperative convergence
    logic with configurable nodes, making workflows more maintainable and testable.

Example usage:
    >>> from kailash.nodes.logic.convergence import ConvergenceCheckerNode
    >>> from kailash import Workflow
    >>>
    >>> workflow = Workflow("convergence-demo")
    >>> workflow.add_node("convergence", ConvergenceCheckerNode(),
    ...     threshold=0.8, mode="threshold")
    >>>
    >>> # Connect to SwitchNode for conditional routing
    >>> workflow.add_node("switch", SwitchNode(
    ...     condition_field="converged",
    ...     true_route="output",
    ...     false_route="processor"
    ... ))
"""

from typing import Any

from ..base import NodeParameter, register_node
from ..base_cycle_aware import CycleAwareNode


@register_node()
class ConvergenceCheckerNode(CycleAwareNode):
    """
    Specialized node for detecting convergence in cyclic workflows.

    This node implements common convergence patterns and eliminates the need
    for custom convergence logic in every workflow. It supports multiple
    convergence modes and provides detailed feedback about convergence status.

    Design Philosophy:
        ConvergenceCheckerNode provides a declarative approach to convergence
        detection. Instead of writing custom convergence logic in each workflow,
        users configure convergence criteria and the node handles the detection
        logic, state tracking, and reporting.

    Upstream Dependencies:
        - Any node producing numeric values to monitor
        - Common patterns: optimizers, iterative refiners, quality improvers
        - Must receive 'value' parameter to check for convergence

    Downstream Consumers:
        - SwitchNode: Routes based on 'converged' field
        - Output nodes: Process final converged results
        - Monitoring nodes: Track convergence progress

    Configuration:
        mode (str): Convergence detection mode
            - 'threshold': Value reaches target threshold
            - 'stability': Value becomes stable (low variance)
            - 'improvement': Rate of improvement drops below threshold
            - 'combined': Multiple criteria must be met
            - 'custom': User-defined convergence expression
        threshold (float): Target value for threshold mode
        stability_window (int): Number of values for stability check
        min_variance (float): Maximum variance for stability
        min_improvement (float): Minimum improvement rate
        patience (int): Iterations without improvement before stopping

    Implementation Details:
        - Inherits from CycleAwareNode for iteration tracking
        - Maintains value history across iterations
        - Tracks best value and no-improvement count
        - Supports multiple convergence detection algorithms
        - Provides detailed metrics for debugging

    Error Handling:
        - Invalid modes raise ValueError
        - Missing value parameter uses default 0.0
        - Custom expressions are safely evaluated

    Side Effects:
        - Logs convergence status each iteration
        - No external state modifications

    Examples:
        >>> # Simple threshold convergence
        >>> convergence = ConvergenceCheckerNode()
        >>> workflow.add_node("convergence", convergence,
        ...     threshold=0.95, mode="threshold")
        >>>
        >>> # Stability-based convergence
        >>> workflow.add_node("stability", ConvergenceCheckerNode(),
        ...     mode="stability", stability_window=5, min_variance=0.001)
        >>>
        >>> # Combined convergence criteria
        >>> workflow.add_node("combined", ConvergenceCheckerNode(),
        ...     mode="combined", threshold=0.9, stability_window=3)
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters for convergence checking."""
        return {
            "value": NodeParameter(
                name="value",
                type=float,  # Changed from Union[float, int] to just float
                required=False,
                default=0.0,
                description="Value to check for convergence",
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=0.8,
                description="Target threshold for convergence (mode: threshold, combined)",
            ),
            "mode": NodeParameter(
                name="mode",
                type=str,
                required=False,
                default="threshold",
                description="Convergence detection mode: threshold|stability|improvement|combined|custom",
            ),
            "stability_window": NodeParameter(
                name="stability_window",
                type=int,
                required=False,
                default=3,
                description="Number of recent values to analyze for stability",
            ),
            "min_variance": NodeParameter(
                name="min_variance",
                type=float,
                required=False,
                default=0.01,
                description="Maximum variance for stability convergence",
            ),
            "min_improvement": NodeParameter(
                name="min_improvement",
                type=float,
                required=False,
                default=0.01,
                description="Minimum improvement rate to continue (mode: improvement)",
            ),
            "improvement_window": NodeParameter(
                name="improvement_window",
                type=int,
                required=False,
                default=3,
                description="Window for calculating improvement rate",
            ),
            "custom_expression": NodeParameter(
                name="custom_expression",
                type=str,
                required=False,
                description="Custom convergence expression (mode: custom)",
            ),
            "early_stop_iterations": NodeParameter(
                name="early_stop_iterations",
                type=int,
                required=False,
                description="Force convergence after this many iterations",
            ),
            "patience": NodeParameter(
                name="patience",
                type=int,
                required=False,
                default=5,
                description="Iterations to wait without improvement before stopping",
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,
                description="Pass-through data to preserve in the output",
            ),
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        """Define output schema for convergence results."""
        return {
            "converged": NodeParameter(
                name="converged",
                type=bool,
                required=True,
                description="Whether convergence has been achieved",
            ),
            "reason": NodeParameter(
                name="reason",
                type=str,
                required=True,
                description="Explanation of convergence decision",
            ),
            "value": NodeParameter(
                name="value",
                type=float,
                required=True,
                description="Current value being monitored",
            ),
            "iteration": NodeParameter(
                name="iteration",
                type=int,
                required=True,
                description="Current iteration number",
            ),
            "convergence_metrics": NodeParameter(
                name="convergence_metrics",
                type=dict,
                required=True,
                description="Detailed metrics about convergence progress",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute convergence checking logic."""
        # Get context
        context = kwargs.get("context", {})

        # Get parameters
        value = kwargs["value"]
        threshold = kwargs.get("threshold", 0.8)
        mode = kwargs.get("mode", "threshold")
        stability_window = kwargs.get("stability_window", 3)
        min_variance = kwargs.get("min_variance", 0.01)
        min_improvement = kwargs.get("min_improvement", 0.01)
        improvement_window = kwargs.get("improvement_window", 3)
        custom_expression = kwargs.get("custom_expression")
        early_stop_iterations = kwargs.get("early_stop_iterations")
        patience = kwargs.get("patience", 5)

        # Get cycle information
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)

        # Update value history
        value_history = self.accumulate_values(context, "values", value)

        # Get previous state for additional tracking
        prev_state = self.get_previous_state(context)
        best_value = prev_state.get("best_value", value)
        no_improvement_count = prev_state.get("no_improvement_count", 0)
        convergence_start_iteration = prev_state.get("convergence_start_iteration")

        # Detect if we're dealing with boolean values (common in cycle convergence)
        is_boolean_convergence = isinstance(value, bool) or (
            len(value_history) >= 2 and all(v in [0.0, 1.0] for v in value_history[-2:])
        )

        # Update best value and improvement tracking (skip for boolean convergence)
        if not is_boolean_convergence:
            if value > best_value:
                best_value = value
                no_improvement_count = 0
            else:
                no_improvement_count += 1
        else:
            # For boolean convergence, don't track "improvement" - just track changes
            if value != prev_state.get("last_value", value):
                no_improvement_count = 0
            else:
                no_improvement_count += 1

        # Initialize convergence state
        converged = False
        reason = ""
        metrics = {
            "value": value,
            "best_value": best_value,
            "value_history": value_history[-10:],  # Keep last 10 for metrics
            "no_improvement_count": no_improvement_count,
            "iteration": iteration,
        }

        # Check early stopping conditions first
        if early_stop_iterations and iteration >= early_stop_iterations:
            converged = True
            reason = f"Early stop: reached {early_stop_iterations} iterations"
        elif (
            patience and no_improvement_count >= patience and not is_boolean_convergence
        ):
            # Only apply patience mechanism for non-boolean convergence
            converged = True
            reason = f"Early stop: no improvement for {patience} iterations"
        else:
            # Apply convergence mode logic
            if mode == "threshold":
                converged, reason, mode_metrics = self._check_threshold_convergence(
                    value, threshold, iteration
                )
            elif mode == "stability":
                converged, reason, mode_metrics = self._check_stability_convergence(
                    value_history, stability_window, min_variance, iteration
                )
            elif mode == "improvement":
                converged, reason, mode_metrics = self._check_improvement_convergence(
                    value_history, improvement_window, min_improvement, iteration
                )
            elif mode == "combined":
                converged, reason, mode_metrics = self._check_combined_convergence(
                    value,
                    value_history,
                    threshold,
                    stability_window,
                    min_variance,
                    iteration,
                )
            elif mode == "custom":
                converged, reason, mode_metrics = self._check_custom_convergence(
                    value, value_history, custom_expression, iteration, **kwargs
                )
            else:
                raise ValueError(f"Unsupported convergence mode: {mode}")

            metrics.update(mode_metrics)

        # Track convergence start time
        if converged and convergence_start_iteration is None:
            convergence_start_iteration = iteration
        elif not converged:
            convergence_start_iteration = None

        metrics["convergence_start_iteration"] = convergence_start_iteration

        # Log convergence status
        if is_first:
            self.log_cycle_info(
                context, f"Starting convergence monitoring (mode: {mode})"
            )
        elif converged:
            self.log_cycle_info(context, f"✅ CONVERGED: {reason}")
        else:
            self.log_cycle_info(context, f"Monitoring: {reason}")

        # Prepare state for next iteration
        next_state = {
            "values": value_history,
            "best_value": best_value,
            "no_improvement_count": no_improvement_count,
            "convergence_start_iteration": convergence_start_iteration,
            "last_value": value,  # Track last value for boolean convergence
        }

        # Include pass-through data if provided
        result = {
            "converged": converged,
            "reason": reason,
            "value": value,
            "iteration": iteration,
            "convergence_metrics": metrics,
            **self.set_cycle_state(next_state),
        }

        # Add data to output if provided
        if "data" in kwargs:
            result["data"] = kwargs["data"]

        return result

    def _check_threshold_convergence(
        self, value: float, threshold: float, iteration: int
    ) -> tuple[bool, str, dict]:
        """Check if value has reached threshold."""
        converged = value >= threshold
        reason = (
            f"Value {value:.3f} {'≥' if converged else '<'} threshold {threshold:.3f}"
        )
        metrics = {"threshold": threshold, "distance_to_threshold": threshold - value}
        return converged, reason, metrics

    def _check_stability_convergence(
        self,
        value_history: list[float],
        window: int,
        min_variance: float,
        iteration: int,
    ) -> tuple[bool, str, dict]:
        """Check if values have stabilized."""
        if len(value_history) < window:
            reason = f"Need {window} values, have {len(value_history)}"
            metrics = {"variance": None, "window_size": len(value_history)}
            return False, reason, metrics

        recent_values = value_history[-window:]
        variance = max(recent_values) - min(recent_values)
        converged = variance <= min_variance

        reason = (
            f"Variance {variance:.4f} {'≤' if converged else '>'} {min_variance:.4f}"
        )
        metrics = {
            "variance": variance,
            "min_variance": min_variance,
            "window_values": recent_values,
        }
        return converged, reason, metrics

    def _check_improvement_convergence(
        self,
        value_history: list[float],
        window: int,
        min_improvement: float,
        iteration: int,
    ) -> tuple[bool, str, dict]:
        """Check if improvement rate has dropped below threshold."""
        if len(value_history) < window:
            reason = f"Need {window} values for improvement calculation"
            metrics = {"improvement_rate": None}
            return False, reason, metrics

        recent_values = value_history[-window:]
        if len(recent_values) < 2:
            improvement_rate = 0.0
        else:
            improvement_rate = (recent_values[-1] - recent_values[0]) / (
                len(recent_values) - 1
            )

        converged = improvement_rate < min_improvement
        reason = f"Improvement rate {improvement_rate:.4f} {'<' if converged else '≥'} {min_improvement:.4f}"
        metrics = {
            "improvement_rate": improvement_rate,
            "min_improvement": min_improvement,
            "window_values": recent_values,
        }
        return converged, reason, metrics

    def _check_combined_convergence(
        self,
        value: float,
        value_history: list[float],
        threshold: float,
        stability_window: int,
        min_variance: float,
        iteration: int,
    ) -> tuple[bool, str, dict]:
        """Check combined threshold and stability convergence."""
        # Check threshold first
        threshold_met, threshold_reason, threshold_metrics = (
            self._check_threshold_convergence(value, threshold, iteration)
        )

        # Check stability
        stability_met, stability_reason, stability_metrics = (
            self._check_stability_convergence(
                value_history, stability_window, min_variance, iteration
            )
        )

        # Both must be met for convergence
        converged = threshold_met and stability_met

        if converged:
            reason = f"Both conditions met: {threshold_reason} AND {stability_reason}"
        elif threshold_met:
            reason = f"Threshold met but unstable: {stability_reason}"
        else:
            reason = f"Threshold not met: {threshold_reason}"

        metrics = {
            "threshold_met": threshold_met,
            "stability_met": stability_met,
            **threshold_metrics,
            **stability_metrics,
        }

        return converged, reason, metrics

    def _check_custom_convergence(
        self,
        value: float,
        value_history: list[float],
        expression: str | None,
        iteration: int,
        **kwargs,
    ) -> tuple[bool, str, dict]:
        """Check custom convergence expression."""
        if not expression:
            return False, "No custom expression provided", {}

        try:
            # Create evaluation context
            eval_context = {
                "value": value,
                "iteration": iteration,
                "history": value_history,
                "len": len,
                "max": max,
                "min": min,
                "sum": sum,
                "abs": abs,
                **kwargs,  # Include all parameters
            }

            # Evaluate custom expression
            converged = bool(eval(expression, {"__builtins__": {}}, eval_context))
            reason = f"Custom expression '{expression}' = {converged}"
            metrics = {"custom_expression": expression, "eval_context": eval_context}

            return converged, reason, metrics

        except Exception as e:
            reason = f"Custom expression error: {e}"
            metrics = {"custom_expression": expression, "error": str(e)}
            return False, reason, metrics


@register_node()
class MultiCriteriaConvergenceNode(CycleAwareNode):
    """
    Node for checking convergence across multiple metrics simultaneously.

    This node monitors multiple values and applies different convergence
    criteria to each, allowing for complex multi-dimensional convergence
    checking.

    Example:
        >>> convergence = MultiCriteriaConvergenceNode()
        >>> workflow.add_node("convergence", convergence,
        ...     criteria={
        ...         "accuracy": {"threshold": 0.95, "mode": "threshold"},
        ...         "loss": {"threshold": 0.01, "mode": "threshold", "direction": "minimize"},
        ...         "stability": {"mode": "stability", "window": 5}
        ...     },
        ...     require_all=True
        ... )
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters for multi-criteria convergence."""
        return {
            "metrics": NodeParameter(
                name="metrics",
                type=dict,
                required=False,
                default={},
                description="Dictionary of metric_name: value pairs to monitor",
            ),
            "criteria": NodeParameter(
                name="criteria",
                type=dict,
                required=False,
                default={},
                description="Dictionary of convergence criteria for each metric",
            ),
            "require_all": NodeParameter(
                name="require_all",
                type=bool,
                required=False,
                default=True,
                description="Whether all criteria must be met (True) or any (False)",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute multi-criteria convergence checking."""
        # Get context
        context = kwargs.get("context", {})

        metrics = kwargs.get("metrics", {})

        # On first iteration, store criteria in state
        if self.is_first_iteration(context):
            criteria = kwargs.get("criteria", {})
            require_all = kwargs.get("require_all", True)
            # Store in cycle state for persistence
            self._stored_criteria = criteria
            self._stored_require_all = require_all
        else:
            # Use stored criteria from previous iterations
            criteria = getattr(self, "_stored_criteria", kwargs.get("criteria", {}))
            require_all = getattr(
                self, "_stored_require_all", kwargs.get("require_all", True)
            )

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Track metrics history
        metrics_history = prev_state.get("metrics_history", {})
        for metric_name, value in metrics.items():
            if metric_name not in metrics_history:
                metrics_history[metric_name] = []
            metrics_history[metric_name].append(value)
            # Keep last 100 values
            metrics_history[metric_name] = metrics_history[metric_name][-100:]

        # Check each criterion
        results = {}
        met_criteria = []
        failed_criteria = []

        for metric_name, criterion in criteria.items():
            if metric_name not in metrics:
                results[metric_name] = {
                    "converged": False,
                    "reason": f"Metric '{metric_name}' not provided",
                    "value": None,
                }
                failed_criteria.append(metric_name)
                continue

            value = metrics[metric_name]
            history = metrics_history.get(metric_name, [])

            # Create individual convergence checker
            checker = ConvergenceCheckerNode()

            # Prepare parameters for the checker
            checker_params = {"value": value, **criterion}

            # Use a mock context for the individual checker
            mock_context = {
                "cycle": {"iteration": iteration, "node_state": {"values": history}}
            }

            # Run individual convergence check
            result = checker.execute(context=mock_context, **checker_params)

            results[metric_name] = {
                "converged": result["converged"],
                "reason": result["reason"],
                "value": value,
                "metrics": result["convergence_metrics"],
            }

            if result["converged"]:
                met_criteria.append(metric_name)
            else:
                failed_criteria.append(metric_name)

        # Determine overall convergence
        if require_all:
            converged = len(failed_criteria) == 0
            if converged:
                reason = f"All {len(met_criteria)} criteria met"
            else:
                reason = f"{len(failed_criteria)} criteria not met: {failed_criteria}"
        else:
            converged = len(met_criteria) > 0
            if converged:
                reason = f"{len(met_criteria)} criteria met: {met_criteria}"
            else:
                reason = "No criteria met"

        # Log status
        self.log_cycle_info(
            context, f"Multi-criteria: {len(met_criteria)}/{len(criteria)} met"
        )

        return {
            "converged": converged,
            "reason": reason,
            "met_criteria": met_criteria,
            "failed_criteria": failed_criteria,
            "detailed_results": results,
            "iteration": iteration,
            "metrics": metrics,  # Pass through current metrics for cycle
            **self.set_cycle_state({"metrics_history": metrics_history}),
        }
