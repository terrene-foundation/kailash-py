# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring test for the EATP-12 vault audit dispatcher (W2-D1).

Exercises ``kailash.trust.vault.dispatch.AuditDispatcher`` end-to-end
against the REAL substrate — real per-tier
:class:`~kailash.delegate.audit.AuditChainEngine`, real
:class:`~kailash.trust.chain.TrustLineageChain`, real Ed25519 signer +
:class:`~kailash.delegate.verifier.Ed25519Verifier`. NO mocks of the
dispatcher, the engines, or the verifier (per ``rules/testing.md`` Tier-2:
real infrastructure, no ``@patch`` / ``MagicMock`` / ``unittest.mock``).

The Ed25519 keypair is produced by the real ``cryptography`` library and the
public key is wired into a real
:class:`~kailash.delegate.types.PrincipalDirectory` — this is the same
posture as ``tests/unit/delegate/_verifier_helpers.py::build_real_verifier_pair``
but inlined so the test is self-contained.

Conformance coverage (EATP-12 §4.5):

- N12-AU-02 — OUTCOME → recovery, DENIAL → safety, receipt returned, head
  advances (tests 1, 2).
- N12-AU-02a — accept-despite-seal: repeated dispatch to recovery/safety
  never fails due to a seal (test 5).
- N12-AU-02b — fail-closed ordering: a failing dispatch RAISES and returns
  NO receipt, and the require_receipt_or_abort helper aborts on None (test 4).
- Per-tier independent chains (N12-AU-01a) — safety head advances
  independently of recovery (test 2).
- unknown-tier → VaultBindingError(N12FT01Code.UNKNOWN_TIER) (test 3).
"""

from __future__ import annotations

import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import (
    AuditChainSignatureError,
    DelegateEventType,
    content_signing_bytes,
)
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.vault.dispatch import (
    AuditDispatcher,
    AuditTier,
    DispatchReceipt,
    require_receipt_or_abort,
)
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError

_EVENT_TYPE = DelegateEventType.EXTERNAL_SIDE_EFFECT.value


def _build_signer() -> tuple[DelegateIdentity, Ed25519Verifier, Callable[[bytes], str]]:
    """Real Ed25519 keypair + directory + signer (NO mocks).

    Returns a (identity, verifier, signer) triple wiring a real Ed25519
    public key into a real PrincipalDirectory and a signer callable that
    produces the 128-hex signature over the canonical pre-image.
    """
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-vault-audit",
        role_binding_ref="rb-vault-audit",
        genesis_ref="gen-vault-audit",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


def _sign_anchor(
    signer: Callable[[bytes], str],
    identity: DelegateIdentity,
    event_payload: dict,
) -> str:
    """Produce the 128-hex Ed25519 signature over the canonical pre-image.

    The pre-image is content_signing_bytes(event_type, event_payload,
    signer_delegate_id) — the SAME bytes the engine re-derives and verifies.
    """
    pre_image = content_signing_bytes(_EVENT_TYPE, event_payload, identity.delegate_id)
    return signer(pre_image)


@pytest.mark.integration
def test_dispatch_outcome_to_recovery_returns_receipt_and_advances_head() -> None:
    """N12-AU-02 — an OUTCOME anchor → recovery returns a receipt; head advances."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    # Recovery starts with no anchors (genesis-only chain).
    assert dispatcher.head_hash(AuditTier.RECOVERY.value) is None
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0

    payload = {
        "subtype": "vault_kek_outcome",
        "alg_id": "slip39-256-v1",  # deployment alg_id rides event_payload
        "operation": "backup",
        "result": "ok",
    }
    signature = _sign_anchor(signer, identity, payload)

    receipt = dispatcher.dispatch(
        event_type=_EVENT_TYPE,
        event_payload=payload,
        signer_identity=identity,
        signature=signature,
        tier=AuditTier.RECOVERY.value,
    )

    # Well-formed receipt.
    assert isinstance(receipt, DispatchReceipt)
    assert receipt.tier == "recovery"
    assert receipt.sequence == 0
    assert receipt.previous_anchor_hash == ""  # genesis of the recovery chain
    assert len(receipt.anchor_hash) == 64  # SHA-256 hex
    assert receipt.signer_delegate_id == str(identity.delegate_id)
    assert receipt.event_subtype == "vault_kek_outcome"
    assert receipt.signed_at  # tz-aware ISO string

    # Recovery chain head advanced; matches the receipt's anchor_hash.
    head = dispatcher.head_hash(AuditTier.RECOVERY.value)
    assert head == receipt.anchor_hash
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 1

    # Round-trip the receipt (to_dict / from_dict).
    assert DispatchReceipt.from_dict(receipt.to_dict()) == receipt


@pytest.mark.integration
def test_safety_tier_chains_independently_of_recovery() -> None:
    """N12-AU-02 + N12-AU-01a — DENIAL → safety; per-tier chains are independent."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    # Seed recovery with one OUTCOME anchor so its head is non-empty.
    rec_payload = {"subtype": "vault_kek_outcome", "alg_id": "a", "result": "ok"}
    rec_receipt = dispatcher.dispatch(
        event_type=_EVENT_TYPE,
        event_payload=rec_payload,
        signer_identity=identity,
        signature=_sign_anchor(signer, identity, rec_payload),
        tier=AuditTier.RECOVERY.value,
    )

    # Safety is still at genesis — recovery's dispatch did NOT advance it.
    assert dispatcher.head_hash(AuditTier.SAFETY.value) is None
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 0

    # Dispatch a DENIAL anchor to safety.
    safety_payload = {
        "subtype": "vault_kek_denial",
        "alg_id": "a",
        "code": "missing-clearance",
    }
    safety_receipt = dispatcher.dispatch(
        event_type=_EVENT_TYPE,
        event_payload=safety_payload,
        signer_identity=identity,
        signature=_sign_anchor(signer, identity, safety_payload),
        tier=AuditTier.SAFETY.value,
    )

    # Safety chain advanced INDEPENDENTLY — its own genesis (seq 0, prev "").
    assert safety_receipt.tier == "safety"
    assert safety_receipt.sequence == 0  # first safety anchor → its own genesis
    assert safety_receipt.previous_anchor_hash == ""  # NO cross-tier chaining
    assert dispatcher.head_hash(AuditTier.SAFETY.value) == safety_receipt.anchor_hash
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1

    # The two tiers' heads are distinct chains — recovery head unchanged by
    # the safety dispatch.
    assert dispatcher.head_hash(AuditTier.RECOVERY.value) == rec_receipt.anchor_hash
    assert safety_receipt.anchor_hash != rec_receipt.anchor_hash
    # Recovery still has exactly one anchor (safety dispatch did not touch it).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 1

    # A SECOND safety anchor chains after the first safety head (the
    # denial-summary "chains after the last stored safety anchor" contract).
    safety_payload_2 = {
        "subtype": "vault_kek_denial",
        "alg_id": "a",
        "code": "kcv-mismatch",
    }
    safety_receipt_2 = dispatcher.dispatch(
        event_type=_EVENT_TYPE,
        event_payload=safety_payload_2,
        signer_identity=identity,
        signature=_sign_anchor(signer, identity, safety_payload_2),
        tier=AuditTier.SAFETY.value,
    )
    assert safety_receipt_2.sequence == 1
    assert safety_receipt_2.previous_anchor_hash == safety_receipt.anchor_hash


@pytest.mark.integration
def test_unknown_tier_raises_typed_vault_binding_error() -> None:
    """N12-AU-02 — a dispatch to an unrecognized tier → unknown-tier."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    payload = {"subtype": "vault_kek_outcome", "alg_id": "a"}
    signature = _sign_anchor(signer, identity, payload)

    with pytest.raises(VaultBindingError) as exc_info:
        dispatcher.dispatch(
            event_type=_EVENT_TYPE,
            event_payload=payload,
            signer_identity=identity,
            signature=signature,
            tier="quarantine",  # not in the closed {recovery, safety} set
        )
    assert exc_info.value.code is N12FT01Code.UNKNOWN_TIER

    # The valid tier names themselves but a NON-vault tier (e.g. an
    # EATP-09 gradient tier) are also rejected — binding hard-targets ONLY
    # recovery/safety.
    with pytest.raises(VaultBindingError) as exc_info2:
        dispatcher.dispatch(
            event_type=_EVENT_TYPE,
            event_payload=payload,
            signer_identity=identity,
            signature=signature,
            tier="HELD",
        )
    assert exc_info2.value.code is N12FT01Code.UNKNOWN_TIER


@pytest.mark.integration
def test_failed_dispatch_raises_and_returns_no_receipt_failclosed() -> None:
    """N12-AU-02b — a dispatch that fails verification RAISES; no receipt.

    Demonstrates the "no receipt → caller MUST abort" contract: a bad
    signature makes dispatch RAISE (AuditChainSignatureError), so a caller
    gating on the receipt never receives one and cannot release a KEK.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    payload = {"subtype": "vault_kek_outcome", "alg_id": "a"}
    # A structurally-valid 128-hex string that is NOT a valid signature over
    # the pre-image — the real Ed25519 verifier rejects it (fail-closed).
    bogus_signature = "00" * 64

    receipt: DispatchReceipt | None = None
    with pytest.raises(AuditChainSignatureError):
        receipt = dispatcher.dispatch(
            event_type=_EVENT_TYPE,
            event_payload=payload,
            signer_identity=identity,
            signature=bogus_signature,
            tier=AuditTier.RECOVERY.value,
        )

    # No receipt was produced — the caller gating on it cannot proceed.
    assert receipt is None
    # The recovery chain did NOT advance (the failed emit appended nothing).
    assert dispatcher.head_hash(AuditTier.RECOVERY.value) is None
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0

    # The fail-closed helper converts a swallowed-to-None dispatch into a
    # loud abort — "no active KEK / no shard release until a receipt".
    with pytest.raises(VaultBindingError) as exc_info:
        require_receipt_or_abort(receipt)
    assert exc_info.value.code is N12FT01Code.UNKNOWN_TIER

    # A real receipt passes the helper through unchanged (the happy path the
    # caller relies on).
    good_sig = _sign_anchor(signer, identity, payload)
    good_receipt = dispatcher.dispatch(
        event_type=_EVENT_TYPE,
        event_payload=payload,
        signer_identity=identity,
        signature=good_sig,
        tier=AuditTier.RECOVERY.value,
    )
    assert require_receipt_or_abort(good_receipt) is good_receipt


@pytest.mark.integration
def test_accept_despite_seal_repeated_dispatch_succeeds() -> None:
    """N12-AU-02a — repeated dispatch to recovery/safety never fails on a seal."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    # Dispatch many anchors to BOTH "sealed" tiers — every one succeeds
    # (append-only ≠ append-prohibited; there is no real seal to violate).
    prev_recovery = ""
    prev_safety = ""
    for i in range(5):
        rec_payload = {"subtype": "vault_kek_outcome", "alg_id": "a", "i": i}
        rec_receipt = dispatcher.dispatch(
            event_type=_EVENT_TYPE,
            event_payload=rec_payload,
            signer_identity=identity,
            signature=_sign_anchor(signer, identity, rec_payload),
            tier=AuditTier.RECOVERY.value,
        )
        assert rec_receipt.sequence == i
        assert rec_receipt.previous_anchor_hash == prev_recovery
        prev_recovery = rec_receipt.anchor_hash

        safety_payload = {"subtype": "vault_kek_denial", "alg_id": "a", "i": i}
        safety_receipt = dispatcher.dispatch(
            event_type=_EVENT_TYPE,
            event_payload=safety_payload,
            signer_identity=identity,
            signature=_sign_anchor(signer, identity, safety_payload),
            tier=AuditTier.SAFETY.value,
        )
        assert safety_receipt.sequence == i
        assert safety_receipt.previous_anchor_hash == prev_safety
        prev_safety = safety_receipt.anchor_hash

    # Both tiers accepted all 5 dispatches despite being "sealed".
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 5
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 5
