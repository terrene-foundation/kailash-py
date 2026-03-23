# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for pact.mcp.types -- MCP governance type validation.

Covers:
- McpToolPolicy: frozen, NaN/Inf defense, serialization
- McpGovernanceConfig: frozen, validation, serialization
- McpActionContext: frozen, NaN/Inf defense, serialization
- DefaultPolicy enum
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpGovernanceConfig,
    McpToolPolicy,
)


# ---------------------------------------------------------------------------
# McpToolPolicy
# ---------------------------------------------------------------------------


class TestMcpToolPolicy:
    """McpToolPolicy construction, validation, and serialization."""

    def test_basic_construction(self) -> None:
        policy = McpToolPolicy(tool_name="web_search", max_cost=1.0, rate_limit=10)
        assert policy.tool_name == "web_search"
        assert policy.max_cost == 1.0
        assert policy.rate_limit == 10

    def test_frozen(self) -> None:
        policy = McpToolPolicy(tool_name="web_search")
        with pytest.raises(AttributeError):
            policy.tool_name = "other"  # type: ignore[misc]

    def test_empty_tool_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="tool_name must not be empty"):
            McpToolPolicy(tool_name="")

    def test_nan_max_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_cost must be finite"):
            McpToolPolicy(tool_name="t", max_cost=float("nan"))

    def test_inf_max_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_cost must be finite"):
            McpToolPolicy(tool_name="t", max_cost=float("inf"))

    def test_neg_inf_max_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_cost must be finite"):
            McpToolPolicy(tool_name="t", max_cost=float("-inf"))

    def test_negative_max_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_cost must be non-negative"):
            McpToolPolicy(tool_name="t", max_cost=-1.0)

    def test_zero_max_cost_accepted(self) -> None:
        policy = McpToolPolicy(tool_name="t", max_cost=0.0)
        assert policy.max_cost == 0.0

    def test_zero_rate_limit_rejected(self) -> None:
        with pytest.raises(ValueError, match="rate_limit must be >= 1"):
            McpToolPolicy(tool_name="t", rate_limit=0)

    def test_negative_rate_limit_rejected(self) -> None:
        with pytest.raises(ValueError, match="rate_limit must be >= 1"):
            McpToolPolicy(tool_name="t", rate_limit=-5)

    def test_allowed_args_frozenset(self) -> None:
        policy = McpToolPolicy(
            tool_name="t",
            allowed_args=frozenset({"query", "limit"}),
        )
        assert policy.allowed_args == frozenset({"query", "limit"})

    def test_denied_args_frozenset(self) -> None:
        policy = McpToolPolicy(
            tool_name="t",
            denied_args=frozenset({"password"}),
        )
        assert policy.denied_args == frozenset({"password"})

    def test_to_dict_roundtrip(self) -> None:
        policy = McpToolPolicy(
            tool_name="web_search",
            allowed_args=frozenset({"query"}),
            denied_args=frozenset({"secret"}),
            max_cost=5.0,
            clearance_required="CONFIDENTIAL",
            rate_limit=20,
            description="Search the web",
        )
        data = policy.to_dict()
        restored = McpToolPolicy.from_dict(data)
        assert restored.tool_name == policy.tool_name
        assert restored.allowed_args == policy.allowed_args
        assert restored.denied_args == policy.denied_args
        assert restored.max_cost == policy.max_cost
        assert restored.clearance_required == policy.clearance_required
        assert restored.rate_limit == policy.rate_limit
        assert restored.description == policy.description

    def test_none_optional_fields(self) -> None:
        policy = McpToolPolicy(tool_name="t")
        assert policy.max_cost is None
        assert policy.clearance_required is None
        assert policy.rate_limit is None
        assert policy.allowed_args == frozenset()
        assert policy.denied_args == frozenset()
        assert policy.description == ""


# ---------------------------------------------------------------------------
# McpGovernanceConfig
# ---------------------------------------------------------------------------


class TestMcpGovernanceConfig:
    """McpGovernanceConfig construction, validation, and serialization."""

    def test_default_construction(self) -> None:
        config = McpGovernanceConfig()
        assert config.default_policy == DefaultPolicy.DENY
        assert config.tool_policies == {}
        assert config.audit_enabled is True
        assert config.max_audit_entries == 10_000

    def test_frozen(self) -> None:
        config = McpGovernanceConfig()
        with pytest.raises(AttributeError):
            config.default_policy = DefaultPolicy.ALLOW  # type: ignore[misc]

    def test_with_policies(self) -> None:
        policy = McpToolPolicy(tool_name="search", max_cost=1.0)
        config = McpGovernanceConfig(
            tool_policies={"search": policy},
        )
        assert "search" in config.tool_policies
        assert config.tool_policies["search"].max_cost == 1.0

    def test_key_mismatch_rejected(self) -> None:
        policy = McpToolPolicy(tool_name="search")
        with pytest.raises(ValueError, match="does not match"):
            McpGovernanceConfig(
                tool_policies={"wrong_key": policy},
            )

    def test_zero_max_audit_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_audit_entries must be >= 1"):
            McpGovernanceConfig(max_audit_entries=0)

    def test_allow_policy(self) -> None:
        config = McpGovernanceConfig(default_policy=DefaultPolicy.ALLOW)
        assert config.default_policy == DefaultPolicy.ALLOW

    def test_to_dict_roundtrip(self) -> None:
        policy = McpToolPolicy(tool_name="run", max_cost=10.0)
        config = McpGovernanceConfig(
            default_policy=DefaultPolicy.ALLOW,
            tool_policies={"run": policy},
            audit_enabled=False,
            max_audit_entries=500,
        )
        data = config.to_dict()
        restored = McpGovernanceConfig.from_dict(data)
        assert restored.default_policy == config.default_policy
        assert "run" in restored.tool_policies
        assert restored.tool_policies["run"].max_cost == 10.0
        assert restored.audit_enabled is False
        assert restored.max_audit_entries == 500


# ---------------------------------------------------------------------------
# McpActionContext
# ---------------------------------------------------------------------------


class TestMcpActionContext:
    """McpActionContext construction, validation, and serialization."""

    def test_basic_construction(self) -> None:
        ctx = McpActionContext(
            tool_name="web_search",
            args={"query": "test"},
            agent_id="agent-1",
        )
        assert ctx.tool_name == "web_search"
        assert ctx.args == {"query": "test"}
        assert ctx.agent_id == "agent-1"
        assert ctx.cost_estimate is None

    def test_frozen(self) -> None:
        ctx = McpActionContext(tool_name="t")
        with pytest.raises(AttributeError):
            ctx.tool_name = "other"  # type: ignore[misc]

    def test_empty_tool_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="tool_name must not be empty"):
            McpActionContext(tool_name="")

    def test_nan_cost_estimate_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost_estimate must be finite"):
            McpActionContext(tool_name="t", cost_estimate=float("nan"))

    def test_inf_cost_estimate_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost_estimate must be finite"):
            McpActionContext(tool_name="t", cost_estimate=float("inf"))

    def test_negative_cost_estimate_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost_estimate must be non-negative"):
            McpActionContext(tool_name="t", cost_estimate=-0.01)

    def test_zero_cost_estimate_accepted(self) -> None:
        ctx = McpActionContext(tool_name="t", cost_estimate=0.0)
        assert ctx.cost_estimate == 0.0

    def test_timestamp_auto_set(self) -> None:
        before = datetime.now(UTC)
        ctx = McpActionContext(tool_name="t")
        after = datetime.now(UTC)
        assert before <= ctx.timestamp <= after

    def test_to_dict_roundtrip(self) -> None:
        now = datetime.now(UTC)
        ctx = McpActionContext(
            tool_name="run_code",
            args={"code": "print(1)"},
            agent_id="agent-42",
            timestamp=now,
            cost_estimate=0.5,
            metadata={"env": "test"},
        )
        data = ctx.to_dict()
        restored = McpActionContext.from_dict(data)
        assert restored.tool_name == ctx.tool_name
        assert restored.args == ctx.args
        assert restored.agent_id == ctx.agent_id
        assert restored.cost_estimate == ctx.cost_estimate
        assert restored.metadata == ctx.metadata


# ---------------------------------------------------------------------------
# DefaultPolicy enum
# ---------------------------------------------------------------------------


class TestDefaultPolicy:
    """DefaultPolicy enum values."""

    def test_deny_value(self) -> None:
        assert DefaultPolicy.DENY.value == "DENY"

    def test_allow_value(self) -> None:
        assert DefaultPolicy.ALLOW.value == "ALLOW"

    def test_from_string(self) -> None:
        assert DefaultPolicy("DENY") == DefaultPolicy.DENY
        assert DefaultPolicy("ALLOW") == DefaultPolicy.ALLOW
