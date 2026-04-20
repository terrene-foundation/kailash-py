# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tier 2 integration tests for PR#7 absorbed governance capabilities (#567).

Unlike the Tier 1 unit tests, these exercise the ABSORBED capabilities
through the FACADE (the real ``PactEngine``) against a real
``GovernanceEngine`` + real in-memory ``AuditChain``. Each test asserts
an externally-observable effect — the MUST Rule 2 contract of
``facade-manager-detection.md``.

We do NOT mock:
- The ``AuditChain`` (real ``kailash.trust.pact.audit.AuditChain``)
- The ``GovernanceEngine`` (real; org-YAML compiled)
- The ``CostTracker`` (real; per-entry append)

What each test proves:
- ``test_verify_audit_chain_end_to_end``: writing entries via normal
  append produces a valid verification result through the facade.
- ``test_envelope_snapshot_through_engine``: the role envelope computed
  through the engine round-trips into a snapshot that carries the
  resolved envelope fields.
- ``test_consumption_report_filters_envelope_id``: a tracker populated
  via ``record()`` returns a correctly-filtered report through the
  facade.
- ``test_iter_audit_anchors_end_to_end_with_tenant_filter``: tenant
  metadata persisted on append is visible to the iterator.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.config import VerificationLevel

from pact.costs import CostTracker
from pact.engine import PactEngine

FIXTURES_DIR = Path(__file__).parent.parent.parent / "unit" / "governance" / "fixtures"
MINIMAL_ORG = FIXTURES_DIR / "minimal-org.yaml"


@pytest.fixture
def engine() -> PactEngine:
    """Real PactEngine + real AuditChain wired onto the governance engine."""
    eng = PactEngine(org=str(MINIMAL_ORG))
    eng._governance._audit_chain = AuditChain(chain_id="test-wiring-chain")
    return eng


# ---------------------------------------------------------------------------
# Integration: verify_audit_chain end-to-end
# ---------------------------------------------------------------------------


def test_verify_audit_chain_end_to_end(engine: PactEngine) -> None:
    """Write 3 anchors via the chain, then verify through the facade."""
    chain = engine._governance.audit_chain
    assert chain is not None, "fixture wires the chain"

    for agent in ("alice", "bob", "carol"):
        chain.append(
            agent_id=agent,
            action="submit",
            verification_level=VerificationLevel.AUTO_APPROVED,
        )

    result = asyncio.run(engine.verify_audit_chain())
    assert result.is_valid is True
    assert result.verified_count == 3
    assert result.first_break_reason is None
    assert result.chain_id == "test-wiring-chain"


def test_verify_audit_chain_tampered_mid_chain(engine: PactEngine) -> None:
    """A mid-chain tamper is detected end-to-end, fail-closed, no raise."""
    chain = engine._governance.audit_chain
    assert chain is not None
    for i in range(4):
        chain.append(
            agent_id=f"agent-{i}",
            action="submit",
            verification_level=VerificationLevel.AUTO_APPROVED,
        )
    # Tamper anchor #2 (middle of the chain).
    chain.anchors[2].content_hash = "f" * 64

    result = asyncio.run(engine.verify_audit_chain())
    # Fail-closed: never raises; carries the break details.
    assert result.is_valid is False
    assert result.first_break_reason is not None
    assert result.verified_count == 4


# ---------------------------------------------------------------------------
# Integration: envelope_snapshot through engine
# ---------------------------------------------------------------------------


def test_envelope_snapshot_through_engine_missing_role_raises_lookup(
    engine: PactEngine,
) -> None:
    """A role that resolves no envelope raises LookupError through the engine.

    The minimal-org fixture defines roles but no envelopes in the
    EnvelopeStore — snapshot-by-role_address raises LookupError, which
    is the correct fail-closed disposition.
    """
    with pytest.raises(LookupError):
        engine.envelope_snapshot(role_address="D1-R1")


def test_envelope_snapshot_lookup_error_on_unknown_envelope_id(
    engine: PactEngine,
) -> None:
    with pytest.raises(LookupError):
        engine.envelope_snapshot(envelope_id="does-not-exist")


# ---------------------------------------------------------------------------
# Integration: iter_audit_anchors with tenant filter
# ---------------------------------------------------------------------------


def test_iter_audit_anchors_end_to_end_with_tenant_filter(
    engine: PactEngine,
) -> None:
    """Tenant metadata persisted on append is respected by the iterator."""
    chain = engine._governance.audit_chain
    assert chain is not None

    chain.append(
        agent_id="alice",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
        metadata={"tenant_id": "tenant-A"},
    )
    chain.append(
        agent_id="bob",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
        metadata={"tenant_id": "tenant-B"},
    )
    chain.append(
        agent_id="carol",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
        metadata={"tenant_id": "tenant-A"},
    )

    a_anchors = list(engine.iter_audit_anchors(tenant_id="tenant-A"))
    assert len(a_anchors) == 2
    assert {a.agent_id for a in a_anchors} == {"alice", "carol"}

    b_anchors = list(engine.iter_audit_anchors(tenant_id="tenant-B"))
    assert len(b_anchors) == 1
    assert b_anchors[0].agent_id == "bob"


def test_iter_audit_anchors_limit_through_engine(engine: PactEngine) -> None:
    chain = engine._governance.audit_chain
    assert chain is not None
    for i in range(7):
        chain.append(
            agent_id=f"agent-{i}",
            action="submit",
            verification_level=VerificationLevel.AUTO_APPROVED,
        )
    out = list(engine.iter_audit_anchors(limit=4))
    assert len(out) == 4


# ---------------------------------------------------------------------------
# Integration: consumption_report via CostTracker.record
# ---------------------------------------------------------------------------


def test_consumption_report_filters_envelope_id() -> None:
    """End-to-end: record 5 entries across 2 envelopes, filter returns subset."""
    tracker = CostTracker(budget_usd=100.0)
    tracker.record(1.00, "a", envelope_id="env-A", agent_id="role-1")
    tracker.record(2.00, "b", envelope_id="env-A", agent_id="role-1")
    tracker.record(0.50, "c", envelope_id="env-B", agent_id="role-2")
    tracker.record(0.25, "d", envelope_id="env-B", agent_id="role-2")
    tracker.record(4.00, "e", envelope_id="env-A", agent_id="role-3")

    report_a = tracker.consumption_report(envelope_id="env-A")
    # 1.00 + 2.00 + 4.00 = 7.00 USD
    assert report_a.entries == 3
    assert report_a.total_microdollars == 7_000_000
    assert pytest.approx(report_a.total_usd) == 7.00
    assert set(report_a.per_agent.keys()) == {"role-1", "role-3"}
    assert report_a.per_agent["role-1"] == 3_000_000
    assert report_a.per_agent["role-3"] == 4_000_000

    report_b = tracker.consumption_report(envelope_id="env-B")
    assert report_b.entries == 2
    assert report_b.total_microdollars == 750_000


def test_consumption_report_end_to_end_totals() -> None:
    """The grand total equals the sum of all entries."""
    tracker = CostTracker()
    for i in range(1, 11):
        tracker.record(float(i), f"desc-{i}", envelope_id="env-x", agent_id="role-x")
    report = tracker.consumption_report()
    # 1 + 2 + ... + 10 = 55
    assert report.entries == 10
    assert report.total_microdollars == 55_000_000
