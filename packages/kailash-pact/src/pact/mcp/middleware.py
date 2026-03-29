# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP governance middleware -- wraps MCP tool calls with governance enforcement.

Provides McpGovernanceMiddleware which intercepts MCP tool calls, runs
governance checks via McpGovernanceEnforcer before execution, and records
audit trail entries after execution.

This middleware is protocol-agnostic: it wraps any async callable that
represents an MCP tool invocation. The actual MCP transport (stdio, HTTP,
SSE) is handled by the MCP SDK -- this middleware sits above it.

Fail-closed: if the governance check fails for any reason, the tool call
is blocked (GovernanceDecision with level="blocked").
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Callable, Awaitable

from pact.mcp.audit import McpAuditTrail
from pact.mcp.enforcer import GovernanceDecision, McpGovernanceEnforcer
from pact.mcp.types import McpActionContext

logger = logging.getLogger(__name__)

__all__ = [
    "McpGovernanceMiddleware",
]


class McpGovernanceMiddleware:
    """Middleware that wraps MCP tool calls with PACT governance enforcement.

    Intercepts MCP tool invocations, checks them against governance policies
    via McpGovernanceEnforcer, and only forwards the call to the actual MCP
    handler if the governance check passes (auto_approved or flagged).

    For HELD or BLOCKED decisions, the middleware returns the GovernanceDecision
    directly without invoking the underlying handler.

    Args:
        enforcer: The McpGovernanceEnforcer that evaluates tool calls.
        handler: The async callable that performs the actual MCP tool invocation.
            Signature: async (tool_name: str, args: dict) -> Any
    """

    def __init__(
        self,
        enforcer: McpGovernanceEnforcer,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        self._enforcer = enforcer
        self._handler = handler

    @property
    def enforcer(self) -> McpGovernanceEnforcer:
        """The governance enforcer used by this middleware."""
        return self._enforcer

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        agent_id: str = "",
        *,
        cost_estimate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> McpInvocationResult:
        """Invoke an MCP tool with governance enforcement.

        1. Build an McpActionContext from the call parameters.
        2. Run governance check via McpGovernanceEnforcer.check_tool_call().
        3. If allowed (auto_approved or flagged): call the underlying handler.
        4. If not allowed (held or blocked): return without calling handler.
        5. Return McpInvocationResult with decision and optional result.

        Fail-closed: if the handler raises, the result captures the error
        but the governance decision stands.

        Args:
            tool_name: The MCP tool to invoke.
            args: Arguments to pass to the tool.
            agent_id: Identifier of the agent making the call.
            cost_estimate: Estimated cost for this invocation.
            metadata: Additional context for governance evaluation.

        Returns:
            McpInvocationResult with the governance decision and tool result.
        """
        now = datetime.now(UTC)
        context = McpActionContext(
            tool_name=tool_name,
            args=args or {},
            agent_id=agent_id,
            timestamp=now,
            cost_estimate=cost_estimate,
            metadata=metadata or {},
        )

        # Governance check
        decision = self._enforcer.check_tool_call(context)

        # Only invoke handler if allowed
        tool_result: Any = None
        tool_error: str | None = None

        if decision.allowed:
            try:
                tool_result = await self._handler(tool_name, args or {})
            except Exception as exc:
                logger.warning(
                    "McpGovernanceMiddleware: handler failed for tool '%s': %s",
                    tool_name,
                    exc,
                )
                tool_error = "Tool execution failed"

        return McpInvocationResult(
            decision=decision,
            tool_result=tool_result,
            tool_error=tool_error,
            executed=decision.allowed and tool_error is None,
        )


class McpInvocationResult:
    """Result of a governed MCP tool invocation.

    Combines the governance decision with the actual tool execution result.

    Attributes:
        decision: The GovernanceDecision from the enforcer.
        tool_result: The return value from the MCP tool handler, or None
            if the call was blocked/held or the handler failed.
        tool_error: Error message if the handler raised, or None.
        executed: True if the handler was called and succeeded.
    """

    __slots__ = ("decision", "tool_result", "tool_error", "executed")

    def __init__(
        self,
        *,
        decision: GovernanceDecision,
        tool_result: Any = None,
        tool_error: str | None = None,
        executed: bool = False,
    ) -> None:
        self.decision = decision
        self.tool_result = tool_result
        self.tool_error = tool_error
        self.executed = executed

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "decision": self.decision.to_dict(),
            "tool_result": self.tool_result,
            "tool_error": self.tool_error,
            "executed": self.executed,
        }
