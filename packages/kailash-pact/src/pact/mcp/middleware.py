# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP governance middleware -- wraps MCP tool calls with governance enforcement.

Provides McpGovernanceMiddleware which intercepts MCP tool calls AND
resources/read invocations (issue #1843), runs governance checks via
McpGovernanceEnforcer before execution, and records audit trail entries
after execution.

This middleware is protocol-agnostic: it wraps any async callable that
represents an MCP tool invocation or resource read. The actual MCP transport
(stdio, HTTP, SSE) is handled by the MCP SDK -- this middleware sits above it.

Fail-closed: if the governance check fails for any reason, the tool call
or resource read is blocked (GovernanceDecision with level="blocked").
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from pact.mcp.enforcer import GovernanceDecision, McpGovernanceEnforcer
from pact.mcp.types import McpActionContext, McpCallerIdentity, McpResourceContext

logger = logging.getLogger(__name__)

__all__ = [
    "McpGovernanceMiddleware",
    "McpInvocationResult",
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
        resource_handler: Optional async callable that performs the actual MCP
            resources/read fetch (issue #1843). Signature: async (uri: str) ->
            Any. None (the default) means invoke_resource_read() evaluates
            governance only and returns no resource content -- the caller's
            own MCP SDK dispatch handles the actual read, matching how this
            middleware "sits above" the SDK transport (see module docstring).
    """

    def __init__(
        self,
        enforcer: McpGovernanceEnforcer,
        handler: Callable[..., Awaitable[Any]],
        resource_handler: Callable[[str], Awaitable[Any]] | None = None,
    ) -> None:
        self._enforcer = enforcer
        self._handler = handler
        self._resource_handler = resource_handler

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
        caller_clearance: str | None = None,
        caller_identity: McpCallerIdentity | None = None,
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
            caller_clearance: The caller's confidentiality clearance level
                (ConfidentialityLevel value). Forwarded to the enforcer so a
                tool whose policy sets clearance_required is gated fail-closed.
                None means no clearance supplied (such tools are BLOCKED).
            caller_identity: The trusted caller identity resolved by the
                transport/auth layer, if any (issue #1843). Its tenant (when
                set) OVERWRITES any self-asserted metadata["tenant_id"]
                (impersonation defeat). Forwarded to the enforcer's tenant
                isolation gate; a no-op when McpGovernanceConfig.tenant_grants
                is empty.
            metadata: Additional context for governance evaluation.

        Returns:
            McpInvocationResult with the governance decision and tool result.
        """
        now = datetime.now(UTC)
        # The middleware IS the network boundary: populate the first-class,
        # server-verified tenant field (issue #1878) from the AUTHENTICATED
        # caller_identity (transport/token-resolved), NEVER from the request
        # body. The enforcer then reads context.tenant as the authoritative
        # tenant-isolation input.
        verified_tenant = (
            caller_identity.tenant if caller_identity is not None else None
        )
        # Defense-in-depth (#1919): scrub any client-asserted
        # metadata["tenant_id"] at the boundary before building the context,
        # mirroring McpActionContext.from_network_transport. A client-asserted
        # tenant can never influence the decision (the enforcer no longer
        # trusts it) AND must never propagate into audit/echo surfaces. The
        # verified `tenant` field below is populated ONLY from caller_identity.
        scrubbed_metadata = {
            k: v for k, v in (metadata or {}).items() if k != "tenant_id"
        }
        context = McpActionContext(
            tool_name=tool_name,
            args=args or {},
            agent_id=agent_id,
            timestamp=now,
            cost_estimate=cost_estimate,
            caller_clearance=caller_clearance,
            metadata=scrubbed_metadata,
            tenant=verified_tenant,
        )

        # Governance check
        decision = self._enforcer.check_tool_call(
            context, caller_identity=caller_identity
        )

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

    async def invoke_resource_read(
        self,
        uri: str,
        agent_id: str = "",
        *,
        caller_identity: McpCallerIdentity | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> McpInvocationResult:
        """Read an MCP resource with tenant-isolation governance (issue #1843).

        1. Build an McpResourceContext from the call parameters.
        2. Run the tenant-isolation check via
           McpGovernanceEnforcer.check_resource_read().
        3. If allowed AND a resource_handler was configured: call it.
        4. If not allowed, or no resource_handler is configured: return
           without invoking any handler.
        5. Return McpInvocationResult with the decision and optional result.

        Fail-closed: if resource_handler raises, the result captures the
        error but the governance decision stands.

        Args:
            uri: The MCP resource URI to read.
            agent_id: Identifier of the agent making the call.
            caller_identity: The trusted caller identity resolved by the
                transport/auth layer, if any. Its tenant (when set)
                OVERWRITES any self-asserted metadata["tenant_id"]
                (impersonation defeat), mirroring invoke().
            metadata: Additional context for governance evaluation.

        Returns:
            McpInvocationResult with the governance decision and resource
            content (in tool_result), or None if no resource_handler was
            configured.
        """
        now = datetime.now(UTC)
        # Network boundary: populate the first-class verified tenant (issue
        # #1878) from the authenticated caller_identity, never the body.
        verified_tenant = (
            caller_identity.tenant if caller_identity is not None else None
        )
        # Defense-in-depth (#1919): scrub any client-asserted
        # metadata["tenant_id"] at the boundary before building the context,
        # mirroring McpResourceContext.from_network_transport. The verified
        # `tenant` field below is populated ONLY from caller_identity.
        scrubbed_metadata = {
            k: v for k, v in (metadata or {}).items() if k != "tenant_id"
        }
        context = McpResourceContext(
            uri=uri,
            agent_id=agent_id,
            timestamp=now,
            metadata=scrubbed_metadata,
            tenant=verified_tenant,
        )

        decision = self._enforcer.check_resource_read(
            context, caller_identity=caller_identity
        )

        resource_result: Any = None
        resource_error: str | None = None
        executed = False

        if decision.allowed and self._resource_handler is not None:
            try:
                resource_result = await self._resource_handler(uri)
                executed = True
            except Exception as exc:
                logger.warning(
                    "McpGovernanceMiddleware: resource_handler failed for "
                    "resource '%s': %s",
                    uri,
                    exc,
                )
                resource_error = "Resource read failed"

        return McpInvocationResult(
            decision=decision,
            tool_result=resource_result,
            tool_error=resource_error,
            executed=executed,
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
