# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tier 1 unit tests for the PR#7 absorbed governance capabilities (#567).

Exercises the five first-class methods that replace the rejected MLFP
`GovernanceDiagnostics`:

- PactEngine.verify_audit_chain(...)
- PactEngine.envelope_snapshot(...)
- PactEngine.iter_audit_anchors(...)
- CostTracker.consumption_report(...)
- pact.governance.testing.run_negative_drills(...)

Focus areas per PACT MUST rules:
- Lock acquisition (MUST Rule 8) — verified behaviourally + via mock.
- Frozen results (MUST Rule 1) — verified via dataclass frozen=True.
- Fail-closed on chain break (MUST Rule 4) — verified by tampering.
- Fail-CLOSED drill semantics — exception != pass, no-raise != pass.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from kailash.trust.pact.config import VerificationLevel
from pact.costs import CostTracker
from pact.engine import PactEngine, GovernanceHeldError
from pact.governance.results import (
    ChainVerificationResult,
    ConsumptionReport,
    EnvelopeSnapshot,
    NegativeDrillResult,
)
from pact.governance.testing import NegativeDrill, run_negative_drills

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MINIMAL_ORG = FIXTURES_DIR / "minimal-org.yaml"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> PactEngine:
    """A real in-memory PactEngine on the minimal-org fixture.

    Wires a real ``AuditChain`` onto the underlying ``GovernanceEngine``
    so the chain-integrity / iter-anchors tests have real state to
    verify. The MinimalOrg fixture is intentionally bare — a production
    engine wires the chain via the trust-plane store layer; for unit
    tests we attach it directly.
    """
    from kailash.trust.pact.audit import AuditChain

    eng = PactEngine(org=str(MINIMAL_ORG))
    eng._governance._audit_chain = AuditChain(
        chain_id=f"test-chain-{eng._governance.org_name}"
    )
    return eng


# ---------------------------------------------------------------------------
# verify_audit_chain — Tier 1
# ---------------------------------------------------------------------------


def test_verify_audit_chain_empty_returns_valid(engine: PactEngine) -> None:
    """An empty / absent chain verifies as valid with zero anchors."""
    result = asyncio.run(engine.verify_audit_chain())
    assert isinstance(result, ChainVerificationResult)
    assert result.is_valid is True
    assert result.verified_count == 0
    assert result.first_break_reason is None
    assert result.first_break_sequence is None


def test_verify_audit_chain_with_appended_anchors_valid(engine: PactEngine) -> None:
    """A clean chain with several anchors verifies valid."""
    chain = engine._governance.audit_chain
    if chain is None:
        pytest.skip("minimal-org does not wire an audit chain in this setup")
    chain.append(
        agent_id="alice",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
    )
    chain.append(
        agent_id="bob",
        action="submit",
        verification_level=VerificationLevel.FLAGGED,
    )
    result = asyncio.run(engine.verify_audit_chain())
    assert result.is_valid is True
    assert result.verified_count == 2
    assert result.first_break_reason is None


def test_verify_audit_chain_detects_break_returns_is_valid_false(
    engine: PactEngine,
) -> None:
    """Tampering with an anchor's content_hash produces fail-closed result."""
    chain = engine._governance.audit_chain
    if chain is None:
        pytest.skip("minimal-org does not wire an audit chain in this setup")
    chain.append(
        agent_id="alice",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
    )
    chain.append(
        agent_id="bob",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
    )
    # Tamper with the second anchor's hash — content no longer matches.
    chain.anchors[1].content_hash = "0" * 64

    result = asyncio.run(engine.verify_audit_chain())
    assert result.is_valid is False
    assert result.first_break_reason is not None
    assert result.first_break_sequence is not None


def test_verify_audit_chain_respects_tenant_filter(engine: PactEngine) -> None:
    """tenant_id filter excludes anchors whose metadata tenant mismatches."""
    chain = engine._governance.audit_chain
    if chain is None:
        pytest.skip("minimal-org does not wire an audit chain in this setup")
    chain.append(
        agent_id="alice",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
        metadata={"tenant_id": "tenant-A"},
    )
    chain.append(
        agent_id="alice",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
        metadata={"tenant_id": "tenant-B"},
    )

    result_a = asyncio.run(engine.verify_audit_chain(tenant_id="tenant-A"))
    assert result_a.verified_count == 1
    assert result_a.tenant_id == "tenant-A"

    result_b = asyncio.run(engine.verify_audit_chain(tenant_id="tenant-B"))
    assert result_b.verified_count == 1

    result_none = asyncio.run(engine.verify_audit_chain(tenant_id="tenant-C"))
    assert result_none.verified_count == 0


def test_verify_audit_chain_result_is_frozen() -> None:
    """ChainVerificationResult is a frozen dataclass (PACT MUST Rule 1)."""
    result = ChainVerificationResult(is_valid=True, verified_count=0)
    with pytest.raises(Exception):  # FrozenInstanceError
        result.is_valid = False  # type: ignore[misc]


def test_verify_audit_chain_acquires_submit_lock(engine: PactEngine) -> None:
    """verify_audit_chain must acquire self._submit_lock (PACT MUST Rule 8).

    Replaces the engine's submit lock with a counting proxy since
    asyncio.Lock's dunder methods can't be monkey-patched directly.
    """

    class _CountingAsyncLock:
        def __init__(self, inner: asyncio.Lock) -> None:
            self._inner = inner
            self.enter_count = 0

        async def __aenter__(self):
            self.enter_count += 1
            return await self._inner.__aenter__()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return await self._inner.__aexit__(exc_type, exc_val, exc_tb)

    original = engine._submit_lock
    proxy = _CountingAsyncLock(original)
    engine._submit_lock = proxy  # type: ignore[assignment]
    try:
        asyncio.run(engine.verify_audit_chain())
    finally:
        engine._submit_lock = original  # type: ignore[assignment]
    assert proxy.enter_count >= 1


# ---------------------------------------------------------------------------
# envelope_snapshot — Tier 1
# ---------------------------------------------------------------------------


def test_envelope_snapshot_requires_exactly_one_selector(engine: PactEngine) -> None:
    """Exactly one of envelope_id or role_address must be provided."""
    with pytest.raises(ValueError, match="exactly one"):
        engine.envelope_snapshot()  # neither
    with pytest.raises(ValueError, match="exactly one"):
        engine.envelope_snapshot(envelope_id="x", role_address="y")  # both


def test_envelope_snapshot_role_address_missing_raises_lookup(
    engine: PactEngine,
) -> None:
    """A role_address with no envelope resolved raises LookupError."""
    with pytest.raises(LookupError):
        engine.envelope_snapshot(role_address="does-not-exist")


def test_envelope_snapshot_envelope_id_missing_raises_lookup(
    engine: PactEngine,
) -> None:
    """An envelope_id that isn't defined anywhere raises LookupError."""
    with pytest.raises(LookupError):
        engine.envelope_snapshot(envelope_id="ghost-envelope")


def test_envelope_snapshot_shape() -> None:
    """EnvelopeSnapshot carries the documented frozen fields."""
    snap = EnvelopeSnapshot(
        envelope_id="env-1",
        role_address="D1-R1",
        resolved_at=datetime.now(timezone.utc),
        clearance={"confidentiality_level": "internal"},
        constraints={"financial": {"max_spend_usd": 10.0}},
        tenant_id="tenant-X",
    )
    with pytest.raises(Exception):
        snap.envelope_id = "env-2"  # type: ignore[misc]
    d = snap.to_dict()
    assert d["envelope_id"] == "env-1"
    assert d["role_address"] == "D1-R1"
    assert d["tenant_id"] == "tenant-X"


# ---------------------------------------------------------------------------
# iter_audit_anchors — Tier 1
# ---------------------------------------------------------------------------


def test_iter_audit_anchors_returns_empty_when_no_chain() -> None:
    """With no configured audit chain, iteration is empty."""
    engine = PactEngine(org=str(MINIMAL_ORG))
    # Force no chain for this test.
    engine._governance._audit_chain = None
    out = list(engine.iter_audit_anchors())
    assert out == []


def test_iter_audit_anchors_respects_limit(engine: PactEngine) -> None:
    """limit caps the number of anchors yielded."""
    chain = engine._governance.audit_chain
    if chain is None:
        pytest.skip("minimal-org does not wire an audit chain in this setup")
    for i in range(5):
        chain.append(
            agent_id=f"agent-{i}",
            action="submit",
            verification_level=VerificationLevel.AUTO_APPROVED,
        )
    out = list(engine.iter_audit_anchors(limit=3))
    assert len(out) == 3

    zero_out = list(engine.iter_audit_anchors(limit=0))
    assert zero_out == []


def test_iter_audit_anchors_rejects_negative_limit(engine: PactEngine) -> None:
    """limit must be non-negative."""
    with pytest.raises(ValueError, match="limit must be >= 0"):
        list(engine.iter_audit_anchors(limit=-1))


def test_iter_audit_anchors_time_range_filter(engine: PactEngine) -> None:
    """since / until bracket which anchors are yielded."""
    chain = engine._governance.audit_chain
    if chain is None:
        pytest.skip("minimal-org does not wire an audit chain in this setup")

    now = datetime.now(timezone.utc)
    a0 = chain.append(
        agent_id="old",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
    )
    a0.timestamp = now - timedelta(days=10)
    a1 = chain.append(
        agent_id="recent",
        action="submit",
        verification_level=VerificationLevel.AUTO_APPROVED,
    )
    a1.timestamp = now

    recent = list(engine.iter_audit_anchors(since=now - timedelta(hours=1)))
    assert len(recent) == 1
    assert recent[0].agent_id == "recent"


# ---------------------------------------------------------------------------
# CostTracker.consumption_report — Tier 1
# ---------------------------------------------------------------------------


def test_consumption_report_empty_returns_zero_totals() -> None:
    tracker = CostTracker(budget_usd=10.0)
    report = tracker.consumption_report()
    assert isinstance(report, ConsumptionReport)
    assert report.total_microdollars == 0
    assert report.entries == 0
    assert report.per_envelope == {}
    assert report.per_agent == {}


def test_consumption_report_totals() -> None:
    tracker = CostTracker(budget_usd=100.0)
    tracker.record(1.50, "first", envelope_id="env-A", agent_id="role-1")
    tracker.record(2.25, "second", envelope_id="env-A", agent_id="role-1")
    tracker.record(0.10, "third", envelope_id="env-B", agent_id="role-2")

    report = tracker.consumption_report()
    # 1.50 + 2.25 + 0.10 = 3.85 USD = 3_850_000 microdollars
    assert report.total_microdollars == 3_850_000
    assert pytest.approx(report.total_usd) == 3.85
    assert report.entries == 3


def test_consumption_report_per_agent_breakdown() -> None:
    tracker = CostTracker()
    tracker.record(1.0, "x", envelope_id="env-A", agent_id="role-1")
    tracker.record(2.0, "y", envelope_id="env-A", agent_id="role-2")
    tracker.record(3.0, "z", envelope_id="env-B", agent_id="role-1")

    report = tracker.consumption_report()
    assert report.per_agent["role-1"] == 4_000_000
    assert report.per_agent["role-2"] == 2_000_000
    assert report.per_envelope["env-A"] == 3_000_000
    assert report.per_envelope["env-B"] == 3_000_000


def test_consumption_report_filters_envelope_id() -> None:
    tracker = CostTracker()
    tracker.record(1.0, "x", envelope_id="env-A", agent_id="role-1")
    tracker.record(2.0, "y", envelope_id="env-B", agent_id="role-1")

    report = tracker.consumption_report(envelope_id="env-A")
    assert report.entries == 1
    assert report.total_microdollars == 1_000_000


def test_consumption_report_filters_agent_id() -> None:
    tracker = CostTracker()
    tracker.record(1.0, "x", envelope_id="env-A", agent_id="role-1")
    tracker.record(2.0, "y", envelope_id="env-A", agent_id="role-2")

    report = tracker.consumption_report(agent_id="role-2")
    assert report.entries == 1
    assert report.total_microdollars == 2_000_000


def test_consumption_report_filters_time_range() -> None:
    tracker = CostTracker()
    tracker.record(1.0, "x")
    tracker.record(2.0, "y")
    now = datetime.now(timezone.utc)

    # since in the future → no entries
    future = now + timedelta(days=1)
    r = tracker.consumption_report(since=future)
    assert r.entries == 0
    assert r.total_microdollars == 0

    # until in the past → no entries
    past = now - timedelta(days=365)
    r2 = tracker.consumption_report(until=past)
    assert r2.entries == 0


def test_consumption_report_result_is_frozen() -> None:
    report = ConsumptionReport(total_microdollars=0, entries=0)
    with pytest.raises(Exception):
        report.entries = 5  # type: ignore[misc]


def test_consumption_report_lock_acquired() -> None:
    """CostTracker.consumption_report MUST acquire self._lock.

    Wraps the tracker's lock with a counting proxy. Python 3.13's
    ``threading.Lock`` is an immutable C type so we cannot monkey-patch
    the class; replacing the instance with a proxy is the supported
    approach.
    """

    class _CountingLock:
        def __init__(self, inner: threading.Lock) -> None:
            self._inner = inner
            self.enter_count = 0

        def __enter__(self) -> threading.Lock:
            self.enter_count += 1
            return self._inner.__enter__()

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            self._inner.__exit__(exc_type, exc_val, exc_tb)

        def acquire(self, *args, **kwargs):  # pragma: no cover
            return self._inner.acquire(*args, **kwargs)

        def release(self) -> None:  # pragma: no cover
            return self._inner.release()

    tracker = CostTracker()
    tracker.record(1.0, "x")
    # Replace the live lock with our counting proxy
    original = tracker._lock
    proxy = _CountingLock(original)
    tracker._lock = proxy  # type: ignore[assignment]

    try:
        report = tracker.consumption_report()
    finally:
        tracker._lock = original  # type: ignore[assignment]

    assert proxy.enter_count >= 1
    assert report.entries == 1


# ---------------------------------------------------------------------------
# run_negative_drills — Tier 1
# ---------------------------------------------------------------------------


def test_run_negative_drills_all_pass() -> None:
    """Drills that correctly raise GovernanceHeldError all pass."""

    def drill_one(engine):
        raise GovernanceHeldError(
            verdict=None, role="D1-R1", action="submit", context={}
        )

    def drill_two(engine):
        raise GovernanceHeldError(
            verdict=None, role="D1-R2", action="submit", context={}
        )

    results = run_negative_drills(
        engine=None,
        drills=[NegativeDrill("one", drill_one), NegativeDrill("two", drill_two)],
    )
    assert len(results) == 2
    assert all(r.passed for r in results)
    assert [r.drill_name for r in results] == ["one", "two"]


def test_run_negative_drills_fail_closed_on_exception() -> None:
    """A drill that raises KeyError (not GovernanceHeldError) FAILS."""

    def bad_drill(engine):
        raise KeyError("unexpected")

    results = run_negative_drills(engine=None, drills=[NegativeDrill("bad", bad_drill)])
    assert len(results) == 1
    assert results[0].passed is False
    assert "unexpected" in results[0].reason.lower() or "KeyError" in results[0].reason
    assert results[0].exception_type == "KeyError"


def test_run_negative_drills_fail_closed_on_no_raise() -> None:
    """A drill that returns normally FAILS (engine should have refused)."""

    def lenient_drill(engine):
        return None  # engine permitted the action — should have refused!

    results = run_negative_drills(
        engine=None, drills=[NegativeDrill("lenient", lenient_drill)]
    )
    assert len(results) == 1
    assert results[0].passed is False
    assert "returned normally" in results[0].reason.lower()
    assert results[0].exception_type is None


def test_run_negative_drills_stop_at_first_failure_short_circuits() -> None:
    """stop_at_first_failure halts the batch after the first fail."""
    executed = []

    def pass_drill(engine):
        executed.append("a")
        raise GovernanceHeldError(verdict=None, role="D1-R1", action="x", context={})

    def fail_drill(engine):
        executed.append("b")
        return None

    def third_drill(engine):
        executed.append("c")
        raise GovernanceHeldError(verdict=None, role="D1-R1", action="x", context={})

    results = run_negative_drills(
        engine=None,
        drills=[
            NegativeDrill("a", pass_drill),
            NegativeDrill("b", fail_drill),
            NegativeDrill("c", third_drill),
        ],
        stop_at_first_failure=True,
    )
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False
    assert executed == ["a", "b"]


def test_run_negative_drills_accepts_tuple_form() -> None:
    """Drills MAY be passed as (name, callable) tuples."""

    def held(engine):
        raise GovernanceHeldError(verdict=None, role="D1-R1", action="x", context={})

    results = run_negative_drills(engine=None, drills=[("my_drill", held)])
    assert results[0].drill_name == "my_drill"
    assert results[0].passed is True


def test_run_negative_drills_accepts_bare_callable() -> None:
    """A bare callable uses its __name__ as the drill name."""

    def my_drill(engine):
        raise GovernanceHeldError(verdict=None, role="D1-R1", action="x", context={})

    results = run_negative_drills(engine=None, drills=[my_drill])
    assert results[0].drill_name == "my_drill"
    assert results[0].passed is True


def test_negative_drill_result_is_frozen() -> None:
    r = NegativeDrillResult(drill_name="x", passed=True, reason="ok")
    with pytest.raises(Exception):
        r.passed = False  # type: ignore[misc]
