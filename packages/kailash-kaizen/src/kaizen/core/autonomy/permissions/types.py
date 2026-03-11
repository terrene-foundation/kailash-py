"""
Core types for the Permission System.

Defines permission modes, tool permissions, and related types.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Pattern


class PermissionMode(Enum):
    """
    Permission modes for agent execution.

    Defines how agent handles tool execution requests and risky operations.
    """

    DEFAULT = "default"
    """
    Default mode: Ask user for approval on risky operations (Bash, Write, Edit).

    Behavior:
    - Safe tools (Read, Grep, Glob): Auto-approved
    - Risky tools (Bash, PythonCode, Write, Edit): Ask for approval
    - Budget limits enforced
    """

    ACCEPT_EDITS = "accept_edits"
    """
    Accept edits mode: Auto-approve file modifications, ask for other risky tools.

    Behavior:
    - File operations (Write, Edit): Auto-approved
    - System operations (Bash, PythonCode): Still ask for approval
    - Read operations: Auto-approved
    - Budget limits enforced
    """

    PLAN = "plan"
    """
    Plan mode: Read-only, no execution allowed.

    Behavior:
    - Read operations (Read, Grep, Glob): Allowed
    - Execution operations (Bash, PythonCode, Write, Edit): Denied
    - Used for planning and analysis without side effects
    - Budget limits still enforced
    """

    BYPASS = "bypass"
    """
    Bypass mode: Disable all permission checks.

    Behavior:
    - All tools allowed without asking
    - No budget enforcement
    - No safety checks
    - Use ONLY in trusted environments or testing
    - **DANGEROUS**: Should not be used in production
    """


class PermissionType(Enum):
    """
    Permission decision types for tool execution.

    Defines the three possible outcomes of a permission check.
    """

    ALLOW = "ALLOW"
    """
    Allow tool execution without asking user.

    Used for:
    - Safe read operations (Read, Grep, Glob)
    - Pre-approved tools in ACCEPT_EDITS mode
    - All tools in BYPASS mode
    """

    DENY = "DENY"
    """
    Deny tool execution completely.

    Used for:
    - Execution operations in PLAN mode
    - Explicitly disallowed tools
    - Budget exceeded scenarios
    """

    ASK = "ASK"
    """
    Ask user for approval before executing tool.

    Used for:
    - Risky operations in DEFAULT mode (Bash, Write, Edit)
    - System operations in ACCEPT_EDITS mode
    - Any tool not explicitly allowed
    """


@dataclass
class ToolPermission:
    """
    Individual tool permission decision.

    Represents a permission decision for a specific tool execution request.
    """

    tool_name: str
    """Name of the tool (e.g., 'Read', 'Bash', 'Write')"""

    permission_type: str
    """Permission decision: 'ALLOW', 'DENY', or 'ASK'"""

    reason: str
    """Human-readable reason for this permission decision"""


@dataclass
class PermissionRule:
    """
    Rule for determining tool permissions via pattern matching.

    Supports regex patterns for flexible tool name matching with priority-based
    evaluation. Higher priority rules are evaluated first.

    Examples:
        >>> # Exact match
        >>> rule = PermissionRule(
        ...     pattern="read_file",
        ...     permission_type=PermissionType.ALLOW,
        ...     reason="Safe read operation"
        ... )
        >>> rule.matches("read_file")
        True

        >>> # Wildcard pattern (all file operations)
        >>> rule = PermissionRule(
        ...     pattern=".*_file",
        ...     permission_type=PermissionType.ALLOW,
        ...     reason="File operations"
        ... )
        >>> rule.matches("read_file")
        True
        >>> rule.matches("write_file")
        True

        >>> # Complex pattern (specific operations)
        >>> rule = PermissionRule(
        ...     pattern="(read|write|delete)_file",
        ...     permission_type=PermissionType.ALLOW,
        ...     reason="File CRUD operations"
        ... )
        >>> rule.matches("read_file")
        True
        >>> rule.matches("edit_file")
        False

        >>> # Priority-based evaluation
        >>> rules = [
        ...     PermissionRule(".*", PermissionType.ASK, "Default", priority=0),
        ...     PermissionRule("read_.*", PermissionType.ALLOW, "Safe", priority=5),
        ...     PermissionRule("bash_.*", PermissionType.DENY, "Dangerous", priority=10),
        ... ]
        >>> sorted_rules = sorted(rules, key=lambda r: r.priority, reverse=True)
        >>> sorted_rules[0].priority  # bash_.* evaluated first
        10
    """

    pattern: str
    """Regex pattern for tool name matching (e.g., 'read_.*', '.*_file')"""

    permission_type: PermissionType
    """Permission decision: ALLOW, DENY, or ASK"""

    reason: str
    """Human-readable reason for this permission rule"""

    priority: int = 0
    """
    Priority for rule evaluation (higher = evaluated first).

    Default: 0 (lowest priority)

    Usage:
    - High priority (10+): Explicit denials (e.g., bash_.*)
    - Medium priority (5-9): Specific allows (e.g., read_.*)
    - Low priority (0-4): Default/fallback rules (e.g., .*)
    """

    conditions: Optional[Dict[str, Any]] = None
    """
    Optional conditions for conditional permission evaluation.

    Reserved for future extension (e.g., cost limits, time restrictions).
    Currently unused but available for custom policy implementations.
    """

    def __post_init__(self):
        """
        Validate and compile regex pattern.

        Raises:
            ValueError: If pattern is empty or invalid regex
        """
        if not self.pattern:
            raise ValueError("Pattern cannot be empty")

        try:
            self._compiled_pattern: Pattern[str] = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{self.pattern}': {e}")

    def matches(self, tool_name: str) -> bool:
        """
        Check if tool name matches this rule's pattern.

        Uses fullmatch (not search) to ensure complete pattern match.

        Args:
            tool_name: Name of the tool to check (e.g., 'read_file', 'bash_command')

        Returns:
            True if tool name matches pattern, False otherwise

        Examples:
            >>> rule = PermissionRule("read_.*", PermissionType.ALLOW, "Safe")
            >>> rule.matches("read_file")
            True
            >>> rule.matches("write_file")
            False
        """
        return self._compiled_pattern.fullmatch(tool_name) is not None


class PermissionDeniedError(Exception):
    """
    Raised when tool execution is denied by permission system.

    This error is raised when:
    - Tool is in denied_tools list
    - Budget limit exceeded
    - User denies approval request
    - Permission policy blocks execution

    Examples:
        >>> raise PermissionDeniedError("Budget exceeded: $0.15/$0.10")
        >>> raise PermissionDeniedError("User denied approval for Bash")
        >>> raise PermissionDeniedError("Tool 'bash_command' not allowed in PLAN mode")
    """

    pass


# Export all public types
__all__ = [
    "PermissionMode",
    "PermissionType",
    "ToolPermission",
    "PermissionRule",
    "PermissionDeniedError",
]
