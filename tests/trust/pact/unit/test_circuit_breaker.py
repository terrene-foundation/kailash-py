# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for :class:`PactCircuitBreaker` (BH5 #1510).

Each security invariant from the module docstring is pinned BEHAVIORALLY: the
method is called and state/return is asserted (NOT source-grep, per
``testing.md`` § Behavioral Regression Tests Over Source-Grep). Time is passed
explicitly via ``now`` so cooldown / window transitions are deterministic and
offline (Tier-1).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.pact.circuit_breaker import CircuitBreakerConfig, PactCircuitBreaker

UTC = timezone.utc
_KEY = "role\x1faction"


def _at(t: float) -> datetime:
    return datetime.fromtimestamp(t, tz=UTC)


def _call(
    br: PactCircuitBreaker,
    cfg: CircuitBreakerConfig,
    t: float,
    *,
    breached: bool,
    key: str = _KEY,
) -> str:
    """Simulate one verify_action: check, then record iff the decision says so."""
    now = _at(t)
    decision = br.check(key, cfg, now)
    if decision.record:
        br.record(key, cfg, now, breached=breached, was_probe=decision.was_probe)
    return decision.level


# ---------------------------------------------------------------------------
# Invariant 1 -- trip after N in-window breaches
# ---------------------------------------------------------------------------


class TestInvariant1_TripAfterN:
    def test_trips_open_on_the_nth_in_window_breach(self) -> None:
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(3, 60.0, 30.0)
        # 3 breached calls within the window are all ADMITTED (the trip happens
        # in record, observable on the NEXT check).
        for t in (0.0, 1.0, 2.0):
            assert _call(br, cfg, t, breached=True) == "auto_approved"
        # The 4th call is BLOCKED -- the breaker tripped OPEN.
        d = br.check(_KEY, cfg, _at(3.0))
        assert d.level == "blocked"
        assert d.state == "open"
        assert d.record is False  # a breaker-blocked call is NOT recorded

    def test_below_threshold_never_trips(self) -> None:
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(3, 60.0, 30.0)
        # Only 2 breaches -> never reaches N=3.
        for t in (0.0, 1.0):
            assert _call(br, cfg, t, breached=True) == "auto_approved"
        assert br.check(_KEY, cfg, _at(2.0)).level == "auto_approved"

    def test_breaches_outside_window_decay_and_do_not_trip(self) -> None:
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(3, 60.0, 30.0)
        # Two breaches, then a third far outside the 60s window -> the first two
        # are pruned; the live in-window count never reaches 3.
        assert _call(br, cfg, 0.0, breached=True) == "auto_approved"
        assert _call(br, cfg, 1.0, breached=True) == "auto_approved"
        assert _call(br, cfg, 200.0, breached=True) == "auto_approved"
        assert br.check(_KEY, cfg, _at(201.0)).level == "auto_approved"

    def test_clean_calls_do_not_hard_reset_the_window(self) -> None:
        # Sliding-window model (mirrors the rate enforcer): a clean call between
        # breaches does NOT clear accumulated failures.
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(3, 60.0, 30.0)
        assert _call(br, cfg, 0.0, breached=True) == "auto_approved"
        assert _call(br, cfg, 1.0, breached=False) == "auto_approved"  # clean
        assert _call(br, cfg, 2.0, breached=True) == "auto_approved"
        assert _call(br, cfg, 3.0, breached=True) == "auto_approved"  # 3rd breach
        assert br.check(_KEY, cfg, _at(4.0)).level == "blocked"


# ---------------------------------------------------------------------------
# Invariant 2 -- OPEN blocks through cooldown; cooldown -> HALF_OPEN probe
# ---------------------------------------------------------------------------


class TestInvariant2_OpenBlocksAndCooldown:
    def _trip(self, br: PactCircuitBreaker, cfg: CircuitBreakerConfig) -> None:
        for t in (0.0, 1.0):
            _call(br, cfg, t, breached=True)  # N=2 -> tripped OPEN at t=1

    def test_open_blocks_every_call_within_cooldown(self) -> None:
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(2, 60.0, 30.0)
        self._trip(br, cfg)
        for t in (2.0, 10.0, 30.0):  # all < opened_at(1) + 30
            assert br.check(_KEY, cfg, _at(t)).level == "blocked"

    def test_cooldown_elapsed_admits_exactly_one_probe(self) -> None:
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(2, 60.0, 30.0)
        self._trip(br, cfg)  # opened_at = 1.0
        d = br.check(_KEY, cfg, _at(1.0 + 30.0))  # cooldown elapsed
        assert d.level == "auto_approved"
        assert d.state == "half_open"
        assert d.was_probe is True
        # A SECOND call while the probe is in flight is blocked (one at a time).
        d2 = br.check(_KEY, cfg, _at(1.0 + 30.1))
        assert d2.level == "blocked"
        assert d2.state == "half_open"
        assert d2.record is False


# ---------------------------------------------------------------------------
# Invariant 3 -- probe resolution: success -> CLOSED, failure -> re-OPEN
# ---------------------------------------------------------------------------


class TestInvariant3_ProbeResolution:
    def _trip(self, br: PactCircuitBreaker, cfg: CircuitBreakerConfig) -> None:
        for t in (0.0, 1.0):
            _call(br, cfg, t, breached=True)

    def test_probe_success_resets_to_closed(self) -> None:
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(2, 60.0, 30.0)
        self._trip(br, cfg)
        probe_t = 31.0
        d = br.check(_KEY, cfg, _at(probe_t))
        assert d.was_probe is True
        br.record(_KEY, cfg, _at(probe_t), breached=False, was_probe=True)
        # Recovered: next call admitted, and the window is clear (no re-trip).
        assert br.check(_KEY, cfg, _at(probe_t + 1)).level == "auto_approved"

    def test_probe_failure_reopens_with_fresh_cooldown(self) -> None:
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(2, 60.0, 30.0)
        self._trip(br, cfg)
        probe_t = 31.0
        d = br.check(_KEY, cfg, _at(probe_t))
        assert d.was_probe is True
        br.record(_KEY, cfg, _at(probe_t), breached=True, was_probe=True)
        # Re-OPEN: blocked again, and the cooldown restarts from probe_t.
        assert br.check(_KEY, cfg, _at(probe_t + 1)).level == "blocked"
        assert br.check(_KEY, cfg, _at(probe_t + 29)).level == "blocked"
        # Only after a FRESH full cooldown does another probe open.
        assert br.check(_KEY, cfg, _at(probe_t + 30)).state == "half_open"


# ---------------------------------------------------------------------------
# Invariant 4 -- fail-closed on malformed config / non-finite now
# ---------------------------------------------------------------------------


class TestInvariant4_FailClosed:
    @pytest.mark.parametrize(
        "cfg",
        [
            CircuitBreakerConfig(3, float("nan"), 30.0),
            CircuitBreakerConfig(3, float("inf"), 30.0),
            CircuitBreakerConfig(3, 60.0, float("nan")),
            CircuitBreakerConfig(3, 0.0, 30.0),  # non-positive window
            CircuitBreakerConfig(3, 60.0, -5.0),  # negative cooldown
            CircuitBreakerConfig(0, 60.0, 30.0),  # threshold < 1
        ],
    )
    def test_check_raises_valueerror_on_malformed_config(
        self, cfg: CircuitBreakerConfig
    ) -> None:
        br = PactCircuitBreaker()
        with pytest.raises(ValueError):
            br.check(_KEY, cfg, _at(0.0))

    def test_record_raises_valueerror_on_malformed_config(self) -> None:
        br = PactCircuitBreaker()
        with pytest.raises(ValueError):
            br.record(
                _KEY,
                CircuitBreakerConfig(3, float("nan"), 30.0),
                _at(0.0),
                breached=True,
                was_probe=False,
            )

    def test_nan_cooldown_cannot_silently_release_a_tripped_breaker(self) -> None:
        # Defense-in-depth: a NaN cooldown must NOT make `now - opened_at < NaN`
        # vacuously admit (NaN comparisons are always False). It fail-closes on
        # validation instead.
        br = PactCircuitBreaker()
        good = CircuitBreakerConfig(2, 60.0, 30.0)
        for t in (0.0, 1.0):
            _call(br, good, t, breached=True)  # tripped OPEN
        with pytest.raises(ValueError):
            br.check(_KEY, CircuitBreakerConfig(2, 60.0, float("nan")), _at(1000.0))


# ---------------------------------------------------------------------------
# Invariant 5 -- bounded memory, fail-CLOSED eviction (never evict a live key)
# ---------------------------------------------------------------------------


class TestInvariant5_BoundedMemory:
    def test_capacity_refuses_new_key_when_full_of_tripped_keys(self) -> None:
        br = PactCircuitBreaker()
        br._MAX_TRACKER_ENTRIES = 2  # instance-shadow the class cap
        cfg = CircuitBreakerConfig(1, 3600.0, 3600.0)  # trips on first breach
        # Trip two distinct keys OPEN (fills the tracker with live keys).
        for k in ("k1", "k2"):
            _call(br, cfg, 0.0, breached=True, key=k)
            assert br.check(k, cfg, _at(1.0)).level == "blocked"  # confirm OPEN
        # A THIRD, new key cannot be admitted without evicting a tripped key ->
        # fail-closed capacity refusal (NOTHING is created).
        d = br.check("k3", cfg, _at(1.0))
        assert d.level == "blocked"
        assert d.state == "capacity"
        assert "k3" not in br._tracker

    def test_tripped_key_is_never_evicted_under_capacity_pressure(self) -> None:
        br = PactCircuitBreaker()
        br._MAX_TRACKER_ENTRIES = 1
        cfg = CircuitBreakerConfig(1, 3600.0, 3600.0)
        _call(br, cfg, 0.0, breached=True, key="tripped")  # OPEN
        # New key refused -> the tripped key survives (its hold is NOT reset).
        assert br.check("other", cfg, _at(1.0)).state == "capacity"
        assert br.check("tripped", cfg, _at(2.0)).level == "blocked"

    def test_expired_closed_key_is_reclaimable_freeing_room(self) -> None:
        br = PactCircuitBreaker()
        br._MAX_TRACKER_ENTRIES = 1
        cfg = CircuitBreakerConfig(3, 60.0, 30.0)  # never trips (only 1 breach)
        # One CLOSED key with a single breach at t=0.
        _call(br, cfg, 0.0, breached=True, key="stale")
        assert "stale" in br._tracker
        # Long after the window, a new key triggers reclaim of the expired CLOSED
        # 'stale' key -> the new key IS admitted (room was freed safely).
        d = br.check("fresh", cfg, _at(10_000.0))
        assert d.level == "auto_approved"
        assert "stale" not in br._tracker


# ---------------------------------------------------------------------------
# Invariant 6 -- monotonic: the breaker only ever returns auto_approved/blocked
# ---------------------------------------------------------------------------


class TestInvariant6_MonotonicVocabulary:
    def test_breaker_never_emits_a_de_escalating_level(self) -> None:
        # The breaker's ONLY levels are auto_approved (admit) and blocked (hold).
        # It never emits flagged/held, so composed via combine_levels it can only
        # TIGHTEN a base, never loosen it.
        br = PactCircuitBreaker()
        cfg = CircuitBreakerConfig(2, 60.0, 30.0)
        seen = set()
        seen.add(br.check(_KEY, cfg, _at(0.0)).level)
        br.record(_KEY, cfg, _at(0.0), breached=True, was_probe=False)
        seen.add(br.check(_KEY, cfg, _at(1.0)).level)
        br.record(_KEY, cfg, _at(1.0), breached=True, was_probe=False)
        seen.add(br.check(_KEY, cfg, _at(2.0)).level)  # OPEN -> blocked
        assert seen <= {"auto_approved", "blocked"}
