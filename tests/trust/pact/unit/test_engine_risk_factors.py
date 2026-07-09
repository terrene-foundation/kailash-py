# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Engine-integration tests for the risk-factor calibration seam (GH #1514).

These exercise ``GovernanceEngine.verify_action`` end-to-end and pin the 6
load-bearing invariants of the extensible risk-factor disposition seam:

1. ``_evaluate_against_envelope`` reads a structured risk-factor set from the
   action context (``ctx["risk_factors"]``).
2. A near-zero-limit-proximity irreversible / high-materiality action is
   ESCALATED (held) or DENIED (blocked) independently of spend proximity, and
   factors can only TIGHTEN (monotonic).
3. A new factor registers via the registry without editing the engine core.
4. The factors that drove the outcome are recorded for audit.
5. A malformed factor set fails closed (blocked), never silently ignored.
6. An action with NO risk_factors behaves EXACTLY as today (regression pin).
"""

from __future__ import annotations

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
from kailash.trust.pact.risk_factors import (
    GLOBAL_RISK_FACTOR_REGISTRY,
    RiskFactor,
    RiskFactorRegistry,
)
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

# A role that has clearance in the university fixture set.
_ROLE = "D1-R1-D1-R1-D1-R1-T1-R1"  # CS Chair
_DEFINER = "D1-R1-D1-R1-D1-R1"  # Dean


# ---------------------------------------------------------------------------
# Fixtures (mirror test_engine.py's module-local fixtures)
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


def _set_envelope(
    engine: GovernanceEngine,
    *,
    max_spend: float = 1000.0,
    approval_above: float | None = None,
    allowed: list[str] | None = None,
) -> None:
    fin = FinancialConstraintConfig(max_spend_usd=max_spend)
    if approval_above is not None:
        fin = FinancialConstraintConfig(
            max_spend_usd=max_spend, requires_approval_above_usd=approval_above
        )
    envelope = ConstraintEnvelopeConfig(
        id="env-risk-test",
        description="risk-factor test envelope",
        financial=fin,
        operational=OperationalConstraintConfig(
            allowed_actions=allowed or ["read", "write", "deploy", "delete"],
        ),
    )
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-risk-test",
            defining_role_address=_DEFINER,
            target_role_address=_ROLE,
            envelope=envelope,
        )
    )


# ---------------------------------------------------------------------------
# Invariant 1 — reads structured risk factors from the action context
# ---------------------------------------------------------------------------


class TestInvariant1_StructuredInput:
    def test_risk_factors_read_from_context(self, engine: GovernanceEngine) -> None:
        _set_envelope(engine)
        verdict = engine.verify_action(
            _ROLE,
            "read",
            {"cost": 1.0, "risk_factors": {"reversibility": "reversible"}},
        )
        # Reversible + tiny cost stays auto_approved, but the factor set was
        # read and recorded.
        assert verdict.level == "auto_approved"
        assert verdict.risk_factors is not None
        assert verdict.risk_factors["per_factor"] == {"reversibility": "auto_approved"}


# ---------------------------------------------------------------------------
# Invariant 2 — escalate independent of spend proximity; monotonic tighten only
# ---------------------------------------------------------------------------


class TestInvariant2_MonotonicEscalation:
    def test_irreversible_near_zero_cost_escalates_to_held(
        self, engine: GovernanceEngine
    ) -> None:
        _set_envelope(engine, max_spend=1000.0)
        # cost 0 -> limit proximity alone is auto_approved.
        verdict = engine.verify_action(
            _ROLE,
            "deploy",
            {"cost": 0.0, "risk_factors": {"reversibility": "irreversible"}},
        )
        assert verdict.level == "held"
        assert verdict.is_held is True

    def test_critical_materiality_near_zero_cost_denies(
        self, engine: GovernanceEngine
    ) -> None:
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(
            _ROLE,
            "delete",
            {
                "cost": 0.0,
                "risk_factors": {
                    "reversibility": "irreversible",
                    "materiality": "critical",
                },
            },
        )
        assert verdict.level == "blocked"
        assert verdict.is_blocked is True

    def test_factor_cannot_downgrade_a_blocked_verdict(
        self, engine: GovernanceEngine
    ) -> None:
        # cost exceeds max_spend -> limit proximity is blocked. A low-severity
        # factor must NOT loosen it to flagged.
        _set_envelope(engine, max_spend=100.0)
        verdict = engine.verify_action(
            _ROLE,
            "deploy",
            {"cost": 9999.0, "risk_factors": {"reversibility": "reversible"}},
        )
        assert verdict.level == "blocked"

    def test_factor_cannot_downgrade_a_held_verdict(
        self, engine: GovernanceEngine
    ) -> None:
        # cost between approval threshold and max -> held. A flagged-level
        # factor must NOT loosen it.
        _set_envelope(engine, max_spend=1000.0, approval_above=100.0)
        verdict = engine.verify_action(
            _ROLE,
            "deploy",
            {"cost": 500.0, "risk_factors": {"novelty": "novel"}},  # novel=flagged
        )
        assert verdict.level == "held"

    def test_factor_tightens_flagged_to_blocked(self, engine: GovernanceEngine) -> None:
        # cost within 20% of max -> flagged; secret sensitivity -> blocked.
        _set_envelope(engine, max_spend=100.0)
        verdict = engine.verify_action(
            _ROLE,
            "deploy",
            {"cost": 90.0, "risk_factors": {"sensitivity": "secret"}},
        )
        assert verdict.level == "blocked"

    def test_escalation_applies_without_any_envelope(
        self, engine: GovernanceEngine
    ) -> None:
        # No envelope set for this role -> limit proximity is auto_approved,
        # but an irreversible action must still escalate.
        verdict = engine.verify_action(
            "D1-R1-D2-R1-T1-R1",  # HR Director: no envelope in this fixture
            "read",
            {"risk_factors": {"materiality": "critical"}},
        )
        assert verdict.level == "blocked"


# ---------------------------------------------------------------------------
# Invariant 3 — a new factor registers WITHOUT editing the engine core
# ---------------------------------------------------------------------------


class TestInvariant3_Extensible:
    def test_new_factor_via_per_engine_registry(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
    ) -> None:
        from kailash.trust.pact.store import MemoryClearanceStore

        clearance_store = MemoryClearanceStore()
        for clr in clearances.values():
            clearance_store.grant_clearance(clr)

        registry = RiskFactorRegistry()
        # A brand-new factor the engine has never heard of.
        registry.register(
            RiskFactor(
                "pii_exposure",
                lambda ctx, value: "blocked" if value == "yes" else "auto_approved",
            )
        )
        engine = GovernanceEngine(
            compiled_org,
            clearance_store=clearance_store,
            risk_factor_registry=registry,
        )
        _set_envelope(engine, max_spend=1000.0)

        verdict = engine.verify_action(
            _ROLE,
            "read",
            {"cost": 1.0, "risk_factors": {"pii_exposure": "yes"}},
        )
        assert verdict.level == "blocked"
        assert verdict.risk_factors is not None
        assert verdict.risk_factors["driving_factors"] == ["pii_exposure"]

    def test_new_factor_via_global_registry(self, engine: GovernanceEngine) -> None:
        _set_envelope(engine, max_spend=1000.0)
        try:
            GLOBAL_RISK_FACTOR_REGISTRY.register(
                RiskFactor("regulatory_hold", lambda ctx, v: "held")
            )
            verdict = engine.verify_action(
                _ROLE,
                "read",
                {"cost": 1.0, "risk_factors": {"regulatory_hold": "on"}},
            )
            assert verdict.level == "held"
        finally:
            GLOBAL_RISK_FACTOR_REGISTRY.unregister("regulatory_hold")


# ---------------------------------------------------------------------------
# Invariant 4 — the driving factors are recorded for audit
# ---------------------------------------------------------------------------


class TestInvariant4_Audit:
    def test_verdict_and_audit_details_record_factors(
        self, engine: GovernanceEngine
    ) -> None:
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(
            _ROLE,
            "deploy",
            {
                "cost": 0.0,
                "risk_factors": {
                    "reversibility": "irreversible",
                    "materiality": "critical",
                },
            },
        )
        assert verdict.level == "blocked"
        # Structured field on the verdict.
        rf = verdict.risk_factors
        assert rf is not None
        assert rf["combined_level"] == "blocked"
        assert rf["driving_factors"] == ["materiality"]
        assert rf["per_factor"] == {
            "reversibility": "held",
            "materiality": "blocked",
        }
        assert rf["factor_values"] == {
            "reversibility": "irreversible",
            "materiality": "critical",
        }
        # Mirrored in audit_details and round-trips through to_dict().
        assert verdict.audit_details["risk_factors"] == rf
        assert verdict.to_dict()["risk_factors"] == rf

    def test_reason_names_the_driving_factor(self, engine: GovernanceEngine) -> None:
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(
            _ROLE,
            "deploy",
            {"cost": 0.0, "risk_factors": {"reversibility": "irreversible"}},
        )
        assert "risk factor" in verdict.reason.lower()
        assert "reversibility" in verdict.reason


# ---------------------------------------------------------------------------
# Invariant 5 — malformed factor set fails closed
# ---------------------------------------------------------------------------


class TestInvariant5_FailClosed:
    def test_non_mapping_factors_blocked(self, engine: GovernanceEngine) -> None:
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(
            _ROLE, "read", {"cost": 1.0, "risk_factors": ["oops"]}
        )
        assert verdict.level == "blocked"
        assert "malformed" in verdict.reason.lower()

    def test_unknown_factor_name_blocked(self, engine: GovernanceEngine) -> None:
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(
            _ROLE,
            "read",
            {"cost": 1.0, "risk_factors": {"not_a_real_factor": "high"}},
        )
        assert verdict.level == "blocked"

    def test_unknown_token_blocked(self, engine: GovernanceEngine) -> None:
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(
            _ROLE,
            "read",
            {"cost": 1.0, "risk_factors": {"reversibility": "sometimes"}},
        )
        assert verdict.level == "blocked"

    def test_malformed_does_not_loosen_a_lower_base(
        self, engine: GovernanceEngine
    ) -> None:
        # Even when limit proximity alone would be auto_approved, malformed
        # factors escalate to blocked (fail-closed to maximal risk).
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(
            _ROLE,
            "read",
            {"cost": 0.0, "risk_factors": {"materiality": {"bad": "shape"}}},
        )
        assert verdict.level == "blocked"


# ---------------------------------------------------------------------------
# Invariant 6 — no risk_factors => byte-for-byte identical to before the seam
# ---------------------------------------------------------------------------


class TestInvariant6_BackwardCompat:
    @pytest.mark.regression
    @pytest.mark.parametrize(
        ("cost", "expected"),
        [
            (10.0, "auto_approved"),  # well within limit
            (90.0, "flagged"),  # within 20% of 100
            (150.0, "blocked"),  # exceeds max_spend=100
        ],
    )
    def test_limit_proximity_verdicts_unchanged(
        self, engine: GovernanceEngine, cost: float, expected: str
    ) -> None:
        _set_envelope(engine, max_spend=100.0)
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": cost})
        assert verdict.level == expected
        # No risk factors present -> the structured field stays None and the
        # audit_details carry no risk_factors key.
        assert verdict.risk_factors is None
        assert "risk_factors" not in verdict.audit_details

    @pytest.mark.regression
    def test_held_via_approval_threshold_unchanged(
        self, engine: GovernanceEngine
    ) -> None:
        _set_envelope(engine, max_spend=1000.0, approval_above=100.0)
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 500.0})
        assert verdict.level == "held"
        assert verdict.risk_factors is None

    @pytest.mark.regression
    def test_no_context_at_all_unchanged(self, engine: GovernanceEngine) -> None:
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(_ROLE, "read")
        assert verdict.level == "auto_approved"
        assert verdict.risk_factors is None

    @pytest.mark.regression
    def test_reason_string_unchanged_without_factors(
        self, engine: GovernanceEngine
    ) -> None:
        # The reason MUST NOT mention risk factors on the no-factor path.
        _set_envelope(engine, max_spend=1000.0)
        verdict = engine.verify_action(_ROLE, "read", {"cost": 10.0})
        assert "risk factor" not in verdict.reason.lower()
