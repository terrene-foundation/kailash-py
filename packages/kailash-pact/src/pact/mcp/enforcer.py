# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP governance enforcer -- the core enforcement engine for MCP tool calls.

Provides McpGovernanceEnforcer which checks MCP tool invocations against
governance policies and returns deterministic decisions. This is a PRIMITIVE
(no LLM, purely deterministic).

Security invariants (per pact-governance.md):
1. Default-deny: unregistered tools are BLOCKED (Rule 5)
2. NaN/Inf defense: math.isfinite() on all numeric fields (Rule 6)
3. Thread-safe: all shared state access acquires self._lock (Rule 8)
4. Fail-closed: all error paths return BLOCKED (Rule 4)
5. Bounded collections: audit trail uses deque(maxlen=N) (Rule 7)
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pact.mcp.audit import McpAuditTrail
from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpGovernanceConfig,
    McpToolPolicy,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GovernanceDecision",
    "McpGovernanceEnforcer",
]


@dataclass(frozen=True)
class GovernanceDecision:
    """Result of an MCP governance check.

    frozen=True: decisions are immutable records of governance evaluations.

    Attributes:
        level: Verification gradient level. One of:
            "auto_approved" -- tool call is within all constraints
            "flagged" -- tool call is near a boundary (cost near limit)
            "held" -- tool call exceeds soft limit, needs approval
            "blocked" -- tool call violates a hard constraint
        tool_name: The MCP tool that was evaluated.
        agent_id: The agent that attempted the call.
        reason: Human-readable explanation of the decision.
        timestamp: When the decision was made.
        policy_snapshot: Serialized policy that was evaluated, if any.
        metadata: Additional structured details.
    """

    level: str
    tool_name: str
    agent_id: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    policy_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """True if the tool call is permitted (auto_approved or flagged).

        FLAGGED calls are allowed but should be logged for review.
        HELD and BLOCKED calls are not allowed.
        """
        return self.level in ("auto_approved", "flagged")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "level": self.level,
            "tool_name": self.tool_name,
            "agent_id": self.agent_id,
            "reason": self.reason,
            "allowed": self.allowed,
            "timestamp": self.timestamp.isoformat(),
            "policy_snapshot": self.policy_snapshot,
            "metadata": self.metadata,
        }


class McpGovernanceEnforcer:
    """Core enforcement engine for MCP tool invocation governance.

    Evaluates MCP tool calls against governance policies and returns
    deterministic GovernanceDecision results. This is a PRIMITIVE -- no LLM
    involvement, purely rule-based.

    Security invariants:
    - Default-deny for unregistered tools (configurable to ALLOW, but DENY
      is the default and strongly recommended).
    - NaN/Inf defense on all numeric fields via math.isfinite().
    - Thread-safe: all shared state access acquires self._lock.
    - Fail-closed: all error paths return BLOCKED decisions.
    - Bounded audit trail via McpAuditTrail.

    Args:
        config: The MCP governance configuration with tool policies.
    """

    def __init__(self, config: McpGovernanceConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._audit_trail = McpAuditTrail(
            max_entries=config.max_audit_entries,
        )
        # Mutable overlay for runtime tool registration
        self._policy_overlay: dict[str, McpToolPolicy] = {}
        # Rate tracking: "agent_id:tool_name" -> deque of timestamps
        self._rate_tracker: dict[str, deque[datetime]] = {}

    @property
    def config(self) -> McpGovernanceConfig:
        """The governance configuration (read-only)."""
        return self._config

    @property
    def audit_trail(self) -> McpAuditTrail:
        """The audit trail for governance decisions."""
        return self._audit_trail

    def check_tool_call(self, context: McpActionContext) -> GovernanceDecision:
        """Main entry point: evaluate an MCP tool call against governance policies.

        Implements the verification gradient:
        1. Check if tool is registered (default-deny for unregistered)
        2. Validate numeric fields (NaN/Inf defense)
        3. Check argument constraints (denied_args, allowed_args)
        4. Check cost constraints (max_cost)
        5. Check rate limits
        6. Return appropriate gradient level

        Fail-closed: any exception during evaluation returns BLOCKED.

        Args:
            context: The MCP action context describing the tool call.

        Returns:
            A GovernanceDecision with the verdict.
        """
        try:
            decision = self._evaluate(context)
        except Exception as exc:
            logger.warning(
                "McpGovernanceEnforcer: evaluation failed for tool '%s': %s",
                context.tool_name,
                exc,
            )
            decision = GovernanceDecision(
                level="blocked",
                tool_name=context.tool_name,
                agent_id=context.agent_id,
                reason="Internal error during governance check -- fail-closed to BLOCKED",
                timestamp=context.timestamp,
            )

        # Record audit entry if enabled
        if self._config.audit_enabled:
            self._audit_trail.record(
                tool_name=context.tool_name,
                agent_id=context.agent_id,
                decision=decision.level,
                reason=decision.reason,
                cost_estimate=context.cost_estimate,
                metadata={
                    "args_keys": sorted(context.args.keys()) if context.args else [],
                    **(context.metadata or {}),
                },
            )

        return decision

    def register_tool(self, policy: McpToolPolicy) -> None:
        """Register or update a tool policy at runtime.

        Thread-safe: acquires self._lock.

        Args:
            policy: The tool policy to register.
        """
        with self._lock:
            self._policy_overlay[policy.tool_name] = policy

    def _get_policy(self, tool_name: str) -> McpToolPolicy | None:
        """Resolve the effective policy for a tool.

        Checks the mutable overlay first (runtime registrations), then
        the immutable config.

        Args:
            tool_name: The tool to look up.

        Returns:
            The McpToolPolicy, or None if not registered.
        """
        with self._lock:
            overlay = self._policy_overlay.get(tool_name)
            if overlay is not None:
                return overlay
        return self._config.tool_policies.get(tool_name)

    def _evaluate(self, context: McpActionContext) -> GovernanceDecision:
        """Internal evaluation logic. Caller handles exceptions.

        Returns:
            A GovernanceDecision with the appropriate gradient level.
        """
        tool_name = context.tool_name
        agent_id = context.agent_id

        # Step 1: Check tool registration
        policy = self._get_policy(tool_name)
        if policy is None:
            if self._config.default_policy == DefaultPolicy.DENY:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"Tool '{tool_name}' is not registered -- default-deny policy",
                    timestamp=context.timestamp,
                )
            else:
                # ALLOW default -- permitted but not governed
                return GovernanceDecision(
                    level="auto_approved",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"Tool '{tool_name}' is not registered -- default-allow policy",
                    timestamp=context.timestamp,
                )

        # Step 2: Validate cost_estimate (NaN/Inf defense)
        cost = context.cost_estimate
        if cost is not None:
            cost_float = float(cost)
            if not math.isfinite(cost_float):
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"cost_estimate is not finite ({cost_float!r}) -- fail-closed to BLOCKED",
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )
            if cost_float < 0:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"cost_estimate is negative ({cost_float}) -- fail-closed to BLOCKED",
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )

        # Step 3: Check argument constraints
        if context.args:
            arg_names = set(context.args.keys())

            # Denied args take precedence
            if policy.denied_args:
                denied_found = arg_names & policy.denied_args
                if denied_found:
                    return GovernanceDecision(
                        level="blocked",
                        tool_name=tool_name,
                        agent_id=agent_id,
                        reason=(
                            f"Arguments {sorted(denied_found)} are denied by "
                            f"tool policy for '{tool_name}'"
                        ),
                        timestamp=context.timestamp,
                        policy_snapshot=policy.to_dict(),
                    )

            # If allowed_args is set, only those args are permitted
            if policy.allowed_args:
                disallowed = arg_names - policy.allowed_args
                if disallowed:
                    return GovernanceDecision(
                        level="blocked",
                        tool_name=tool_name,
                        agent_id=agent_id,
                        reason=(
                            f"Arguments {sorted(disallowed)} are not in the allowed "
                            f"set for tool '{tool_name}'"
                        ),
                        timestamp=context.timestamp,
                        policy_snapshot=policy.to_dict(),
                    )

        # Step 4: Check cost constraints
        if cost is not None and policy.max_cost is not None:
            cost_float = float(cost)
            max_cost = float(policy.max_cost)

            if cost_float > max_cost:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=(
                        f"cost_estimate (${cost_float:.2f}) exceeds max_cost "
                        f"(${max_cost:.2f}) for tool '{tool_name}'"
                    ),
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )

            # Flagged if within 20% of max_cost
            if max_cost > 0 and cost_float > max_cost * 0.8:
                return GovernanceDecision(
                    level="flagged",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=(
                        f"cost_estimate (${cost_float:.2f}) is within 20% of max_cost "
                        f"(${max_cost:.2f}) for tool '{tool_name}'"
                    ),
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )

        # Step 5: Check rate limits
        if policy.rate_limit is not None:
            rate_decision = self._check_rate_limit(
                agent_id, tool_name, policy.rate_limit, context.timestamp
            )
            if rate_decision is not None:
                return rate_decision

        # All checks passed
        return GovernanceDecision(
            level="auto_approved",
            tool_name=tool_name,
            agent_id=agent_id,
            reason=f"Tool '{tool_name}' call is within all governance constraints",
            timestamp=context.timestamp,
            policy_snapshot=policy.to_dict(),
        )

    def _check_rate_limit(
        self,
        agent_id: str,
        tool_name: str,
        rate_limit: int,
        now: datetime,
    ) -> GovernanceDecision | None:
        """Check rate limit for a specific agent+tool combination.

        Thread-safe: acquires self._lock.

        Args:
            agent_id: The agent making the call.
            tool_name: The tool being invoked.
            rate_limit: Maximum invocations per minute.
            now: Current timestamp.

        Returns:
            A BLOCKED GovernanceDecision if rate limit exceeded, None otherwise.
        """
        key = f"{agent_id}:{tool_name}"
        with self._lock:
            if key not in self._rate_tracker:
                # Bounded deque for rate tracking
                self._rate_tracker[key] = deque(maxlen=rate_limit + 1)

            tracker = self._rate_tracker[key]

            # Prune entries older than 60 seconds
            cutoff = now.timestamp() - 60.0
            while tracker and tracker[0].timestamp() < cutoff:
                tracker.popleft()

            if len(tracker) >= rate_limit:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=(
                        f"Rate limit exceeded: {len(tracker)} calls in last 60s "
                        f"(limit: {rate_limit}/min) for tool '{tool_name}'"
                    ),
                    timestamp=now,
                )

            # Record this invocation timestamp
            tracker.append(now)

        return None
