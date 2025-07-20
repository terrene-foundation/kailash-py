"""Global ordering service for distributed events using hybrid logical clocks."""

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class HybridLogicalClock:
    """Hybrid Logical Clock (HLC) implementation for global ordering.

    Combines physical time with logical counters to provide:
    - Causally consistent timestamps
    - Tolerance for clock skew
    - Total ordering of events
    """

    def __init__(self, node_id: str):
        """Initialize HLC.

        Args:
            node_id: Unique identifier for this node
        """
        self.node_id = node_id
        self.logical_time = 0
        self.logical_counter = 0
        self._lock = asyncio.Lock()

    async def now(self) -> Tuple[int, int, str]:
        """Get current HLC timestamp.

        Returns:
            Tuple of (logical_time, logical_counter, node_id)
        """
        async with self._lock:
            physical_time = int(datetime.now().timestamp() * 1000)  # Milliseconds

            if physical_time > self.logical_time:
                self.logical_time = physical_time
                self.logical_counter = 0
            else:
                self.logical_counter += 1

            return (self.logical_time, self.logical_counter, self.node_id)

    async def update(self, remote_time: int, remote_counter: int):
        """Update clock with remote timestamp.

        Args:
            remote_time: Remote logical time
            remote_counter: Remote logical counter
        """
        async with self._lock:
            physical_time = int(datetime.now().timestamp() * 1000)

            if physical_time > max(self.logical_time, remote_time):
                self.logical_time = physical_time
                self.logical_counter = 0
            elif self.logical_time == remote_time:
                self.logical_counter = max(self.logical_counter, remote_counter) + 1
            elif self.logical_time < remote_time:
                self.logical_time = remote_time
                self.logical_counter = remote_counter + 1
            else:
                self.logical_counter += 1

    def compare(self, ts1: Tuple[int, int, str], ts2: Tuple[int, int, str]) -> int:
        """Compare two HLC timestamps.

        Args:
            ts1: First timestamp
            ts2: Second timestamp

        Returns:
            -1 if ts1 < ts2, 0 if equal, 1 if ts1 > ts2
        """
        if ts1[0] != ts2[0]:
            return -1 if ts1[0] < ts2[0] else 1
        if ts1[1] != ts2[1]:
            return -1 if ts1[1] < ts2[1] else 1
        if ts1[2] != ts2[2]:
            return -1 if ts1[2] < ts2[2] else 1
        return 0


class GlobalOrderingService:
    """Global ordering service for distributed events.

    Provides:
    - Total ordering of events across edge nodes
    - Causal dependency tracking
    - Conflict detection and resolution
    - Event deduplication
    """

    def __init__(self, node_id: str):
        """Initialize global ordering service.

        Args:
            node_id: Unique identifier for this node
        """
        self.node_id = node_id
        self.clock = HybridLogicalClock(node_id)
        self.event_history: List[Dict[str, Any]] = []
        self.causal_graph: Dict[str, List[str]] = defaultdict(list)
        self.seen_events: set = set()
        self._lock = asyncio.Lock()

    async def order_events(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Order a list of events globally.

        Args:
            events: List of events to order

        Returns:
            Dict with ordered events and metadata
        """
        async with self._lock:
            ordered_events = []

            for event in events:
                # Generate event ID if not present
                if "id" not in event:
                    event["id"] = self._generate_event_id(event)

                # Skip duplicates
                if event["id"] in self.seen_events:
                    continue

                # Assign HLC timestamp
                timestamp = await self.clock.now()
                event["hlc_timestamp"] = timestamp
                event["hlc_time"] = timestamp[0]
                event["hlc_counter"] = timestamp[1]
                event["hlc_node"] = timestamp[2]

                # Track causal dependencies
                if "depends_on" in event:
                    for dep in event["depends_on"]:
                        self.causal_graph[event["id"]].append(dep)

                ordered_events.append(event)
                self.seen_events.add(event["id"])

            # Sort by HLC timestamp
            ordered_events.sort(
                key=lambda e: (e["hlc_time"], e["hlc_counter"], e["hlc_node"])
            )

            # Add to history
            self.event_history.extend(ordered_events)

            return {
                "ordered_events": ordered_events,
                "logical_clock": self.clock.logical_time,
                "causal_dependencies": dict(self.causal_graph),
                "total_events": len(self.event_history),
            }

    async def merge_histories(
        self, remote_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Merge remote event history with local history.

        Args:
            remote_history: Event history from remote node

        Returns:
            Dict with merged history and conflict information
        """
        async with self._lock:
            conflicts = []
            merged_events = []

            # Update clock with remote timestamps
            for event in remote_history:
                if "hlc_time" in event and "hlc_counter" in event:
                    await self.clock.update(event["hlc_time"], event["hlc_counter"])

            # Merge histories
            local_by_id = {e["id"]: e for e in self.event_history if "id" in e}

            for remote_event in remote_history:
                event_id = remote_event.get("id")
                if not event_id:
                    continue

                if event_id in local_by_id:
                    # Check for conflicts
                    local_event = local_by_id[event_id]
                    if self._events_conflict(local_event, remote_event):
                        conflicts.append(
                            {
                                "event_id": event_id,
                                "local": local_event,
                                "remote": remote_event,
                            }
                        )
                    # Keep event with higher timestamp
                    if self._compare_event_timestamps(remote_event, local_event) > 0:
                        local_by_id[event_id] = remote_event
                else:
                    # New event
                    local_by_id[event_id] = remote_event
                    self.seen_events.add(event_id)

            # Rebuild ordered history
            self.event_history = list(local_by_id.values())
            self.event_history.sort(
                key=lambda e: (
                    e.get("hlc_time", 0),
                    e.get("hlc_counter", 0),
                    e.get("hlc_node", ""),
                )
            )

            return {
                "merged_events": len(self.event_history),
                "conflicts": conflicts,
                "conflict_count": len(conflicts),
                "logical_clock": self.clock.logical_time,
            }

    def get_causal_order(self, event_id: str) -> List[str]:
        """Get causal ordering for an event.

        Args:
            event_id: Event ID to get dependencies for

        Returns:
            List of event IDs that must precede this event
        """
        visited = set()
        order = []

        def dfs(eid: str):
            if eid in visited:
                return
            visited.add(eid)

            for dep in self.causal_graph.get(eid, []):
                dfs(dep)

            order.append(eid)

        dfs(event_id)
        return order[:-1]  # Exclude the event itself

    def detect_causal_violations(self) -> List[Dict[str, Any]]:
        """Detect violations of causal ordering.

        Returns:
            List of violations found
        """
        violations = []
        event_positions = {
            e["id"]: i for i, e in enumerate(self.event_history) if "id" in e
        }

        for event_id, deps in self.causal_graph.items():
            event_pos = event_positions.get(event_id)
            if event_pos is None:
                continue

            for dep in deps:
                dep_pos = event_positions.get(dep)
                if dep_pos is None:
                    violations.append(
                        {
                            "type": "missing_dependency",
                            "event": event_id,
                            "missing": dep,
                        }
                    )
                elif dep_pos > event_pos:
                    violations.append(
                        {
                            "type": "causal_violation",
                            "event": event_id,
                            "dependency": dep,
                            "event_position": event_pos,
                            "dependency_position": dep_pos,
                        }
                    )

        return violations

    def _generate_event_id(self, event: Dict[str, Any]) -> str:
        """Generate unique event ID.

        Args:
            event: Event data

        Returns:
            Unique event ID
        """
        # Create deterministic ID from event content
        content = json.dumps(event, sort_keys=True)
        hash_obj = hashlib.sha256(content.encode())
        return f"event_{hash_obj.hexdigest()[:16]}_{self.node_id}"

    def _events_conflict(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> bool:
        """Check if two events conflict.

        Args:
            event1: First event
            event2: Second event

        Returns:
            True if events conflict
        """
        # Events conflict if they have same ID but different content
        if event1.get("id") != event2.get("id"):
            return False

        # Compare non-timestamp fields
        e1_copy = {
            k: v
            for k, v in event1.items()
            if not k.startswith("hlc_") and k != "timestamp"
        }
        e2_copy = {
            k: v
            for k, v in event2.items()
            if not k.startswith("hlc_") and k != "timestamp"
        }

        return e1_copy != e2_copy

    def _compare_event_timestamps(
        self, event1: Dict[str, Any], event2: Dict[str, Any]
    ) -> int:
        """Compare event timestamps.

        Args:
            event1: First event
            event2: Second event

        Returns:
            -1 if event1 < event2, 0 if equal, 1 if event1 > event2
        """
        ts1 = (
            event1.get("hlc_time", 0),
            event1.get("hlc_counter", 0),
            event1.get("hlc_node", ""),
        )
        ts2 = (
            event2.get("hlc_time", 0),
            event2.get("hlc_counter", 0),
            event2.get("hlc_node", ""),
        )

        return self.clock.compare(ts1, ts2)
