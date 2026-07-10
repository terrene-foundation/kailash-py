# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Engine-integration tests for the confidence/evidence-quality gate (#1516 leg b).

These exercise ``GovernanceEngine.verify_action`` end-to-end and pin the 4
load-bearing invariants of wiring an evidence-quality disposition input into the
verdict path, composed MONOTONICALLY via ``combine_levels`` alongside the merged
risk-factor seam (#1514) and rate-limit step (#1516-a):

1. An action whose ``ctx["confidence"]`` is BELOW the configured threshold is
   escalated to ``held`` (human review) REGARDLESS of value / limit-proximity --
   even an otherwise-``auto_approved`` action. Composed via ``combine_levels`` so
   it can only TIGHTEN, never de-escalate.
2. A configured threshold with confidence ABSENT fails CLOSED to ``held`` (never
   a silent pass) -- pact-governance.md Rule 4 / zero-tolerance Rule 3.
3. A NaN / Inf / out-of-[0,1] / non-numeric confidence fails CLOSED to ``held``
   (math.isfinite + range guard) -- pact-governance.md Rule 6.
4. The confidence value + the fact it drove the verdict are recorded in the
   audit trail (``verdict.audit_details["confidence"]``).

Backward-compat: an engine with NO confidence config configured behaves EXACTLY
as before -- ``ctx["confidence"]`` is ignored and the audit trail carries no
``confidence`` key.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest

from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    ConfidenceThresholdConfig,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.store import MemoryAccessPolicyStore, MemoryClearanceStore
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

_ROLE = "D1-R1-D1-R1-D1-R1-T1-R1"  # CS Chair
_DEFINER = "D1-R1-D1-R1-D1-R1"  # Dean

# A factory that builds a fresh engine with an optional confidence config.
EngineFactory = Callable[[ConfidenceThresholdConfig | None], GovernanceEngine]


# ---------------------------------------------------------------------------
# Fixtures (mirror test_engine_rate_limit.py)
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
def engine_factory(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> EngineFactory:
    """Return a builder that stamps out engines with a given confidence config."""

    def _build(
        confidence_config: ConfidenceThresholdConfig | None = None,
    ) -> GovernanceEngine:
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
            confidence_threshold_config=confidence_config,
        )

    return _build


def _set_envelope(
    engine: GovernanceEngine,
    *,
    max_spend: float = 10_000.0,
    approval_above: float | None = None,
    allowed: list[str] | None = None,
) -> None:
    """Attach an envelope that AUTO-APPROVES a cheap in-list action, so the only
    thing that can escalate the verdict is the confidence gate under test."""
    envelope = ConstraintEnvelopeConfig(
        id="env-conf-test",
        description="confidence-threshold test envelope",
        financial=FinancialConstraintConfig(
            max_spend_usd=max_spend, requires_approval_above_usd=approval_above
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=allowed or ["read", "write", "deploy", "delete"],
        ),
    )
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-conf-test",
            defining_role_address=_DEFINER,
            target_role_address=_ROLE,
            envelope=envelope,
        )
    )


# ---------------------------------------------------------------------------
# Invariant 1 -- below-threshold confidence -> held, regardless of value
# ---------------------------------------------------------------------------


class TestInvariant1_BelowThresholdHeld:
    def test_below_threshold_escalates_auto_approved_to_held(
        self, engine_factory: EngineFactory
    ) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        # A cheap, in-limit, allowed action -> base verdict is auto_approved.
        # Low confidence escalates it to held REGARDLESS of the cheap cost.
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.5})
        assert verdict.level == "held"
        assert "below the required threshold" in verdict.reason

    def test_at_or_above_threshold_passes(self, engine_factory: EngineFactory) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        # confidence == threshold is NOT below -> passes.
        assert (
            engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.7}).level
            == "auto_approved"
        )
        assert (
            engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.99}).level
            == "auto_approved"
        )

    def test_held_regardless_of_high_value_in_limit(
        self, engine_factory: EngineFactory
    ) -> None:
        # Even a high-but-in-limit spend (which alone would only FLAG, near the
        # 80% boundary) is escalated to HELD by low confidence -- confidence is
        # orthogonal to value.
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.8))
        _set_envelope(engine, max_spend=100.0)
        verdict = engine.verify_action(
            _ROLE, "write", {"cost": 90.0, "confidence": 0.4}
        )
        # combine_levels(flagged, held) == held -- confidence tightens further.
        assert verdict.level == "held"

    def test_per_action_override_beats_default(
        self, engine_factory: EngineFactory
    ) -> None:
        engine = engine_factory(
            ConfidenceThresholdConfig(
                default_threshold=0.7, per_action={"deploy": 0.95}
            )
        )
        _set_envelope(engine)
        # 0.9 clears the 0.7 default for "read" ...
        assert (
            engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.9}).level
            == "auto_approved"
        )
        # ... but is BELOW the 0.95 override for "deploy" -> held.
        assert (
            engine.verify_action(
                _ROLE, "deploy", {"cost": 1.0, "confidence": 0.9}
            ).level
            == "held"
        )

    def test_gate_runs_even_with_no_envelope(
        self, engine_factory: EngineFactory
    ) -> None:
        # No envelope set for this role -> the base verdict is auto_approved,
        # yet the confidence gate (intrinsic to the action) still escalates it.
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        verdict = engine.verify_action(_ROLE, "read", {"confidence": 0.2})
        assert verdict.level == "held"


# ---------------------------------------------------------------------------
# Invariant 2 -- threshold set + confidence ABSENT -> held (fail-closed)
# ---------------------------------------------------------------------------


class TestInvariant2_MissingFailsClosed:
    def test_absent_confidence_key_is_held(self, engine_factory: EngineFactory) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        # ctx carries NO confidence key at all -> fail-closed to held.
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0})
        assert verdict.level == "held"
        assert "absent" in verdict.reason
        assert verdict.audit_details["confidence"]["reason"] == "missing"

    def test_explicit_none_confidence_is_held(
        self, engine_factory: EngineFactory
    ) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": None})
        assert verdict.level == "held"


# ---------------------------------------------------------------------------
# Invariant 3 -- NaN / Inf / out-of-range / non-numeric -> fail-closed
# ---------------------------------------------------------------------------


class TestInvariant3_InvalidFailsClosed:
    @pytest.mark.parametrize(
        "bad",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
            1.5,  # above 1.0
            -0.1,  # below 0.0
            2.0,
        ],
    )
    def test_nan_inf_out_of_range_is_held(
        self, engine_factory: EngineFactory, bad: float
    ) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": bad})
        assert verdict.level == "held", f"{bad!r} must fail closed to held"
        # A non-finite value must NOT be stored raw in the audit dict.
        recorded = verdict.audit_details["confidence"].get("value")
        assert recorded is None or math.isfinite(recorded)

    def test_non_numeric_confidence_is_held(
        self, engine_factory: EngineFactory
    ) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        verdict = engine.verify_action(
            _ROLE, "read", {"cost": 1.0, "confidence": "high"}
        )
        assert verdict.level == "held"
        assert verdict.audit_details["confidence"]["reason"] == "non_numeric"

    def test_nan_config_threshold_is_rejected_at_construction(self) -> None:
        # A NaN threshold cannot even be constructed (Rule 6 finite guard).
        with pytest.raises(ValueError):
            ConfidenceThresholdConfig(default_threshold=float("nan"))
        with pytest.raises(ValueError):
            ConfidenceThresholdConfig(per_action={"deploy": float("inf")})
        with pytest.raises(ValueError):
            ConfidenceThresholdConfig(per_action={"deploy": 1.5})


# ---------------------------------------------------------------------------
# Invariant 4 -- confidence + drove-the-verdict recorded in the audit trail
# ---------------------------------------------------------------------------


class TestInvariant4_Audited:
    def test_below_threshold_recorded_and_escalated(
        self, engine_factory: EngineFactory
    ) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.3})
        conf = verdict.audit_details["confidence"]
        assert conf["value"] == 0.3
        assert conf["threshold"] == 0.7
        assert conf["below_threshold"] is True
        assert conf["escalated"] is True

    def test_above_threshold_recorded_not_escalated(
        self, engine_factory: EngineFactory
    ) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine)
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.9})
        conf = verdict.audit_details["confidence"]
        assert conf["value"] == 0.9
        assert conf["below_threshold"] is False
        assert conf["escalated"] is False


# ---------------------------------------------------------------------------
# Monotonic composition -- the gate only TIGHTENS, never de-escalates
# ---------------------------------------------------------------------------


class TestMonotonicComposition:
    def test_low_confidence_never_deescalates_a_blocked_base(
        self, engine_factory: EngineFactory
    ) -> None:
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        # "delete" is NOT in the allowed list -> base verdict is blocked.
        _set_envelope(engine, allowed=["read"])
        # Even a high OR a low confidence must leave the blocked verdict blocked
        # (the gate can only tighten; blocked is already max-severity).
        assert (
            engine.verify_action(
                _ROLE, "delete", {"cost": 1.0, "confidence": 0.9}
            ).level
            == "blocked"
        )
        assert (
            engine.verify_action(
                _ROLE, "delete", {"cost": 1.0, "confidence": 0.1}
            ).level
            == "blocked"
        )

    def test_high_confidence_does_not_relax_a_held_base(
        self, engine_factory: EngineFactory
    ) -> None:
        # Base verdict is held via the financial approval threshold; a HIGH
        # confidence must NOT relax it back to auto_approved.
        engine = engine_factory(ConfidenceThresholdConfig(default_threshold=0.7))
        _set_envelope(engine, max_spend=1000.0, approval_above=100.0)
        verdict = engine.verify_action(
            _ROLE, "deploy", {"cost": 500.0, "confidence": 0.99}
        )
        assert verdict.level == "held"


# ---------------------------------------------------------------------------
# Backward-compat -- no threshold configured -> confidence ignored
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_no_config_ignores_confidence(self, engine_factory: EngineFactory) -> None:
        # confidence_config=None -> gate inactive.
        engine = engine_factory(None)
        _set_envelope(engine)
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.01})
        assert verdict.level == "auto_approved"
        # Audit trail is byte-unchanged: no confidence key.
        assert "confidence" not in verdict.audit_details

    def test_empty_config_ignores_confidence(
        self, engine_factory: EngineFactory
    ) -> None:
        # A config with no default and no per_action -> gate inactive for every
        # action (threshold_for returns None).
        engine = engine_factory(ConfidenceThresholdConfig())
        _set_envelope(engine)
        verdict = engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.01})
        assert verdict.level == "auto_approved"
        assert "confidence" not in verdict.audit_details

    def test_unlisted_action_with_no_default_ignored(
        self, engine_factory: EngineFactory
    ) -> None:
        # per_action gates only "deploy"; "read" has no default -> ignored.
        engine = engine_factory(ConfidenceThresholdConfig(per_action={"deploy": 0.9}))
        _set_envelope(engine)
        assert (
            engine.verify_action(_ROLE, "read", {"cost": 1.0, "confidence": 0.01}).level
            == "auto_approved"
        )
        # But "deploy" IS gated.
        assert (
            engine.verify_action(
                _ROLE, "deploy", {"cost": 1.0, "confidence": 0.01}
            ).level
            == "held"
        )
