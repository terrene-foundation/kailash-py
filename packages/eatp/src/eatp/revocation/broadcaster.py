# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Revocation event broadcasting for real-time cascade revocation.

Implements a pub/sub system for broadcasting revocation events across the
trust system. When an agent is revoked, all delegates in the delegation
tree receive immediate notification.

Part of CARE-007: Revocation Event Broadcasting.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Union

logger = logging.getLogger(__name__)


class RevocationType(str, Enum):
    """Type of revocation event.

    Defines the different kinds of revocation that can occur in the
    trust system.

    - AGENT_REVOKED: An agent's trust is completely revoked
    - DELEGATION_REVOKED: A specific delegation is revoked
    - HUMAN_SESSION_REVOKED: A human session that authorized agents is revoked
    - KEY_REVOKED: A cryptographic key is revoked
    - CASCADE_REVOCATION: Automatic revocation due to parent being revoked
    """

    AGENT_REVOKED = "agent_revoked"
    DELEGATION_REVOKED = "delegation_revoked"
    HUMAN_SESSION_REVOKED = "human_session_revoked"
    KEY_REVOKED = "key_revoked"
    CASCADE_REVOCATION = "cascade_revocation"


@dataclass
class RevocationEvent:
    """Record of a revocation event.

    Contains all information about a revocation, including the target,
    who revoked it, why, and any affected agents in the delegation tree.

    Attributes:
        event_id: Unique identifier for this event
        revocation_type: Type of revocation
        target_id: ID of the entity being revoked
        revoked_by: ID of the entity performing the revocation
        reason: Human-readable reason for revocation
        affected_agents: List of agent IDs affected by this revocation
        timestamp: When the revocation occurred
        cascade_from: For CASCADE_REVOCATION, the parent event that caused this
    """

    event_id: str
    revocation_type: RevocationType
    target_id: str
    revoked_by: str
    reason: str
    affected_agents: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cascade_from: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage or transmission.

        Returns:
            Dictionary representation of the event
        """
        return {
            "event_id": self.event_id,
            "revocation_type": self.revocation_type.value,
            "target_id": self.target_id,
            "revoked_by": self.revoked_by,
            "reason": self.reason,
            "affected_agents": self.affected_agents,
            "timestamp": self.timestamp.isoformat(),
            "cascade_from": self.cascade_from,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RevocationEvent":
        """Deserialize from dictionary.

        Args:
            data: Dictionary with RevocationEvent fields

        Returns:
            RevocationEvent instance
        """
        return cls(
            event_id=data["event_id"],
            revocation_type=RevocationType(data["revocation_type"]),
            target_id=data["target_id"],
            revoked_by=data["revoked_by"],
            reason=data["reason"],
            affected_agents=data.get("affected_agents", []),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            cascade_from=data.get("cascade_from"),
        )


# Type alias for callback functions (sync or async)
RevocationCallback = Union[
    Callable[[RevocationEvent], None],
    Callable[[RevocationEvent], "asyncio.Future[None]"],
]


class RevocationBroadcaster(ABC):
    """Abstract base class for revocation event broadcasting.

    Defines the interface for broadcasting revocation events and
    managing subscriptions.
    """

    @abstractmethod
    def broadcast(self, event: RevocationEvent) -> None:
        """Broadcast a revocation event to all subscribers.

        Args:
            event: The revocation event to broadcast
        """
        pass

    @abstractmethod
    def subscribe(
        self,
        callback: RevocationCallback,
        filter_types: Optional[List[RevocationType]] = None,
    ) -> str:
        """Subscribe to revocation events.

        Args:
            callback: Function to call when events occur (sync or async)
            filter_types: Optional list of event types to filter on.
                         If None, receives all events.

        Returns:
            Subscription ID for later unsubscription
        """
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from revocation events.

        Args:
            subscription_id: The subscription ID returned from subscribe()
        """
        pass


@dataclass
class DeadLetterEntry:
    """Record of a failed broadcast attempt.

    Attributes:
        event: The event that failed to be delivered
        subscription_id: The subscription that failed
        error: The error that occurred
        timestamp: When the failure occurred
    """

    event: RevocationEvent
    subscription_id: str
    error: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryRevocationBroadcaster(RevocationBroadcaster):
    """In-memory implementation of revocation broadcasting.

    Stores events in memory and delivers to subscribers synchronously
    or asynchronously depending on the callback type.

    This implementation is suitable for single-process deployments.
    For distributed systems, use a message queue-backed implementation.

    Example:
        >>> broadcaster = InMemoryRevocationBroadcaster()
        >>> def on_revocation(event):
        ...     print(f"Agent {event.target_id} was revoked")
        ...
        >>> sub_id = broadcaster.subscribe(on_revocation)
        >>> event = RevocationEvent(
        ...     event_id="rev-001",
        ...     revocation_type=RevocationType.AGENT_REVOKED,
        ...     target_id="agent-001",
        ...     revoked_by="admin",
        ...     reason="Security violation",
        ... )
        >>> broadcaster.broadcast(event)
        Agent agent-001 was revoked
    """

    def __init__(self):
        """Initialize the broadcaster."""
        self._subscribers: Dict[str, RevocationCallback] = {}
        self._filters: Dict[str, Optional[List[RevocationType]]] = {}
        self._history: List[RevocationEvent] = []
        self._dead_letters: List[DeadLetterEntry] = []
        self._lock = asyncio.Lock()

    def broadcast(self, event: RevocationEvent) -> None:
        """Broadcast a revocation event to all subscribers.

        Stores the event in history and delivers to all matching subscribers.
        Supports both sync and async callbacks. Errors in one subscriber
        do not prevent delivery to other subscribers.

        Args:
            event: The revocation event to broadcast
        """
        # Store in history
        self._history.append(event)

        # Deliver to each subscriber
        for sub_id, callback in list(self._subscribers.items()):
            # Apply filter if present
            filter_types = self._filters.get(sub_id)
            if filter_types is not None and event.revocation_type not in filter_types:
                continue

            # Call the callback
            try:
                result = callback(event)
                # If the callback is async, we need to run it
                if asyncio.iscoroutine(result):
                    # Run async callback in event loop if available
                    try:
                        loop = asyncio.get_running_loop()
                        # Schedule the coroutine to run
                        asyncio.ensure_future(result)
                    except RuntimeError:
                        # No running event loop, run synchronously
                        asyncio.run(result)
            except Exception as e:
                # Log error but continue with other subscribers
                logger.error(
                    f"Error broadcasting revocation event {event.event_id} "
                    f"to subscriber {sub_id}: {e}"
                )
                # Track in dead letter queue
                self._dead_letters.append(
                    DeadLetterEntry(
                        event=event,
                        subscription_id=sub_id,
                        error=str(e),
                    )
                )

        logger.debug(
            f"Broadcast revocation event {event.event_id} "
            f"({event.revocation_type.value}) for {event.target_id}"
        )

    def subscribe(
        self,
        callback: RevocationCallback,
        filter_types: Optional[List[RevocationType]] = None,
    ) -> str:
        """Subscribe to revocation events.

        Args:
            callback: Function to call when events occur (sync or async)
            filter_types: Optional list of event types to filter on.
                         If None, receives all events.

        Returns:
            Subscription ID for later unsubscription
        """
        subscription_id = f"sub-{uuid.uuid4()}"
        self._subscribers[subscription_id] = callback
        self._filters[subscription_id] = filter_types

        logger.debug(f"New subscription {subscription_id} with filter: {filter_types}")

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from revocation events.

        Args:
            subscription_id: The subscription ID returned from subscribe()
        """
        if subscription_id in self._subscribers:
            del self._subscribers[subscription_id]
        if subscription_id in self._filters:
            del self._filters[subscription_id]

        logger.debug(f"Unsubscribed {subscription_id}")

    def get_history(self) -> List[RevocationEvent]:
        """Get the history of all broadcast events.

        Returns:
            List of all RevocationEvents in broadcast order
        """
        return list(self._history)

    def get_dead_letters(self) -> List[DeadLetterEntry]:
        """Get the dead letter queue for failed broadcasts.

        Returns:
            List of DeadLetterEntry for failed deliveries
        """
        return list(self._dead_letters)

    def clear_history(self) -> None:
        """Clear the event history."""
        self._history.clear()

    def clear_dead_letters(self) -> None:
        """Clear the dead letter queue."""
        self._dead_letters.clear()


class DelegationRegistry(Protocol):
    """Protocol for delegation registry access.

    Defines the interface for looking up delegation relationships.
    The cascade revocation manager uses this to find all agents
    that need to be revoked when a parent is revoked.
    """

    def get_delegates(self, agent_id: str) -> List[str]:
        """Get all agents that were delegated to by the given agent.

        Args:
            agent_id: The delegating agent ID

        Returns:
            List of delegate agent IDs
        """
        ...


class InMemoryDelegationRegistry:
    """In-memory implementation of delegation registry.

    Tracks delegation relationships between agents for testing
    and single-process deployments.

    Example:
        >>> registry = InMemoryDelegationRegistry()
        >>> registry.register_delegation("agent-A", "agent-B")
        >>> registry.register_delegation("agent-A", "agent-C")
        >>> registry.get_delegates("agent-A")
        ['agent-B', 'agent-C']
    """

    def __init__(self):
        """Initialize the registry."""
        self._delegations: Dict[str, Set[str]] = {}

    def register_delegation(self, delegator_id: str, delegate_id: str) -> None:
        """Register a delegation from one agent to another.

        Args:
            delegator_id: The agent granting delegation
            delegate_id: The agent receiving delegation
        """
        if delegator_id not in self._delegations:
            self._delegations[delegator_id] = set()
        self._delegations[delegator_id].add(delegate_id)

    def unregister_delegation(self, delegator_id: str, delegate_id: str) -> None:
        """Remove a delegation relationship.

        Args:
            delegator_id: The agent that granted delegation
            delegate_id: The agent that received delegation
        """
        if delegator_id in self._delegations:
            self._delegations[delegator_id].discard(delegate_id)

    def get_delegates(self, agent_id: str) -> List[str]:
        """Get all agents that were delegated to by the given agent.

        Args:
            agent_id: The delegating agent ID

        Returns:
            List of delegate agent IDs
        """
        return list(self._delegations.get(agent_id, set()))

    def clear(self) -> None:
        """Clear all delegation records."""
        self._delegations.clear()


class CascadeRevocationManager:
    """Manages cascade revocation through delegation trees.

    When an agent is revoked, all of its delegates must also be revoked.
    This manager handles the recursive traversal of the delegation tree
    and generates CASCADE_REVOCATION events for each affected agent.

    Features:
    - Circular delegation detection to prevent infinite loops
    - Dead-letter tracking for failed broadcasts
    - Complete event list returned for audit trails

    Example:
        >>> registry = InMemoryDelegationRegistry()
        >>> registry.register_delegation("agent-A", "agent-B")
        >>> registry.register_delegation("agent-B", "agent-C")
        >>>
        >>> broadcaster = InMemoryRevocationBroadcaster()
        >>> manager = CascadeRevocationManager(broadcaster, registry)
        >>>
        >>> events = manager.cascade_revoke(
        ...     target_id="agent-A",
        ...     revoked_by="admin",
        ...     reason="Security violation"
        ... )
        >>> # events will contain revocation for A, B, and C
    """

    def __init__(
        self,
        broadcaster: RevocationBroadcaster,
        delegation_registry: DelegationRegistry,
    ):
        """Initialize the cascade revocation manager.

        Args:
            broadcaster: The broadcaster to use for sending events
            delegation_registry: Registry for looking up delegations
        """
        self._broadcaster = broadcaster
        self._delegation_registry = delegation_registry
        self._dead_letters: List[DeadLetterEntry] = []

    def cascade_revoke(
        self,
        target_id: str,
        revoked_by: str,
        reason: str,
        revocation_type: RevocationType = RevocationType.AGENT_REVOKED,
    ) -> List[RevocationEvent]:
        """Revoke an agent and cascade to all its delegates.

        Creates revocation events for the target and all agents in
        its delegation tree. Uses breadth-first traversal to ensure
        proper ordering of cascade events.

        Args:
            target_id: The agent to revoke
            revoked_by: Who is performing the revocation
            reason: Reason for the revocation
            revocation_type: Type of the initial revocation

        Returns:
            List of all RevocationEvents created (initial + cascades)
        """
        all_events: List[RevocationEvent] = []
        visited: Set[str] = set()

        # Create the initial revocation event
        initial_event = RevocationEvent(
            event_id=f"rev-{uuid.uuid4()}",
            revocation_type=revocation_type,
            target_id=target_id,
            revoked_by=revoked_by,
            reason=reason,
        )

        # Find all affected agents (delegates in the tree)
        affected = self._find_all_delegates(target_id, visited)
        initial_event.affected_agents = affected

        # Broadcast and track the initial event
        self._safe_broadcast(initial_event)
        all_events.append(initial_event)
        visited.add(target_id)

        # Process cascade revocations using BFS
        queue: List[tuple] = [(target_id, initial_event.event_id)]

        while queue:
            parent_id, parent_event_id = queue.pop(0)
            delegates = self._delegation_registry.get_delegates(parent_id)

            for delegate_id in delegates:
                # Skip if already visited (circular delegation detection)
                if delegate_id in visited:
                    logger.warning(
                        f"Circular delegation detected: {parent_id} -> {delegate_id}. "
                        f"Skipping to prevent infinite loop."
                    )
                    continue

                visited.add(delegate_id)

                # Create cascade event for this delegate
                cascade_event = RevocationEvent(
                    event_id=f"rev-{uuid.uuid4()}",
                    revocation_type=RevocationType.CASCADE_REVOCATION,
                    target_id=delegate_id,
                    revoked_by=revoked_by,
                    reason=f"Cascade revocation from {parent_id}: {reason}",
                    cascade_from=parent_event_id,
                )

                # Find this delegate's affected agents
                sub_affected = self._find_all_delegates(delegate_id, visited.copy())
                cascade_event.affected_agents = sub_affected

                # Broadcast and track
                self._safe_broadcast(cascade_event)
                all_events.append(cascade_event)

                # Add to queue for further processing
                queue.append((delegate_id, cascade_event.event_id))

        logger.info(
            f"Cascade revocation complete for {target_id}. "
            f"Total events: {len(all_events)}"
        )

        return all_events

    def _find_all_delegates(self, agent_id: str, visited: Set[str]) -> List[str]:
        """Find all delegates in the tree below an agent.

        Uses depth-first search with cycle detection.

        Args:
            agent_id: The agent to find delegates for
            visited: Set of already-visited agent IDs

        Returns:
            List of all delegate agent IDs
        """
        all_delegates: List[str] = []
        stack = [agent_id]
        local_visited = visited.copy()

        while stack:
            current = stack.pop()
            if current in local_visited and current != agent_id:
                continue
            local_visited.add(current)

            delegates = self._delegation_registry.get_delegates(current)
            for delegate in delegates:
                if delegate not in local_visited:
                    all_delegates.append(delegate)
                    stack.append(delegate)

        return all_delegates

    def _safe_broadcast(self, event: RevocationEvent) -> None:
        """Safely broadcast an event, tracking failures.

        Args:
            event: The event to broadcast
        """
        try:
            self._broadcaster.broadcast(event)
        except Exception as e:
            logger.error(f"Failed to broadcast revocation event {event.event_id}: {e}")
            self._dead_letters.append(
                DeadLetterEntry(
                    event=event,
                    subscription_id="broadcast",
                    error=str(e),
                )
            )

    def get_dead_letters(self) -> List[DeadLetterEntry]:
        """Get failed broadcast attempts.

        Returns:
            List of DeadLetterEntry for failed broadcasts
        """
        return list(self._dead_letters)

    def clear_dead_letters(self) -> None:
        """Clear the dead letter queue."""
        self._dead_letters.clear()


class TrustRevocationList:
    """Tracks revoked agents in real-time.

    Subscribes to revocation events and maintains a set of all
    revoked agent IDs for fast lookup. Useful for access control
    and trust verification.

    Example:
        >>> broadcaster = InMemoryRevocationBroadcaster()
        >>> trl = TrustRevocationList(broadcaster)
        >>> trl.initialize()
        >>>
        >>> # After some revocations...
        >>> if trl.is_revoked("agent-001"):
        ...     print("Agent is revoked!")
        >>>
        >>> trl.close()  # Clean up subscription
    """

    def __init__(self, broadcaster: RevocationBroadcaster):
        """Initialize the trust revocation list.

        Args:
            broadcaster: The broadcaster to subscribe to
        """
        self._broadcaster = broadcaster
        self._revoked: Set[str] = set()
        self._events: Dict[str, RevocationEvent] = {}
        self._subscription_id: Optional[str] = None

    def initialize(self) -> None:
        """Start listening for revocation events.

        Subscribes to all revocation event types.
        """
        self._subscription_id = self._broadcaster.subscribe(
            callback=self._on_revocation_event,
            filter_types=None,  # Receive all types
        )
        logger.info("TrustRevocationList initialized")

    def _on_revocation_event(self, event: RevocationEvent) -> None:
        """Handle a revocation event.

        Adds the target and all affected agents to the revoked set.

        Args:
            event: The revocation event
        """
        # Mark the target as revoked
        self._revoked.add(event.target_id)
        self._events[event.target_id] = event

        # Mark all affected agents as revoked
        for agent_id in event.affected_agents:
            self._revoked.add(agent_id)
            # Store reference to the originating event
            if agent_id not in self._events:
                self._events[agent_id] = event

        logger.debug(
            f"TRL updated: {event.target_id} and {len(event.affected_agents)} "
            f"affected agents marked as revoked"
        )

    def is_revoked(self, agent_id: str) -> bool:
        """Check if an agent is revoked.

        Args:
            agent_id: The agent ID to check

        Returns:
            True if the agent is revoked, False otherwise
        """
        return agent_id in self._revoked

    def get_revocation_event(self, agent_id: str) -> Optional[RevocationEvent]:
        """Get the revocation event for an agent.

        Args:
            agent_id: The agent ID

        Returns:
            The RevocationEvent if the agent is revoked, None otherwise
        """
        return self._events.get(agent_id)

    def get_all_revoked(self) -> Set[str]:
        """Get all revoked agent IDs.

        Returns:
            Set of all revoked agent IDs
        """
        return self._revoked.copy()

    def close(self) -> None:
        """Stop listening for revocation events.

        Unsubscribes from the broadcaster.
        """
        if self._subscription_id:
            self._broadcaster.unsubscribe(self._subscription_id)
            self._subscription_id = None
            logger.info("TrustRevocationList closed")


__all__ = [
    "RevocationType",
    "RevocationEvent",
    "RevocationBroadcaster",
    "InMemoryRevocationBroadcaster",
    "DelegationRegistry",
    "InMemoryDelegationRegistry",
    "CascadeRevocationManager",
    "TrustRevocationList",
    "DeadLetterEntry",
]
