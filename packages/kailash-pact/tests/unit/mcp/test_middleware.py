# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for pact.mcp.middleware -- MCP governance middleware.

Covers:
- McpGovernanceMiddleware: wrap/invoke pattern
- Governance check before handler invocation
- Blocked calls do not invoke handler
- Handler errors are captured (fail-closed)
- McpInvocationResult structure
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from pact.mcp.enforcer import GovernanceDecision, McpGovernanceEnforcer
from pact.mcp.middleware import McpGovernanceMiddleware, McpInvocationResult
from pact.mcp.types import (
    DefaultPolicy,
    McpGovernanceConfig,
    McpToolPolicy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _policy(name: str, max_cost: float | None = 10.0) -> McpToolPolicy:
    return McpToolPolicy(tool_name=name, max_cost=max_cost)


def _config(
    policies: dict[str, McpToolPolicy] | None = None,
) -> McpGovernanceConfig:
    return McpGovernanceConfig(
        default_policy=DefaultPolicy.DENY,
        tool_policies=policies or {},
    )


class MockHandler:
    """Async handler that records calls and returns a fixed value."""

    def __init__(self, return_value: Any = "result") -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.return_value = return_value
        self.should_raise: Exception | None = None

    async def __call__(self, tool_name: str, args: dict[str, Any]) -> Any:
        self.calls.append((tool_name, args))
        if self.should_raise is not None:
            raise self.should_raise
        return self.return_value


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def handler() -> MockHandler:
    return MockHandler(return_value={"status": "ok"})


@pytest.fixture
def enforcer() -> McpGovernanceEnforcer:
    policy = _policy("search", max_cost=10.0)
    config = _config(policies={"search": policy})
    return McpGovernanceEnforcer(config)


@pytest.fixture
def middleware(
    enforcer: McpGovernanceEnforcer, handler: MockHandler
) -> McpGovernanceMiddleware:
    return McpGovernanceMiddleware(enforcer=enforcer, handler=handler)


# ---------------------------------------------------------------------------
# Basic Invoke Tests
# ---------------------------------------------------------------------------


class TestInvoke:
    """McpGovernanceMiddleware.invoke() behavior."""

    @pytest.mark.asyncio
    async def test_approved_call_invokes_handler(
        self, middleware: McpGovernanceMiddleware, handler: MockHandler
    ) -> None:
        result = await middleware.invoke(
            "search",
            {"query": "test"},
            agent_id="agent-1",
            cost_estimate=1.0,
        )
        assert result.decision.level == "auto_approved"
        assert result.decision.allowed is True
        assert result.executed is True
        assert result.tool_result == {"status": "ok"}
        assert result.tool_error is None
        assert len(handler.calls) == 1
        assert handler.calls[0] == ("search", {"query": "test"})

    @pytest.mark.asyncio
    async def test_blocked_call_does_not_invoke_handler(
        self, middleware: McpGovernanceMiddleware, handler: MockHandler
    ) -> None:
        result = await middleware.invoke(
            "unregistered_tool",
            {},
            agent_id="agent-1",
        )
        assert result.decision.level == "blocked"
        assert result.decision.allowed is False
        assert result.executed is False
        assert result.tool_result is None
        assert len(handler.calls) == 0

    @pytest.mark.asyncio
    async def test_over_budget_blocked(
        self, middleware: McpGovernanceMiddleware, handler: MockHandler
    ) -> None:
        result = await middleware.invoke(
            "search",
            {},
            agent_id="agent-1",
            cost_estimate=50.0,
        )
        assert result.decision.level == "blocked"
        assert result.executed is False
        assert len(handler.calls) == 0

    @pytest.mark.asyncio
    async def test_flagged_call_still_invokes_handler(
        self, middleware: McpGovernanceMiddleware, handler: MockHandler
    ) -> None:
        """Flagged (near limit) calls are still allowed and invoke the handler."""
        result = await middleware.invoke(
            "search",
            {},
            agent_id="agent-1",
            cost_estimate=8.5,  # 85% of 10.0 -> flagged
        )
        assert result.decision.level == "flagged"
        assert result.decision.allowed is True
        assert result.executed is True
        assert len(handler.calls) == 1


# ---------------------------------------------------------------------------
# Handler Error Tests
# ---------------------------------------------------------------------------


class TestHandlerErrors:
    """Middleware captures handler errors without crashing."""

    @pytest.mark.asyncio
    async def test_handler_error_captured(
        self, middleware: McpGovernanceMiddleware, handler: MockHandler
    ) -> None:
        handler.should_raise = RuntimeError("connection lost")
        result = await middleware.invoke(
            "search",
            {},
            agent_id="agent-1",
            cost_estimate=1.0,
        )
        # Decision was approved, but handler failed
        assert result.decision.level == "auto_approved"
        assert result.executed is False
        assert result.tool_error == "connection lost"
        assert result.tool_result is None


# ---------------------------------------------------------------------------
# McpInvocationResult Tests
# ---------------------------------------------------------------------------


class TestMcpInvocationResult:
    """McpInvocationResult structure and serialization."""

    def test_to_dict(self) -> None:
        decision = GovernanceDecision(
            level="auto_approved",
            tool_name="t",
            agent_id="a",
            reason="ok",
        )
        result = McpInvocationResult(
            decision=decision,
            tool_result={"data": 42},
            tool_error=None,
            executed=True,
        )
        data = result.to_dict()
        assert data["decision"]["level"] == "auto_approved"
        assert data["tool_result"] == {"data": 42}
        assert data["tool_error"] is None
        assert data["executed"] is True

    def test_blocked_result(self) -> None:
        decision = GovernanceDecision(
            level="blocked",
            tool_name="t",
            agent_id="a",
            reason="denied",
        )
        result = McpInvocationResult(
            decision=decision,
            executed=False,
        )
        assert result.tool_result is None
        assert result.tool_error is None
        assert result.executed is False


# ---------------------------------------------------------------------------
# Middleware Properties
# ---------------------------------------------------------------------------


class TestMiddlewareProperties:
    """Middleware exposes enforcer property."""

    def test_enforcer_property(
        self,
        middleware: McpGovernanceMiddleware,
        enforcer: McpGovernanceEnforcer,
    ) -> None:
        assert middleware.enforcer is enforcer

    @pytest.mark.asyncio
    async def test_default_args(
        self, middleware: McpGovernanceMiddleware, handler: MockHandler
    ) -> None:
        """Invoke with minimal args uses defaults."""
        result = await middleware.invoke("search", agent_id="a", cost_estimate=1.0)
        assert result.executed is True
        assert handler.calls[0] == ("search", {})

    @pytest.mark.asyncio
    async def test_metadata_passed(
        self, middleware: McpGovernanceMiddleware
    ) -> None:
        """Metadata is passed through to governance context."""
        result = await middleware.invoke(
            "search",
            {},
            agent_id="a",
            cost_estimate=1.0,
            metadata={"request_id": "r-123"},
        )
        # The governance check should have recorded metadata via audit trail
        entries = middleware.enforcer.audit_trail.to_list()
        assert len(entries) >= 1
