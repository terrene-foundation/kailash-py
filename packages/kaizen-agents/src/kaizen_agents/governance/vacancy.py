# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Vacancy Handling -- orphan detection and acting parent designation.

Per PACT Section 5.5: when a parent terminates, children need an acting
parent (the grandparent). If no acting parent is designated within the
deadline (default 60s for L3), orphaned children are suspended (HELD)
and escalated to the nearest living ancestor.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "VacancyManager",
    "VacancyEvent",
    "OrphanRecord",
]


@dataclass(frozen=True)
class OrphanRecord:
    """Tracks an orphaned agent awaiting acting parent designation.

    Attributes:
        agent_id: The orphaned agent's instance ID.
        terminated_parent_id: The parent that was terminated.
        detected_at: Monotonic timestamp when orphan was detected.
        deadline_seconds: Time allowed for acting parent designation.
        acting_parent_id: The designated acting parent, if any.
        suspended: Whether the agent has been suspended (HELD).
    """

    agent_id: str
    terminated_parent_id: str
    detected_at: float
    deadline_seconds: float = 60.0
    acting_parent_id: str | None = None
    suspended: bool = False


@dataclass(frozen=True)
class VacancyEvent:
    """Events emitted during vacancy handling.

    Attributes:
        event_type: One of: orphan_detected, acting_parent_designated,
            orphan_suspended, orphan_escalated.
        agent_id: The affected agent.
        details: Structured event details.
    """

    event_type: str
    agent_id: str
    details: dict[str, Any] = field(default_factory=dict)


class VacancyManager:
    """Manages vacancy handling: orphan detection, acting parent, suspension.

    Thread-safe. Tracks the parent-child hierarchy and detects orphans
    when parents terminate. Provides a deadline-based mechanism for
    designating acting parents, with suspension as the fallback.

    Usage:
        mgr = VacancyManager(deadline_seconds=60.0)
        mgr.register("root", None)
        mgr.register("child", "root")
        events = mgr.handle_parent_termination("root")
        # -> orphan_detected events for "child"
        mgr.designate_acting_parent("child", "grandparent")
        # -> acting_parent_designated event
    """

    def __init__(self, deadline_seconds: float = 60.0, max_agents: int = 100_000) -> None:
        if not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
            raise ValueError(
                f"deadline_seconds must be finite and positive, got {deadline_seconds}"
            )
        self._lock = threading.Lock()
        self._max_agents = max_agents
        self._deadline = deadline_seconds
        self._parent: dict[str, str | None] = {}  # agent_id -> parent_id
        self._children: dict[str, list[str]] = {}  # parent_id -> [child_ids]
        self._orphans: dict[str, OrphanRecord] = {}  # agent_id -> OrphanRecord
        self._terminated: set[str] = set()

    def register(self, agent_id: str, parent_id: str | None) -> None:
        """Register an agent in the hierarchy.

        Args:
            agent_id: The agent's instance ID.
            parent_id: Parent's instance ID, or None for root.
        """
        with self._lock:
            if len(self._parent) >= self._max_agents:
                raise ValueError(
                    f"Agent registration limit ({self._max_agents}) reached. "
                    f"Cannot register '{agent_id}'."
                )
            self._parent[agent_id] = parent_id
            self._children.setdefault(agent_id, [])
            if parent_id is not None:
                self._children.setdefault(parent_id, []).append(agent_id)

    def handle_parent_termination(self, parent_id: str) -> list[VacancyEvent]:
        """Handle a parent's termination by detecting orphaned children.

        Children become orphans. If the parent had a parent (grandparent),
        attempt to designate it as acting parent. Otherwise children are
        immediately orphaned and the deadline clock starts.

        Args:
            parent_id: The terminated parent's instance ID.

        Returns:
            List of VacancyEvents describing what happened.
        """
        with self._lock:
            events: list[VacancyEvent] = []
            # R1-03: Bound _terminated set to prevent unbounded memory growth
            if len(self._terminated) >= self._max_agents:
                self._terminated.clear()
            self._terminated.add(parent_id)

            children = self._children.get(parent_id, [])
            grandparent_id = self._parent.get(parent_id)

            for child_id in children:
                if child_id in self._terminated:
                    continue

                now = time.monotonic()
                orphan = OrphanRecord(
                    agent_id=child_id,
                    terminated_parent_id=parent_id,
                    detected_at=now,
                    deadline_seconds=self._deadline,
                )
                self._orphans[child_id] = orphan

                events.append(
                    VacancyEvent(
                        event_type="orphan_detected",
                        agent_id=child_id,
                        details={
                            "terminated_parent": parent_id,
                            "deadline_seconds": self._deadline,
                        },
                    )
                )

                # Auto-designate grandparent if alive
                if grandparent_id is not None and grandparent_id not in self._terminated:
                    self._orphans[child_id] = OrphanRecord(
                        agent_id=child_id,
                        terminated_parent_id=parent_id,
                        detected_at=now,
                        deadline_seconds=self._deadline,
                        acting_parent_id=grandparent_id,
                    )
                    self._parent[child_id] = grandparent_id
                    self._children.setdefault(grandparent_id, []).append(child_id)

                    events.append(
                        VacancyEvent(
                            event_type="acting_parent_designated",
                            agent_id=child_id,
                            details={
                                "acting_parent": grandparent_id,
                                "auto_designated": True,
                            },
                        )
                    )

            return events

    def designate_acting_parent(self, agent_id: str, acting_parent_id: str) -> VacancyEvent | None:
        """Manually designate an acting parent for an orphaned agent.

        Args:
            agent_id: The orphaned agent.
            acting_parent_id: The new acting parent.

        Returns:
            A VacancyEvent if successful, None if agent is not an orphan.
        """
        with self._lock:
            orphan = self._orphans.get(agent_id)
            if orphan is None:
                return None

            if acting_parent_id in self._terminated:
                logger.warning(
                    "Cannot designate terminated agent %s as acting parent for %s",
                    acting_parent_id,
                    agent_id,
                )
                return None

            self._orphans[agent_id] = OrphanRecord(
                agent_id=agent_id,
                terminated_parent_id=orphan.terminated_parent_id,
                detected_at=orphan.detected_at,
                deadline_seconds=orphan.deadline_seconds,
                acting_parent_id=acting_parent_id,
            )
            self._parent[agent_id] = acting_parent_id
            self._children.setdefault(acting_parent_id, []).append(agent_id)

            return VacancyEvent(
                event_type="acting_parent_designated",
                agent_id=agent_id,
                details={
                    "acting_parent": acting_parent_id,
                    "auto_designated": False,
                },
            )

    def check_deadlines(self) -> list[VacancyEvent]:
        """Check all orphans for deadline expiration. Suspend expired orphans.

        Call this periodically (e.g., every few seconds) to enforce deadlines.

        Returns:
            List of VacancyEvents for newly suspended agents.
        """
        with self._lock:
            events: list[VacancyEvent] = []
            now = time.monotonic()

            for agent_id, orphan in list(self._orphans.items()):
                if orphan.acting_parent_id is not None:
                    continue  # Has acting parent, not expired
                if orphan.suspended:
                    continue  # Already suspended

                elapsed = now - orphan.detected_at
                if elapsed >= orphan.deadline_seconds:
                    self._orphans[agent_id] = OrphanRecord(
                        agent_id=orphan.agent_id,
                        terminated_parent_id=orphan.terminated_parent_id,
                        detected_at=orphan.detected_at,
                        deadline_seconds=orphan.deadline_seconds,
                        suspended=True,
                    )

                    events.append(
                        VacancyEvent(
                            event_type="orphan_suspended",
                            agent_id=agent_id,
                            details={
                                "reason": "deadline_expired",
                                "elapsed_seconds": elapsed,
                            },
                        )
                    )

                    # Escalate to nearest living ancestor
                    ancestor = self._find_nearest_ancestor(agent_id)
                    if ancestor is not None:
                        events.append(
                            VacancyEvent(
                                event_type="orphan_escalated",
                                agent_id=agent_id,
                                details={"escalated_to": ancestor},
                            )
                        )

            return events

    def get_orphans(self) -> list[OrphanRecord]:
        """Return all current orphan records.

        Returns:
            List of OrphanRecords for all tracked orphans.
        """
        with self._lock:
            return list(self._orphans.values())

    def is_orphaned(self, agent_id: str) -> bool:
        """Check if an agent is currently orphaned.

        Args:
            agent_id: The agent to check.

        Returns:
            True if the agent is in the orphan registry without an acting parent.
        """
        with self._lock:
            orphan = self._orphans.get(agent_id)
            return orphan is not None and orphan.acting_parent_id is None

    def _find_nearest_ancestor(self, agent_id: str) -> str | None:
        """Walk up the hierarchy to find the nearest non-terminated ancestor.

        Caller must hold lock.
        R1-08: Uses visited set for cycle detection.
        """
        current = self._parent.get(agent_id)
        visited: set[str] = set()
        while current is not None:
            if current in visited:
                break  # R1-08: Cycle detected, stop traversal
            visited.add(current)
            if current not in self._terminated:
                return current
            current = self._parent.get(current)
        return None
