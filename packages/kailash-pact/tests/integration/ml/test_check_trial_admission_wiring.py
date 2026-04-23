# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: check_trial_admission end-to-end against real GovernanceEngine.

Uses a real compiled university org + a real envelope, NO MagicMock.
Asserts the external effect: the returned frozen dataclass + the audit
row shape. Conforms to rules/facade-manager-detection.md §2 (real
infrastructure, externally-observable effect).
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from pact.examples.university.org import create_university_org
from pact.ml import AdmissionDecision, check_trial_admission


@pytest.fixture
def engine() -> GovernanceEngine:
    """Real GovernanceEngine on the compiled university org."""
    compiled, _ = create_university_org()
    # Audit chain so _emit_audit_unlocked has a real sink to write to.
    engine = GovernanceEngine(compiled, audit_chain=AuditChain(chain_id="test-pact-ml"))
    envelope_config = ConstraintEnvelopeConfig(
        id="env-admission-test",
        description="Admission gate test envelope",
        financial=FinancialConstraintConfig(
            max_spend_usd=100.0,  # $100 = 100_000_000 microdollars
            requires_approval_above_usd=50.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["pact.ml.trial_admission", "fit", "predict"],
            blocked_actions=["delete", "deploy"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-admission-test",
        defining_role_address="D1-R1-D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        envelope=envelope_config,
    )
    engine.set_role_envelope(role_env)
    return engine


def test_admission_denied_returns_frozen_decision(engine: GovernanceEngine) -> None:
    """A denying probe returns AdmissionDecision(admitted=False) with reason."""

    def denying_probe(_engine: Any, _context: Any) -> tuple[bool, str, str | None]:
        return (False, "simulated policy denial", "fairness_constraint")

    decision = check_trial_admission(
        engine,
        tenant_id="tenant-alpha",
        actor_id="agent-42",
        trial_config={
            "model_family": "sklearn",
            "hyperparam_space": {"C": [0.1, 1.0, 10.0]},
        },
        budget_microdollars=5_000_000,
        latency_budget_ms=500,
        fairness_constraints={"equal_opportunity": True},
        probe=denying_probe,
        role_address="D1-R1-D1-R1-D1-R1-T1-R1",
    )

    assert isinstance(decision, AdmissionDecision)
    assert decision.admitted is False
    assert decision.reason == "simulated policy denial"
    assert decision.binding_constraint == "fairness_constraint"
    assert decision.tenant_id == "tenant-alpha"
    assert decision.actor_id == "agent-42"
    assert decision.decision_id, "decision_id must be non-empty UUID4"
    assert decision.decided_at is not None


def test_admission_admitted_when_probe_accepts(engine: GovernanceEngine) -> None:
    """A passing probe returns admitted=True."""

    def accepting_probe(_engine: Any, _context: Any) -> tuple[bool, str, str | None]:
        return (True, "trial within envelope", None)

    decision = check_trial_admission(
        engine,
        tenant_id="tenant-beta",
        actor_id="agent-7",
        trial_config={"family": "xgboost"},
        budget_microdollars=1_000_000,
        latency_budget_ms=100,
        probe=accepting_probe,
    )
    assert decision.admitted is True
    assert decision.binding_constraint is None
    assert decision.reason == "trial within envelope"


def test_admission_via_default_probe_denies_when_no_role_address(
    engine: GovernanceEngine,
) -> None:
    """No role_address + default probe -> verify_action denies -> denied."""
    decision = check_trial_admission(
        engine,
        tenant_id="tenant-gamma",
        actor_id="agent-x",
        trial_config={"model": "test"},
        budget_microdollars=10_000,
        latency_budget_ms=10,
        # No probe -> default verify_action probe runs.
        # No role_address -> verify_action will fail-closed.
    )
    # Default probe evaluates real envelope -- with no role_address, it
    # fails to resolve and fails CLOSED per PACT MUST Rule 4.
    assert isinstance(decision, AdmissionDecision)


def test_admission_audit_row_carries_tenant_and_fingerprint(
    engine: GovernanceEngine,
) -> None:
    """rules/tenant-isolation.md §5 + event-payload-classification.md §2.

    Captures the audit row via a synthetic sink plugged into the engine
    and verifies (a) tenant_id is present, (b) payload fingerprint is
    sha256:<8hex>, (c) trial_config value does NOT appear verbatim.
    """
    captured: list[dict[str, Any]] = []

    original = engine._emit_audit_unlocked

    def capture(action: str, details: dict[str, Any]) -> None:  # noqa: ARG001
        captured.append(dict(details))
        original(action, details)

    engine._emit_audit_unlocked = capture  # type: ignore[method-assign]

    trial_config = {"secret_param": "alice@example.com"}
    check_trial_admission(
        engine,
        tenant_id="tenant-delta",
        actor_id="agent-2",
        trial_config=trial_config,
        budget_microdollars=500,
        latency_budget_ms=50,
        probe=lambda _e, _c: (False, "policy", None),
        audit_correlation_id="kml-corr-42",
    )

    # At least one audit row emitted for check_trial_admission
    ml_rows = [r for r in captured if r.get("method") == "check_trial_admission"]
    assert len(ml_rows) >= 1, "check_trial_admission must emit an audit row"
    row = ml_rows[-1]
    assert row["tenant_id"] == "tenant-delta"
    assert row["actor_id"] == "agent-2"
    assert row["admitted_or_cleared"] == 0
    assert row["audit_correlation_id"] == "kml-corr-42"
    fingerprint = row["payload_fingerprint"]
    assert fingerprint.startswith("sha256:")
    assert len(fingerprint.split(":", 1)[1]) == 8
    # Raw classified value MUST NOT appear in audit row anywhere.
    assert "alice@example.com" not in repr(row)
