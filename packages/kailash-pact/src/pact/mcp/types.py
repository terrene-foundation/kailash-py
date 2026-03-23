# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP governance types -- frozen dataclasses for tool policy, config, and action context.

All dataclasses are frozen=True (immutable after construction) per pact-governance.md
Rule 5 (MUST NOT Construct as Mutable). All numeric fields are validated with
math.isfinite() per pact-governance.md Rule 6.
"""

from __future__ import annotations

import logging
import math
import types as _builtin_types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "DefaultPolicy",
    "McpActionContext",
    "McpGovernanceConfig",
    "McpToolPolicy",
]


class DefaultPolicy(str, Enum):
    """Default policy for unregistered tools."""

    DENY = "DENY"
    ALLOW = "ALLOW"


@dataclass(frozen=True)
class McpToolPolicy:
    """Policy for a single MCP tool.

    Defines what constraints apply when an agent invokes a specific MCP tool.
    frozen=True prevents mutation after construction.

    Attributes:
        tool_name: The MCP tool name this policy applies to.
        allowed_args: Frozenset of allowed argument name patterns. Empty means
            all arguments are allowed (no arg-level restriction).
        denied_args: Frozenset of explicitly denied argument name patterns.
            Takes precedence over allowed_args.
        max_cost: Maximum cost (USD) for a single invocation of this tool.
            None means no cost limit.
        clearance_required: Minimum confidentiality level required to invoke
            this tool. None means no clearance requirement.
        rate_limit: Maximum number of invocations per minute. None means
            no rate limit.
        description: Human-readable description of this policy.

    Raises:
        ValueError: If max_cost or rate_limit is NaN, Inf, or negative.
    """

    tool_name: str
    allowed_args: frozenset[str] = field(default_factory=frozenset)
    denied_args: frozenset[str] = field(default_factory=frozenset)
    max_cost: float | None = None
    clearance_required: str | None = None
    rate_limit: int | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name must not be empty")
        if self.max_cost is not None:
            cost = float(self.max_cost)
            if not math.isfinite(cost):
                raise ValueError(f"max_cost must be finite, got {self.max_cost!r}")
            if cost < 0:
                raise ValueError(
                    f"max_cost must be non-negative, got {self.max_cost!r}"
                )
        if self.rate_limit is not None:
            if self.rate_limit < 1:
                raise ValueError(f"rate_limit must be >= 1, got {self.rate_limit!r}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "tool_name": self.tool_name,
            "allowed_args": sorted(self.allowed_args),
            "denied_args": sorted(self.denied_args),
            "max_cost": self.max_cost,
            "clearance_required": self.clearance_required,
            "rate_limit": self.rate_limit,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpToolPolicy:
        """Deserialize from a dictionary."""
        return cls(
            tool_name=data["tool_name"],
            allowed_args=frozenset(data.get("allowed_args", [])),
            denied_args=frozenset(data.get("denied_args", [])),
            max_cost=data.get("max_cost"),
            clearance_required=data.get("clearance_required"),
            rate_limit=data.get("rate_limit"),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class McpGovernanceConfig:
    """Configuration for MCP governance enforcement.

    Defines the default policy and per-tool policies for an MCP governance
    enforcer instance. frozen=True prevents mutation after construction.

    Attributes:
        default_policy: Whether unregistered tools are denied (DENY) or
            allowed (ALLOW). DENY is strongly recommended per pact-governance.md
            Rule 5 (default-deny tool registration).
        tool_policies: Mapping of tool name to McpToolPolicy.
        audit_enabled: Whether to record audit entries for tool invocations.
        max_audit_entries: Maximum audit trail entries (bounded collection).

    Raises:
        ValueError: If max_audit_entries is < 1.
    """

    default_policy: DefaultPolicy = DefaultPolicy.DENY
    tool_policies: dict[str, McpToolPolicy] = field(default_factory=dict)
    audit_enabled: bool = True
    max_audit_entries: int = 10_000

    def __post_init__(self) -> None:
        if self.max_audit_entries < 1:
            raise ValueError(
                f"max_audit_entries must be >= 1, got {self.max_audit_entries}"
            )
        # Validate each policy tool_name matches its dict key
        for key, policy in self.tool_policies.items():
            if key != policy.tool_name:
                raise ValueError(
                    f"tool_policies key '{key}' does not match "
                    f"policy.tool_name '{policy.tool_name}'"
                )
        # C3: Replace mutable dict with immutable MappingProxyType.
        # Use object.__setattr__ because the dataclass is frozen.
        object.__setattr__(
            self,
            "tool_policies",
            _builtin_types.MappingProxyType(dict(self.tool_policies)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "default_policy": self.default_policy.value,
            "tool_policies": {
                name: policy.to_dict() for name, policy in self.tool_policies.items()
            },
            "audit_enabled": self.audit_enabled,
            "max_audit_entries": self.max_audit_entries,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpGovernanceConfig:
        """Deserialize from a dictionary."""
        policies = {}
        for name, pdata in data.get("tool_policies", {}).items():
            policies[name] = McpToolPolicy.from_dict(pdata)
        return cls(
            default_policy=DefaultPolicy(data.get("default_policy", "DENY")),
            tool_policies=policies,
            audit_enabled=data.get("audit_enabled", True),
            max_audit_entries=data.get("max_audit_entries", 10_000),
        )


@dataclass(frozen=True)
class McpActionContext:
    """Context for a single MCP tool invocation being evaluated.

    Carries all the information needed for the enforcer to make a governance
    decision about an MCP tool call. frozen=True prevents mutation.

    Attributes:
        tool_name: The MCP tool being invoked.
        args: Arguments being passed to the tool.
        agent_id: Identifier of the agent making the call.
        timestamp: When the invocation was initiated.
        cost_estimate: Estimated cost (USD) for this invocation.
            None means no cost estimate available.
        metadata: Additional context for governance evaluation.

    Raises:
        ValueError: If cost_estimate is NaN, Inf, or negative.
    """

    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    cost_estimate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name must not be empty")
        if self.cost_estimate is not None:
            cost = float(self.cost_estimate)
            if not math.isfinite(cost):
                raise ValueError(
                    f"cost_estimate must be finite, got {self.cost_estimate!r}"
                )
            if cost < 0:
                raise ValueError(
                    f"cost_estimate must be non-negative, got {self.cost_estimate!r}"
                )
        # H3: Replace mutable dicts with immutable MappingProxyType.
        object.__setattr__(
            self,
            "args",
            _builtin_types.MappingProxyType(dict(self.args)),
        )
        object.__setattr__(
            self,
            "metadata",
            _builtin_types.MappingProxyType(dict(self.metadata)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "tool_name": self.tool_name,
            "args": self.args,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "cost_estimate": self.cost_estimate,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpActionContext:
        """Deserialize from a dictionary."""
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            tool_name=data["tool_name"],
            args=data.get("args", {}),
            agent_id=data.get("agent_id", ""),
            timestamp=ts or datetime.now(UTC),
            cost_estimate=data.get("cost_estimate"),
            metadata=data.get("metadata", {}),
        )
