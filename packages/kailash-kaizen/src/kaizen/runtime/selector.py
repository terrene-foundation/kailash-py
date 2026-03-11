"""
Runtime Selector for Intelligent Runtime Selection

Provides RuntimeSelector class that chooses the best runtime adapter
for a given task based on capabilities, cost, latency, and user preferences.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from kaizen.runtime.adapter import RuntimeAdapter
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext

logger = logging.getLogger(__name__)


class SelectionStrategy(Enum):
    """Strategy for selecting a runtime."""

    CAPABILITY_MATCH = "capability_match"
    """Select first runtime that meets all requirements."""

    COST_OPTIMIZED = "cost_optimized"
    """Select cheapest runtime that meets requirements."""

    LATENCY_OPTIMIZED = "latency_optimized"
    """Select fastest runtime that meets requirements."""

    PREFERRED = "preferred"
    """Use preferred runtime if capable, fallback otherwise."""

    BALANCED = "balanced"
    """Balance between cost and latency."""


class RuntimeSelector:
    """Intelligent runtime selector for autonomous agent tasks.

    Analyzes task requirements and selects the most appropriate runtime
    based on capabilities, cost, latency, or user preferences.

    Example:
        >>> selector = RuntimeSelector({
        ...     "kaizen_local": kaizen_adapter,
        ...     "claude_code": claude_adapter,
        ... })
        >>>
        >>> # Select based on capabilities
        >>> adapter = selector.select(context, SelectionStrategy.CAPABILITY_MATCH)
        >>>
        >>> # Use preferred runtime with fallback
        >>> context.preferred_runtime = "claude_code"
        >>> adapter = selector.select(context, SelectionStrategy.PREFERRED)
    """

    def __init__(
        self,
        runtimes: Dict[str, RuntimeAdapter],
        default_runtime: str = "kaizen_local",
    ):
        """Initialize the selector with available runtimes.

        Args:
            runtimes: Dictionary mapping runtime names to adapter instances
            default_runtime: Name of default runtime to use as fallback
        """
        self.runtimes = runtimes
        self.default_runtime = default_runtime

    def select(
        self,
        context: ExecutionContext,
        strategy: SelectionStrategy = SelectionStrategy.CAPABILITY_MATCH,
    ) -> Optional[RuntimeAdapter]:
        """Select the best runtime for the given context.

        Args:
            context: Execution context with task and requirements
            strategy: Selection strategy to use

        Returns:
            Selected RuntimeAdapter, or None if no suitable runtime found
        """
        requirements = self._analyze_requirements(context)

        logger.debug(
            f"Selecting runtime for task with requirements: {requirements}, "
            f"strategy: {strategy.value}"
        )

        # Get capable runtimes
        capable_runtimes = self._get_capable_runtimes(requirements)

        if not capable_runtimes:
            logger.warning(
                f"No runtime meets requirements {requirements}, "
                f"falling back to {self.default_runtime}"
            )
            return self.runtimes.get(self.default_runtime)

        # Apply selection strategy
        if strategy == SelectionStrategy.CAPABILITY_MATCH:
            return self._select_capability_match(capable_runtimes, context)
        elif strategy == SelectionStrategy.COST_OPTIMIZED:
            return self._select_cost_optimized(capable_runtimes, context)
        elif strategy == SelectionStrategy.LATENCY_OPTIMIZED:
            return self._select_latency_optimized(capable_runtimes, context)
        elif strategy == SelectionStrategy.PREFERRED:
            return self._select_preferred(capable_runtimes, context)
        elif strategy == SelectionStrategy.BALANCED:
            return self._select_balanced(capable_runtimes, context)
        else:
            return capable_runtimes[0][1]

    def _analyze_requirements(self, context: ExecutionContext) -> List[str]:
        """Extract capability requirements from execution context.

        Analyzes the task, tools, and constraints to determine what
        capabilities are needed.

        Args:
            context: Execution context to analyze

        Returns:
            List of required capability names
        """
        requirements = []

        # Tool-based requirements
        if context.tools:
            requirements.append("tool_calling")

            # Check for specific tool types
            for tool in context.tools:
                tool_name = tool.get("function", {}).get("name", "").lower()
                tool_name = tool.get("name", tool_name).lower()

                if any(kw in tool_name for kw in ["file", "read", "write", "edit"]):
                    requirements.append("file_access")
                if any(kw in tool_name for kw in ["web", "fetch", "http", "url"]):
                    requirements.append("web_access")
                if any(kw in tool_name for kw in ["bash", "shell", "command", "exec"]):
                    requirements.append("code_execution")
                if any(kw in tool_name for kw in ["image", "vision", "screenshot"]):
                    requirements.append("vision")

        # Task-based requirements
        task_lower = context.task.lower()

        task_capability_map = {
            "vision": ["image", "screenshot", "picture", "photo", "see", "look at"],
            "audio": ["audio", "sound", "voice", "listen", "hear"],
            "code_execution": ["run", "execute", "bash", "terminal", "command"],
            "file_access": ["file", "read", "write", "save", "create file"],
            "web_access": ["fetch", "download", "url", "website", "http"],
        }

        for capability, keywords in task_capability_map.items():
            if any(kw in task_lower for kw in keywords):
                if capability not in requirements:
                    requirements.append(capability)

        # Context-based requirements
        if context.memory_context or context.conversation_history:
            # Larger context might need more tokens
            pass

        # Interrupt support for long tasks
        if context.timeout_seconds and context.timeout_seconds > 60:
            requirements.append("interrupt")

        return list(set(requirements))  # Remove duplicates

    def _get_capable_runtimes(
        self,
        requirements: List[str],
    ) -> List[Tuple[str, RuntimeAdapter]]:
        """Get list of runtimes that meet all requirements.

        Args:
            requirements: List of required capabilities

        Returns:
            List of (name, adapter) tuples for capable runtimes
        """
        capable = []

        for name, adapter in self.runtimes.items():
            caps = adapter.capabilities
            if caps.meets_requirements(requirements):
                capable.append((name, adapter))
            else:
                missing = caps.get_missing_requirements(requirements)
                logger.debug(f"Runtime {name} missing requirements: {missing}")

        return capable

    def _select_capability_match(
        self,
        capable_runtimes: List[Tuple[str, RuntimeAdapter]],
        context: ExecutionContext,
    ) -> RuntimeAdapter:
        """Select first runtime that matches capabilities.

        Prefers default runtime if it's capable.
        """
        # Prefer default if capable
        for name, adapter in capable_runtimes:
            if name == self.default_runtime:
                return adapter

        # Otherwise return first capable
        return capable_runtimes[0][1]

    def _select_cost_optimized(
        self,
        capable_runtimes: List[Tuple[str, RuntimeAdapter]],
        context: ExecutionContext,
    ) -> RuntimeAdapter:
        """Select cheapest runtime based on estimated cost."""
        # Estimate input tokens (rough heuristic)
        estimated_input = len(context.task) // 4
        if context.memory_context:
            estimated_input += len(context.memory_context) // 4
        for msg in context.conversation_history:
            estimated_input += len(msg.get("content", "")) // 4

        # Estimate output tokens
        estimated_output = context.max_tokens or 1000

        def get_cost(adapter: RuntimeAdapter) -> float:
            cost = adapter.capabilities.estimated_cost(
                estimated_input, estimated_output
            )
            return cost if cost is not None else float("inf")

        # Sort by cost
        sorted_runtimes = sorted(
            capable_runtimes,
            key=lambda x: get_cost(x[1]),
        )

        return sorted_runtimes[0][1]

    def _select_latency_optimized(
        self,
        capable_runtimes: List[Tuple[str, RuntimeAdapter]],
        context: ExecutionContext,
    ) -> RuntimeAdapter:
        """Select fastest runtime based on typical latency."""

        def get_latency(adapter: RuntimeAdapter) -> float:
            latency = adapter.capabilities.typical_latency_ms
            return latency if latency is not None else float("inf")

        # Sort by latency
        sorted_runtimes = sorted(
            capable_runtimes,
            key=lambda x: get_latency(x[1]),
        )

        return sorted_runtimes[0][1]

    def _select_preferred(
        self,
        capable_runtimes: List[Tuple[str, RuntimeAdapter]],
        context: ExecutionContext,
    ) -> RuntimeAdapter:
        """Use preferred runtime if capable, otherwise fallback."""
        if context.preferred_runtime:
            for name, adapter in capable_runtimes:
                if name == context.preferred_runtime:
                    return adapter

            logger.warning(
                f"Preferred runtime '{context.preferred_runtime}' not capable, "
                f"using fallback"
            )

        # Fallback to capability match
        return self._select_capability_match(capable_runtimes, context)

    def _select_balanced(
        self,
        capable_runtimes: List[Tuple[str, RuntimeAdapter]],
        context: ExecutionContext,
    ) -> RuntimeAdapter:
        """Balance between cost and latency using scoring.

        Uses a weighted score combining normalized cost and latency.
        """
        # Collect metrics
        costs = []
        latencies = []

        for _, adapter in capable_runtimes:
            caps = adapter.capabilities

            # Get cost (default to high if unknown)
            input_cost = caps.cost_per_1k_input_tokens or 0.1
            output_cost = caps.cost_per_1k_output_tokens or 0.1
            costs.append(input_cost + output_cost)

            # Get latency (default to high if unknown)
            latency = caps.typical_latency_ms or 1000
            latencies.append(latency)

        # Normalize to 0-1 range
        max_cost = max(costs) if costs else 1
        max_latency = max(latencies) if latencies else 1

        def score(idx: int) -> float:
            norm_cost = costs[idx] / max_cost if max_cost else 0
            norm_latency = latencies[idx] / max_latency if max_latency else 0
            # Equal weight to cost and latency
            return 0.5 * norm_cost + 0.5 * norm_latency

        # Find best score (lowest)
        best_idx = min(range(len(capable_runtimes)), key=score)
        return capable_runtimes[best_idx][1]

    def get_all_capabilities(self) -> Dict[str, RuntimeCapabilities]:
        """Get capabilities for all registered runtimes.

        Returns:
            Dictionary mapping runtime names to their capabilities
        """
        return {name: adapter.capabilities for name, adapter in self.runtimes.items()}

    def get_capable_runtimes_for_task(
        self,
        context: ExecutionContext,
    ) -> List[str]:
        """Get names of all runtimes capable of handling the task.

        Args:
            context: Execution context to analyze

        Returns:
            List of runtime names
        """
        requirements = self._analyze_requirements(context)
        capable = self._get_capable_runtimes(requirements)
        return [name for name, _ in capable]

    def explain_selection(
        self,
        context: ExecutionContext,
        strategy: SelectionStrategy = SelectionStrategy.CAPABILITY_MATCH,
    ) -> Dict[str, Any]:
        """Explain why a runtime was selected.

        Useful for debugging and understanding selection decisions.

        Args:
            context: Execution context
            strategy: Selection strategy

        Returns:
            Dictionary with selection explanation
        """
        requirements = self._analyze_requirements(context)
        capable = self._get_capable_runtimes(requirements)
        selected = self.select(context, strategy)

        return {
            "requirements": requirements,
            "capable_runtimes": [name for name, _ in capable],
            "strategy": strategy.value,
            "selected": selected.capabilities.runtime_name if selected else None,
            "reason": self._explain_selection_reason(
                requirements, capable, selected, strategy, context
            ),
        }

    def _explain_selection_reason(
        self,
        requirements: List[str],
        capable: List[Tuple[str, RuntimeAdapter]],
        selected: Optional[RuntimeAdapter],
        strategy: SelectionStrategy,
        context: ExecutionContext,
    ) -> str:
        """Generate human-readable explanation for selection."""
        if not selected:
            return "No runtime meets the requirements"

        if not capable:
            return f"No capable runtime found, using default ({self.default_runtime})"

        selected_name = selected.capabilities.runtime_name

        if strategy == SelectionStrategy.CAPABILITY_MATCH:
            if selected_name == self.default_runtime:
                return f"Default runtime '{selected_name}' meets all requirements"
            return f"Selected '{selected_name}' as first capable runtime"

        elif strategy == SelectionStrategy.COST_OPTIMIZED:
            return f"Selected '{selected_name}' as lowest cost option"

        elif strategy == SelectionStrategy.LATENCY_OPTIMIZED:
            return f"Selected '{selected_name}' as lowest latency option"

        elif strategy == SelectionStrategy.PREFERRED:
            if context.preferred_runtime == selected_name:
                return f"Used preferred runtime '{selected_name}'"
            return f"Preferred runtime not capable, fell back to '{selected_name}'"

        elif strategy == SelectionStrategy.BALANCED:
            return f"Selected '{selected_name}' with best cost/latency balance"

        return f"Selected '{selected_name}'"
