"""
Base class for cycle-aware nodes that provides built-in helpers for cyclic workflow patterns.

This module provides CycleAwareNode, a base class that eliminates boilerplate code
for nodes that need to work with cyclic workflows. It provides convenient methods
for accessing cycle information, managing state across iterations, and implementing
common cycle patterns.

Design Philosophy:
    CycleAwareNode abstracts away the complexity of managing state and iteration
    tracking in cyclic workflows. It provides a clean API for nodes to focus on
    their business logic while the base class handles cycle mechanics.

Example usage:
    >>> from kailash.nodes.base_cycle_aware import CycleAwareNode
    >>> from kailash.nodes.base import NodeParameter
    >>>
    >>> class MyProcessorNode(CycleAwareNode):
    ...     def get_parameters(self):
    ...         return {
    ...             "data": NodeParameter(name="data", type=list, required=True)
    ...         }
    ...
    ...     def run(self, **kwargs):
    ...         context = kwargs.get("context", {})
    ...         iteration = self.get_iteration(context)
    ...         is_first = self.is_first_iteration(context)
    ...         prev_results = self.get_previous_state(context)
    ...
    ...         # Process data with cycle awareness
    ...         processed = self.process_with_history(kwargs["data"], prev_results)
    ...
    ...         # Return result with state for next iteration
    ...         return {
    ...             "result": processed,
    ...             **self.set_cycle_state({"last_result": processed})
    ...         }
"""

import time
from typing import Any

from .base import Node


class CycleAwareNode(Node):
    """
    Base class for nodes that are cycle-aware with built-in helpers.

    This class provides convenient methods for working with cyclic workflows,
    eliminating common boilerplate code for cycle information access and
    state management across iterations.

    Design Philosophy:
        CycleAwareNode is designed to make cyclic workflows as simple to write
        as regular nodes. It handles all the complexity of iteration tracking,
        state persistence, and cycle information management, allowing developers
        to focus on the iterative logic.

    Upstream Dependencies:
        - Node: Base class that provides core node functionality
        - CyclicWorkflowExecutor: Provides cycle context in execution
        - Workflow: Must be configured with cycle=True connections

    Downstream Consumers:
        - ConvergenceCheckerNode: Uses cycle helpers for convergence detection
        - A2ACoordinatorNode: Tracks agent performance across iterations
        - Any custom nodes needing cycle-aware behavior

    Configuration:
        No specific configuration required. Inherit from this class and use
        the provided helper methods in your run() implementation.

    Implementation Details:
        - Extracts cycle information from execution context
        - Provides safe accessors with sensible defaults
        - Manages state persistence through _cycle_state convention
        - Offers utility methods for common patterns

    Error Handling:
        - Returns default values if cycle information is missing
        - Handles missing state gracefully with empty dicts
        - Safe for use in non-cyclic contexts (acts as regular node)

    Side Effects:
        - Logs cycle progress when log_cycle_info() is called
        - No other external side effects

    Examples:
        >>> class QualityImproverNode(CycleAwareNode):
        ...     def run(self, **kwargs):
        ...         context = kwargs.get("context", {})
        ...         iteration = self.get_iteration(context)
        ...         quality = kwargs.get("quality", 0.0)
        ...
        ...         if self.is_first_iteration(context):
        ...             print("Starting quality improvement process")
        ...
        ...         # Improve quality based on iteration
        ...         improved_quality = quality + (0.1 * iteration)
        ...
        ...         return {
        ...             "quality": improved_quality,
        ...             **self.set_cycle_state({"last_quality": improved_quality})
        ...         }
    """

    def get_cycle_info(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Get cycle information with sensible defaults.

        Extracts cycle information from the execution context, providing
        default values for missing fields to prevent KeyError exceptions.

        Args:
            context: Execution context containing cycle information

        Returns:
            Dictionary containing cycle information with guaranteed fields:
            - iteration: Current iteration number (default: 0)
            - elapsed_time: Time elapsed in seconds (default: 0.0)
            - cycle_id: Unique cycle identifier (default: "default")
            - max_iterations: Maximum allowed iterations (default: 100)
            - start_time: Cycle start timestamp (default: current time)

        Example:
            >>> cycle_info = self.get_cycle_info(context)
            >>> print(f"Iteration {cycle_info['iteration']} of {cycle_info['max_iterations']}")
        """
        cycle_info = context.get("cycle", {})
        current_time = time.time()

        return {
            "iteration": cycle_info.get("iteration", 0),
            "elapsed_time": cycle_info.get("elapsed_time", 0.0),
            "cycle_id": cycle_info.get("cycle_id", "default"),
            "max_iterations": cycle_info.get("max_iterations", 100),
            "start_time": cycle_info.get("start_time", current_time),
            "convergence_check": cycle_info.get("convergence_check"),
            **cycle_info,  # Include any additional cycle information
        }

    def get_iteration(self, context: dict[str, Any]) -> int:
        """
        Get current iteration number.

        Args:
            context: Execution context

        Returns:
            Current iteration number (0-based)

        Example:
            >>> iteration = self.get_iteration(context)
            >>> if iteration > 10:
            ...     print("Long-running cycle detected")
        """
        return self.get_cycle_info(context)["iteration"]

    def is_first_iteration(self, context: dict[str, Any]) -> bool:
        """
        Check if this is the first iteration of the cycle.

        Args:
            context: Execution context

        Returns:
            True if this is iteration 0, False otherwise

        Example:
            >>> if self.is_first_iteration(context):
            ...     print("Initializing cycle state")
            ...     return self.initialize_state()
        """
        return self.get_iteration(context) == 0

    def is_last_iteration(self, context: dict[str, Any]) -> bool:
        """
        Check if this is the last iteration of the cycle.

        Args:
            context: Execution context

        Returns:
            True if this is the final iteration, False otherwise

        Example:
            >>> if self.is_last_iteration(context):
            ...     print("Performing final cleanup")
        """
        cycle_info = self.get_cycle_info(context)
        return cycle_info["iteration"] >= cycle_info["max_iterations"] - 1

    def get_previous_state(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Get previous iteration state safely.

        Retrieves state that was persisted from the previous iteration
        using set_cycle_state(). Returns empty dict if no state exists.

        Args:
            context: Execution context

        Returns:
            Dictionary containing state from previous iteration

        Example:
            >>> prev_state = self.get_previous_state(context)
            >>> history = prev_state.get("value_history", [])
            >>> print(f"Previous values: {history}")
        """
        return self.get_cycle_info(context).get("node_state", {})

    def set_cycle_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Set state to persist to next iteration.

        Creates the special _cycle_state return value that the cycle
        executor will persist and make available in the next iteration
        via get_previous_state().

        Args:
            state: Dictionary of state to persist

        Returns:
            Dictionary with _cycle_state key for return from run()

        Example:
            >>> # In run() method:
            >>> current_values = [1, 2, 3]
            >>> return {
            ...     "result": processed_data,
            ...     **self.set_cycle_state({"values": current_values})
            ... }
        """
        return {"_cycle_state": state}

    def get_cycle_progress(self, context: dict[str, Any]) -> float:
        """
        Get cycle progress as a percentage.

        Args:
            context: Execution context

        Returns:
            Progress percentage (0.0 to 1.0)

        Example:
            >>> progress = self.get_cycle_progress(context)
            >>> print(f"Cycle {progress*100:.1f}% complete")
        """
        cycle_info = self.get_cycle_info(context)
        iteration = cycle_info["iteration"]
        max_iterations = cycle_info["max_iterations"]

        if max_iterations <= 0:
            return 1.0

        return min(iteration / max_iterations, 1.0)

    def log_cycle_info(self, context: dict[str, Any], message: str = "") -> None:
        """
        Log cycle information for debugging.

        Convenient method to log current cycle state with optional message.

        Args:
            context: Execution context
            message: Optional message to include in log

        Example:
            >>> self.log_cycle_info(context, "Processing batch")
            # Output: [Cycle default] Iteration 3/10 (30.0%): Processing batch
        """
        cycle_info = self.get_cycle_info(context)
        progress = self.get_cycle_progress(context)

        log_msg = (
            f"[Cycle {cycle_info['cycle_id']}] "
            f"Iteration {cycle_info['iteration']}/{cycle_info['max_iterations']} "
            f"({progress*100:.1f}%)"
        )

        if message:
            log_msg += f": {message}"

        print(log_msg)

    def should_continue_cycle(self, context: dict[str, Any], **kwargs) -> bool:
        """
        Helper method to determine if cycle should continue.

        This is a convenience method that can be overridden by subclasses
        to implement custom continuation logic. Default implementation
        checks if max iterations reached.

        Args:
            context: Execution context
            **kwargs: Additional parameters for decision making

        Returns:
            True if cycle should continue, False otherwise

        Example:
            >>> def should_continue_cycle(self, context, **kwargs):
            ...     quality = kwargs.get("quality", 0.0)
            ...     return quality < 0.95 and not self.is_last_iteration(context)
        """
        return not self.is_last_iteration(context)

    def accumulate_values(
        self, context: dict[str, Any], key: str, value: Any, max_history: int = 100
    ) -> list:
        """
        Accumulate values across iterations with automatic history management.

        Convenience method for maintaining a list of values across iterations
        with automatic size management to prevent memory growth.

        Args:
            context: Execution context
            key: State key for the value list
            value: Value to add to the list
            max_history: Maximum number of values to keep

        Returns:
            Updated list of values

        Example:
            >>> quality_history = self.accumulate_values(context, "quality", current_quality)
            >>> avg_quality = sum(quality_history) / len(quality_history)
        """
        prev_state = self.get_previous_state(context)
        values = prev_state.get(key, [])
        values.append(value)

        # Keep only recent values to prevent memory growth
        if len(values) > max_history:
            values = values[-max_history:]

        return values

    def detect_convergence_trend(
        self,
        context: dict[str, Any],
        key: str,
        threshold: float = 0.01,
        window: int = 3,
    ) -> bool:
        """
        Detect if values are converging (becoming stable).

        Analyzes recent values to determine if they are converging to a stable value.

        Args:
            context: Execution context
            key: State key containing value history
            threshold: Maximum variance for convergence
            window: Number of recent values to analyze

        Returns:
            True if values are converging, False otherwise

        Example:
            >>> if self.detect_convergence_trend(context, "error_rate", 0.001):
            ...     return {"converged": True, "reason": "error_rate_stable"}
        """
        prev_state = self.get_previous_state(context)
        values = prev_state.get(key, [])

        if len(values) < window:
            return False

        recent_values = values[-window:]
        variance = max(recent_values) - min(recent_values)
        return variance <= threshold
