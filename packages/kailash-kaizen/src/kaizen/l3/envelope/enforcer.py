# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EnvelopeEnforcer — non-bypassable middleware for L3 operations.

Combines EnvelopeTracker (continuous budget tracking) with optional
strict enforcement for non-depletable dimensions (via a callback).

INV-3: Cannot be disabled, paused, or bypassed at runtime.
No disable(), bypass(), skip(), or pause() methods.
No enabled/active flag.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any, Callable

from kaizen.l3.envelope.errors import EnforcerError
from kaizen.l3.envelope.tracker import EnvelopeTracker
from kaizen.l3.envelope.types import (
    CostEntry,
    DimensionUsage,
    EnforcementContext,
    GradientZone,
    Verdict,
)

__all__ = ["EnvelopeEnforcer"]

logger = logging.getLogger(__name__)

# Type for the strict check callback.
# Returns a dimension name (str) if the action should be BLOCKED
# on a non-depletable dimension, or None if the action passes.
StrictCheckFn = Callable[[EnforcementContext], str | None]


class EnvelopeEnforcer:
    """Non-bypassable envelope enforcement middleware.

    Wraps an EnvelopeTracker and provides check_action() / record_action()
    for the enforced execution path. An optional strict_check callback
    handles non-depletable dimension validation (data_access, communication).

    INV-3: This class has NO disable(), bypass(), skip(), or pause() methods.
    It cannot be deactivated at runtime. The only way to widen an envelope
    is through PACT emergency bypass protocol (creating a new Delegation
    Record with a time-limited expanded envelope).

    Args:
        tracker: The EnvelopeTracker to enforce against.
        strict_check: Optional callback for non-depletable dimension checks.
                     Returns a dimension name if BLOCKED, None if allowed.
    """

    __slots__ = (
        "_tracker",
        "_strict_check",
        "_approved_actions",
        "_agent_envelopes",
    )

    def __init__(
        self,
        tracker: EnvelopeTracker,
        strict_check: StrictCheckFn | None = None,
    ) -> None:
        if tracker is None:
            raise ValueError("EnvelopeEnforcer requires a non-None tracker")
        self._tracker = tracker
        self._strict_check = strict_check
        # Track which actions have been approved (keyed by action+agent_instance_id)
        self._approved_actions: set[str] = set()
        # L3 integration: per-agent envelope registry (agent_id -> envelope dict)
        self._agent_envelopes: dict[str, dict[str, Any]] = {}

    @property
    def tracker(self) -> EnvelopeTracker:
        """Read-only access to the underlying tracker."""
        return self._tracker

    # -------------------------------------------------------------------
    # L3 integration: per-agent envelope registration
    # -------------------------------------------------------------------

    def register(self, agent_id: str, envelope: dict[str, Any]) -> None:
        """Register an agent's envelope for enforcement tracking.

        Called by AgentFactory at spawn time to associate an agent instance
        with its constraint envelope. This enables per-agent enforcement
        queries via :meth:`is_registered` and future per-agent budget checks.

        Args:
            agent_id: The agent instance ID.
            envelope: The constraint envelope dict for this agent.

        Raises:
            ValueError: If agent_id is empty or already registered.
        """
        if not agent_id:
            raise ValueError("agent_id must be a non-empty string")
        if agent_id in self._agent_envelopes:
            raise ValueError(
                f"Agent '{agent_id}' is already registered with the enforcer"
            )
        self._agent_envelopes[agent_id] = envelope
        logger.debug("Registered agent envelope: agent_id=%s", agent_id)

    def deregister(self, agent_id: str) -> None:
        """Remove an agent's envelope registration.

        Called when an agent is terminated to clean up the registry.

        Args:
            agent_id: The agent instance ID to deregister.
        """
        self._agent_envelopes.pop(agent_id, None)
        logger.debug("Deregistered agent envelope: agent_id=%s", agent_id)

    def is_registered(self, agent_id: str) -> bool:
        """Check if an agent has a registered envelope.

        Args:
            agent_id: The agent instance ID.

        Returns:
            True if the agent has a registered envelope.
        """
        return agent_id in self._agent_envelopes

    def get_agent_envelope(self, agent_id: str) -> dict[str, Any] | None:
        """Retrieve the registered envelope for an agent.

        Args:
            agent_id: The agent instance ID.

        Returns:
            The envelope dict, or None if the agent is not registered.
        """
        return self._agent_envelopes.get(agent_id)

    async def check_action(self, context: EnforcementContext) -> Verdict:
        """Pre-execution check — returns a Verdict without recording cost.

        Spec 4.3.2. Check sequence:
        1. Strict enforcer checks non-depletable dimensions -> BLOCKED if rejected
        2. Tracker evaluates estimated cost against depletable dimensions
        3. If HELD, create hold entry
        4. Return verdict

        Args:
            context: The enforcement context describing the action.

        Returns:
            Verdict indicating whether the action may proceed.

        Raises:
            EnforcerError: If the context is invalid.
        """
        # Step 1: Strict check for non-depletable dimensions
        if self._strict_check is not None:
            blocked_dim = self._strict_check(context)
            if blocked_dim is not None:
                return Verdict.blocked(
                    dimension=blocked_dim,
                    detail=f"Action '{context.action}' blocked by "
                    f"non-depletable dimension '{blocked_dim}'",
                    requested=context.estimated_cost,
                    available=0.0,
                )

        # Step 2: Check depletable dimensions via tracker's can_afford
        can = await self._tracker.can_afford(context)
        if not can:
            return Verdict.blocked(
                dimension="financial",
                detail=f"Estimated cost {context.estimated_cost} exceeds budget",
                requested=context.estimated_cost,
                available=0.0,
            )

        # Step 3: Determine zone by simulating the cost
        # Use the tracker's usage to determine what zone we'd be in
        usage = await self._tracker.usage_pct()

        # Compute post-action usage for each dimension
        highest_zone = usage.highest_zone
        for dim, cost in context.dimension_costs.items():
            consumed, limit = self._tracker._get_consumed_and_limit(dim)
            if limit is not None and limit > 0:
                post_usage = (consumed + cost) / limit
                zone = self._tracker._zone_for_usage(post_usage, dim)
                if zone == GradientZone.HELD:
                    hold_id = str(uuid.uuid4())
                    # Mark as approved (held actions are still approved for recording)
                    action_key = self._action_key(context)
                    self._approved_actions.add(action_key)
                    return Verdict.held(
                        dimension=dim,
                        current_usage=post_usage,
                        threshold=self._tracker.gradient.get_thresholds(dim)[1],
                        hold_id=hold_id,
                    )
                if zone == GradientZone.BLOCKED:
                    return Verdict.blocked(
                        dimension=dim,
                        detail=f"Would exceed budget for '{dim}'",
                        requested=cost,
                        available=max(0.0, limit - consumed),
                    )

        # Approved — compute final zone from usage
        post_usage = await self._tracker.usage_pct()

        # Determine the zone we'd be in after this action
        result_zone = GradientZone.AUTO_APPROVED
        for dim, cost in context.dimension_costs.items():
            consumed, limit = self._tracker._get_consumed_and_limit(dim)
            if limit is not None and limit > 0:
                post_pct = (consumed + cost) / limit
                flag_t, hold_t = self._tracker.gradient.get_thresholds(dim)
                if post_pct >= flag_t:
                    from kaizen.l3.envelope.types import zone_max

                    result_zone = zone_max(result_zone, GradientZone.FLAGGED)

        action_key = self._action_key(context)
        self._approved_actions.add(action_key)

        return Verdict.approved(
            zone=result_zone,
            dimension_usage=post_usage,
        )

    async def record_action(
        self,
        context: EnforcementContext,
        actual_cost: float,
    ) -> Verdict:
        """Post-execution recording — records the actual cost.

        Spec 4.3.3. Must call check_action() first.

        Args:
            context: The same context that was checked.
            actual_cost: The actual financial cost incurred.

        Returns:
            Verdict reflecting the post-action state.

        Raises:
            EnforcerError: If check_action was not called first, or cost invalid.
        """
        # Validate actual_cost
        if not math.isfinite(actual_cost):
            raise EnforcerError.invalid_context(
                reason=f"actual_cost must be finite, got {actual_cost!r}"
            )
        if actual_cost < 0:
            raise EnforcerError.invalid_context(
                reason=f"actual_cost must be non-negative, got {actual_cost!r}"
            )

        # Check that check_action was called
        action_key = self._action_key(context)
        if action_key not in self._approved_actions:
            raise EnforcerError.action_not_approved(action=context.action)
        self._approved_actions.discard(action_key)

        # Record via tracker
        entry = CostEntry(
            action=context.action,
            dimension="financial",
            cost=actual_cost,
            timestamp=datetime.now(UTC),
            agent_instance_id=context.agent_instance_id,
            metadata=context.metadata,
        )
        return await self._tracker.record_consumption(entry)

    @staticmethod
    def _action_key(context: EnforcementContext) -> str:
        """Generate a key for tracking approved actions."""
        return f"{context.action}:{context.agent_instance_id}"
