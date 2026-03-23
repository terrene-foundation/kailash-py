# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Cascade Revocation -- envelope tightening and termination propagation.

When a parent's envelope is tightened at runtime, all descendants' envelopes
must be re-intersected to maintain monotonic tightening. When a parent is
terminated, all descendants cascade-terminate (depth-first, leaves first).
Budget reclaimed from terminated children flows back to the parent pool.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CascadeManager",
    "CascadeEvent",
    "CascadeEventType",
]


class CascadeEventType:
    """Event types emitted during cascade operations."""

    ENVELOPE_TIGHTENED = "envelope_tightened"
    CHILD_RE_INTERSECTED = "child_re_intersected"
    CASCADE_TERMINATE = "cascade_terminate"
    BUDGET_RECLAIMED = "budget_reclaimed"


@dataclass(frozen=True)
class CascadeEvent:
    """An event emitted during a cascade operation.

    Attributes:
        event_type: The type of cascade event.
        agent_id: The agent this event pertains to.
        parent_id: The parent that triggered the cascade.
        details: Structured event details.
    """

    event_type: str
    agent_id: str
    parent_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


# Type alias for the hierarchy
_Hierarchy = dict[str, list[str]]  # parent_id -> [child_ids]


class CascadeManager:
    """Manages cascade operations: envelope tightening and termination.

    Thread-safe. Maintains the parent-child hierarchy and envelope
    assignments. When a parent's envelope changes, descendants are
    re-intersected. When a parent terminates, descendants cascade-terminate.

    Usage:
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": 50.0}})
        events = mgr.tighten_envelope("root", {"financial": {"limit": 30.0}})
        # child's envelope is now re-intersected to be <= 30.0
    """

    def __init__(self, max_agents: int = 100_000) -> None:
        self._lock = threading.Lock()
        self._max_agents = max_agents
        self._children: _Hierarchy = {}  # parent_id -> [child_ids]
        self._parent: dict[str, str | None] = {}  # agent_id -> parent_id
        self._envelopes: dict[str, dict[str, Any]] = {}  # agent_id -> envelope
        self._budget_consumed: dict[str, float] = {}  # agent_id -> consumed amount
        self._budget_allocated: dict[str, float] = {}  # agent_id -> allocated amount

    def register(
        self,
        agent_id: str,
        parent_id: str | None,
        envelope: dict[str, Any],
        budget_allocated: float = 0.0,
    ) -> None:
        """Register an agent in the cascade hierarchy.

        Args:
            agent_id: The agent's instance ID.
            parent_id: The parent's instance ID, or None for root.
            envelope: The agent's current envelope (as dict).
            budget_allocated: The budget allocated to this agent.

        Raises:
            ValueError: If agent_id is already registered.
            ValueError: If budget_allocated is NaN or Inf.
        """
        if not math.isfinite(budget_allocated):
            raise ValueError(f"budget_allocated must be finite, got {budget_allocated}")
        if budget_allocated < 0:
            raise ValueError(f"budget_allocated must be non-negative, got {budget_allocated}")

        with self._lock:
            if agent_id in self._parent:
                raise ValueError(f"Agent '{agent_id}' is already registered")
            if len(self._parent) >= self._max_agents:
                raise ValueError(
                    f"Agent registration limit ({self._max_agents}) reached. "
                    f"Cannot register '{agent_id}'."
                )

            self._parent[agent_id] = parent_id
            self._envelopes[agent_id] = dict(envelope)
            self._budget_consumed[agent_id] = 0.0
            self._budget_allocated[agent_id] = budget_allocated

            if parent_id is not None:
                self._children.setdefault(parent_id, []).append(agent_id)
            self._children.setdefault(agent_id, [])

    def tighten_envelope(
        self,
        agent_id: str,
        new_envelope: dict[str, Any],
    ) -> list[CascadeEvent]:
        """Tighten an agent's envelope and re-intersect all descendants.

        The new envelope must be at most as permissive as the current one.
        All descendants are re-intersected by applying _intersect_dicts
        against the new parent envelope.

        Args:
            agent_id: The agent whose envelope is being tightened.
            new_envelope: The new (tighter) envelope.

        Returns:
            List of CascadeEvents describing what happened.

        Raises:
            ValueError: If agent_id is not registered.
        """
        with self._lock:
            if agent_id not in self._parent:
                raise ValueError(f"Agent '{agent_id}' is not registered")

            events: list[CascadeEvent] = []

            old_envelope = self._envelopes[agent_id]
            # Enforce monotonic tightening: intersect with current envelope
            # so the result can only be equal or more restrictive.
            validated_envelope = _intersect_dicts(old_envelope, new_envelope)
            self._envelopes[agent_id] = validated_envelope

            events.append(
                CascadeEvent(
                    event_type=CascadeEventType.ENVELOPE_TIGHTENED,
                    agent_id=agent_id,
                    details={"old_envelope": old_envelope, "new_envelope": validated_envelope},
                )
            )

            # Re-intersect all descendants (BFS).
            # Each child is intersected against its DIRECT parent's new envelope,
            # not the originating agent's envelope. This ensures correct propagation
            # through multi-level hierarchies.
            queue = list(self._children.get(agent_id, []))
            while queue:
                child_id = queue.pop(0)
                child_env = self._envelopes.get(child_id, {})
                direct_parent_id = self._parent.get(child_id) or agent_id
                direct_parent_env = self._envelopes.get(direct_parent_id, new_envelope)
                new_child_env = _intersect_dicts(direct_parent_env, child_env)
                self._envelopes[child_id] = new_child_env

                events.append(
                    CascadeEvent(
                        event_type=CascadeEventType.CHILD_RE_INTERSECTED,
                        agent_id=child_id,
                        parent_id=direct_parent_id,
                        details={
                            "old_envelope": child_env,
                            "new_envelope": new_child_env,
                        },
                    )
                )

                queue.extend(self._children.get(child_id, []))

            return events

    def cascade_terminate(self, agent_id: str) -> list[CascadeEvent]:
        """Terminate an agent and all descendants (depth-first, leaves first).

        Budget is reclaimed from each terminated child back to the parent pool.

        Args:
            agent_id: The agent to terminate.

        Returns:
            List of CascadeEvents describing terminations and budget reclamation.

        Raises:
            ValueError: If agent_id is not registered.
        """
        with self._lock:
            if agent_id not in self._parent:
                raise ValueError(f"Agent '{agent_id}' is not registered")

            events: list[CascadeEvent] = []

            # Collect all descendants depth-first
            descendants = self._collect_descendants(agent_id)

            # Terminate in reverse order (leaves first)
            for desc_id in reversed(descendants):
                reclaimed = self._reclaim_budget(desc_id)
                events.append(
                    CascadeEvent(
                        event_type=CascadeEventType.CASCADE_TERMINATE,
                        agent_id=desc_id,
                        parent_id=self._parent.get(desc_id),
                        details={"reason": "parent_terminated"},
                    )
                )
                if reclaimed > 0:
                    events.append(
                        CascadeEvent(
                            event_type=CascadeEventType.BUDGET_RECLAIMED,
                            agent_id=desc_id,
                            parent_id=self._parent.get(desc_id),
                            details={"amount": reclaimed},
                        )
                    )

            # Terminate the agent itself
            events.append(
                CascadeEvent(
                    event_type=CascadeEventType.CASCADE_TERMINATE,
                    agent_id=agent_id,
                    details={"reason": "explicit_termination"},
                )
            )

            # Clean up all terminated agents
            for desc_id in descendants:
                self._cleanup_agent(desc_id)
            self._cleanup_agent(agent_id)

            return events

    def record_consumption(self, agent_id: str, amount: float) -> None:
        """Record budget consumption for an agent.

        Args:
            agent_id: The agent consuming budget.
            amount: The amount consumed (must be finite and non-negative).

        Raises:
            ValueError: If amount is NaN, Inf, or negative.
            ValueError: If agent_id is not registered.
        """
        if not math.isfinite(amount):
            raise ValueError(f"amount must be finite, got {amount}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

        with self._lock:
            if agent_id not in self._parent:
                raise ValueError(f"Agent '{agent_id}' is not registered")
            self._budget_consumed[agent_id] = self._budget_consumed.get(agent_id, 0.0) + amount

    def get_envelope(self, agent_id: str) -> dict[str, Any] | None:
        """Get the current envelope for an agent.

        Args:
            agent_id: The agent's instance ID.

        Returns:
            The envelope dict, or None if not registered.
        """
        with self._lock:
            return self._envelopes.get(agent_id)

    def get_children(self, agent_id: str) -> list[str]:
        """Get direct children of an agent.

        Args:
            agent_id: The parent agent's instance ID.

        Returns:
            List of child agent IDs.
        """
        with self._lock:
            return list(self._children.get(agent_id, []))

    def _collect_descendants(self, agent_id: str) -> list[str]:
        """Collect all descendants depth-first. Caller must hold lock."""
        result: list[str] = []
        stack = list(self._children.get(agent_id, []))
        while stack:
            child = stack.pop()
            result.append(child)
            stack.extend(self._children.get(child, []))
        return result

    def _reclaim_budget(self, agent_id: str) -> float:
        """Reclaim unused budget from an agent. Caller must hold lock.

        Returns:
            The amount reclaimed (allocated - consumed).
        """
        allocated = self._budget_allocated.get(agent_id, 0.0)
        consumed = self._budget_consumed.get(agent_id, 0.0)
        reclaimed = max(0.0, allocated - consumed)

        parent_id = self._parent.get(agent_id)
        if parent_id is not None and reclaimed > 0:
            self._budget_allocated[parent_id] = (
                self._budget_allocated.get(parent_id, 0.0) + reclaimed
            )

        return reclaimed

    def _cleanup_agent(self, agent_id: str) -> None:
        """Remove an agent from all tracking structures. Caller must hold lock."""
        parent_id = self._parent.get(agent_id)
        if parent_id is not None and parent_id in self._children:
            children = self._children[parent_id]
            if agent_id in children:
                children.remove(agent_id)

        self._parent.pop(agent_id, None)
        self._envelopes.pop(agent_id, None)
        self._budget_consumed.pop(agent_id, None)
        self._budget_allocated.pop(agent_id, None)
        self._children.pop(agent_id, None)


def _intersect_dicts(
    parent: dict[str, Any],
    child: dict[str, Any],
    _depth: int = 0,
) -> dict[str, Any]:
    """Intersect two envelope dicts -- take the more restrictive value.

    For numeric fields (like financial.limit), takes the minimum.
    For list fields (like operational.allowed), takes the intersection.
    For list fields (like operational.blocked), takes the union.
    Type mismatches default to the parent's value (more restrictive).
    NaN/Inf values in numeric fields raise ValueError (fail-closed).

    R1-07: Recursion is bounded to max_depth=10 to prevent stack overflow
    on deeply nested or maliciously crafted envelope structures.
    """
    if _depth > 10:
        raise ValueError("Envelope nesting exceeds max depth 10")

    result: dict[str, Any] = {}

    for key in set(parent.keys()) | set(child.keys()):
        parent_val = parent.get(key)
        child_val = child.get(key)

        if parent_val is None:
            result[key] = child_val
        elif child_val is None:
            result[key] = parent_val
        elif isinstance(parent_val, dict) and isinstance(child_val, dict):
            result[key] = _intersect_dicts(parent_val, child_val, _depth + 1)
        elif isinstance(parent_val, (int, float)) and isinstance(child_val, (int, float)):
            # NaN/Inf guard: fail-closed on non-finite values
            if not math.isfinite(float(parent_val)) or not math.isfinite(float(child_val)):
                raise ValueError(
                    f"Non-finite value in envelope intersection for key '{key}': "
                    f"parent={parent_val}, child={child_val}"
                )
            result[key] = min(parent_val, child_val)
        elif isinstance(parent_val, list) and isinstance(child_val, list):
            if key in ("blocked", "blocked_actions", "blackout_periods", "blocked_data_types"):
                result[key] = sorted(set(parent_val) | set(child_val))
            else:
                result[key] = sorted(set(parent_val) & set(child_val))
        else:
            # Type mismatch: take parent value (more restrictive)
            result[key] = parent_val

    return result
