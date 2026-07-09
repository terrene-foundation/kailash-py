# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the stateful sliding-window RateLimitEnforcer (#1516a).

These pin the enforcer primitive directly with INJECTED timestamps so the
sliding-window / GC / eviction behavior is deterministic (no reliance on
wall-clock). The 6 load-bearing invariants:

1. Stateful tally: N calls admitted, (N+1)-th within the window breaches.
2. Compose/monotonic: exercised at the engine layer (test_engine_rate_limit.py);
   here we prove the breach signal the engine composes on.
3. Fail-closed: a non-finite / non-positive spec raises (engine -> BLOCKED).
4. Thread-safe atomic tally: concurrent calls admit EXACTLY the limit.
5. Bounded memory: deque(maxlen=limit+1) + window-expiry GC + LRU hard cap.
6. Finite guards: NaN/Inf limit or window raises, never silently bypasses.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from kailash.trust.pact.rate_limit_enforcer import RateBreach, RateLimitEnforcer

_T0 = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    return _T0 + timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Invariant 1 — stateful tally: N admitted, (N+1)-th breaches
# ---------------------------------------------------------------------------


class TestInvariant1_StatefulTally:
    def test_admits_up_to_limit_then_breaches(self) -> None:
        enf = RateLimitEnforcer()
        specs = [("role:action:hour", 3, 3600.0)]
        # 3 calls within the same window are admitted (recorded).
        assert enf.check_and_record(specs, _at(0)) is None
        assert enf.check_and_record(specs, _at(1)) is None
        assert enf.check_and_record(specs, _at(2)) is None
        # The 4th call within the window breaches -- a LIVE tally, no caller count.
        breach = enf.check_and_record(specs, _at(3))
        assert breach == RateBreach(3, 3600.0, "window")

    def test_breaching_call_is_not_recorded(self) -> None:
        # A breach must not consume budget: once the window rolls, the same
        # count of slots is free again (the breach did not append).
        enf = RateLimitEnforcer()
        specs = [("k", 2, 100.0)]
        assert enf.check_and_record(specs, _at(0)) is None
        assert enf.check_and_record(specs, _at(1)) is None
        # Breach at t=2 (window holds [0,1]); NOT recorded.
        assert enf.check_and_record(specs, _at(2)) == RateBreach(2, 100.0, "window")
        # At t=101 the t=0 entry expired -> one slot free -> admitted; the t=2
        # breach never added a phantom entry.
        assert enf.check_and_record(specs, _at(101)) is None

    def test_limit_zero_blocks_every_call(self) -> None:
        enf = RateLimitEnforcer()
        specs = [("k", 0, 60.0)]
        assert enf.check_and_record(specs, _at(0)) == RateBreach(0, 60.0, "window")


# ---------------------------------------------------------------------------
# Sliding-window pruning
# ---------------------------------------------------------------------------


class TestSlidingWindow:
    def test_expired_entries_pruned_admit_again(self) -> None:
        enf = RateLimitEnforcer()
        specs = [("k", 2, 100.0)]
        assert enf.check_and_record(specs, _at(0)) is None
        assert enf.check_and_record(specs, _at(10)) is None
        # At t=20 the window [t-100, t] still holds both -> breach.
        assert enf.check_and_record(specs, _at(20)) == RateBreach(2, 100.0, "window")
        # At t=111 the t=0 and t=10 entries are both older than 100s -> pruned.
        assert enf.check_and_record(specs, _at(111)) is None
        assert enf.check_and_record(specs, _at(112)) is None
        assert enf.check_and_record(specs, _at(113)) == RateBreach(2, 100.0, "window")


# ---------------------------------------------------------------------------
# Multi-window atomicity — no partial record on breach
# ---------------------------------------------------------------------------


class TestMultiWindowAtomic:
    def test_breach_in_one_window_records_nothing(self) -> None:
        enf = RateLimitEnforcer()
        day_key, hour_key = "k:day", "k:hour"
        specs = [(day_key, 100, 86400.0), (hour_key, 2, 3600.0)]
        assert enf.check_and_record(specs, _at(0)) is None  # day=1, hour=1
        assert enf.check_and_record(specs, _at(1)) is None  # day=2, hour=2
        # 3rd call: hour breaches at limit 2. Day (limit 100) MUST NOT be
        # recorded -- atomic all-or-nothing.
        breach = enf.check_and_record(specs, _at(2))
        assert breach == RateBreach(2, 3600.0, "window")
        # Inspect the live deques: day still holds exactly 2 (no phantom 3rd).
        _, day_dq = enf._tracker[day_key]
        _, hour_dq = enf._tracker[hour_key]
        assert len(day_dq) == 2
        assert len(hour_dq) == 2

    def test_admits_when_all_windows_within_limit(self) -> None:
        enf = RateLimitEnforcer()
        specs = [("k:day", 5, 86400.0), ("k:hour", 5, 3600.0)]
        for i in range(5):
            assert enf.check_and_record(specs, _at(i)) is None
        # 6th breaches -- the FIRST window in spec order (day) is named.
        assert enf.check_and_record(specs, _at(5)) == RateBreach(5, 86400.0, "window")


# ---------------------------------------------------------------------------
# Invariant 6 — finite guards; Invariant 3 — fail-closed (raise)
# ---------------------------------------------------------------------------


class TestFiniteGuards:
    def test_nan_limit_raises(self) -> None:
        enf = RateLimitEnforcer()
        with pytest.raises(ValueError, match="limit must be finite"):
            enf.check_and_record([("k", float("nan"), 3600.0)], _at(0))  # type: ignore[arg-type]

    def test_inf_window_raises(self) -> None:
        enf = RateLimitEnforcer()
        with pytest.raises(ValueError, match="window_seconds must be finite"):
            enf.check_and_record([("k", 5, float("inf"))], _at(0))

    def test_nan_window_raises(self) -> None:
        enf = RateLimitEnforcer()
        with pytest.raises(ValueError, match="window_seconds must be finite"):
            enf.check_and_record([("k", 5, float("nan"))], _at(0))

    def test_non_positive_window_raises(self) -> None:
        enf = RateLimitEnforcer()
        with pytest.raises(ValueError, match="finite and > 0"):
            enf.check_and_record([("k", 5, 0.0)], _at(0))
        with pytest.raises(ValueError, match="finite and > 0"):
            enf.check_and_record([("k", 5, -60.0)], _at(0))

    def test_empty_specs_admit_unconditionally(self) -> None:
        enf = RateLimitEnforcer()
        assert enf.check_and_record([], _at(0)) is None


# ---------------------------------------------------------------------------
# Invariant 5 — bounded memory
# ---------------------------------------------------------------------------


class TestBoundedMemory:
    def test_deque_bounded_by_maxlen(self) -> None:
        enf = RateLimitEnforcer()
        specs = [("k", 3, 3600.0)]
        for i in range(3):
            enf.check_and_record(specs, _at(i))
        _, dq = enf._tracker["k"]
        assert dq.maxlen == 4  # limit + 1

    def test_limit_growth_recreates_wider_deque_no_fail_open(self) -> None:
        # If the declared limit GROWS, a stale small maxlen would cap storage
        # below the new limit (fail-OPEN: count never reaches limit). The
        # enforcer recreates the deque wider, preserving in-window entries.
        enf = RateLimitEnforcer()
        small = [("k", 2, 3600.0)]
        enf.check_and_record(small, _at(0))
        enf.check_and_record(small, _at(1))
        # Now the limit grows to 5 -- must admit up to 5, not stay capped at 2.
        wide = [("k", 5, 3600.0)]
        assert enf.check_and_record(wide, _at(2)) is None  # 3
        assert enf.check_and_record(wide, _at(3)) is None  # 4
        assert enf.check_and_record(wide, _at(4)) is None  # 5
        assert enf.check_and_record(wide, _at(5)) == RateBreach(
            5, 3600.0, "window"
        )  # 6 -> breach
        _, dq = enf._tracker["k"]
        assert dq.maxlen == 6

    def test_gc_evicts_silent_keys(self) -> None:
        # A key whose window fully expired is reclaimed by the amortized GC on a
        # later call past the GC interval.
        enf = RateLimitEnforcer()
        enf.check_and_record([("stale", 5, 100.0)], _at(0))
        assert "stale" in enf._tracker
        # Advance well past both the window (100s) AND the GC interval (60s) so
        # the sweep runs and the stale key is silent (last entry < now - window).
        enf.check_and_record([("fresh", 5, 100.0)], _at(1000.0))
        assert "stale" not in enf._tracker
        assert "fresh" in enf._tracker

    def test_hard_cap_bounds_tracker_by_refusing_new_keys(self) -> None:
        enf = RateLimitEnforcer()
        enf._MAX_TRACKER_ENTRIES = 50  # shrink the cap for the test
        # Insert many distinct ACTIVE keys within one window at the same instant
        # (no expired key to reclaim) -> the fail-CLOSED cap REFUSES new keys
        # (it never evicts an active one) so the map stays bounded.
        results = [
            enf.check_and_record([(f"key-{i}", 5, 3600.0)], _at(0)) for i in range(500)
        ]
        assert len(enf._tracker) <= enf._MAX_TRACKER_ENTRIES
        # The over-cap calls were REFUSED (capacity breach), not silently admitted.
        capacity_refusals = [
            r for r in results if r is not None and r.kind == "capacity"
        ]
        assert len(capacity_refusals) > 0


# ---------------------------------------------------------------------------
# Invariant 4 — thread-safe atomic tally
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_calls_admit_exactly_the_limit(self) -> None:
        enf = RateLimitEnforcer()
        limit = 20
        threads_count = 200
        specs = [("shared", limit, 3600.0)]
        admitted = 0
        admitted_lock = threading.Lock()
        barrier = threading.Barrier(threads_count)
        now = _at(0)  # same instant for all -> all within the window

        def worker() -> None:
            nonlocal admitted
            barrier.wait()  # maximize contention
            if enf.check_and_record(specs, now) is None:
                with admitted_lock:
                    admitted += 1

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Atomic check-then-record: EXACTLY `limit` calls admitted, no over-admit.
        assert admitted == limit
        _, dq = enf._tracker["shared"]
        assert len(dq) == limit


# ---------------------------------------------------------------------------
# Security regression (#1516a HIGH) — eviction MUST be fail-CLOSED
# ---------------------------------------------------------------------------


class TestFailClosedEviction:
    """The hard-cap MUST NOT reset an active tally to admit a new key.

    The original design evicted the least-recently-active key at the cap. A
    throttled agent could then flood distinct junk keys to evict its OWN active
    ``(role, action)`` key -- resetting its tally to 0 = a repeatable rate-limit
    RESET bypass. The fix: at the cap, reclaim only EXPIRED keys and REFUSE the
    new key (fail-closed); an active tally is never evicted.
    """

    def test_over_cap_refuses_new_key_and_preserves_active_tally(self) -> None:
        enf = RateLimitEnforcer()
        enf._MAX_TRACKER_ENTRIES = 10  # tiny cap so the flood is cheap
        now = _at(0)

        # A throttled victim key: limit 1, one call recorded -> now at its limit.
        victim = [("victim", 1, 3600.0)]
        assert enf.check_and_record(victim, now) is None
        # Confirm the victim is throttled (its live tally == its limit).
        assert enf.check_and_record(victim, now) == RateBreach(1, 3600.0, "window")

        # Flood 200 distinct ACTIVE junk keys at the SAME instant (no expired key
        # to reclaim). The exploit WANTS one of these to evict "victim".
        for i in range(200):
            enf.check_and_record([(f"flood-{i}", 5, 3600.0)], now)

        # HIGH assertion 1: the victim key was NOT evicted (its tally survives).
        assert "victim" in enf._tracker
        _, victim_dq = enf._tracker["victim"]
        assert len(victim_dq) == 1  # tally intact, NOT reset to 0

        # HIGH assertion 2: the victim is STILL throttled -- the flood did not
        # buy it a fresh budget (the reset-bypass is closed).
        assert enf.check_and_record(victim, now) == RateBreach(1, 3600.0, "window")

        # HIGH assertion 3: a brand-new over-cap key is REFUSED (capacity breach),
        # not admitted by evicting an active key.
        newcomer = enf.check_and_record([("newcomer", 5, 3600.0)], now)
        assert newcomer is not None and newcomer.kind == "capacity"
        assert "newcomer" not in enf._tracker

        # Memory stayed bounded throughout (refuse, never grow past the cap).
        assert len(enf._tracker) <= enf._MAX_TRACKER_ENTRIES

    def test_expired_keys_are_still_reclaimed_at_the_cap(self) -> None:
        # Fail-closed refusal must NOT block admission when EXPIRED keys can be
        # reclaimed to make room (the safe half of the bound still works).
        enf = RateLimitEnforcer()
        enf._MAX_TRACKER_ENTRIES = 10
        # Fill the cap with keys in a SHORT window.
        for i in range(10):
            enf.check_and_record([(f"old-{i}", 5, 60.0)], _at(0))
        assert len(enf._tracker) == 10
        # Long after the 60s window expires, a new key is admitted because the
        # expired keys are reclaimed (room freed without evicting an active key).
        assert enf.check_and_record([("fresh", 5, 60.0)], _at(10_000.0)) is None
        assert "fresh" in enf._tracker
