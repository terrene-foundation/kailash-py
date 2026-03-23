# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for PACT MCP red team findings C1, C2, C3, H3, H4.

C1: register_tool() must enforce monotonic tightening
C2: _rate_tracker dict must be bounded (10,000 entries max)
C3: McpGovernanceConfig.tool_policies must be immutable (MappingProxyType)
H3: McpActionContext.args and .metadata must be immutable (MappingProxyType)
H4: McpAuditEntry.metadata must be immutable (MappingProxyType)
"""

from __future__ import annotations

import types as _builtin_types
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pact.mcp.audit import McpAuditEntry
from pact.mcp.enforcer import McpGovernanceEnforcer
from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpGovernanceConfig,
    McpToolPolicy,
)


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# C1: register_tool() monotonic tightening
# ---------------------------------------------------------------------------


class TestC1MonotonicTightening:
    """register_tool() must reject policies that widen constraints."""

    def test_widen_max_cost_rejected(self) -> None:
        """Increasing max_cost is a widening violation."""
        policy = _policy("t", max_cost=10.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        with pytest.raises(ValueError, match="Monotonic tightening violation.*max_cost"):
            enforcer.register_tool(_policy("t", max_cost=20.0))

    def test_remove_max_cost_rejected(self) -> None:
        """Setting max_cost to None (unlimited) when it was set is widening."""
        policy = _policy("t", max_cost=10.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        with pytest.raises(ValueError, match="Monotonic tightening violation.*max_cost.*None"):
            enforcer.register_tool(_policy("t", max_cost=None))

    def test_tighten_max_cost_accepted(self) -> None:
        """Decreasing max_cost is allowed (tightening)."""
        policy = _policy("t", max_cost=10.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        enforcer.register_tool(_policy("t", max_cost=5.0))
        # Verify the tightened policy is active
        ctx = _context(tool_name="t", cost_estimate=8.0)
        assert enforcer.check_tool_call(ctx).level == "blocked"

    def test_equal_max_cost_accepted(self) -> None:
        """Same max_cost is allowed (not widening)."""
        policy = _policy("t", max_cost=10.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        enforcer.register_tool(_policy("t", max_cost=10.0))  # should not raise

    def test_widen_rate_limit_rejected(self) -> None:
        """Increasing rate_limit is a widening violation."""
        policy = _policy("t", max_cost=None, rate_limit=5)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        with pytest.raises(ValueError, match="Monotonic tightening violation.*rate_limit"):
            enforcer.register_tool(_policy("t", max_cost=None, rate_limit=10))

    def test_remove_rate_limit_rejected(self) -> None:
        """Setting rate_limit to None (unlimited) when it was set is widening."""
        policy = _policy("t", max_cost=None, rate_limit=5)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        with pytest.raises(ValueError, match="Monotonic tightening violation.*rate_limit.*None"):
            enforcer.register_tool(_policy("t", max_cost=None, rate_limit=None))

    def test_tighten_rate_limit_accepted(self) -> None:
        """Decreasing rate_limit is allowed."""
        policy = _policy("t", max_cost=None, rate_limit=10)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        enforcer.register_tool(_policy("t", max_cost=None, rate_limit=5))

    def test_widen_allowed_args_rejected(self) -> None:
        """Adding new allowed args is a widening violation."""
        policy = _policy("t", max_cost=None, allowed_args=frozenset({"query"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        with pytest.raises(ValueError, match="Monotonic tightening violation.*allowed_args"):
            enforcer.register_tool(
                _policy("t", max_cost=None, allowed_args=frozenset({"query", "extra"}))
            )

    def test_remove_allowed_args_rejected(self) -> None:
        """Setting allowed_args to empty (any) when it was restricted is widening."""
        policy = _policy("t", max_cost=None, allowed_args=frozenset({"query"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        with pytest.raises(ValueError, match="Monotonic tightening violation.*allowed_args.*empty"):
            enforcer.register_tool(_policy("t", max_cost=None, allowed_args=frozenset()))

    def test_subset_allowed_args_accepted(self) -> None:
        """Restricting allowed_args to a subset is tightening."""
        policy = _policy("t", max_cost=None, allowed_args=frozenset({"query", "limit"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        enforcer.register_tool(
            _policy("t", max_cost=None, allowed_args=frozenset({"query"}))
        )

    def test_narrow_denied_args_rejected(self) -> None:
        """Removing denied args is a narrowing violation."""
        policy = _policy("t", max_cost=None, denied_args=frozenset({"password", "secret"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        with pytest.raises(ValueError, match="Monotonic tightening violation.*denied_args"):
            enforcer.register_tool(
                _policy("t", max_cost=None, denied_args=frozenset({"password"}))
            )

    def test_superset_denied_args_accepted(self) -> None:
        """Adding more denied args is tightening (wider deny list)."""
        policy = _policy("t", max_cost=None, denied_args=frozenset({"password"}))
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        enforcer.register_tool(
            _policy("t", max_cost=None, denied_args=frozenset({"password", "secret"}))
        )

    def test_new_tool_no_existing_accepted(self) -> None:
        """Registering a brand-new tool (no existing policy) always succeeds."""
        config = _config()
        enforcer = McpGovernanceEnforcer(config)

        enforcer.register_tool(_policy("brand_new", max_cost=100.0))
        ctx = _context(tool_name="brand_new", cost_estimate=5.0)
        assert enforcer.check_tool_call(ctx).level == "auto_approved"

    def test_successive_tightening(self) -> None:
        """Multiple successive tightenings are all valid."""
        config = _config()
        enforcer = McpGovernanceEnforcer(config)

        enforcer.register_tool(_policy("t", max_cost=100.0))
        enforcer.register_tool(_policy("t", max_cost=50.0))
        enforcer.register_tool(_policy("t", max_cost=25.0))

        # Cannot widen back
        with pytest.raises(ValueError, match="Monotonic tightening violation"):
            enforcer.register_tool(_policy("t", max_cost=30.0))

    def test_overlay_checked_before_config(self) -> None:
        """If overlay already has a tighter policy, widening relative to overlay fails."""
        policy = _policy("t", max_cost=10.0)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        # Tighten via overlay to 5.0
        enforcer.register_tool(_policy("t", max_cost=5.0))

        # Now try to widen to 8.0 (still tighter than config's 10.0 but wider
        # than overlay's 5.0) -- should fail because overlay takes precedence
        with pytest.raises(ValueError, match="Monotonic tightening violation"):
            enforcer.register_tool(_policy("t", max_cost=8.0))


# ---------------------------------------------------------------------------
# C2: _rate_tracker bounded dict
# ---------------------------------------------------------------------------


class TestC2BoundedRateTracker:
    """_rate_tracker dict must be bounded to _MAX_RATE_TRACKER_ENTRIES."""

    def test_rate_tracker_bounded(self) -> None:
        """When rate_tracker reaches max size, old entries are evicted."""
        policy = _policy("t", max_cost=None, rate_limit=100)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        # Lower the limit for test speed
        enforcer._MAX_RATE_TRACKER_ENTRIES = 100

        now = datetime.now(UTC)
        # Create 110 unique agent:tool keys to exceed the limit
        for i in range(110):
            ctx = _context(
                tool_name="t",
                agent_id=f"agent-{i}",
                timestamp=now + timedelta(milliseconds=i),
            )
            enforcer.check_tool_call(ctx)

        # The tracker should have been evicted down below the limit
        assert len(enforcer._rate_tracker) <= 100

    def test_eviction_preserves_recent_entries(self) -> None:
        """Eviction removes the oldest entries, not the newest."""
        policy = _policy("t", max_cost=None, rate_limit=100)
        config = _config(policies={"t": policy})
        enforcer = McpGovernanceEnforcer(config)

        enforcer._MAX_RATE_TRACKER_ENTRIES = 10

        now = datetime.now(UTC)
        # Create entries 0..14 with progressively newer timestamps
        for i in range(15):
            ctx = _context(
                tool_name="t",
                agent_id=f"agent-{i}",
                timestamp=now + timedelta(seconds=i),
            )
            enforcer.check_tool_call(ctx)

        # The newest entries should still be present
        newest_key = "agent-14:t"
        assert newest_key in enforcer._rate_tracker

    def test_max_rate_tracker_entries_constant(self) -> None:
        """The constant exists and has the expected default value."""
        assert McpGovernanceEnforcer._MAX_RATE_TRACKER_ENTRIES == 10_000


# ---------------------------------------------------------------------------
# C3: McpGovernanceConfig.tool_policies immutable
# ---------------------------------------------------------------------------


class TestC3ImmutableToolPolicies:
    """McpGovernanceConfig.tool_policies must be a MappingProxyType."""

    def test_tool_policies_is_mapping_proxy(self) -> None:
        """tool_policies should be MappingProxyType after construction."""
        policy = _policy("t")
        config = _config(policies={"t": policy})
        assert isinstance(config.tool_policies, _builtin_types.MappingProxyType)

    def test_tool_policies_not_mutable(self) -> None:
        """Attempting to mutate tool_policies should raise TypeError."""
        policy = _policy("t")
        config = _config(policies={"t": policy})
        with pytest.raises(TypeError):
            config.tool_policies["new_tool"] = _policy("new_tool")  # type: ignore[index]

    def test_tool_policies_deletion_blocked(self) -> None:
        """Attempting to delete from tool_policies should raise TypeError."""
        policy = _policy("t")
        config = _config(policies={"t": policy})
        with pytest.raises(TypeError):
            del config.tool_policies["t"]  # type: ignore[arg-type]

    def test_empty_tool_policies_is_mapping_proxy(self) -> None:
        """Even empty tool_policies should be a MappingProxyType."""
        config = _config()
        assert isinstance(config.tool_policies, _builtin_types.MappingProxyType)

    def test_original_dict_not_linked(self) -> None:
        """Mutating the original dict should not affect config.tool_policies."""
        policies = {"t": _policy("t")}
        config = McpGovernanceConfig(tool_policies=policies)
        policies["new"] = _policy("new")  # mutate original
        assert "new" not in config.tool_policies


# ---------------------------------------------------------------------------
# H3: McpActionContext.args and .metadata immutable
# ---------------------------------------------------------------------------


class TestH3ImmutableActionContext:
    """McpActionContext.args and .metadata must be MappingProxyType."""

    def test_args_is_mapping_proxy(self) -> None:
        ctx = _context(args={"query": "test"})
        assert isinstance(ctx.args, _builtin_types.MappingProxyType)

    def test_args_not_mutable(self) -> None:
        ctx = _context(args={"query": "test"})
        with pytest.raises(TypeError):
            ctx.args["new_key"] = "val"  # type: ignore[index]

    def test_metadata_is_mapping_proxy(self) -> None:
        ctx = McpActionContext(tool_name="t", metadata={"env": "test"})
        assert isinstance(ctx.metadata, _builtin_types.MappingProxyType)

    def test_metadata_not_mutable(self) -> None:
        ctx = McpActionContext(tool_name="t", metadata={"env": "test"})
        with pytest.raises(TypeError):
            ctx.metadata["injected"] = "attack"  # type: ignore[index]

    def test_original_dict_not_linked(self) -> None:
        """Mutating the original dict should not affect ctx.args."""
        args = {"query": "test"}
        ctx = McpActionContext(tool_name="t", args=args)
        args["injected"] = "attack"
        assert "injected" not in ctx.args

    def test_empty_args_is_mapping_proxy(self) -> None:
        ctx = _context()
        assert isinstance(ctx.args, _builtin_types.MappingProxyType)

    def test_empty_metadata_is_mapping_proxy(self) -> None:
        ctx = _context()
        assert isinstance(ctx.metadata, _builtin_types.MappingProxyType)


# ---------------------------------------------------------------------------
# H4: McpAuditEntry.metadata immutable
# ---------------------------------------------------------------------------


class TestH4ImmutableAuditMetadata:
    """McpAuditEntry.metadata must be a MappingProxyType."""

    def test_metadata_is_mapping_proxy(self) -> None:
        entry = McpAuditEntry(
            tool_name="t",
            agent_id="a",
            decision="blocked",
            metadata={"key": "val"},
        )
        assert isinstance(entry.metadata, _builtin_types.MappingProxyType)

    def test_metadata_not_mutable(self) -> None:
        entry = McpAuditEntry(
            tool_name="t",
            agent_id="a",
            decision="blocked",
            metadata={"key": "val"},
        )
        with pytest.raises(TypeError):
            entry.metadata["injected"] = "attack"  # type: ignore[index]

    def test_original_dict_not_linked(self) -> None:
        metadata = {"key": "val"}
        entry = McpAuditEntry(
            tool_name="t",
            agent_id="a",
            decision="blocked",
            metadata=metadata,
        )
        metadata["injected"] = "attack"
        assert "injected" not in entry.metadata

    def test_empty_metadata_is_mapping_proxy(self) -> None:
        entry = McpAuditEntry(
            tool_name="t",
            agent_id="a",
            decision="blocked",
        )
        assert isinstance(entry.metadata, _builtin_types.MappingProxyType)

    def test_from_dict_roundtrip_preserves_metadata(self) -> None:
        """from_dict should produce a MappingProxyType metadata too."""
        entry = McpAuditEntry(
            tool_name="t",
            agent_id="a",
            decision="blocked",
            metadata={"key": "val"},
        )
        restored = McpAuditEntry.from_dict(entry.to_dict())
        assert isinstance(restored.metadata, _builtin_types.MappingProxyType)
        assert dict(restored.metadata) == {"key": "val"}
