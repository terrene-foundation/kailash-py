# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Budget Reclamation and Predictive Warnings.

Tracks budget allocation and consumption across the agent hierarchy.
Provides:
- Predictive warnings at configurable thresholds (default 70% projected)
- Budget reclamation on child completion (unused → parent pool)
- Exhaustion handling: HELD (not immediate BLOCKED) to allow reallocation

Budget exhaustion triggers HELD rather than BLOCKED because a sibling may
have unused budget that can be reallocated. Only after reallocation fails
does exhaustion escalate to BLOCKED.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetTracker",
    "BudgetEvent",
    "BudgetSnapshot",
]


@dataclass(frozen=True)
class BudgetSnapshot:
    """Point-in-time budget state for an agent.

    Attributes:
        agent_id: The agent's instance ID.
        allocated: Total budget allocated.
        consumed: Budget consumed so far.
        remaining: Budget remaining (allocated - consumed).
        utilization: Fraction consumed (consumed / allocated), or 0 if unallocated.
    """

    agent_id: str
    allocated: float
    consumed: float

    @property
    def remaining(self) -> float:
        """Budget remaining."""
        return max(0.0, self.allocated - self.consumed)

    @property
    def utilization(self) -> float:
        """Fraction of budget consumed."""
        if self.allocated <= 0:
            return 0.0
        return min(1.0, self.consumed / self.allocated)


@dataclass(frozen=True)
class BudgetEvent:
    """An event from the budget tracking system.

    Attributes:
        event_type: One of: warning, exhaustion_held, reclaimed, reallocated.
        agent_id: The agent this event pertains to.
        details: Structured event details.
    """

    event_type: str
    agent_id: str
    details: dict[str, Any] = field(default_factory=dict)


class BudgetTracker:
    """Tracks budget across the agent hierarchy with predictive warnings.

    Thread-safe. Bounded event history (maxlen=10000).

    Usage:
        tracker = BudgetTracker(warning_threshold=0.70)
        tracker.allocate("root", 100.0)
        tracker.allocate("child-1", 30.0, parent_id="root")
        events = tracker.record_consumption("child-1", 25.0)
        # events may contain a warning if projected to exceed 70%
    """

    def __init__(
        self,
        warning_threshold: float = 0.70,
        hold_threshold: float = 1.0,
        maxlen: int = 10000,
        max_agents: int = 100_000,
    ) -> None:
        if not math.isfinite(warning_threshold):
            raise ValueError(f"warning_threshold must be finite, got {warning_threshold}")
        if not math.isfinite(hold_threshold):
            raise ValueError(f"hold_threshold must be finite, got {hold_threshold}")
        if warning_threshold < 0.0 or warning_threshold > 1.0:
            raise ValueError(f"warning_threshold must be in [0, 1], got {warning_threshold}")
        if hold_threshold < warning_threshold:
            raise ValueError(
                f"hold_threshold ({hold_threshold}) must be >= warning_threshold ({warning_threshold})"
            )

        self._lock = threading.Lock()
        self._max_agents = max_agents
        self._warning_threshold = warning_threshold
        self._hold_threshold = hold_threshold
        self._allocated: dict[str, float] = {}
        self._consumed: dict[str, float] = {}
        self._parent: dict[str, str | None] = {}
        self._children: dict[str, list[str]] = {}
        self._warned: set[str] = set()  # agents that already received warnings
        self._held: set[str] = set()  # agents currently HELD for budget exhaustion
        self._events: deque[BudgetEvent] = deque(maxlen=maxlen)

    def allocate(
        self,
        agent_id: str,
        amount: float,
        parent_id: str | None = None,
    ) -> None:
        """Allocate budget to an agent.

        Args:
            agent_id: The agent to allocate to.
            amount: The budget amount (must be finite and non-negative).
            parent_id: The parent agent, for hierarchy tracking.

        Raises:
            ValueError: If amount is NaN, Inf, or negative.
        """
        if not math.isfinite(amount):
            raise ValueError(f"amount must be finite, got {amount}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

        with self._lock:
            # R1-03: Bounded agent tracking for new agents only
            if agent_id not in self._allocated and len(self._allocated) >= self._max_agents:
                raise ValueError(
                    f"Agent registration limit ({self._max_agents}) reached. "
                    f"Cannot allocate for '{agent_id}'."
                )
            self._allocated[agent_id] = self._allocated.get(agent_id, 0.0) + amount
            self._consumed.setdefault(agent_id, 0.0)
            self._parent[agent_id] = parent_id
            self._children.setdefault(agent_id, [])
            if parent_id is not None:
                self._children.setdefault(parent_id, []).append(agent_id)

    def record_consumption(self, agent_id: str, amount: float) -> list[BudgetEvent]:
        """Record budget consumption and check for warnings/exhaustion.

        Args:
            agent_id: The consuming agent.
            amount: The amount consumed (must be finite and non-negative).

        Returns:
            List of BudgetEvents (warnings, holds) triggered by this consumption.

        Raises:
            ValueError: If amount is NaN, Inf, or negative.
            ValueError: If agent_id is not allocated.
        """
        if not math.isfinite(amount):
            raise ValueError(f"amount must be finite, got {amount}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

        with self._lock:
            if agent_id not in self._allocated:
                raise ValueError(f"Agent '{agent_id}' has no budget allocation")

            self._consumed[agent_id] = self._consumed.get(agent_id, 0.0) + amount
            events: list[BudgetEvent] = []

            allocated = self._allocated[agent_id]
            consumed = self._consumed[agent_id]

            if allocated <= 0:
                return events

            utilization = consumed / allocated

            # Check warning threshold
            if utilization >= self._warning_threshold and agent_id not in self._warned:
                self._warned.add(agent_id)
                event = BudgetEvent(
                    event_type="warning",
                    agent_id=agent_id,
                    details={
                        "utilization": utilization,
                        "allocated": allocated,
                        "consumed": consumed,
                        "threshold": self._warning_threshold,
                    },
                )
                events.append(event)
                self._events.append(event)

                logger.warning(
                    "Budget warning: agent=%s utilization=%.1f%% (threshold=%.1f%%)",
                    agent_id,
                    utilization * 100,
                    self._warning_threshold * 100,
                )

            # Check exhaustion (HELD, not BLOCKED)
            if utilization >= self._hold_threshold and agent_id not in self._held:
                self._held.add(agent_id)
                event = BudgetEvent(
                    event_type="exhaustion_held",
                    agent_id=agent_id,
                    details={
                        "utilization": utilization,
                        "allocated": allocated,
                        "consumed": consumed,
                        "reason": "budget_exhaustion",
                    },
                )
                events.append(event)
                self._events.append(event)

                logger.warning(
                    "Budget exhaustion HELD: agent=%s utilization=%.1f%%",
                    agent_id,
                    utilization * 100,
                )

            return events

    def reclaim(self, agent_id: str) -> BudgetEvent | None:
        """Reclaim unused budget from a completed agent back to its parent.

        Args:
            agent_id: The completed agent.

        Returns:
            A BudgetEvent describing the reclamation, or None if nothing to reclaim.
        """
        with self._lock:
            allocated = self._allocated.get(agent_id, 0.0)
            consumed = self._consumed.get(agent_id, 0.0)
            reclaimed = max(0.0, allocated - consumed)

            if reclaimed <= 0:
                return None

            parent_id = self._parent.get(agent_id)
            if parent_id is not None and parent_id in self._allocated:
                self._allocated[parent_id] += reclaimed

                # If parent was HELD, check if reclamation resolves it
                if parent_id in self._held and self._allocated[parent_id] > 0:
                    parent_util = self._consumed.get(parent_id, 0.0) / self._allocated[parent_id]
                    if parent_util < self._hold_threshold:
                        self._held.discard(parent_id)

            # Clean up the completed agent
            self._allocated.pop(agent_id, None)
            self._consumed.pop(agent_id, None)
            self._warned.discard(agent_id)
            self._held.discard(agent_id)

            event = BudgetEvent(
                event_type="reclaimed",
                agent_id=agent_id,
                details={
                    "allocated": allocated,
                    "consumed": consumed,
                    "reclaimed": reclaimed,
                    "returned_to": parent_id,
                },
            )
            self._events.append(event)

            logger.info(
                "Budget reclaimed: agent=%s reclaimed=%.2f returned_to=%s",
                agent_id,
                reclaimed,
                parent_id,
            )

            return event

    def reallocate(
        self,
        from_agent_id: str,
        to_agent_id: str,
        amount: float,
    ) -> BudgetEvent | None:
        """Reallocate budget from one agent to another.

        Used when a sibling has unused budget that can resolve another
        sibling's exhaustion.

        Args:
            from_agent_id: The agent donating budget.
            to_agent_id: The agent receiving budget.
            amount: The amount to reallocate.

        Returns:
            A BudgetEvent, or None if reallocation is not possible.

        Raises:
            ValueError: If amount is NaN, Inf, or negative.
        """
        if not math.isfinite(amount):
            raise ValueError(f"amount must be finite, got {amount}")
        if amount <= 0:
            raise ValueError(f"amount must be positive, got {amount}")

        with self._lock:
            from_remaining = self._allocated.get(from_agent_id, 0.0) - self._consumed.get(
                from_agent_id, 0.0
            )
            if from_remaining < amount:
                return None

            self._allocated[from_agent_id] -= amount
            self._allocated[to_agent_id] = self._allocated.get(to_agent_id, 0.0) + amount

            # If recipient was HELD, check if reallocation resolves it
            if to_agent_id in self._held:
                to_util = self._consumed.get(to_agent_id, 0.0) / self._allocated[to_agent_id]
                if to_util < self._hold_threshold:
                    self._held.discard(to_agent_id)
                    self._warned.discard(to_agent_id)

            event = BudgetEvent(
                event_type="reallocated",
                agent_id=to_agent_id,
                details={
                    "from_agent": from_agent_id,
                    "amount": amount,
                },
            )
            self._events.append(event)

            logger.info(
                "Budget reallocated: %.2f from %s to %s",
                amount,
                from_agent_id,
                to_agent_id,
            )

            return event

    def get_snapshot(self, agent_id: str) -> BudgetSnapshot | None:
        """Get a point-in-time budget snapshot for an agent.

        Args:
            agent_id: The agent to snapshot.

        Returns:
            A BudgetSnapshot, or None if agent not tracked.
        """
        with self._lock:
            if agent_id not in self._allocated:
                return None
            return BudgetSnapshot(
                agent_id=agent_id,
                allocated=self._allocated[agent_id],
                consumed=self._consumed.get(agent_id, 0.0),
            )

    def is_held(self, agent_id: str) -> bool:
        """Check if an agent is HELD due to budget exhaustion.

        Args:
            agent_id: The agent to check.

        Returns:
            True if the agent is currently HELD.
        """
        with self._lock:
            return agent_id in self._held

    def get_events(self) -> list[BudgetEvent]:
        """Return the event history.

        Returns:
            List of all BudgetEvents.
        """
        with self._lock:
            return list(self._events)
