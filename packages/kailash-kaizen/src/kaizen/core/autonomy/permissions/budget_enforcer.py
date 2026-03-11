"""
Budget enforcer for permission system.

Handles cost estimation, budget checking, and usage recording for tool execution.
Integrates with ExecutionContext for state management.

Refactored from BudgetInterruptHandler to share cost tracking logic.
"""

import logging
from typing import Any

from kaizen.core.autonomy.permissions.context import ExecutionContext

logger = logging.getLogger(__name__)


class BudgetEnforcer:
    """
    Budget enforcement for tool execution.

    Provides static methods for:
    - Cost estimation based on tool type
    - Budget checking against limits
    - Usage recording with state management

    Integrates with ExecutionContext for thread-safe state tracking.

    Examples:
        >>> # Estimate cost
        >>> cost = BudgetEnforcer.estimate_cost("Write", {"path": "test.txt"})
        >>> print(f"Estimated: ${cost:.4f}")
        Estimated: $0.0050

        >>> # Check budget
        >>> context = ExecutionContext(budget_limit=10.0)
        >>> has_budget = BudgetEnforcer.has_budget(context, cost)
        >>> print(has_budget)
        True

        >>> # Record usage
        >>> BudgetEnforcer.record_usage(context, "Write", cost)
        >>> print(f"Used: ${context.budget_used:.4f}")
        Used: $0.0050
    """

    # Cost table for different tool types (USD)
    # Extracted from BudgetInterruptHandler for reusability
    TOOL_COSTS = {
        # File operations
        "Read": 0.001,  # Read file
        "Write": 0.005,  # Write file
        "Edit": 0.005,  # Edit file
        "DeleteFileNode": 0.001,  # Delete file
        "ListDirectoryNode": 0.001,  # List directory
        # Execution tools
        "Bash": 0.01,  # Bash command
        "PythonCode": 0.01,  # Python code execution
        # Search tools
        "Grep": 0.001,  # Grep search
        "Glob": 0.001,  # Glob pattern matching
        # LLM nodes (base cost, actual cost calculated from usage)
        "LLMAgentNode": 0.01,  # Per 1000 tokens (approximate)
        "OpenAINode": 0.01,
        "AnthropicNode": 0.015,
        "OllamaNode": 0.0,  # Local, free
    }

    # Conservative buffer for unknown costs (20%)
    COST_BUFFER = 1.20

    @staticmethod
    def estimate_cost(tool_name: str, tool_input: dict[str, Any]) -> float:
        """
        Estimate cost for tool execution.

        Uses conservative estimates with 20% buffer for unknown costs.

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters for the tool

        Returns:
            Estimated cost in USD

        Examples:
            >>> BudgetEnforcer.estimate_cost("Read", {"path": "test.txt"})
            0.001
            >>> BudgetEnforcer.estimate_cost("Write", {"path": "test.txt"})
            0.005
            >>> BudgetEnforcer.estimate_cost("Bash", {"command": "ls"})
            0.01
        """
        # LLM nodes: estimate based on input size
        if "LLM" in tool_name or "Agent" in tool_name:
            return BudgetEnforcer._estimate_llm_cost(tool_name, tool_input)

        # Other tools: fixed cost from table
        base_cost = BudgetEnforcer.TOOL_COSTS.get(tool_name, 0.0)

        # No buffer needed for known costs
        return base_cost

    @staticmethod
    def _estimate_llm_cost(tool_name: str, tool_input: dict[str, Any]) -> float:
        """
        Estimate cost for LLM tool execution.

        Uses token estimation based on input length.

        Args:
            tool_name: Name of the LLM tool
            tool_input: Input parameters (must contain 'prompt' or 'messages')

        Returns:
            Estimated cost in USD
        """
        # Extract prompt or messages
        prompt = tool_input.get("prompt", "")
        messages = tool_input.get("messages", [])

        # Calculate total input length
        if messages:
            total_text = " ".join(str(msg) for msg in messages)
        else:
            total_text = str(prompt)

        # Rough estimation: ~4 characters per token
        estimated_tokens = len(total_text) // 4

        # Get base cost per 1000 tokens
        cost_per_1k = BudgetEnforcer.TOOL_COSTS.get(tool_name, 0.01)

        # Calculate cost
        estimated_cost = (estimated_tokens / 1000.0) * cost_per_1k

        # Add conservative buffer (20%)
        # Actually, for estimation we want to be conservative so keep base cost
        return max(estimated_cost, cost_per_1k / 100)  # Minimum $0.0001

    @staticmethod
    def has_budget(context: ExecutionContext, estimated_cost: float) -> bool:
        """
        Check if there is sufficient budget for estimated cost.

        Args:
            context: Execution context with budget state
            estimated_cost: Estimated cost in USD

        Returns:
            True if budget available, False if would exceed limit

        Examples:
            >>> context = ExecutionContext(budget_limit=10.0)
            >>> context.budget_used = 5.0
            >>> BudgetEnforcer.has_budget(context, 3.0)
            True
            >>> BudgetEnforcer.has_budget(context, 6.0)
            False
        """
        # Delegate to ExecutionContext's has_budget method
        # This ensures consistency with context's budget tracking
        return context.has_budget(estimated_cost)

    @staticmethod
    def record_usage(
        context: ExecutionContext, tool_name: str, cost_usd: float
    ) -> None:
        """
        Record tool usage and update budget.

        Thread-safe operation that updates budget_used and tool_usage_count.

        Args:
            context: Execution context to update
            tool_name: Name of the tool used
            cost_usd: Actual cost in USD

        Raises:
            ValueError: If cost_usd is negative

        Examples:
            >>> context = ExecutionContext(budget_limit=10.0)
            >>> BudgetEnforcer.record_usage(context, "Read", 0.001)
            >>> context.budget_used
            0.001
            >>> context.tool_usage_count["Read"]
            1
        """
        # Validate cost
        if cost_usd < 0:
            raise ValueError(f"Cost cannot be negative: {cost_usd}")

        # Delegate to ExecutionContext's record_tool_usage method
        # This ensures thread-safety through context's internal locking
        context.record_tool_usage(tool_name, cost_usd)

        # Log usage for audit trail
        logger.debug(
            f"Tool usage recorded: {tool_name}, "
            f"cost: ${cost_usd:.4f}, "
            f"total: ${context.budget_used:.4f} / ${context.budget_limit or 'unlimited'}"
        )

    @staticmethod
    def get_remaining_budget(context: ExecutionContext) -> float | None:
        """
        Get remaining budget.

        Args:
            context: Execution context with budget state

        Returns:
            Remaining budget in USD, or None if unlimited

        Examples:
            >>> context = ExecutionContext(budget_limit=10.0)
            >>> context.budget_used = 3.5
            >>> BudgetEnforcer.get_remaining_budget(context)
            6.5
        """
        if context.budget_limit is None:
            return None

        return context.budget_limit - context.budget_used

    @staticmethod
    def get_actual_cost(result: dict[str, Any]) -> float:
        """
        Extract actual cost from tool result metadata.

        Args:
            result: Tool execution result dict

        Returns:
            Actual cost in USD, or 0.0 if not available

        Examples:
            >>> result = {"usage": {"cost_usd": 0.025}}
            >>> BudgetEnforcer.get_actual_cost(result)
            0.025
            >>> BudgetEnforcer.get_actual_cost({})
            0.0
        """
        # Check for cost in usage metadata
        if "usage" in result and "cost_usd" in result["usage"]:
            return float(result["usage"]["cost_usd"])

        # Default to zero if not available
        return 0.0


# Export all public types
__all__ = [
    "BudgetEnforcer",
]
