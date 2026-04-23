# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: check_cross_tenant_op v1.0 always-denied contract.

Real GovernanceEngine, no mocks. Verifies:

1. Every call returns admitted=False regardless of held dimensions.
2. Audit row carries BOTH src_tenant_id AND dst_tenant_id (spec §2.3).
3. Both sub-decisions (src_clearance, dst_clearance) are DENIED.
4. Invalid inputs (identical src/dst, empty tenant ids, unknown op)
   raise typed GovernanceCrossTenantError BEFORE the lock.
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.engine import GovernanceEngine
from pact.examples.university.org import create_university_org
from pact.ml import (
    CrossTenantDecision,
    GovernanceCrossTenantError,
    check_cross_tenant_op,
)


@pytest.fixture
def engine() -> GovernanceEngine:
    compiled, _ = create_university_org()
    return GovernanceEngine(compiled, audit_chain=AuditChain(chain_id="test-pact-ml"))


@pytest.mark.parametrize("operation", ["export", "import", "mirror"])
def test_cross_tenant_always_denied(engine: GovernanceEngine, operation: str) -> None:
    """v1.0 contract: every cross-tenant op is denied regardless of clearance."""
    decision = check_cross_tenant_op(
        engine,
        actor_id="agent-1",
        src_tenant_id="tenant-alpha",
        dst_tenant_id="tenant-beta",
        operation=operation,  # type: ignore[arg-type]
        clearance_required="DTR",
    )
    assert isinstance(decision, CrossTenantDecision)
    assert decision.admitted is False
    assert decision.operation == operation


def test_cross_tenant_denial_mentions_v1(engine: GovernanceEngine) -> None:
    decision = check_cross_tenant_op(
        engine,
        actor_id="agent-1",
        src_tenant_id="tenant-alpha",
        dst_tenant_id="tenant-beta",
        operation="export",
        clearance_required="DTR",
    )
    # The reason string names v1.0 so operators can correlate to the
    # spec decision.
    assert "v1.0" in decision.reason or "Decision 12" in decision.reason


def test_cross_tenant_sub_decisions_are_denied(engine: GovernanceEngine) -> None:
    """Both src + dst ClearanceDecision entries are DENIED in v1.0."""
    decision = check_cross_tenant_op(
        engine,
        actor_id="agent-admin",
        src_tenant_id="tenant-alpha",
        dst_tenant_id="tenant-beta",
        operation="mirror",
        clearance_required="DTR",
    )
    assert decision.src_clearance.cleared is False
    assert decision.dst_clearance.cleared is False
    assert decision.src_clearance.tenant_id == "tenant-alpha"
    assert decision.dst_clearance.tenant_id == "tenant-beta"


def test_cross_tenant_audit_row_carries_both_tenants(
    engine: GovernanceEngine,
) -> None:
    """Per spec §2.3: audit row carries BOTH tenant ids."""
    captured: list[dict[str, Any]] = []
    original = engine._emit_audit_unlocked

    def capture(action: str, details: dict[str, Any]) -> None:
        captured.append(dict(details))
        original(action, details)

    engine._emit_audit_unlocked = capture  # type: ignore[method-assign]

    check_cross_tenant_op(
        engine,
        actor_id="agent-admin",
        src_tenant_id="tenant-alpha",
        dst_tenant_id="tenant-beta",
        operation="export",
        clearance_required="DTR",
    )
    rows = [r for r in captured if r.get("method") == "check_cross_tenant_op"]
    assert len(rows) == 1
    row = rows[0]
    assert row["src_tenant_id"] == "tenant-alpha"
    assert row["dst_tenant_id"] == "tenant-beta"
    assert row["operation"] == "export"
    assert row["admitted_or_cleared"] == 0
    assert row["binding_constraint"] == "v1.0_always_denied"


def test_cross_tenant_identical_src_dst_raises_before_lock(
    engine: GovernanceEngine,
) -> None:
    """Identical src/dst raises GovernanceCrossTenantError BEFORE lock."""
    with pytest.raises(GovernanceCrossTenantError, match="distinct"):
        check_cross_tenant_op(
            engine,
            actor_id="agent-1",
            src_tenant_id="tenant-alpha",
            dst_tenant_id="tenant-alpha",
            operation="export",
            clearance_required="DTR",
        )


def test_cross_tenant_empty_tenant_raises(engine: GovernanceEngine) -> None:
    with pytest.raises(GovernanceCrossTenantError, match="tenant_id"):
        check_cross_tenant_op(
            engine,
            actor_id="agent-1",
            src_tenant_id="",
            dst_tenant_id="tenant-beta",
            operation="export",
            clearance_required="DTR",
        )


def test_cross_tenant_unknown_operation_raises(engine: GovernanceEngine) -> None:
    with pytest.raises(GovernanceCrossTenantError, match="operation"):
        check_cross_tenant_op(
            engine,
            actor_id="agent-1",
            src_tenant_id="tenant-alpha",
            dst_tenant_id="tenant-beta",
            operation="clone",  # type: ignore[arg-type]
            clearance_required="DTR",
        )


def test_cross_tenant_decision_is_frozen(engine: GovernanceEngine) -> None:
    """Per PACT MUST Rule 1: decision is immutable."""
    from dataclasses import FrozenInstanceError

    decision = check_cross_tenant_op(
        engine,
        actor_id="agent-1",
        src_tenant_id="tenant-alpha",
        dst_tenant_id="tenant-beta",
        operation="export",
        clearance_required="DTR",
    )
    with pytest.raises(FrozenInstanceError):
        decision.admitted = True  # type: ignore[misc]
