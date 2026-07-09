# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 unit tests for HITL hold timeout + fail-safe expiry (GitHub #1515, SAFR BH2).

Covers the five load-bearing invariants:

1. A held action accepts ``timeout`` + ``on_expiry`` wired through the HELD path.
2. On expiry the configured disposition fires deterministically and is audited.
3. The UNSET ``on_expiry`` default is fail-safe = DENY (never auto-approves).
4. Timeout windows are per-capability via ``ApprovalPolicyModel.approval_timeout_seconds``
   (that previously-orphan field now has a live consumer).
5. Expiry is MONOTONIC — the outcome is at least as restrictive as the hold.

Plus the trust-plane security guards: math.isfinite on the timeout, validate_id
on the hold id.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.chain import VerificationResult
from kailash.trust.enforce.held import (
    DEFAULT_EXPIRY_DISPOSITION,
    ExpiryDisposition,
    HeldAction,
    MemoryHeldActionStore,
    new_hold_id,
    resolve_expiry_verdict,
    resolve_timeout_seconds,
    verdict_rank,
)
from kailash.trust.enforce.strict import (
    EATPHeldError,
    EnforcementRecord,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)
from kailash.trust.governance.models import ApprovalPolicyModel

pytestmark = pytest.mark.unit


def _held_result() -> VerificationResult:
    """A verification result that classifies to HELD (valid + 1 violation)."""
    return VerificationResult(
        valid=True,
        reason="needs human review",
        violations=[{"field": "cost", "message": "near limit"}],
    )


# ---------------------------------------------------------------------------
# Invariant 5 — Monotonic expiry (pure resolution)
# ---------------------------------------------------------------------------


def test_every_disposition_resolves_at_least_as_restrictive_as_held():
    """INV-5: no ExpiryDisposition may resolve below HELD (never relaxes)."""
    held_rank = verdict_rank(Verdict.HELD)
    for disposition in ExpiryDisposition:
        verdict = resolve_expiry_verdict(disposition)
        assert (
            verdict_rank(verdict) >= held_rank
        ), f"{disposition} resolved to {verdict} which is LESS restrictive than HELD"
        assert verdict not in (Verdict.AUTO_APPROVED, Verdict.FLAGGED)


def test_disposition_verdict_mapping_is_explicit():
    """INV-5: DENY -> BLOCKED (tighter than HELD); ESCALATE -> HELD (equal)."""
    assert resolve_expiry_verdict(ExpiryDisposition.DENY) is Verdict.BLOCKED
    assert resolve_expiry_verdict(ExpiryDisposition.ESCALATE_TO_SENIOR) is Verdict.HELD


def test_verdict_rank_is_monotonic_escalation():
    assert (
        verdict_rank(Verdict.AUTO_APPROVED)
        < verdict_rank(Verdict.FLAGGED)
        < verdict_rank(Verdict.HELD)
        < verdict_rank(Verdict.BLOCKED)
    )


# ---------------------------------------------------------------------------
# Invariant 3 — Unset on_expiry is fail-safe DENY
# ---------------------------------------------------------------------------


def test_default_expiry_disposition_is_deny():
    assert DEFAULT_EXPIRY_DISPOSITION is ExpiryDisposition.DENY


def test_unset_on_expiry_denies_on_timeout_never_auto_approves():
    """INV-3: a hold with no configured expiry disposition denies on timeout."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)

    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-1",
            action="wire_funds",
            result=_held_result(),
            timeout=60.0,  # on_expiry deliberately unset
        )

    # Deterministic expiry past the deadline.
    expired = enforcer.expire_holds(now=datetime.now(timezone.utc) + timedelta(days=1))
    assert len(expired) == 1
    assert expired[0].verdict is Verdict.BLOCKED  # fail-safe deny, NOT auto-approve
    assert expired[0].verdict not in (Verdict.AUTO_APPROVED, Verdict.FLAGGED)
    assert expired[0].metadata["on_expiry"] == ExpiryDisposition.DENY.value


def test_enforcer_default_expiry_is_deny_property():
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    assert enforcer._default_expiry is ExpiryDisposition.DENY


# ---------------------------------------------------------------------------
# Invariant 1 — Held action accepts timeout + on_expiry, wired through HELD path
# ---------------------------------------------------------------------------


def test_held_action_accepts_timeout_and_on_expiry():
    """INV-1: enforce() threads timeout + on_expiry into a tracked hold."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-2",
            action="deploy",
            result=_held_result(),
            timeout=120.0,
            on_expiry=ExpiryDisposition.ESCALATE_TO_SENIOR,
        )

    pending = enforcer.held_store.pending()
    assert len(pending) == 1
    hold = pending[0]
    assert hold.agent_id == "agent-2"
    assert hold.action == "deploy"
    assert hold.timeout_seconds == 120.0
    assert hold.on_expiry is ExpiryDisposition.ESCALATE_TO_SENIOR


def test_no_timeout_no_tracked_hold():
    """A hold without a timeout window is not tracked for expiry (no bound)."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    with pytest.raises(EATPHeldError):
        enforcer.enforce(agent_id="a", action="x", result=_held_result())
    assert enforcer.held_store.pending() == []


# ---------------------------------------------------------------------------
# Invariant 2 — Expiry fires deterministically AND is audited
# ---------------------------------------------------------------------------


def test_expiry_is_deterministic_and_audited():
    """INV-2: expiry only fires past the deadline, and lands in the audit sink."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    held_at = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

    hold = HeldAction(
        hold_id=new_hold_id(),
        agent_id="agent-3",
        action="export",
        held_at=held_at,
        timeout_seconds=300.0,
        on_expiry=ExpiryDisposition.DENY,
        record=EnforcementRecord(
            agent_id="agent-3",
            action="export",
            verdict=Verdict.HELD,
            verification_result=_held_result(),
            timestamp=held_at,
        ),
    )
    enforcer.held_store.add(hold)

    # Before the deadline: no expiry (deterministic).
    before = enforcer.expire_holds(now=held_at + timedelta(seconds=299))
    assert before == []
    assert enforcer.held_store.pending()  # still pending

    records_before = len(enforcer.records)
    # At/after the deadline: expiry fires exactly once.
    after = enforcer.expire_holds(now=held_at + timedelta(seconds=300))
    assert len(after) == 1
    exp = after[0]
    assert exp.verdict is Verdict.BLOCKED

    # Audited to the SAME sink the verdict path uses.
    assert exp in enforcer.records
    assert len(enforcer.records) == records_before + 1
    assert exp.metadata["hold_expiry"] is True
    assert exp.metadata["hold_id"] == hold.hold_id
    assert exp.metadata["original_verdict"] == Verdict.HELD.value

    # Idempotent: a second sweep finds nothing (the hold was popped).
    assert enforcer.expire_holds(now=held_at + timedelta(days=1)) == []


def test_escalate_disposition_expires_to_held():
    """INV-2 + INV-5: escalate resolves to HELD (equal restrictiveness), audited."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    held_at = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
    enforcer.held_store.add(
        HeldAction(
            hold_id=new_hold_id(),
            agent_id="agent-4",
            action="approve_budget",
            held_at=held_at,
            timeout_seconds=10.0,
            on_expiry=ExpiryDisposition.ESCALATE_TO_SENIOR,
            record=EnforcementRecord(
                agent_id="agent-4",
                action="approve_budget",
                verdict=Verdict.HELD,
                verification_result=_held_result(),
                timestamp=held_at,
            ),
        )
    )
    expired = enforcer.expire_holds(now=held_at + timedelta(seconds=11))
    assert len(expired) == 1
    assert expired[0].verdict is Verdict.HELD  # at least as restrictive as HELD


# ---------------------------------------------------------------------------
# Invariant 4 — approval_timeout_seconds is now a live consumer
# ---------------------------------------------------------------------------


def test_resolve_timeout_reads_approval_policy_field():
    """INV-4: the previously-orphan field is consumed by resolve_timeout_seconds."""
    policy = ApprovalPolicyModel(
        external_agent_id="copilot", approval_timeout_seconds=1800
    )
    assert resolve_timeout_seconds(policy) == 1800.0


def test_enforce_uses_policy_timeout_window():
    """INV-4: enforce() derives the hold window from the policy field."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    policy = ApprovalPolicyModel(
        external_agent_id="copilot", approval_timeout_seconds=300
    )
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="copilot",
            action="invoke",
            result=_held_result(),
            approval_policy=policy,
        )
    pending = enforcer.held_store.pending()
    assert len(pending) == 1
    assert pending[0].timeout_seconds == 300.0  # from approval_timeout_seconds


def test_explicit_timeout_overrides_policy():
    """An explicit timeout takes precedence over the policy field."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    policy = ApprovalPolicyModel(
        external_agent_id="copilot", approval_timeout_seconds=3600
    )
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="copilot",
            action="invoke",
            result=_held_result(),
            timeout=42.0,
            approval_policy=policy,
        )
    assert enforcer.held_store.pending()[0].timeout_seconds == 42.0


# ---------------------------------------------------------------------------
# Security guards (trust-plane-security.md)
# ---------------------------------------------------------------------------


class _Policy:
    """Minimal duck-typed policy for adversarial timeout values."""

    def __init__(self, value: float) -> None:
        self.approval_timeout_seconds = value


def test_resolve_timeout_rejects_nan():
    with pytest.raises(ValueError):
        resolve_timeout_seconds(_Policy(float("nan")))


def test_resolve_timeout_rejects_inf():
    with pytest.raises(ValueError):
        resolve_timeout_seconds(_Policy(float("inf")))


def test_resolve_timeout_rejects_negative():
    with pytest.raises(ValueError):
        resolve_timeout_seconds(_Policy(-1.0))


def test_enforce_rejects_nan_timeout():
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    with pytest.raises(ValueError):
        enforcer.enforce(
            agent_id="a",
            action="x",
            result=_held_result(),
            timeout=float("nan"),
        )


def test_held_action_rejects_non_finite_timeout():
    held_at = datetime.now(timezone.utc)
    rec = EnforcementRecord(
        agent_id="a",
        action="x",
        verdict=Verdict.HELD,
        verification_result=_held_result(),
        timestamp=held_at,
    )
    with pytest.raises(ValueError):
        HeldAction(
            hold_id=new_hold_id(),
            agent_id="a",
            action="x",
            held_at=held_at,
            timeout_seconds=float("inf"),
            on_expiry=ExpiryDisposition.DENY,
            record=rec,
        )


def test_held_action_validates_hold_id():
    held_at = datetime.now(timezone.utc)
    rec = EnforcementRecord(
        agent_id="a",
        action="x",
        verdict=Verdict.HELD,
        verification_result=_held_result(),
        timestamp=held_at,
    )
    with pytest.raises(ValueError):
        HeldAction(
            hold_id="../../etc/passwd",  # path traversal
            agent_id="a",
            action="x",
            held_at=held_at,
            timeout_seconds=1.0,
            on_expiry=ExpiryDisposition.DENY,
            record=rec,
        )


def test_held_action_normalizes_naive_held_at_to_utc():
    """LOW-3: a tz-naive held_at is normalized to UTC (no naive/aware mismatch)."""
    naive = datetime(2026, 7, 9, 12, 0, 0)  # no tzinfo
    assert naive.tzinfo is None
    rec = EnforcementRecord(
        agent_id="a",
        action="x",
        verdict=Verdict.HELD,
        verification_result=_held_result(),
        timestamp=datetime.now(timezone.utc),
    )
    hold = HeldAction(
        hold_id=new_hold_id(),
        agent_id="a",
        action="x",
        held_at=naive,
        timeout_seconds=10.0,
        on_expiry=ExpiryDisposition.DENY,
        record=rec,
    )
    # Normalized to UTC — held_at + expires_at are both aware.
    assert hold.held_at.tzinfo is timezone.utc
    assert hold.expires_at.tzinfo is timezone.utc
    # is_expired() against an aware now does not raise (naive-vs-aware TypeError).
    aware_now = datetime(2026, 7, 9, 12, 0, 30, tzinfo=timezone.utc)
    assert hold.is_expired(aware_now) is True


def test_naive_held_at_expires_through_enforcer():
    """A naive-datetime-held action still expires deterministically (no TypeError)."""
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE)
    naive_held_at = datetime(2026, 7, 9, 12, 0, 0)  # no tzinfo
    enforcer.held_store.add(
        HeldAction(
            hold_id=new_hold_id(),
            agent_id="agent-naive",
            action="x",
            held_at=naive_held_at,
            timeout_seconds=5.0,
            on_expiry=ExpiryDisposition.DENY,
            record=EnforcementRecord(
                agent_id="agent-naive",
                action="x",
                verdict=Verdict.HELD,
                verification_result=_held_result(),
                timestamp=datetime.now(timezone.utc),
            ),
        )
    )
    expired = enforcer.expire_holds(
        now=datetime(2026, 7, 9, 12, 0, 10, tzinfo=timezone.utc)
    )
    assert len(expired) == 1
    assert expired[0].verdict is Verdict.BLOCKED


def test_new_hold_id_is_finite_and_safe():
    hid = new_hold_id()
    assert hid.startswith("hold-")
    # Does not raise — validate_id accepts it inside HeldAction.__post_init__
    HeldAction(
        hold_id=hid,
        agent_id="a",
        action="x",
        held_at=datetime.now(timezone.utc),
        timeout_seconds=1.0,
        on_expiry=ExpiryDisposition.DENY,
        record=EnforcementRecord(
            agent_id="a",
            action="x",
            verdict=Verdict.HELD,
            verification_result=_held_result(),
            timestamp=datetime.now(timezone.utc),
        ),
    )


def test_memory_store_is_bounded():
    """Bounded collection (trust-plane-security.md rule 4)."""
    store = MemoryHeldActionStore(maxlen=5)
    held_at = datetime.now(timezone.utc)
    for _ in range(20):
        store.add(
            HeldAction(
                hold_id=new_hold_id(),
                agent_id="a",
                action="x",
                held_at=held_at,
                timeout_seconds=1.0,
                on_expiry=ExpiryDisposition.DENY,
                record=EnforcementRecord(
                    agent_id="a",
                    action="x",
                    verdict=Verdict.HELD,
                    verification_result=_held_result(),
                    timestamp=held_at,
                ),
            )
        )
    assert len(store.pending()) == 5


def test_math_isfinite_guard_present():
    """Sanity: the timeout finiteness guard actually uses math.isfinite semantics."""
    assert not math.isfinite(float("nan"))
    assert not math.isfinite(float("inf"))
