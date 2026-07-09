# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Engine-integration tests for the stateful rate-limit enforcer (#1516 leg a).

These exercise ``GovernanceEngine.verify_action`` end-to-end and pin the 6
load-bearing invariants of wiring a LIVE sliding-window rate counter into the
verdict path:

1. A stateful counter TALLIES real verify_action calls (not a caller-supplied
   count): N calls within the window are admitted, the (N+1)-th is BLOCKED by
   the live counter.
2. A rate breach composes MONOTONICALLY via ``combine_levels`` -- it can only
   TIGHTEN (a held base becomes blocked); it never de-escalates a held/blocked
   base.
3. A counter/backend error fails CLOSED to BLOCKED (never fail-open).
4. Concurrent tally is thread-safe: exactly ``limit`` calls are admitted.
5. Backward-compat: an action with NO rate config behaves exactly as before,
   and the pre-existing caller-supplied ``daily_calls`` path still blocks.
6. Finite guards on the window/limit numerics (covered directly in
   test_rate_limit_enforcer.py; the engine's fail-closed wrapper is pinned here).

Windows are 1 hour / 1 day, far larger than a test's wall-clock, so every call
in one test is within the window -- the LIVE counter alone decides the breach.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

_ROLE = "D1-R1-D1-R1-D1-R1-T1-R1"  # CS Chair
_DEFINER = "D1-R1-D1-R1-D1-R1"  # Dean


# ---------------------------------------------------------------------------
# Fixtures (mirror test_engine_risk_factors.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def university_compiled() -> tuple[CompiledOrg, Any]:
    return create_university_org()


@pytest.fixture
def compiled_org(university_compiled: tuple[CompiledOrg, Any]) -> CompiledOrg:
    return university_compiled[0]


@pytest.fixture
def clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    return create_university_clearances(compiled_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    return create_university_ksps()


@pytest.fixture
def engine(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> GovernanceEngine:
    from kailash.trust.pact.store import MemoryAccessPolicyStore, MemoryClearanceStore

    clearance_store = MemoryClearanceStore()
    for clr in clearances.values():
        clearance_store.grant_clearance(clr)
    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)
    return GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
    )


def _set_rate_envelope(
    engine: GovernanceEngine,
    *,
    max_per_hour: int | None = None,
    max_per_day: int | None = None,
    max_spend: float = 1000.0,
    approval_above: float | None = None,
    allowed: list[str] | None = None,
) -> None:
    fin = FinancialConstraintConfig(
        max_spend_usd=max_spend, requires_approval_above_usd=approval_above
    )
    envelope = ConstraintEnvelopeConfig(
        id="env-rate-test",
        description="rate-limit test envelope",
        financial=fin,
        operational=OperationalConstraintConfig(
            allowed_actions=allowed or ["read", "write", "deploy", "delete"],
            max_actions_per_hour=max_per_hour,
            max_actions_per_day=max_per_day,
        ),
    )
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-rate-test",
            defining_role_address=_DEFINER,
            target_role_address=_ROLE,
            envelope=envelope,
        )
    )


# ---------------------------------------------------------------------------
# Invariant 1 — the LIVE counter tallies (not a caller-supplied count)
# ---------------------------------------------------------------------------


class TestInvariant1_LiveTally:
    def test_n_calls_admitted_then_blocked_by_live_counter(
        self, engine: GovernanceEngine
    ) -> None:
        _set_rate_envelope(engine, max_per_hour=3)
        # NO caller-supplied daily_calls/hourly_calls anywhere -- the counter
        # tallies the real calls itself.
        for _ in range(3):
            verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0})
            assert verdict.level == "auto_approved"
        # The 4th call within the window is blocked by the live counter.
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0})
        assert verdict.level == "blocked"
        assert verdict.is_blocked is True
        assert "sliding-window" in verdict.reason

    def test_counter_is_per_action(self, engine: GovernanceEngine) -> None:
        # Distinct actions have independent budgets.
        _set_rate_envelope(engine, max_per_hour=1)
        assert engine.verify_action(_ROLE, "read", {}).level == "auto_approved"
        # "read" is now exhausted, but "write" has its own fresh budget.
        assert engine.verify_action(_ROLE, "write", {}).level == "auto_approved"
        assert engine.verify_action(_ROLE, "read", {}).level == "blocked"

    def test_day_and_hour_windows_both_enforced(self, engine: GovernanceEngine) -> None:
        _set_rate_envelope(engine, max_per_hour=100, max_per_day=2)
        assert engine.verify_action(_ROLE, "deploy", {}).level == "auto_approved"
        assert engine.verify_action(_ROLE, "deploy", {}).level == "auto_approved"
        # 3rd trips the daily window even though the hourly window is far from
        # its limit.
        verdict = engine.verify_action(_ROLE, "deploy", {})
        assert verdict.level == "blocked"
        assert "day" in verdict.reason


# ---------------------------------------------------------------------------
# Invariant 2 — monotonic composition via combine_levels
# ---------------------------------------------------------------------------


class TestInvariant2_MonotonicCompose:
    def test_rate_breach_tightens_a_held_base_to_blocked(
        self, engine: GovernanceEngine
    ) -> None:
        # cost between approval threshold and max -> base is HELD every call.
        _set_rate_envelope(
            engine, max_per_hour=2, max_spend=1000.0, approval_above=100.0
        )
        ctx = {"cost": 500.0}
        assert engine.verify_action(_ROLE, "deploy", ctx).level == "held"
        assert engine.verify_action(_ROLE, "deploy", ctx).level == "held"
        # 3rd: base still HELD, but the rate breach TIGHTENS it to blocked.
        verdict = engine.verify_action(_ROLE, "deploy", ctx)
        assert verdict.level == "blocked"
        assert "sliding-window" in verdict.reason

    def test_rate_ok_does_not_de_escalate_a_held_base(
        self, engine: GovernanceEngine
    ) -> None:
        # A within-limit rate verdict (auto_approved) must NOT loosen a HELD base.
        _set_rate_envelope(
            engine, max_per_hour=10, max_spend=1000.0, approval_above=100.0
        )
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 500.0})
        assert verdict.level == "held"  # stayed held, not dropped to auto_approved

    def test_rate_ok_does_not_de_escalate_a_blocked_base(
        self, engine: GovernanceEngine
    ) -> None:
        # cost exceeds max_spend -> base BLOCKED. A within-limit rate verdict
        # must not loosen it.
        _set_rate_envelope(engine, max_per_hour=10, max_spend=100.0)
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 9999.0})
        assert verdict.level == "blocked"


# ---------------------------------------------------------------------------
# Invariant 3 — fail-closed on counter error
# ---------------------------------------------------------------------------


class TestInvariant3_FailClosed:
    def test_counter_error_fails_closed_to_blocked(
        self, engine: GovernanceEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_rate_envelope(engine, max_per_hour=5)

        def _boom(*_a: Any, **_kw: Any) -> None:
            raise RuntimeError("counter backend exploded")

        monkeypatch.setattr(engine._rate_enforcer, "check_and_record", _boom)
        verdict = engine.verify_action(_ROLE, "read", {})
        # NEVER fail-open -- a counter error is BLOCKED (pact-governance Rule 4).
        assert verdict.level == "blocked"
        assert verdict.is_blocked is True

    def test_counter_error_does_not_de_escalate(
        self, engine: GovernanceEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Even if the base were auto_approved, a counter error blocks.
        _set_rate_envelope(engine, max_per_hour=5, max_spend=1000.0)

        def _boom(*_a: Any, **_kw: Any) -> None:
            raise RuntimeError("counter backend exploded")

        monkeypatch.setattr(engine._rate_enforcer, "check_and_record", _boom)
        assert engine.verify_action(_ROLE, "read", {"cost": 1.0}).level == "blocked"


# ---------------------------------------------------------------------------
# Invariant 4 — concurrent tally is thread-safe (exactly `limit` admitted)
# ---------------------------------------------------------------------------


class TestInvariant4_ThreadSafe:
    def test_concurrent_verify_action_admits_exactly_the_limit(
        self, engine: GovernanceEngine
    ) -> None:
        limit = 15
        threads_count = 150
        _set_rate_envelope(engine, max_per_hour=limit)

        results: list[str] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(threads_count)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                barrier.wait()
                verdict = engine.verify_action(_ROLE, "read", {})
                with results_lock:
                    results.append(verdict.level)
            except BaseException as exc:  # noqa: BLE001 -- test records, re-checks
                with results_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"verify_action raised under concurrency: {errors}"
        admitted = sum(1 for level in results if level == "auto_approved")
        blocked = sum(1 for level in results if level == "blocked")
        # Atomic tally: EXACTLY `limit` admitted, the rest blocked -- no over-admit.
        assert admitted == limit
        assert blocked == threads_count - limit


# ---------------------------------------------------------------------------
# Invariant 5 — backward compatibility
# ---------------------------------------------------------------------------


class TestInvariant5_BackwardCompat:
    def test_no_rate_config_behaves_as_before(self, engine: GovernanceEngine) -> None:
        # No max_actions_per_hour/day -> the live counter never fires; repeated
        # calls stay auto_approved exactly as before the seam.
        _set_rate_envelope(engine)  # neither window set
        for _ in range(25):
            assert engine.verify_action(_ROLE, "read", {"cost": 1.0}).level == (
                "auto_approved"
            )

    def test_caller_supplied_daily_calls_path_still_blocks(
        self, engine: GovernanceEngine
    ) -> None:
        # The pre-existing caller-supplied count path is untouched: a caller
        # passing daily_calls at/over the limit is still blocked (regression pin).
        _set_rate_envelope(engine, max_per_day=5)
        verdict = engine.verify_action(_ROLE, "read", {"daily_calls": 10})
        assert verdict.level == "blocked"
        assert "Daily rate limit exceeded" in verdict.reason

    def test_no_envelope_action_unaffected(self, engine: GovernanceEngine) -> None:
        # A role with no envelope in the fixture -> rate enforcement never runs.
        verdict = engine.verify_action("D1-R1-D2-R1-T1-R1", "read", {})
        assert verdict.level == "auto_approved"


# ---------------------------------------------------------------------------
# Security regression (#1516a MED) — already-blocked actions do NOT mint keys
# ---------------------------------------------------------------------------


class TestAlreadyBlockedDoesNotMintKey:
    """An action blocked BEFORE the rate step must NOT create a tracker key.

    Tallying already-blocked attempts both over-counts (the caller never
    performed the action) AND is the enabler for the fail-closed-eviction
    key-flood: any junk allowlist-rejected action string would otherwise mint a
    key. The engine gates the rate step on ``level != 'blocked'``.
    """

    def test_allowlist_rejected_action_creates_no_tracker_key(
        self, engine: GovernanceEngine
    ) -> None:
        # "read" is the ONLY allowed action; anything else is blocked pre-rate.
        _set_rate_envelope(engine, max_per_hour=5, allowed=["read"])

        # Flood junk action strings -- each is allowlist-rejected (blocked).
        for i in range(20):
            verdict = engine.verify_action(_ROLE, f"junk_action_{i}", {})
            assert verdict.level == "blocked"

        # NOT ONE junk action minted a rate-tracker key (the key-flood enabler
        # is closed): the tracker holds no key for any junk action.
        tracker = engine._rate_enforcer._tracker
        assert not any("junk_action_" in key for key in tracker)

        # An ALLOWED action still tallies normally (the gate did not break the
        # happy path): 5 admitted, 6th blocked by the live counter.
        for _ in range(5):
            assert engine.verify_action(_ROLE, "read", {}).level == "auto_approved"
        assert engine.verify_action(_ROLE, "read", {}).level == "blocked"
        assert any("\x1fread\x1f" in key for key in engine._rate_enforcer._tracker)
