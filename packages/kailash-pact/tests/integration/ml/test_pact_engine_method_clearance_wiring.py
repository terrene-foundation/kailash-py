# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: check_engine_method_clearance end-to-end.

Real GovernanceEngine, real compiled org, no mocks. Asserts:

1. ``promote_model("production")`` refused without clearance.
2. Same call succeeds WITH the required D/T/R dimensions.
3. ClearanceRequirement decorator enforces the gate at the method
   entry point (surface exercised end-to-end).
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.exceptions import PactError
from pact.examples.university.org import create_university_org
from pact.ml import (
    ClearanceDecision,
    ClearanceRequirement,
    MLGovernanceContext,
    check_engine_method_clearance,
)


@pytest.fixture
def engine() -> GovernanceEngine:
    compiled, _ = create_university_org()
    return GovernanceEngine(compiled, audit_chain=AuditChain(chain_id="test-pact-ml"))


def test_promote_denied_without_clearance(engine: GovernanceEngine) -> None:
    """Actor holding no D/T/R dimensions is refused a DTR-required promotion."""
    decision = check_engine_method_clearance(
        engine,
        tenant_id="tenant-alpha",
        actor_id="agent-unauth",
        engine_name="ClassificationEngine",
        method_name="promote",
        clearance_required="DTR",
        held_dimensions=(),  # actor holds nothing
    )

    assert isinstance(decision, ClearanceDecision)
    assert decision.cleared is False
    assert set(decision.missing_dimensions) == {"D", "T", "R"}
    assert decision.engine_name == "ClassificationEngine"
    assert decision.method_name == "promote"
    assert decision.tenant_id == "tenant-alpha"
    assert decision.actor_id == "agent-unauth"


def test_promote_cleared_with_full_dtr(engine: GovernanceEngine) -> None:
    """Actor holding D+T+R dimensions is cleared for DTR-required promotion."""
    decision = check_engine_method_clearance(
        engine,
        tenant_id="tenant-alpha",
        actor_id="agent-staff",
        engine_name="ClassificationEngine",
        method_name="promote",
        clearance_required="DTR",
        held_dimensions=("D", "T", "R"),
    )
    assert decision.cleared is True
    assert decision.missing_dimensions == ()


def test_promote_denied_with_partial_dtr(engine: GovernanceEngine) -> None:
    """Actor holding D only is refused for DTR-required promotion."""
    decision = check_engine_method_clearance(
        engine,
        tenant_id="tenant-alpha",
        actor_id="agent-partial",
        engine_name="ClassificationEngine",
        method_name="promote",
        clearance_required="DTR",
        held_dimensions=("D",),
    )
    assert decision.cleared is False
    assert set(decision.missing_dimensions) == {"T", "R"}


def test_single_dimension_clearance_cleared(engine: GovernanceEngine) -> None:
    """D-required request with an actor holding D is cleared."""
    decision = check_engine_method_clearance(
        engine,
        tenant_id="tenant-alpha",
        actor_id="agent-d",
        engine_name="ClassificationEngine",
        method_name="fit",
        clearance_required="D",
        held_dimensions=("D",),
    )
    assert decision.cleared is True


def test_audit_row_carries_tenant_and_engine_method(
    engine: GovernanceEngine,
) -> None:
    """Per spec §5: audit row has tenant_id + engine_name + method_name."""
    captured: list[dict[str, Any]] = []
    original = engine._emit_audit_unlocked

    def capture(action: str, details: dict[str, Any]) -> None:
        captured.append(dict(details))
        original(action, details)

    engine._emit_audit_unlocked = capture  # type: ignore[method-assign]

    check_engine_method_clearance(
        engine,
        tenant_id="tenant-omega",
        actor_id="agent-99",
        engine_name="RegressionEngine",
        method_name="rollback",
        clearance_required="DTR",
        held_dimensions=(),
        audit_correlation_id="kml-corr-777",
    )

    rows = [r for r in captured if r.get("method") == "check_engine_method_clearance"]
    assert len(rows) == 1
    row = rows[0]
    assert row["tenant_id"] == "tenant-omega"
    assert row["engine_name"] == "RegressionEngine"
    assert row["method_name"] == "rollback"
    assert row["admitted_or_cleared"] == 0
    assert row["audit_correlation_id"] == "kml-corr-777"


# --- ClearanceRequirement decorator wiring test ---


class _EngineHarness:
    """Minimal harness that simulates a MLEngine using ClearanceRequirement.

    This is NOT a mock: it is a real class whose ``promote`` method is
    decorated with :class:`ClearanceRequirement`. Calling it triggers the
    real clearance check against the real engine.
    """

    def __init__(self, engine: GovernanceEngine) -> None:
        self.governance_engine = engine
        self.promoted: list[str] = []

    @ClearanceRequirement("DTR", method_name="promote")
    def promote(self, model_id: str, *, ml_context: MLGovernanceContext) -> str:
        self.promoted.append(model_id)
        return f"promoted:{model_id}"


def test_decorator_enforces_clearance_on_promote(engine: GovernanceEngine) -> None:
    """Decorator refuses when actor lacks DTR; succeeds when they hold it."""
    harness = _EngineHarness(engine)

    # Without clearance -> PactError raised, method body not invoked.
    ctx_no_clearance = MLGovernanceContext(
        tenant_id="tenant-alpha", actor_id="agent-u", held_dimensions=()
    )
    with pytest.raises(PactError, match="clearance denied"):
        harness.promote("model-v1", ml_context=ctx_no_clearance)
    assert harness.promoted == []

    # With clearance -> method body runs.
    ctx_full = MLGovernanceContext(
        tenant_id="tenant-alpha",
        actor_id="agent-s",
        held_dimensions=("D", "T", "R"),
    )
    result = harness.promote("model-v1", ml_context=ctx_full)
    assert result == "promoted:model-v1"
    assert harness.promoted == ["model-v1"]


def test_decorator_requires_ml_context(engine: GovernanceEngine) -> None:
    """Missing ml_context raises PactError per rules/security.md."""
    harness = _EngineHarness(engine)
    with pytest.raises(PactError, match="ml_context"):
        harness.promote("model-v1")  # type: ignore[call-arg]
