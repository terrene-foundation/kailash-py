# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1440 -- MCP Layer-5 rate-limit silent-pair GC.

The MCP governance enforcer's per-(agent_id, tool_name) rate-limit map MUST
evict pairs whose sliding window has fully expired ("silent" pairs), so the map
tracks CURRENTLY-ACTIVE pairs rather than every pair ever seen. Without it, a
caller rotating ``agent_id`` per request accumulates rate-state entries -- a
memory-exhaustion DoS surface against any rate-limited MCP tool (the very layer
meant to bound abuse).

Acceptance criteria (issue #1440):
  1. The map evicts entries whose sliding window has fully expired.
  2. Driving N distinct silent pairs keeps the map bounded (not ~linear in N).
  3. Eviction never weakens enforcement for active pairs (a pair still inside
     its window is never evicted).

Cross-SDK parity: kailash-rs#1491 (kailash-rs v4.16.1) fixed the same enforcer
with the same window-expiry GC. EATP D6 -- independent implementation, matching
semantics.

These are white-box tests: a memory-bound invariant is asserted against the
enforcer's internal ``_rate_tracker`` map size, exactly as criterion 2 requires.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta

import pytest

from pact.mcp.enforcer import McpGovernanceEnforcer
from pact.mcp.types import McpActionContext, McpGovernanceConfig, McpToolPolicy

# Fixed base instant so every test is fully deterministic (no wall-clock).
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _enforcer(rate_limit: int = 5) -> McpGovernanceEnforcer:
    return McpGovernanceEnforcer(
        McpGovernanceConfig(
            tool_policies={
                "search": McpToolPolicy(tool_name="search", rate_limit=rate_limit)
            },
            audit_enabled=False,
        )
    )


def _call(enf: McpGovernanceEnforcer, agent_id: str, at: datetime):
    return enf.check_tool_call(
        McpActionContext(tool_name="search", agent_id=agent_id, timestamp=at)
    )


@pytest.mark.regression
def test_issue_1440_silent_pair_evicted_after_window_expiry() -> None:
    """Criterion 1: a pair whose window fully expired is GC'd, not retained."""
    enf = _enforcer()
    _call(enf, "agent-silent", _T0)
    assert "agent-silent:search" in enf._rate_tracker

    # Advance past one window + one GC interval, then drive an unrelated pair to
    # trigger the amortized sweep.
    later = _T0 + timedelta(
        seconds=enf._RATE_LIMIT_WINDOW_SECONDS + enf._RATE_GC_INTERVAL_SECONDS + 1
    )
    _call(enf, "agent-other", later)

    assert "agent-silent:search" not in enf._rate_tracker, (
        "a silent pair past its window must be evicted, not retained until the "
        "size cap forces it out"
    )


@pytest.mark.regression
def test_issue_1440_map_bounded_under_many_silent_pairs() -> None:
    """Criterion 2: map size stays bounded; it does NOT grow ~linearly with N.

    Models the rotating-agent DoS: N distinct pairs that each call once and then
    go silent. With window-expiry GC the map tracks only the active-window worth
    of pairs, far below N.
    """
    enf = _enforcer()
    n = 2_000
    for i in range(n):
        _call(enf, f"agent-{i}", _T0 + timedelta(seconds=i))

    size = len(enf._rate_tracker)
    # The active-window worth is ~window + GC-interval pairs (~120 at 1 call/s);
    # generous headroom, but nowhere near linear in N.
    assert size < n // 4, f"map grew to {size} for {n} silent pairs -- not bounded"
    assert size <= 250, f"map size {size} exceeds the active-window bound"


@pytest.mark.regression
def test_issue_1440_window_gc_preserves_active_pairs() -> None:
    """Criterion 3 (direct): window-expiry GC evicts ONLY expired pairs.

    Seeds one active pair (last call within the window) and one silent pair
    (last call past the window), then runs the sweep and asserts the active
    pair survives untouched while only the silent pair is reclaimed.
    """
    enf = _enforcer()
    now = _T0 + timedelta(seconds=1_000)
    cutoff = now.timestamp() - enf._RATE_LIMIT_WINDOW_SECONDS

    active_last = now - timedelta(seconds=10)  # inside the 60s window
    silent_last = now - timedelta(seconds=120)  # well past the window
    enf._rate_tracker["active:search"] = deque([active_last])
    enf._rate_tracker["silent:search"] = deque([silent_last])
    enf._last_rate_gc_ts = None  # force the amortized sweep to run

    enf._gc_expired_rate_entries(cutoff, now)

    assert "active:search" in enf._rate_tracker, "active pair must survive GC"
    assert "silent:search" not in enf._rate_tracker, "expired pair must be GC'd"
    # State preserved -- GC did not delete-and-recreate the active pair.
    assert list(enf._rate_tracker["active:search"]) == [active_last]


@pytest.mark.regression
def test_issue_1440_active_pair_survives_gc_churn_end_to_end() -> None:
    """Criterion 3 (end-to-end): a continuously-active pair survives repeated GC
    sweeps triggered by churning silent pairs AND keeps enforcing its limit."""
    enf = _enforcer(rate_limit=5)
    t = _T0
    for rnd in range(6):
        decision = _call(enf, "vip", t)  # active pair, ~once per 30s (under limit)
        assert decision.allowed
        assert "vip:search" in enf._rate_tracker, "active pair must never be GC'd"
        for j in range(15):  # churn distinct silent pairs to advance time + GC
            _call(enf, f"noise-{rnd}-{j}", t)
            t += timedelta(seconds=2)

    # The active pair is still present and still enforces: burst past its limit
    # within a single window and confirm enforcement bites (GC did not reset it).
    burst_blocked = any(
        not _call(enf, "vip", t + timedelta(seconds=k)).allowed for k in range(7)
    )
    assert burst_blocked, (
        "GC must not weaken enforcement -- the active pair must still be "
        "rate-limited after surviving the GC churn"
    )


@pytest.mark.regression
def test_issue_1440_size_cap_bounds_simultaneous_burst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backstop: a same-instant burst of >cap distinct pairs (GC cannot reclaim
    active pairs within one instant) is bounded by the hard size cap."""
    # Shrink the cap to keep the test fast; the eviction logic under test is
    # identical at the shipped 10_000 cap.
    cap = 50
    monkeypatch.setattr(McpGovernanceEnforcer, "_MAX_RATE_TRACKER_ENTRIES", cap)
    enf = _enforcer()

    # All at the SAME timestamp -> no observed-time advance -> GC never fires,
    # so the size cap is the only bound. Drive well past the cap.
    for i in range(cap + 200):
        _call(enf, f"burst-{i}", _T0)

    assert (
        len(enf._rate_tracker) <= cap
    ), f"size cap breached: {len(enf._rate_tracker)} > {cap}"
