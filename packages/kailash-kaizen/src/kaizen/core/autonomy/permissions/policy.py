"""
Permission policy decision engine.

Implements the 8-layer permission decision logic for safe autonomous agent operation.
"""

import logging
from typing import Optional, Tuple

from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.types import PermissionMode, PermissionType

logger = logging.getLogger(__name__)


class PermissionPolicy:
    """
    Permission decision engine with 8-layer evaluation logic.

    Evaluates tool execution requests through a series of checks:
    1. BYPASS mode (skip all checks)
    2. ACCEPT_EDITS mode (auto-approve file edits)
    3. PLAN mode (read-only restrictions)
    4. Explicit denied tools
    5. Explicit allowed tools
    6. Permission rules (pattern matching)
    7. Budget exhaustion
    8. Mode-based defaults / ASK fallback

    Returns:
        (True, None): Allow tool execution
        (False, reason): Deny tool execution with reason
        (None, None): Ask user for approval
    """

    def __init__(self, context: ExecutionContext):
        """
        Initialize permission policy.

        Args:
            context: Execution context tracking runtime state
        """
        self.context = context

    def check_permission(
        self,
        tool_name: str,
        tool_input: dict,
        estimated_cost: float = 0.0,
    ) -> Tuple[Optional[bool], Optional[str]]:
        """
        Check if tool execution is permitted.

        Implements 8-layer decision logic as specified in ADR-012.

        Args:
            tool_name: Name of the tool to execute (e.g., 'Read', 'Bash', 'Write')
            tool_input: Input parameters for the tool
            estimated_cost: Estimated cost in USD for this tool execution

        Returns:
            Tuple of (decision, reason):
            - (True, None): Allow tool execution
            - (False, reason): Deny with human-readable reason
            - (None, None): Ask user for approval

        Examples:
            >>> # BYPASS mode allows everything
            >>> ctx = ExecutionContext(mode=PermissionMode.BYPASS)
            >>> policy = PermissionPolicy(ctx)
            >>> policy.check_permission("Bash", {"command": "rm -rf /"}, 0.0)
            (True, None)

            >>> # DEFAULT mode asks for risky tools
            >>> ctx = ExecutionContext(mode=PermissionMode.DEFAULT)
            >>> policy = PermissionPolicy(ctx)
            >>> policy.check_permission("Bash", {"command": "ls"}, 0.0)
            (None, None)

            >>> # Budget exceeded
            >>> ctx = ExecutionContext(budget_limit=10.0)
            >>> ctx.budget_used = 9.5
            >>> policy = PermissionPolicy(ctx)
            >>> policy.check_permission("LLMNode", {}, 1.0)
            (False, 'Budget exceeded: ...')
        """

        # ──────────────────────────────────────────────────────────
        # LAYER 1: BYPASS MODE - Skip all checks (early exit)
        # ──────────────────────────────────────────────────────────
        if self.context.mode == PermissionMode.BYPASS:
            logger.debug(f"BYPASS mode: Allowing tool '{tool_name}' without checks")
            return True, None

        # ──────────────────────────────────────────────────────────
        # LAYER 2: BUDGET CHECK - Check budget BEFORE mode checks
        # ──────────────────────────────────────────────────────────
        if not self.context.has_budget(estimated_cost):
            remaining = (
                self.context.budget_limit - self.context.budget_used
                if self.context.budget_limit is not None
                else 0.0
            )
            reason = (
                f"Budget exceeded: ${self.context.budget_used:.2f} spent, "
                f"${remaining:.2f} remaining, tool needs ${estimated_cost:.2f}"
            )
            logger.warning(f"Budget exceeded for tool '{tool_name}': {reason}")
            return False, reason

        # ──────────────────────────────────────────────────────────
        # LAYER 3: PLAN MODE - Read-only restrictions
        # ──────────────────────────────────────────────────────────
        if self.context.mode == PermissionMode.PLAN:
            # Read-only tools are allowed
            read_only_tools = {"Read", "Grep", "Glob", "ListDirectoryNode"}
            if tool_name in read_only_tools:
                logger.debug(f"PLAN mode: Allowing read-only tool '{tool_name}'")
                return True, None

            # All other tools are denied in PLAN mode
            reason = f"Plan mode: Only read-only tools allowed (tried: {tool_name})"
            logger.info(f"PLAN mode: Denying execution tool '{tool_name}'")
            return False, reason

        # ──────────────────────────────────────────────────────────
        # LAYER 4: EXPLICIT DENIED TOOLS - Hard deny
        # ──────────────────────────────────────────────────────────
        if tool_name in self.context.denied_tools:
            reason = f"Tool '{tool_name}' is explicitly disallowed"
            logger.info(f"Denied tool: '{tool_name}' (explicit disallow)")
            return False, reason

        # ──────────────────────────────────────────────────────────
        # LAYER 5: EXPLICIT ALLOWED TOOLS - Skip further checks
        # ──────────────────────────────────────────────────────────
        if tool_name in self.context.allowed_tools:
            logger.debug(f"Allowed tool: '{tool_name}' (explicit allow)")
            return True, None

        # ──────────────────────────────────────────────────────────
        # LAYER 6: PERMISSION RULES - Pattern matching (priority order)
        # ──────────────────────────────────────────────────────────
        if self.context.rules:
            # Sort rules by priority (high to low)
            sorted_rules = sorted(
                self.context.rules, key=lambda r: r.priority, reverse=True
            )

            for rule in sorted_rules:
                if rule.matches(tool_name):
                    logger.debug(
                        f"Rule matched: pattern='{rule.pattern}', "
                        f"type={rule.permission_type.value}, "
                        f"priority={rule.priority}"
                    )

                    if rule.permission_type == PermissionType.ALLOW:
                        logger.debug(f"Rule allows tool '{tool_name}': {rule.reason}")
                        return True, None

                    elif rule.permission_type == PermissionType.DENY:
                        reason = f"Denied by rule: {rule.pattern}"
                        logger.info(f"Rule denies tool '{tool_name}': {rule.reason}")
                        return False, reason

                    elif rule.permission_type == PermissionType.ASK:
                        logger.debug(f"Rule asks for approval: '{tool_name}'")
                        return None, None

        # ──────────────────────────────────────────────────────────
        # LAYER 7: MODE-BASED DEFAULTS (DEFAULT mode)
        # ──────────────────────────────────────────────────────────
        if self.context.mode == PermissionMode.DEFAULT:
            # Risky tools require approval
            risky_tools = {"Write", "Edit", "Bash", "PythonCode", "DeleteFileNode"}
            if tool_name in risky_tools:
                logger.debug(
                    f"DEFAULT mode: Requesting approval for risky tool '{tool_name}'"
                )
                return None, None

            # Safe tools are allowed
            logger.debug(f"DEFAULT mode: Allowing safe tool '{tool_name}'")
            return True, None

        # ──────────────────────────────────────────────────────────
        # LAYER 7: MODE-BASED DEFAULTS (ACCEPT_EDITS mode)
        # ──────────────────────────────────────────────────────────
        if self.context.mode == PermissionMode.ACCEPT_EDITS:
            # Auto-approve file modifications
            if tool_name in {"Write", "Edit"}:
                logger.debug(
                    f"ACCEPT_EDITS mode: Auto-approving file operation '{tool_name}'"
                )
                return True, None

            # Ask for system operations
            if tool_name in {"Bash", "PythonCode"}:
                logger.debug(
                    f"ACCEPT_EDITS mode: Requesting approval for system operation '{tool_name}'"
                )
                return None, None

            # Allow other tools
            logger.debug(f"ACCEPT_EDITS mode: Allowing tool '{tool_name}'")
            return True, None

        # ──────────────────────────────────────────────────────────
        # LAYER 8: ASK FALLBACK (final catch-all)
        # ──────────────────────────────────────────────────────────
        logger.debug(f"Fallback: Requesting approval for tool '{tool_name}'")
        return None, None


# Export all public types
__all__ = [
    "PermissionPolicy",
]
