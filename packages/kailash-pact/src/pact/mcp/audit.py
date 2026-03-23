# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP audit trail -- bounded, append-only record of MCP governance decisions.

Provides McpAuditEntry and McpAuditTrail for recording and querying MCP tool
invocation governance decisions. Uses collections.deque(maxlen=N) for bounded
memory per pact-governance.md Rule 7 (compilation limits) and trust-plane-security.md
Rule 4 (bounded collections).

Thread-safe: all mutations acquire an internal lock per pact-governance.md Rule 8.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "McpAuditEntry",
    "McpAuditTrail",
]


@dataclass(frozen=True)
class McpAuditEntry:
    """A single audit record for an MCP tool governance decision.

    frozen=True per pact-governance.md: audit records are immutable once created.

    Attributes:
        tool_name: The MCP tool that was invoked.
        agent_id: The agent that made the call.
        decision: The governance decision (auto_approved, flagged, held, blocked).
        reason: Human-readable explanation for the decision.
        timestamp: When the decision was made.
        cost_estimate: Cost estimate at the time of the call, if available.
        metadata: Additional structured context.
    """

    tool_name: str
    agent_id: str
    decision: str
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    cost_estimate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "tool_name": self.tool_name,
            "agent_id": self.agent_id,
            "decision": self.decision,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "cost_estimate": self.cost_estimate,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpAuditEntry:
        """Deserialize from a dictionary."""
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            tool_name=data["tool_name"],
            agent_id=data["agent_id"],
            decision=data["decision"],
            reason=data.get("reason", ""),
            timestamp=ts or datetime.now(UTC),
            cost_estimate=data.get("cost_estimate"),
            metadata=data.get("metadata", {}),
        )


class McpAuditTrail:
    """Bounded, append-only audit trail for MCP governance decisions.

    Uses collections.deque(maxlen=N) to enforce bounded memory. When the
    deque is full, the oldest entries are automatically evicted (FIFO).

    Thread-safe: all methods that access the deque acquire self._lock.

    Args:
        max_entries: Maximum number of audit entries to retain.
            Defaults to 10,000 per trust-plane-security.md Rule 4.
    """

    _DEFAULT_MAX_ENTRIES = 10_000

    def __init__(self, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be >= 1, got {max_entries}")
        self._entries: deque[McpAuditEntry] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._max_entries = max_entries

    @property
    def max_entries(self) -> int:
        """Maximum number of entries this trail retains."""
        return self._max_entries

    def record(
        self,
        *,
        tool_name: str,
        agent_id: str,
        decision: str,
        reason: str = "",
        cost_estimate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> McpAuditEntry:
        """Record a governance decision in the audit trail.

        Thread-safe: acquires self._lock.

        Args:
            tool_name: The MCP tool that was invoked.
            agent_id: The agent making the call.
            decision: The governance decision level.
            reason: Human-readable reason for the decision.
            cost_estimate: Optional cost estimate.
            metadata: Optional additional context.

        Returns:
            The newly created McpAuditEntry.
        """
        entry = McpAuditEntry(
            tool_name=tool_name,
            agent_id=agent_id,
            decision=decision,
            reason=reason,
            cost_estimate=cost_estimate,
            metadata=metadata or {},
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def to_list(self) -> list[McpAuditEntry]:
        """Return a snapshot of all entries as a list.

        Thread-safe: acquires self._lock.

        Returns:
            A list copy of all current audit entries (oldest first).
        """
        with self._lock:
            return list(self._entries)

    def get_by_agent(self, agent_id: str) -> list[McpAuditEntry]:
        """Return all entries for a specific agent.

        Thread-safe: acquires self._lock.

        Args:
            agent_id: The agent identifier to filter by.

        Returns:
            A list of entries for the given agent (oldest first).
        """
        with self._lock:
            return [e for e in self._entries if e.agent_id == agent_id]

    def get_by_tool(self, tool_name: str) -> list[McpAuditEntry]:
        """Return all entries for a specific tool.

        Thread-safe: acquires self._lock.

        Args:
            tool_name: The tool name to filter by.

        Returns:
            A list of entries for the given tool (oldest first).
        """
        with self._lock:
            return [e for e in self._entries if e.tool_name == tool_name]

    def get_by_decision(self, decision: str) -> list[McpAuditEntry]:
        """Return all entries with a specific decision level.

        Thread-safe: acquires self._lock.

        Args:
            decision: The decision level to filter by (e.g. "blocked").

        Returns:
            A list of entries with the given decision (oldest first).
        """
        with self._lock:
            return [e for e in self._entries if e.decision == decision]

    def __len__(self) -> int:
        """Return the current number of entries."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Remove all entries from the audit trail.

        Thread-safe: acquires self._lock.
        """
        with self._lock:
            self._entries.clear()
