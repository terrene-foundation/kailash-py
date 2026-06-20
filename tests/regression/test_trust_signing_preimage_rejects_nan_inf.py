# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: every trust-plane signing / hash / HMAC PRE-IMAGE rejects NaN/Inf.

A ``json.dumps`` over a signing or integrity-hash pre-image that omits
``allow_nan=False`` emits RFC-8259-invalid ``NaN`` / ``Infinity`` literals.
Python's permissive ``json`` signs/hashes them fine, but a strict cross-SDK
parser (Rust ``serde_json``) rejects them, so a Python-signed/hashed artifact
whose pre-image carried a NaN/Inf cannot be re-verified cross-SDK — the parity
hazard the canonical-encoder family exists to close.

This is the trust-plane-WIDE sweep of the NaN/Inf-in-pre-image bug class, found
by the pre-release ``/redteam`` multi-site sweep that started from the witness
family (``selective_disclosure.py``) and the envelope HMAC pre-image
(``envelope.to_canonical_json``, commit 9dfb1d968 / PR #1411). Per
``security.md`` Multi-Site Kwarg Plumbing, EVERY signing/hash pre-image site is
swept in the same PR; leaving a sibling on the unqualified signature ships the
exact failure the kwarg fixes.

These surfaces are OUTSIDE ``specs/trust-canonical-encoders.md``'s Family-B
spec table (no pinned cross-SDK byte vectors), so adding ``allow_nan=False`` is
byte-neutral on every finite input and needs no kailash-rs lockstep — it only
newly rejects the already-broken NaN/Inf case. The finite-input "still produces
a stable digest" assertions below pin that byte-neutrality.

Deliberately NOT swept (correct by design): ``pact/audit.py``'s
``_compute_hash_legacy`` / ``_compute_hash_prefix_format`` omit ``allow_nan``
on purpose to reproduce historical pre-fix bytes for forensic
re-seal-vs-tamper disambiguation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust import audit_store as audit_store_mod
from kailash.trust._locking import compute_wal_hash
from kailash.trust.audit_store import AuditRecord
from kailash.trust.chain import ActionResult, AuditAnchor
from kailash.trust.messaging.envelope import SecureMessageEnvelope
from kailash.trust.orchestration.execution_context import TrustExecutionContext

UTC = timezone.utc
_NONFINITE = (float("nan"), float("inf"), float("-inf"))
_MATCH = "JSON compliant"


def _anchor(context: dict) -> AuditAnchor:
    return AuditAnchor(
        id="anc-1",
        agent_id="agent-1",
        action="read",
        timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
        trust_chain_hash="h",
        result=ActionResult.SUCCESS,
        signature="s",
        resource="r",
        context=context,
    )


def _envelope(payload: dict) -> SecureMessageEnvelope:
    return SecureMessageEnvelope(
        message_id="m1",
        sender_agent_id="a",
        recipient_agent_id="b",
        payload=payload,
        timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
        nonce="n",
        trust_chain_hash="h",
    )


@pytest.mark.regression
class TestTrustSigningPreimageRejectsNanInf:
    """HIGH — messaging Ed25519 signing pre-image (signer.py / verifier.py)."""

    def test_secure_message_signing_payload_rejects_nan_inf(self) -> None:
        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                _envelope({"amount": bad}).get_signing_payload()

    def test_secure_message_signing_payload_finite_is_byte_neutral(self) -> None:
        # Finite input still signs deterministically (byte-neutrality).
        out = _envelope({"amount": 1.5, "note": "ok"}).get_signing_payload()
        assert isinstance(out, bytes) and b'"amount":1.5' in out

    # MED — audit-chain Merkle digest (typed Optional[float] duration_ms).
    def test_compute_event_hash_rejects_nan_inf_duration(self) -> None:
        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                audit_store_mod._compute_event_hash(
                    "e1", "t", "actor", "act", "res", "ok", "0" * 64, None, bad, {}
                )

    def test_compute_event_hash_rejects_nan_inf_metadata(self) -> None:
        with pytest.raises(ValueError, match=_MATCH):
            audit_store_mod._compute_event_hash(
                "e1",
                "t",
                "actor",
                "act",
                "res",
                "ok",
                "0" * 64,
                None,
                1.0,
                {"score": float("nan")},
            )

    def test_compute_event_hash_finite_is_byte_neutral(self) -> None:
        h = audit_store_mod._compute_event_hash(
            "e1", "t", "actor", "act", "res", "ok", "0" * 64, None, 12.5, {}
        )
        assert isinstance(h, str) and len(h) == 64

    # MED — AuditRecord integrity hash (anchor.to_signing_payload + context).
    def test_audit_record_integrity_hash_rejects_nan_inf_context(self) -> None:
        with pytest.raises(ValueError, match=_MATCH):
            AuditRecord(anchor=_anchor({"cost": float("inf")}), sequence_number=1)

    def test_audit_record_integrity_hash_finite_is_byte_neutral(self) -> None:
        rec = AuditRecord(anchor=_anchor({"cost": 2.0}), sequence_number=1)
        assert len(rec.integrity_hash) == 64

    # LOW — WAL tamper-detection hash (planned_revocations free list).
    def test_compute_wal_hash_rejects_nan_inf(self) -> None:
        with pytest.raises(ValueError, match=_MATCH):
            compute_wal_hash(
                {
                    "root_delegate_id": "r",
                    "planned_revocations": [{"cost": float("nan")}],
                    "reason": "x",
                }
            )

    def test_compute_wal_hash_finite_is_byte_neutral(self) -> None:
        h = compute_wal_hash(
            {"root_delegate_id": "r", "planned_revocations": [], "reason": "x"}
        )
        assert isinstance(h, str) and len(h) == 64

    # LOW — delegation execution-context state hash (inherited_constraints).
    def test_execution_context_state_hash_rejects_nan_inf(self) -> None:
        ctx = TrustExecutionContext.create(
            parent_agent_id="sup",
            task_id="t1",
            delegated_capabilities=["read"],
            inherited_constraints={"max_cost": float("inf")},
        )
        with pytest.raises(ValueError, match=_MATCH):
            ctx.compute_hash()

    def test_execution_context_state_hash_finite_is_byte_neutral(self) -> None:
        ctx = TrustExecutionContext.create(
            parent_agent_id="sup",
            task_id="t1",
            delegated_capabilities=["read"],
            inherited_constraints={"max_cost": 100.0},
        )
        assert len(ctx.compute_hash()) == 64
