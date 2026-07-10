# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Engine-integration tests for the governance circuit-breaker (BH5 #1510).

Exercise ``GovernanceEngine.verify_action`` end-to-end and pin the load-bearing
invariants of wiring a first-class trip-and-hold breaker into the verdict path
at Step 3.7:

1. Trip-and-hold: N repeatedly-HELD calls TRIP the breaker; the next call is
   BLOCKED by the breaker even though its underlying outcome would be held.
2. Monotonic compose: a tripped breaker can only TIGHTEN -- an auto_approved
   base becomes blocked; it never de-escalates a held/blocked base.
3. Already-blocked base does NOT run the breaker nor mint a key (matches the
   rate-limiter key-flood defense; Step 3.7 gates on level != "blocked").
4. Fail-closed: a breaker check error BLOCKS (never fail-open).
5. Audit: the breaker's state is recorded under audit_details["circuit_breaker"]
   ONLY when the breaker governs the action (byte-unchanged otherwise).
6. Enforcement-surface parity: RoleEnvelope registration REJECTS a child that
   strips or loosens a parent's breaker (validate_tightening learned BH5).

Windows/cooldowns are far larger than a test's wall-clock, so every call is
in-window and inside the cooldown -- the breaker state alone decides the verdict.
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import MonotonicTighteningError, RoleEnvelope
from kailash.trust.pact.store import MemoryClearanceStore
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

_ROLE = "D1-R1-D1-R1-D1-R1-T1-R1"  # CS Chair
_DEFINER = "D1-R1-D1-R1-D1-R1"  # Dean


@pytest.fixture
def engine() -> GovernanceEngine:
    org, _ = create_university_org()
    clearance_store = MemoryClearanceStore()
    for clr in create_university_clearances(org).values():
        clearance_store.grant_clearance(clr)
    return GovernanceEngine(org, clearance_store=clearance_store)


def _set_breaker_envelope(
    engine: GovernanceEngine,
    *,
    threshold: int | None = 3,
    window: float | None = 3600.0,
    cooldown: float | None = 300.0,
    max_spend: float = 1000.0,
    approval_above: float | None = 100.0,
    allowed: list[str] | None = None,
) -> None:
    envelope = ConstraintEnvelopeConfig(
        id="env-breaker-test",
        financial=FinancialConstraintConfig(
            max_spend_usd=max_spend, requires_approval_above_usd=approval_above
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=allowed or ["deploy", "read"],
            circuit_failure_threshold=threshold,
            circuit_window_seconds=window,
            circuit_cooldown_seconds=cooldown,
        ),
    )
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-breaker-test",
            defining_role_address=_DEFINER,
            target_role_address=_ROLE,
            envelope=envelope,
        )
    )


# ---------------------------------------------------------------------------
# Invariant 1 -- trip-and-hold
# ---------------------------------------------------------------------------


class TestInvariant1_TripAndHold:
    def test_repeated_held_calls_trip_the_breaker_then_block(
        self, engine: GovernanceEngine
    ) -> None:
        _set_breaker_envelope(engine, threshold=3)
        held_ctx = {"cost": 500.0}  # above approval, below max -> HELD
        for _ in range(3):
            assert engine.verify_action(_ROLE, "deploy", held_ctx).level == "held"
        # 4th: underlying still held, but the tripped breaker BLOCKS it.
        verdict = engine.verify_action(_ROLE, "deploy", held_ctx)
        assert verdict.level == "blocked"
        assert "Circuit-breaker OPEN" in verdict.reason

    def test_breaker_is_per_role_action(self, engine: GovernanceEngine) -> None:
        _set_breaker_envelope(engine, threshold=2)
        held = {"cost": 500.0}
        assert engine.verify_action(_ROLE, "deploy", held).level == "held"
        assert engine.verify_action(_ROLE, "deploy", held).level == "held"
        # 'deploy' now tripped; 'read' has its own independent breaker.
        assert engine.verify_action(_ROLE, "read", held).level == "held"
        assert engine.verify_action(_ROLE, "deploy", held).level == "blocked"


# ---------------------------------------------------------------------------
# Invariant 2 -- monotonic compose (only tightens)
# ---------------------------------------------------------------------------


class TestInvariant2_MonotonicCompose:
    def test_tripped_breaker_blocks_even_an_auto_approved_base(
        self, engine: GovernanceEngine
    ) -> None:
        _set_breaker_envelope(engine, threshold=2)
        held = {"cost": 500.0}
        engine.verify_action(_ROLE, "deploy", held)
        engine.verify_action(_ROLE, "deploy", held)  # tripped
        # A cheap (auto_approved) call is still BLOCKED by the tripped breaker.
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 1.0})
        assert verdict.level == "blocked"

    def test_breaker_never_de_escalates_a_blocked_base(
        self, engine: GovernanceEngine
    ) -> None:
        # Base BLOCKED (cost exceeds max_spend). Step 3.7 is skipped entirely ->
        # the breaker neither runs nor mints a key.
        _set_breaker_envelope(engine, threshold=3, max_spend=100.0)
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 9999.0})
        assert verdict.level == "blocked"
        assert "circuit_breaker" not in verdict.audit_details
        assert not any("\x1fdeploy" in k for k in engine._circuit_breaker._tracker)


# ---------------------------------------------------------------------------
# Invariant 3 -- already-blocked base mints no key
# ---------------------------------------------------------------------------


class TestInvariant3_NoKeyForBlockedBase:
    def test_allowlist_rejected_action_mints_no_breaker_key(
        self, engine: GovernanceEngine
    ) -> None:
        _set_breaker_envelope(engine, threshold=3, allowed=["deploy"])
        for i in range(10):
            assert (
                engine.verify_action(_ROLE, f"junk_{i}", {"cost": 1.0}).level
                == "blocked"
            )
        assert not any("junk_" in k for k in engine._circuit_breaker._tracker)


# ---------------------------------------------------------------------------
# Invariant 4 -- fail-closed on breaker error
# ---------------------------------------------------------------------------


class TestInvariant4_FailClosed:
    def test_breaker_check_error_fails_closed_to_blocked(
        self, engine: GovernanceEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_breaker_envelope(engine, threshold=3)

        def _boom(*_a: Any, **_kw: Any) -> None:
            raise RuntimeError("breaker backend exploded")

        monkeypatch.setattr(engine._circuit_breaker, "check", _boom)
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 1.0})
        assert verdict.level == "blocked"
        assert verdict.audit_details["circuit_breaker"]["state"] == "error"


# ---------------------------------------------------------------------------
# Invariant 5 -- audit surface (present only when governed)
# ---------------------------------------------------------------------------


class TestInvariant5_Audit:
    def test_audit_has_circuit_breaker_block_when_governed(
        self, engine: GovernanceEngine
    ) -> None:
        _set_breaker_envelope(engine, threshold=3)
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 1.0})
        cb = verdict.audit_details.get("circuit_breaker")
        assert cb is not None
        assert cb["state"] == "closed"
        assert cb["tripped"] is False

    def test_audit_byte_unchanged_when_no_breaker_configured(
        self, engine: GovernanceEngine
    ) -> None:
        _set_breaker_envelope(
            engine, threshold=None, window=None, cooldown=None
        )  # no breaker
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 1.0})
        assert "circuit_breaker" not in verdict.audit_details


# ---------------------------------------------------------------------------
# Invariant 6 -- enforcement-surface parity (re-registration cannot strip it)
# ---------------------------------------------------------------------------


class TestInvariant6_TighteningParity:
    def _parent_child(
        self,
        engine: GovernanceEngine,
        *,
        child_op: OperationalConstraintConfig,
    ) -> None:
        parent = ConstraintEnvelopeConfig(
            id="parent",
            operational=OperationalConstraintConfig(
                allowed_actions=["deploy"],
                circuit_failure_threshold=3,
                circuit_window_seconds=3600.0,
                circuit_cooldown_seconds=300.0,
            ),
        )
        engine.set_role_envelope(
            RoleEnvelope(
                id="re-parent",
                defining_role_address="D1-R1-D1-R1-D1-R1",
                target_role_address=_DEFINER,
                envelope=parent,
            )
        )
        child = ConstraintEnvelopeConfig(id="child", operational=child_op)
        engine.set_role_envelope(
            RoleEnvelope(
                id="re-child",
                defining_role_address=_DEFINER,
                target_role_address=_ROLE,
                envelope=child,
            )
        )

    def test_child_stripping_the_breaker_is_rejected(
        self, engine: GovernanceEngine
    ) -> None:
        with pytest.raises(MonotonicTighteningError, match="circuit-breaker widened"):
            self._parent_child(
                engine,
                child_op=OperationalConstraintConfig(allowed_actions=["deploy"]),
            )

    def test_child_loosening_the_breaker_is_rejected(
        self, engine: GovernanceEngine
    ) -> None:
        with pytest.raises(MonotonicTighteningError, match="circuit_failure_threshold"):
            self._parent_child(
                engine,
                child_op=OperationalConstraintConfig(
                    allowed_actions=["deploy"],
                    circuit_failure_threshold=99,  # higher = trips less = wider
                    circuit_window_seconds=3600.0,
                    circuit_cooldown_seconds=300.0,
                ),
            )

    def test_child_tightening_the_breaker_is_accepted(
        self, engine: GovernanceEngine
    ) -> None:
        # Lower threshold + longer cooldown/window = strictly tighter -> allowed.
        self._parent_child(
            engine,
            child_op=OperationalConstraintConfig(
                allowed_actions=["deploy"],
                circuit_failure_threshold=2,
                circuit_window_seconds=7200.0,
                circuit_cooldown_seconds=600.0,
            ),
        )
