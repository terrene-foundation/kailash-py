# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for HITL reviewer authority (GitHub #1510, SAFR BH2 legs 2-3).

Exercises the fail-closed reviewer-decision surface + capacity gate THROUGH the
``StrictEnforcer`` facade against a REAL on-disk ``SqliteHeldActionStore`` (no
mocking — testing.md Tier 2 + facade-manager-detection.md Rule 1; the store is a
manager-shape facade, so the real SQLite round-trip is used, never a mock).

The five governance invariants (each asserted below):

1. A reviewer MODIFY never widens authority — a modified verdict below HELD is
   clamped fail-closed to BLOCKED (monotonic-tightening only).
2. Capacity saturation fails CLOSED to BLOCKED — a NEW escalation is denied
   when the review queue is full, never queued and never silently dropped.
3. Expiry still defaults to DENY when ``on_expiry`` is unset (BH2 leg 1
   unchanged).
4. Every reviewer decision binds ``reviewer_id`` into the audit record.
5. A corrupt / missing / unsafe ``hold_id`` fails closed with a typed error.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.chain import VerificationResult
from kailash.trust.enforce.held import (
    ExpiryDisposition,
    ReviewDecisionError,
    ReviewerDecision,
    SqliteHeldActionStore,
)
from kailash.trust.enforce.strict import (
    EATPBlockedError,
    EATPHeldError,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)

pytestmark = [pytest.mark.integration, pytest.mark.tier2]


def _held_result() -> VerificationResult:
    """A verification result that classifies as HELD (>= flag_threshold)."""
    return VerificationResult(
        valid=True,
        reason="needs human review",
        violations=[{"field": "cost", "message": "near limit"}],
    )


def _enforcer(tmp_path, *, max_pending_holds: int = 1000, default_expiry=None):
    """A QUEUE-behavior enforcer backed by a REAL on-disk SQLite store."""
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(
        on_held=HeldBehavior.QUEUE,
        held_store=store,
        max_pending_holds=max_pending_holds,
        default_expiry=default_expiry,
    )
    return enforcer, store


def _queue_one(enforcer, agent_id="agent-x", action="deploy", *, timeout=300.0):
    """Escalate one HELD action to the review queue; return its hold_id."""
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id=agent_id,
            action=action,
            result=_held_result(),
            timeout=timeout,
        )
    return enforcer.review_queue[-1].metadata["hold_id"]


# ---------------------------------------------------------------------------
# Invariant 2 — capacity saturation fails CLOSED (leg 2)
# ---------------------------------------------------------------------------


def test_capacity_saturation_denies_new_escalation_blocked(tmp_path):
    """Fill review queue to max_pending_holds → next escalation DENIED (BLOCKED)."""
    enforcer, store = _enforcer(tmp_path, max_pending_holds=3)

    # Fill to capacity (each held → EATPHeldError, queued).
    for i in range(3):
        _queue_one(enforcer, agent_id=f"agent-{i}", timeout=300.0)
    assert len(enforcer.review_queue) == 3

    # The NEXT escalation is admission-denied, fail-closed to BLOCKED —
    # NOT queued, NOT silently dropped.
    with pytest.raises(EATPBlockedError) as excinfo:
        enforcer.enforce(
            agent_id="agent-overflow",
            action="deploy",
            result=_held_result(),
            timeout=300.0,
        )
    assert "saturated" in str(excinfo.value).lower()

    # The queue did NOT grow (the escalation was denied, not enqueued).
    assert len(enforcer.review_queue) == 3

    # A BLOCKED audit record was emitted for the denial (never silent).
    denial = [
        r
        for r in enforcer.records
        if r.metadata.get("admission_denied") and r.agent_id == "agent-overflow"
    ]
    assert len(denial) == 1
    assert denial[0].verdict is Verdict.BLOCKED
    assert denial[0].metadata["max_pending_holds"] == 3
    store.close()


# ---------------------------------------------------------------------------
# Invariant 4 — APPROVE resolves to AUTO_APPROVED, binds reviewer_id
# ---------------------------------------------------------------------------


def test_reviewer_approve_resolves_to_auto_approved_binds_reviewer(tmp_path):
    """APPROVE -> AUTO_APPROVED (original action sanctioned), reviewer_id bound."""
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-approve", timeout=300.0)

    # The hold persisted to the REAL SQLite store; the review-queue entry and
    # the store hold are correlated by the same hold_id.
    pending = store.pending()
    assert len(pending) == 1
    assert pending[0].hold_id == hold_id

    record = enforcer.apply_review_decision(
        hold_id, ReviewerDecision.APPROVE, "reviewer-alice"
    )

    # APPROVE sanctions the originally-held action WITHOUT escalating authority.
    assert record.verdict is Verdict.AUTO_APPROVED
    # Invariant 4: reviewer_id bound for audit.
    assert record.metadata["reviewer_id"] == "reviewer-alice"
    assert record.metadata["reviewer_decision"] == ReviewerDecision.APPROVE.value
    assert record.metadata["hold_id"] == hold_id
    # The decision record landed in the enforcer's audit sink.
    assert record in enforcer.records

    # Real SQLite round-trip: the hold was popped from the store (cannot be
    # re-reviewed nor expire).
    assert store.pending() == []
    assert enforcer.review_queue == []
    store.close()


# ---------------------------------------------------------------------------
# DECLINE resolves to BLOCKED
# ---------------------------------------------------------------------------


def test_reviewer_decline_resolves_to_blocked(tmp_path):
    """DECLINE -> BLOCKED (fail-closed denial by reviewer authority)."""
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-decline", timeout=300.0)

    record = enforcer.apply_review_decision(
        hold_id, ReviewerDecision.DECLINE, "reviewer-bob"
    )
    assert record.verdict is Verdict.BLOCKED
    assert record.metadata["reviewer_id"] == "reviewer-bob"
    assert store.pending() == []
    store.close()


# ---------------------------------------------------------------------------
# Invariant 1 — MODIFY never widens authority (monotonic-tightening only)
# ---------------------------------------------------------------------------


def test_reviewer_modify_widening_is_clamped_to_blocked(tmp_path):
    """MODIFY that attempts to WIDEN (AUTO_APPROVED) is clamped to BLOCKED."""
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-modify", timeout=300.0)

    # A MODIFY targeting a verdict LESS restrictive than HELD is a widening —
    # clamped fail-closed to BLOCKED (invariant 1).
    record = enforcer.apply_review_decision(
        hold_id,
        ReviewerDecision.MODIFY,
        "reviewer-carol",
        modified_verdict=Verdict.AUTO_APPROVED,
    )
    assert record.verdict is Verdict.BLOCKED
    assert record.metadata["reviewer_id"] == "reviewer-carol"
    # The reviewer's (rejected) intent is preserved in the audit trail.
    assert record.metadata["modified_verdict_requested"] == Verdict.AUTO_APPROVED.value
    store.close()


def test_reviewer_modify_tightening_is_allowed(tmp_path):
    """MODIFY to a verdict >= HELD is monotonic-tightening and passes through."""
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-modify2", timeout=300.0)

    # MODIFY -> HELD (re-hold for further review) is a valid non-widening.
    record = enforcer.apply_review_decision(
        hold_id,
        ReviewerDecision.MODIFY,
        "reviewer-dave",
        modified_verdict=Verdict.HELD,
    )
    assert record.verdict is Verdict.HELD
    store.close()


def test_reviewer_modify_without_target_fails_closed(tmp_path):
    """MODIFY without an explicit modified_verdict fails closed (typed error)."""
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-modify3", timeout=300.0)

    with pytest.raises(ReviewDecisionError):
        enforcer.apply_review_decision(hold_id, ReviewerDecision.MODIFY, "reviewer-eve")
    store.close()


# ---------------------------------------------------------------------------
# Invariant 5 — missing / unsafe hold_id fails closed with a typed error
# ---------------------------------------------------------------------------


def test_unknown_hold_id_fails_closed(tmp_path):
    """An unknown (or already-resolved) hold_id raises the typed error."""
    enforcer, store = _enforcer(tmp_path)
    _queue_one(enforcer, agent_id="agent-real", timeout=300.0)

    with pytest.raises(ReviewDecisionError):
        enforcer.apply_review_decision(
            "hold-does-not-exist", ReviewerDecision.APPROVE, "reviewer-x"
        )
    store.close()


def test_unsafe_hold_id_rejected(tmp_path):
    """A path-traversal-shaped hold_id is rejected before any lookup."""
    enforcer, store = _enforcer(tmp_path)
    with pytest.raises(ValueError):
        enforcer.apply_review_decision(
            "../../etc/passwd", ReviewerDecision.DECLINE, "reviewer-x"
        )
    store.close()


def test_double_review_fails_closed(tmp_path):
    """A resolved hold cannot be re-reviewed (fail-closed on the second call)."""
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-twice", timeout=300.0)

    enforcer.apply_review_decision(hold_id, ReviewerDecision.APPROVE, "reviewer-1")
    with pytest.raises(ReviewDecisionError):
        enforcer.apply_review_decision(hold_id, ReviewerDecision.APPROVE, "reviewer-2")
    store.close()


# ---------------------------------------------------------------------------
# Invariant 3 — expiry still defaults to DENY (leg 1 unchanged)
# ---------------------------------------------------------------------------


def test_expiry_unset_still_defaults_to_deny_blocked(tmp_path):
    """A timeout-bearing hold with no on_expiry expires to BLOCKED (fail-safe DENY)."""
    # default_expiry unset -> the fail-safe ExpiryDisposition.DENY applies.
    enforcer, store = _enforcer(tmp_path, default_expiry=None)

    # A zero-timeout hold is already past its deadline; on_expiry is unset.
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-expire",
            action="deploy",
            result=_held_result(),
            timeout=0.0,
        )
    # The persisted hold carries the fail-safe DENY disposition.
    assert store.pending()[0].on_expiry is ExpiryDisposition.DENY

    later = datetime.now(timezone.utc) + timedelta(seconds=1)
    expiry_records = enforcer.expire_holds(now=later)
    assert len(expiry_records) == 1
    assert expiry_records[0].verdict is Verdict.BLOCKED
    assert store.pending() == []
    store.close()


# ---------------------------------------------------------------------------
# Merge-gate regression coverage (BH2 legs 2-3 review findings)
# ---------------------------------------------------------------------------


def test_bad_decision_raises_before_hold_is_consumed(tmp_path):
    """Finding 1: a MODIFY without modified_verdict raises BEFORE the hold is
    popped, so the hold SURVIVES and is resolvable on a corrected retry.

    Guards against state-advance-before-validation: the pure resolver runs
    first, so a bad decision cannot destroy the hold (leaving the action stuck
    blocked forever with no audit trail).
    """
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-survive", timeout=300.0)

    # MODIFY with no modified_verdict fails closed...
    with pytest.raises(ReviewDecisionError):
        enforcer.apply_review_decision(hold_id, ReviewerDecision.MODIFY, "rev-1")

    # ...and the hold was NOT consumed: still in the store AND the review queue.
    assert [h.hold_id for h in store.pending()] == [hold_id]
    assert enforcer.review_queue[-1].metadata["hold_id"] == hold_id

    # A corrected retry resolves the SAME hold — proving it survived intact.
    record = enforcer.apply_review_decision(
        hold_id,
        ReviewerDecision.MODIFY,
        "rev-1",
        modified_verdict=Verdict.HELD,
    )
    assert record.verdict is Verdict.HELD
    assert store.pending() == []
    store.close()


def _insert_corrupt_row(db_path: str, hold_id: str) -> None:
    """Write a corrupt held-action row (bad on_expiry) straight into SQLite so
    the store's pop() must fall back to its fail-closed DENY sentinel."""
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO held_actions "
            "(hold_id, agent_id, action, held_at, timeout_seconds, expires_at, "
            "on_expiry, reason, violations_json, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                hold_id,
                "agent-corrupt",
                "deploy",
                now.isoformat(),
                300.0,
                (now + timedelta(seconds=300)).isoformat(),
                "not_a_valid_disposition",  # ExpiryDisposition(...) will raise
                "",
                "[]",
                "{}",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_approve_over_corrupt_sentinel_fails_closed_to_blocked(tmp_path):
    """Finding 2: an APPROVE addressed to a hold that pop() recovers as the
    corrupt DENY sentinel resolves to BLOCKED, never AUTO_APPROVED."""
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store)

    hold_id = "hold-corrupt-sentinel"
    _insert_corrupt_row(db_path, hold_id)

    # Real SQLite round-trip: apply_review_decision pops the row, which converts
    # to the fail-closed DENY sentinel (valid=False) inside the store.
    record = enforcer.apply_review_decision(
        hold_id, ReviewerDecision.APPROVE, "reviewer-corrupt"
    )
    # APPROVE must NOT honor a corrupt hold — forced fail-closed to BLOCKED.
    assert record.verdict is Verdict.BLOCKED
    assert record.metadata["corrupt_hold"] is True
    assert record.metadata["reviewer_id"] == "reviewer-corrupt"
    # The corrupt row was consumed by the pop (real round-trip).
    assert store.pop(hold_id) is None
    store.close()


def test_reviewer_id_with_control_char_is_rejected(tmp_path):
    """Finding 3: a newline/control-char reviewer_id (audit-log injection
    vector) is rejected before it is bound or logged — and the hold survives."""
    enforcer, store = _enforcer(tmp_path)
    hold_id = _queue_one(enforcer, agent_id="agent-inject", timeout=300.0)

    with pytest.raises(ValueError):
        enforcer.apply_review_decision(
            hold_id,
            ReviewerDecision.DECLINE,
            "reviewer\ninjected-audit-log-line",
        )

    # reviewer_id is validated before any state mutation — the hold survives.
    assert [h.hold_id for h in store.pending()] == [hold_id]
    assert enforcer.review_queue[-1].metadata["hold_id"] == hold_id
    store.close()
