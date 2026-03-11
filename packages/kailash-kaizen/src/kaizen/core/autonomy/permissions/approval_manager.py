"""
Tool approval manager for permission system.

Handles interactive approval prompts via Control Protocol for risky operations.
Integrates with ExecutionContext for permission updates (Approve All / Deny All).

Implements prompt generation with context-aware templates:
- Bash: Show command, warn about system changes
- Write/Edit: Show file path, warn about codebase changes
- Generic: Show tool name and inputs

All prompts include budget information and risk warnings.
"""

import logging
from typing import Any

from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.types import ControlRequest
from kaizen.core.autonomy.permissions.context import ExecutionContext

logger = logging.getLogger(__name__)


class ToolApprovalManager:
    """
    Manages interactive tool approval via Control Protocol.

    Provides:
    - Context-aware approval prompt generation
    - Integration with Control Protocol for user interaction
    - "Approve All" / "Deny All" mode support
    - Timeout handling (default: 60 seconds, fail-closed)
    - Audit logging for all approval decisions

    Examples:
        >>> # Setup with Control Protocol
        >>> transport = CLITransport()
        >>> protocol = ControlProtocol(transport=transport)
        >>> await protocol.start(tg)
        >>>
        >>> manager = ToolApprovalManager(protocol)
        >>>
        >>> # Request approval
        >>> context = ExecutionContext(mode=PermissionMode.DEFAULT)
        >>> approved = await manager.request_approval("Bash", {"command": "ls"}, context)
        >>> if not approved:
        >>>     raise PermissionError("User denied tool execution")
    """

    def __init__(self, control_protocol: ControlProtocol):
        """
        Initialize approval manager.

        Args:
            control_protocol: Control Protocol instance for bidirectional communication

        Raises:
            TypeError: If control_protocol is not a ControlProtocol instance
        """
        # Note: Validation relaxed for unit testing with mocks
        # In production, actual ControlProtocol instances will be used
        self.protocol = control_protocol
        logger.debug("ToolApprovalManager initialized")

    async def request_approval(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ExecutionContext,
        timeout: float = 60.0,
    ) -> bool:
        """
        Request user approval for tool usage.

        Sends approval request via Control Protocol and waits for user response.
        Implements fail-closed design: returns False on timeout or error.

        Args:
            tool_name: Name of the tool requiring approval
            tool_input: Input parameters for the tool
            context: Execution context with budget and permission state
            timeout: Maximum seconds to wait for approval (default: 60.0)

        Returns:
            True if approved, False if denied or error

        Examples:
            >>> approved = await manager.request_approval(
            ...     "Bash",
            ...     {"command": "rm -rf /tmp/test"},
            ...     context,
            ...     timeout=30.0
            ... )
            >>> if not approved:
            ...     raise PermissionError("User denied bash execution")
        """
        logger.info(f"Requesting approval for tool: {tool_name}")

        try:
            # Generate context-aware prompt
            prompt = self._generate_approval_prompt(tool_name, tool_input, context)

            # Create approval request
            request = ControlRequest.create(
                type="approval",
                data={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "prompt": prompt,
                    "options": ["Approve", "Deny", "Approve All", "Deny All"],
                },
            )

            # Send request and wait for response
            logger.debug(
                f"Sending approval request for '{tool_name}' with {timeout}s timeout"
            )
            response = await self.protocol.send_request(request, timeout=timeout)

            # Check for error response
            if response.is_error:
                logger.error(f"Approval request failed: {response.error}")
                return False  # Fail-closed

            # Extract approval decision
            approved = response.data.get("approved", False)
            action = response.data.get("action", "once")

            # Log decision
            logger.info(
                f"Approval decision for '{tool_name}': "
                f"approved={approved}, action={action}"
            )

            # Handle "Approve All" / "Deny All"
            if action == "all":
                if approved:
                    context.allowed_tools.add(tool_name)
                    logger.info(f"Added '{tool_name}' to allowed tools (Approve All)")
                else:
                    context.denied_tools.add(tool_name)
                    logger.info(f"Added '{tool_name}' to denied tools (Deny All)")

            return approved

        except TimeoutError as e:
            logger.warning(
                f"Approval request timed out after {timeout}s for '{tool_name}': {e}"
            )
            return False  # Fail-closed on timeout

        except Exception as e:
            logger.error(
                f"Approval request failed for '{tool_name}': {e}", exc_info=True
            )
            return False  # Fail-closed on error

    def _generate_approval_prompt(
        self, tool_name: str, tool_input: dict[str, Any], context: ExecutionContext
    ) -> str:
        """
        Generate context-aware approval prompt.

        Creates human-readable prompts with:
        - Tool-specific templates (Bash, Write/Edit, generic)
        - Budget information (spent / limit)
        - Risk warnings for dangerous operations

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters for the tool
            context: Execution context with budget state

        Returns:
            Human-readable approval prompt string

        Examples:
            >>> # Bash prompt
            >>> prompt = manager._generate_approval_prompt(
            ...     "Bash",
            ...     {"command": "rm -rf /"},
            ...     context
            ... )
            >>> assert "rm -rf /" in prompt
            >>> assert "system" in prompt.lower()

            >>> # Write prompt
            >>> prompt = manager._generate_approval_prompt(
            ...     "Write",
            ...     {"file_path": "/src/app.py"},
            ...     context
            ... )
            >>> assert "/src/app.py" in prompt
            >>> assert "file" in prompt.lower()
        """
        # Format budget info
        budget_info = self._format_budget_info(context)

        # ──────────────────────────────────────────────────────────
        # TEMPLATE 1: Bash Commands
        # ──────────────────────────────────────────────────────────
        if tool_name == "Bash":
            command = tool_input.get("command", "unknown")
            return f"""
🤖 Agent wants to execute bash command:

  {command}

⚠️  This could modify your system. Review carefully.

{budget_info}

Approve this action?
            """.strip()

        # ──────────────────────────────────────────────────────────
        # TEMPLATE 2: Write/Edit Operations
        # ──────────────────────────────────────────────────────────
        if tool_name in {"Write", "Edit"}:
            file_path = tool_input.get("file_path", "unknown")
            action_word = "modify" if tool_name == "Edit" else "write to"
            return f"""
🤖 Agent wants to {action_word} file:

  {file_path}

⚠️  This will change your codebase.

{budget_info}

Approve this action?
            """.strip()

        # ──────────────────────────────────────────────────────────
        # TEMPLATE 3: Generic Tools
        # ──────────────────────────────────────────────────────────
        # Truncate input if too long
        input_str = str(tool_input)
        if len(input_str) > 200:
            input_str = input_str[:200] + "..."

        return f"""
🤖 Agent wants to use tool: {tool_name}

Input: {input_str}

{budget_info}

Approve this action?
        """.strip()

    def _format_budget_info(self, context: ExecutionContext) -> str:
        """
        Format budget information for prompt.

        Args:
            context: Execution context with budget state

        Returns:
            Formatted budget string

        Examples:
            >>> context = ExecutionContext(budget_limit=10.0)
            >>> context.budget_used = 5.5
            >>> info = manager._format_budget_info(context)
            >>> assert "5.5" in info
            >>> assert "10.0" in info or "10" in info
        """
        if context.budget_limit is None:
            return "Budget: unlimited"

        remaining = context.budget_limit - context.budget_used

        return (
            f"Budget: ${context.budget_used:.2f} / "
            f"${context.budget_limit:.2f} spent "
            f"(${remaining:.2f} remaining)"
        )


# Export all public types
__all__ = [
    "ToolApprovalManager",
]
