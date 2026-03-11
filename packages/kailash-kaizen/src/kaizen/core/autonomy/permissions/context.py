"""
Execution context for permission tracking.

Manages runtime permission state including budget, tool usage, and allowed/denied tools.
Thread-safe for concurrent tool execution.
"""

import threading
from typing import Literal

from kaizen.core.autonomy.permissions.types import PermissionMode, PermissionRule


class ExecutionContext:
    """
    Runtime permission state for agent execution.

    Tracks budget usage, tool permissions, and usage counts during agent execution.
    Thread-safe with internal locking for concurrent tool execution.

    Examples:
        >>> # Basic usage
        >>> ctx = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=10.0)
        >>> ctx.can_use_tool("Read")  # True (safe tool)
        >>> ctx.record_tool_usage("Read", cost_usd=0.5)
        >>> ctx.budget_used  # 0.5

        >>> # Thread-safe budget tracking
        >>> ctx = ExecutionContext(budget_limit=100.0)
        >>> # Safe to call from multiple threads
        >>> ctx.record_tool_usage("LLMNode", cost_usd=2.5)
    """

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        budget_limit: float | None = None,
        allowed_tools: set[str] | None = None,
        denied_tools: set[str] | None = None,
        rules: list[PermissionRule] | None = None,
    ):
        """
        Initialize execution context.

        Args:
            mode: Permission mode (DEFAULT, ACCEPT_EDITS, PLAN, BYPASS)
            budget_limit: Maximum budget in USD (None = unlimited)
            allowed_tools: Set of explicitly allowed tool names
            denied_tools: Set of explicitly denied tool names
            rules: List of permission rules for pattern-based matching
        """
        self.mode = mode
        self.budget_limit = budget_limit
        self.budget_used = 0.0
        self.allowed_tools = allowed_tools or set()
        self.denied_tools = denied_tools or set()
        self.rules = rules or []
        self.tool_usage_count: dict[str, int] = {}

        # Thread safety
        self._lock = threading.Lock()

    def can_use_tool(self, tool_name: str) -> bool:
        """
        Check if tool is allowed based on allowed/denied lists.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is allowed, False if denied

        Note:
            - If tool in denied_tools → False
            - If tool in allowed_tools → True
            - If tool not in either list → True (default allow)
        """
        with self._lock:
            # Explicit deny takes precedence
            if tool_name in self.denied_tools:
                return False

            # Explicit allow or default allow
            if tool_name in self.allowed_tools:
                return True

            # Default: allow if not explicitly denied
            return True

    def record_tool_usage(self, tool_name: str, cost_usd: float) -> None:
        """
        Record tool usage and update budget.

        Thread-safe operation that increments usage count and adds cost to budget.

        Args:
            tool_name: Name of the tool used
            cost_usd: Cost of this tool execution in USD
        """
        with self._lock:
            # Increment usage count
            if tool_name not in self.tool_usage_count:
                self.tool_usage_count[tool_name] = 0
            self.tool_usage_count[tool_name] += 1

            # Add to budget
            self.budget_used += cost_usd

    def has_budget(self, estimated_cost: float) -> bool:
        """
        Check if there is sufficient budget for estimated cost.

        Args:
            estimated_cost: Estimated cost in USD for next operation

        Returns:
            True if budget available, False if would exceed limit

        Note:
            If no budget_limit set, always returns True (unlimited budget)
        """
        with self._lock:
            # No budget limit = always has budget
            if self.budget_limit is None:
                return True

            # Check if estimated cost would exceed budget
            projected_total = self.budget_used + estimated_cost
            return projected_total <= self.budget_limit

    def add_tool_permission(
        self,
        tool_name: str,
        action: Literal["allow", "deny"],
    ) -> None:
        """
        Add tool to allowed or denied list.

        Thread-safe operation for dynamic permission updates during execution.

        Args:
            tool_name: Name of the tool to allow/deny
            action: "allow" to add to allowed_tools, "deny" to add to denied_tools
        """
        with self._lock:
            if action == "allow":
                self.allowed_tools.add(tool_name)
                # Remove from denied if present
                self.denied_tools.discard(tool_name)
            elif action == "deny":
                self.denied_tools.add(tool_name)
                # Remove from allowed if present
                self.allowed_tools.discard(tool_name)


# Export all public types
__all__ = [
    "ExecutionContext",
]
