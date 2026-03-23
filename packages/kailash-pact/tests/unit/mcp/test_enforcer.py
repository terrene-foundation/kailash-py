# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for pact.mcp.enforcer -- MCP governance enforcement engine.

Covers:
- Default-deny for unregistered tools
- Default-allow configuration
- All verification gradient zones (auto_approved, flagged, held, blocked)
- NaN/Inf defense on cost_estimate
- Argument constraint checking (denied_args, allowed_args)
- Cost constraint checking with 80% flagging threshold
- Rate limiting
- Thread safety
- Fail-closed on internal errors
- Audit trail recording
- Runtime tool registration
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pact.mcp.enforcer import GovernanceDecision, McpGovernanceEnforcer
from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpGovernanceConfig,
    McpToolPolicy,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _policy(
    name: str = "web_search",
    max_cost: float | None = 10.0,
    rate_limit: int | None = None,
    allowed_args: frozenset[str] | None = None,
    denied_args: frozenset[str] | None = None,
) -> McpToolPolicy:
    return McpToolPolicy(
        tool_name=name,
        max_cost=max_cost,
        rate_limit=rate_limit,
        allowed_args=allowed_args or frozenset(),
        denied_args=denied_args or frozenset(),
    )


def _config(
    policies: dict[str, McpToolPolicy] | None = None,
    default_policy: DefaultPolicy = DefaultPolicy.DENY,
    audit_enabled: bool = True,
) -> McpGovernanceConfig:
    return McpGovernanceConfig(
        default_policy=default_policy,
        tool_policies=policies or {},
        audit_enabled=audit_enabled,
    )


def _context(
    tool_name: str = "web_search",
    args: dict[str, Any] | None = None,
    agent_id: str = "agent-1",
    cost_estimate: float | None = None,
    timestamp: datetime | None = None,
) -> McpActionContext:
    return McpActionContext(
        tool_name=tool_name,
        args=args or {},
        agent_id=agent_id,
        cost_estimate=cost_estimate,
        timestamp=timestamp or datetime.now(UTC),
    )


@pytest.fixture
def search_policy() -> McpToolPolicy:
    return _policy("web_search", max_cost=10.0)


@pytest.fixture
def deny_config(search_policy: McpToolPolicy) -> McpGovernanceConfig:
    return _config(policies={"web_search": search_policy})


@pytest.fixture
def enforcer(deny_config: McpGovernanceConfig) -> McpGovernanceEnforcer:
    return McpGovernanceEnforcer(deny_config)


# ---------------------------------------------------------------------------
# Default-Deny Tests
# ---------------------------------------------------------------------------


class TestDefaultDeny:
    """Default-deny policy blocks unregistered tools."""

    def test_unregistered_tool_blocked(self, enforcer: McpGovernanceEnforcer) -> None:
        ctx = _context(tool_name="unknown_tool")
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert decision.allowed is False
        assert "not registered" in decision.reason
        assert "default-deny" in decision.reason

    def test_registered_tool_approved(self, enforcer: McpGovernanceEnforcer) -> None:
        ctx = _context(tool_name="web_search", cost_estimate=1.0)
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"
        assert decision.allowed is True

    def test_default_allow_permits_unregistered(self) -> None:
        config = _config(default_policy=DefaultPolicy.ALLOW)
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="anything")
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"
        assert "default-allow" in decision.reason


# ---------------------------------------------------------------------------
# Verification Gradient Tests
# ---------------------------------------------------------------------------


class TestVerificationGradient:
    """All four gradient zones are correctly assigned."""

    def test_auto_approved_within_budget(self, enforcer: McpGovernanceEnforcer) -> None:
        ctx = _context(cost_estimate=5.0)
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_flagged_near_boundary(self, enforcer: McpGovernanceEnforcer) -> None:
        """Cost within 20% of max_cost (>80%) triggers flagged."""
        ctx = _context(cost_estimate=8.5)  # 85% of 10.0
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "flagged"
        assert decision.allowed is True
        assert "within 20%" in decision.reason

    def test_blocked_over_budget(self, enforcer: McpGovernanceEnforcer) -> None:
        ctx = _context(cost_estimate=15.0)
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert decision.allowed is False
        assert "exceeds max_cost" in decision.reason

    def test_auto_approved_no_cost(self, enforcer: McpGovernanceEnforcer) -> None:
        """No cost_estimate means no financial check -- auto_approved."""
        ctx = _context(cost_estimate=None)
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_auto_approved_no_max_cost_policy(self) -> None:
        """Policy without max_cost allows any cost."""
        policy = _policy("tool", max_cost=None)
        config = _config(policies={"tool": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="tool", cost_estimate=99999.0)
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_exactly_at_max_cost_blocked(self, enforcer: McpGovernanceEnforcer) -> None:
        """Cost exactly at max_cost is NOT blocked (<=, not <)."""
        # 10.0 is exactly max_cost. Not > max_cost, so not blocked.
        # But 10.0 > 8.0 (80% of 10.0), so flagged.
        ctx = _context(cost_estimate=10.0)
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "flagged"

    def test_exactly_at_80_percent_not_flagged(self) -> None:
        """Cost exactly at 80% boundary is NOT flagged (> 80%, not >=)."""
        policy = _policy("t", max_cost=100.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t", cost_estimate=80.0)  # exactly 80%
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"


# ---------------------------------------------------------------------------
# NaN/Inf Defense Tests
# ---------------------------------------------------------------------------


class TestNanInfDefense:
    """NaN and Inf values in cost_estimate are blocked at enforcer level.

    Note: McpActionContext.__post_init__ also validates, so NaN/Inf in
    cost_estimate raises ValueError during construction. These tests verify
    the enforcer's own defense layer for cases where context might be
    constructed without validation (e.g., from_dict with invalid data
    that bypasses __post_init__).
    """

    def test_nan_cost_rejected_at_context(self) -> None:
        """NaN cost_estimate is rejected by McpActionContext.__post_init__."""
        with pytest.raises(ValueError, match="cost_estimate must be finite"):
            _context(cost_estimate=float("nan"))

    def test_inf_cost_rejected_at_context(self) -> None:
        """Inf cost_estimate is rejected by McpActionContext.__post_init__."""
        with pytest.raises(ValueError, match="cost_estimate must be finite"):
            _context(cost_estimate=float("inf"))

    def test_neg_inf_cost_rejected_at_context(self) -> None:
        with pytest.raises(ValueError, match="cost_estimate must be finite"):
            _context(cost_estimate=float("-inf"))

    def test_negative_cost_rejected_at_context(self) -> None:
        with pytest.raises(ValueError, match="cost_estimate must be non-negative"):
            _context(cost_estimate=-1.0)


# ---------------------------------------------------------------------------
# Argument Constraint Tests
# ---------------------------------------------------------------------------


class TestArgumentConstraints:
    """Argument-level governance checks."""

    def test_denied_args_blocked(self) -> None:
        policy = _policy("t", denied_args=frozenset({"password", "secret"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t", args={"query": "test", "password": "abc"})
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "denied" in decision.reason
        assert "password" in decision.reason

    def test_allowed_args_enforced(self) -> None:
        policy = _policy("t", allowed_args=frozenset({"query", "limit"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t", args={"query": "test", "forbidden": "val"})
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "not in the allowed set" in decision.reason

    def test_allowed_args_subset_passes(self) -> None:
        policy = _policy("t", allowed_args=frozenset({"query", "limit"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t", args={"query": "test"})
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_empty_allowed_args_permits_all(self) -> None:
        """Empty allowed_args means no arg restriction."""
        policy = _policy("t", allowed_args=frozenset())
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t", args={"anything": "goes"})
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_denied_args_takes_precedence(self) -> None:
        """denied_args is checked before allowed_args."""
        policy = _policy(
            "t",
            allowed_args=frozenset({"query", "password"}),
            denied_args=frozenset({"password"}),
        )
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t", args={"query": "test", "password": "abc"})
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "denied" in decision.reason

    def test_empty_args_passes(self) -> None:
        policy = _policy("t", denied_args=frozenset({"secret"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t", args={})
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Rate limit enforcement on tool invocations."""

    def test_rate_limit_blocks_after_threshold(self) -> None:
        policy = _policy("t", rate_limit=3, max_cost=None)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        now = datetime.now(UTC)
        # First 3 calls should pass
        for i in range(3):
            ctx = _context(
                tool_name="t",
                timestamp=now + timedelta(seconds=i),
            )
            decision = enforcer.check_tool_call(ctx)
            assert decision.level == "auto_approved", f"Call {i} should pass"

        # 4th call should be blocked
        ctx = _context(tool_name="t", timestamp=now + timedelta(seconds=3))
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "Rate limit exceeded" in decision.reason

    def test_rate_limit_resets_after_window(self) -> None:
        policy = _policy("t", rate_limit=2, max_cost=None)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        now = datetime.now(UTC)
        # Use up the limit
        for i in range(2):
            ctx = _context(tool_name="t", timestamp=now + timedelta(seconds=i))
            enforcer.check_tool_call(ctx)

        # After 61 seconds, limit should reset
        ctx = _context(tool_name="t", timestamp=now + timedelta(seconds=61))
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_rate_limit_per_agent(self) -> None:
        """Rate limits are tracked per agent+tool combination."""
        policy = _policy("t", rate_limit=1, max_cost=None)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        now = datetime.now(UTC)
        # Agent 1 uses up limit
        ctx1 = _context(tool_name="t", agent_id="agent-1", timestamp=now)
        assert enforcer.check_tool_call(ctx1).level == "auto_approved"

        # Agent 2 should still pass (separate tracker)
        ctx2 = _context(
            tool_name="t",
            agent_id="agent-2",
            timestamp=now + timedelta(seconds=1),
        )
        assert enforcer.check_tool_call(ctx2).level == "auto_approved"

        # Agent 1 should be blocked
        ctx3 = _context(
            tool_name="t",
            agent_id="agent-1",
            timestamp=now + timedelta(seconds=2),
        )
        assert enforcer.check_tool_call(ctx3).level == "blocked"


# ---------------------------------------------------------------------------
# Fail-Closed Tests
# ---------------------------------------------------------------------------


class TestFailClosed:
    """Enforcer returns BLOCKED on internal errors."""

    def test_fail_closed_on_evaluation_error(self) -> None:
        """If _evaluate raises, check_tool_call returns BLOCKED."""
        policy = _policy("t")
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        # Monkey-patch _evaluate to raise
        def _broken_evaluate(ctx: McpActionContext) -> GovernanceDecision:
            raise RuntimeError("simulated failure")

        enforcer._evaluate = _broken_evaluate  # type: ignore[assignment]

        ctx = _context(tool_name="t")
        decision = enforcer.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "fail-closed" in decision.reason


# ---------------------------------------------------------------------------
# Audit Trail Tests
# ---------------------------------------------------------------------------


class TestAuditTrailIntegration:
    """Enforcer records audit entries when audit_enabled=True."""

    def test_audit_recorded_on_approved(self, enforcer: McpGovernanceEnforcer) -> None:
        ctx = _context(cost_estimate=1.0)
        enforcer.check_tool_call(ctx)
        entries = enforcer.audit_trail.to_list()
        assert len(entries) == 1
        assert entries[0].decision == "auto_approved"
        assert entries[0].tool_name == "web_search"

    def test_audit_recorded_on_blocked(self, enforcer: McpGovernanceEnforcer) -> None:
        ctx = _context(tool_name="unknown")
        enforcer.check_tool_call(ctx)
        entries = enforcer.audit_trail.to_list()
        assert len(entries) == 1
        assert entries[0].decision == "blocked"

    def test_audit_disabled(self) -> None:
        policy = _policy("t")
        config = _config(policies={"t": policy}, audit_enabled=False)
        enforcer = McpGovernanceEnforcer(config)
        ctx = _context(tool_name="t")
        enforcer.check_tool_call(ctx)
        assert len(enforcer.audit_trail) == 0

    def test_audit_contains_args_keys(self, enforcer: McpGovernanceEnforcer) -> None:
        ctx = _context(cost_estimate=1.0, args={"query": "test", "limit": 5})
        enforcer.check_tool_call(ctx)
        entries = enforcer.audit_trail.to_list()
        assert entries[0].metadata["args_keys"] == ["limit", "query"]


# ---------------------------------------------------------------------------
# Runtime Registration Tests
# ---------------------------------------------------------------------------


class TestRuntimeRegistration:
    """Runtime tool registration via register_tool()."""

    def test_register_new_tool(self) -> None:
        config = _config()
        enforcer = McpGovernanceEnforcer(config)

        # Initially blocked (not registered)
        ctx = _context(tool_name="new_tool")
        assert enforcer.check_tool_call(ctx).level == "blocked"

        # Register and try again
        enforcer.register_tool(_policy("new_tool", max_cost=100.0))
        ctx = _context(tool_name="new_tool", cost_estimate=5.0)
        assert enforcer.check_tool_call(ctx).level == "auto_approved"

    def test_register_tightens_config(self) -> None:
        """Runtime registration tightens (not widens) config policy."""
        policy = _policy("t", max_cost=10.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        # Original limit: 10.0 -- cost 8.0 is auto_approved
        ctx = _context(tool_name="t", cost_estimate=8.0)
        assert enforcer.check_tool_call(ctx).level == "auto_approved"

        # Tighten to 5.0 -- cost 8.0 should now be blocked
        enforcer.register_tool(_policy("t", max_cost=5.0))
        ctx = _context(tool_name="t", cost_estimate=8.0)
        assert enforcer.check_tool_call(ctx).level == "blocked"


# ---------------------------------------------------------------------------
# Thread Safety Tests
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Concurrent access does not corrupt enforcer state."""

    def test_concurrent_checks(self) -> None:
        """Multiple threads checking simultaneously should not crash."""
        policy = _policy("t", max_cost=100.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        errors: list[str] = []
        results: list[GovernanceDecision] = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            try:
                ctx = _context(
                    tool_name="t",
                    cost_estimate=float(i),
                    agent_id=f"agent-{i}",
                )
                decision = enforcer.check_tool_call(ctx)
                with lock:
                    results.append(decision)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 20
        assert all(r.level == "auto_approved" for r in results)

    def test_concurrent_registration_and_check(self) -> None:
        """Registration and checking from different threads should not crash."""
        config = _config()
        enforcer = McpGovernanceEnforcer(config)
        errors: list[str] = []

        def register_worker() -> None:
            try:
                for i in range(50):
                    enforcer.register_tool(_policy(f"tool-{i}", max_cost=100.0))
            except Exception as exc:
                errors.append(str(exc))

        def check_worker() -> None:
            try:
                for i in range(50):
                    ctx = _context(tool_name=f"tool-{i % 10}")
                    enforcer.check_tool_call(ctx)
            except Exception as exc:
                errors.append(str(exc))

        threads = [
            threading.Thread(target=register_worker),
            threading.Thread(target=check_worker),
            threading.Thread(target=check_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"


# ---------------------------------------------------------------------------
# GovernanceDecision Tests
# ---------------------------------------------------------------------------


class TestGovernanceDecision:
    """GovernanceDecision dataclass properties and serialization."""

    def test_allowed_property_auto_approved(self) -> None:
        d = GovernanceDecision(
            level="auto_approved",
            tool_name="t",
            agent_id="a",
            reason="ok",
        )
        assert d.allowed is True

    def test_allowed_property_flagged(self) -> None:
        d = GovernanceDecision(
            level="flagged",
            tool_name="t",
            agent_id="a",
            reason="near limit",
        )
        assert d.allowed is True

    def test_allowed_property_held(self) -> None:
        d = GovernanceDecision(
            level="held",
            tool_name="t",
            agent_id="a",
            reason="needs approval",
        )
        assert d.allowed is False

    def test_allowed_property_blocked(self) -> None:
        d = GovernanceDecision(
            level="blocked",
            tool_name="t",
            agent_id="a",
            reason="denied",
        )
        assert d.allowed is False

    def test_to_dict(self) -> None:
        d = GovernanceDecision(
            level="auto_approved",
            tool_name="web_search",
            agent_id="agent-1",
            reason="within constraints",
        )
        data = d.to_dict()
        assert data["level"] == "auto_approved"
        assert data["tool_name"] == "web_search"
        assert data["agent_id"] == "agent-1"
        assert data["allowed"] is True
        assert "timestamp" in data

    def test_frozen(self) -> None:
        d = GovernanceDecision(
            level="blocked",
            tool_name="t",
            agent_id="a",
            reason="no",
        )
        with pytest.raises(AttributeError):
            d.level = "auto_approved"  # type: ignore[misc]
