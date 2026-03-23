# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT for MCP -- governance enforcement on MCP tool invocations.

MCP (Model Context Protocol) has zero built-in governance: any connected agent
can call any tool with any arguments. PACT for MCP adds deterministic governance
enforcement as a middleware layer:

- **Constraint envelopes**: per-tool policies with cost limits, arg restrictions,
  rate limits, and clearance requirements.
- **Verification gradient**: AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED decisions
  based on policy evaluation.
- **Audit trail**: bounded, append-only record of all governance decisions.
- **Monotonic tightening**: runtime-registered tools can only narrow policies,
  not widen them.

Architecture:
    pact.mcp.types      -- McpToolPolicy, McpGovernanceConfig, McpActionContext
    pact.mcp.enforcer   -- McpGovernanceEnforcer (the core decision engine)
    pact.mcp.middleware  -- McpGovernanceMiddleware (wraps MCP tool calls)
    pact.mcp.audit      -- McpAuditTrail, McpAuditEntry

This is a PRIMITIVE (deterministic, no LLM). All decisions are rule-based.

Example::

    from pact.mcp import (
        McpGovernanceConfig,
        McpGovernanceEnforcer,
        McpGovernanceMiddleware,
        McpToolPolicy,
    )

    # Configure policies
    config = McpGovernanceConfig(
        tool_policies={
            "web_search": McpToolPolicy(
                tool_name="web_search",
                max_cost=1.0,
                rate_limit=10,
            ),
        },
    )

    # Create enforcer and middleware
    enforcer = McpGovernanceEnforcer(config)
    middleware = McpGovernanceMiddleware(enforcer, handler=my_mcp_handler)

    # Invoke with governance
    result = await middleware.invoke("web_search", {"query": "test"}, agent_id="agent-1")
    if result.decision.allowed:
        print(result.tool_result)
"""

from pact.mcp.audit import McpAuditEntry, McpAuditTrail
from pact.mcp.enforcer import GovernanceDecision, McpGovernanceEnforcer
from pact.mcp.middleware import McpGovernanceMiddleware, McpInvocationResult
from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpGovernanceConfig,
    McpToolPolicy,
)

__all__ = [
    # Types
    "DefaultPolicy",
    "McpActionContext",
    "McpGovernanceConfig",
    "McpToolPolicy",
    # Enforcer
    "GovernanceDecision",
    "McpGovernanceEnforcer",
    # Middleware
    "McpGovernanceMiddleware",
    "McpInvocationResult",
    # Audit
    "McpAuditEntry",
    "McpAuditTrail",
]
