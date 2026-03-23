# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for pact.mcp.audit -- MCP audit trail.

Covers:
- McpAuditEntry: frozen, serialization
- McpAuditTrail: bounded collection (deque maxlen), thread safety,
  query methods (get_by_agent, get_by_tool, get_by_decision)
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest

from pact.mcp.audit import McpAuditEntry, McpAuditTrail


# ---------------------------------------------------------------------------
# McpAuditEntry
# ---------------------------------------------------------------------------


class TestMcpAuditEntry:
    """McpAuditEntry construction and serialization."""

    def test_basic_construction(self) -> None:
        entry = McpAuditEntry(
            tool_name="web_search",
            agent_id="agent-1",
            decision="auto_approved",
            reason="within constraints",
        )
        assert entry.tool_name == "web_search"
        assert entry.agent_id == "agent-1"
        assert entry.decision == "auto_approved"

    def test_frozen(self) -> None:
        entry = McpAuditEntry(
            tool_name="t", agent_id="a", decision="blocked"
        )
        with pytest.raises(AttributeError):
            entry.decision = "auto_approved"  # type: ignore[misc]

    def test_timestamp_auto_set(self) -> None:
        before = datetime.now(UTC)
        entry = McpAuditEntry(
            tool_name="t", agent_id="a", decision="blocked"
        )
        after = datetime.now(UTC)
        assert before <= entry.timestamp <= after

    def test_to_dict_roundtrip(self) -> None:
        now = datetime.now(UTC)
        entry = McpAuditEntry(
            tool_name="run_code",
            agent_id="agent-42",
            decision="flagged",
            reason="near limit",
            timestamp=now,
            cost_estimate=5.0,
            metadata={"env": "prod"},
        )
        data = entry.to_dict()
        restored = McpAuditEntry.from_dict(data)
        assert restored.tool_name == entry.tool_name
        assert restored.agent_id == entry.agent_id
        assert restored.decision == entry.decision
        assert restored.reason == entry.reason
        assert restored.cost_estimate == entry.cost_estimate
        assert restored.metadata == entry.metadata


# ---------------------------------------------------------------------------
# McpAuditTrail
# ---------------------------------------------------------------------------


class TestMcpAuditTrail:
    """McpAuditTrail bounded collection and query methods."""

    def test_basic_record(self) -> None:
        trail = McpAuditTrail()
        entry = trail.record(
            tool_name="t",
            agent_id="a",
            decision="auto_approved",
        )
        assert entry.tool_name == "t"
        assert len(trail) == 1

    def test_to_list(self) -> None:
        trail = McpAuditTrail()
        trail.record(tool_name="t1", agent_id="a", decision="blocked")
        trail.record(tool_name="t2", agent_id="a", decision="auto_approved")
        entries = trail.to_list()
        assert len(entries) == 2
        assert entries[0].tool_name == "t1"
        assert entries[1].tool_name == "t2"

    def test_bounded_collection(self) -> None:
        """Deque evicts oldest entries when maxlen is reached."""
        trail = McpAuditTrail(max_entries=5)
        for i in range(10):
            trail.record(
                tool_name=f"tool-{i}",
                agent_id="a",
                decision="auto_approved",
            )
        assert len(trail) == 5
        entries = trail.to_list()
        # Only the last 5 entries should remain
        assert entries[0].tool_name == "tool-5"
        assert entries[-1].tool_name == "tool-9"

    def test_max_entries_property(self) -> None:
        trail = McpAuditTrail(max_entries=42)
        assert trail.max_entries == 42

    def test_invalid_max_entries(self) -> None:
        with pytest.raises(ValueError, match="max_entries must be >= 1"):
            McpAuditTrail(max_entries=0)

    def test_get_by_agent(self) -> None:
        trail = McpAuditTrail()
        trail.record(tool_name="t", agent_id="agent-1", decision="blocked")
        trail.record(tool_name="t", agent_id="agent-2", decision="auto_approved")
        trail.record(tool_name="t", agent_id="agent-1", decision="flagged")
        entries = trail.get_by_agent("agent-1")
        assert len(entries) == 2
        assert all(e.agent_id == "agent-1" for e in entries)

    def test_get_by_tool(self) -> None:
        trail = McpAuditTrail()
        trail.record(tool_name="search", agent_id="a", decision="blocked")
        trail.record(tool_name="execute", agent_id="a", decision="auto_approved")
        trail.record(tool_name="search", agent_id="b", decision="flagged")
        entries = trail.get_by_tool("search")
        assert len(entries) == 2
        assert all(e.tool_name == "search" for e in entries)

    def test_get_by_decision(self) -> None:
        trail = McpAuditTrail()
        trail.record(tool_name="t1", agent_id="a", decision="blocked")
        trail.record(tool_name="t2", agent_id="a", decision="auto_approved")
        trail.record(tool_name="t3", agent_id="a", decision="blocked")
        entries = trail.get_by_decision("blocked")
        assert len(entries) == 2
        assert all(e.decision == "blocked" for e in entries)

    def test_get_by_agent_empty(self) -> None:
        trail = McpAuditTrail()
        assert trail.get_by_agent("nonexistent") == []

    def test_get_by_tool_empty(self) -> None:
        trail = McpAuditTrail()
        assert trail.get_by_tool("nonexistent") == []

    def test_clear(self) -> None:
        trail = McpAuditTrail()
        trail.record(tool_name="t", agent_id="a", decision="blocked")
        trail.record(tool_name="t", agent_id="a", decision="blocked")
        assert len(trail) == 2
        trail.clear()
        assert len(trail) == 0

    def test_record_with_metadata(self) -> None:
        trail = McpAuditTrail()
        entry = trail.record(
            tool_name="t",
            agent_id="a",
            decision="blocked",
            reason="over budget",
            cost_estimate=50.0,
            metadata={"extra": "data"},
        )
        assert entry.reason == "over budget"
        assert entry.cost_estimate == 50.0
        assert entry.metadata == {"extra": "data"}


# ---------------------------------------------------------------------------
# Thread Safety Tests
# ---------------------------------------------------------------------------


class TestAuditTrailThreadSafety:
    """Concurrent access to McpAuditTrail."""

    def test_concurrent_records(self) -> None:
        trail = McpAuditTrail(max_entries=1000)
        errors: list[str] = []

        def worker(agent_id: str) -> None:
            try:
                for i in range(100):
                    trail.record(
                        tool_name=f"tool-{i}",
                        agent_id=agent_id,
                        decision="auto_approved",
                    )
            except Exception as exc:
                errors.append(str(exc))

        threads = [
            threading.Thread(target=worker, args=(f"agent-{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        # 5 agents x 100 records = 500, all fit within 1000
        assert len(trail) == 500

    def test_concurrent_record_and_query(self) -> None:
        trail = McpAuditTrail(max_entries=500)
        errors: list[str] = []

        def writer() -> None:
            try:
                for i in range(200):
                    trail.record(
                        tool_name="t",
                        agent_id="writer",
                        decision="auto_approved",
                    )
            except Exception as exc:
                errors.append(str(exc))

        def reader() -> None:
            try:
                for _ in range(200):
                    trail.to_list()
                    trail.get_by_agent("writer")
                    trail.get_by_tool("t")
            except Exception as exc:
                errors.append(str(exc))

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
