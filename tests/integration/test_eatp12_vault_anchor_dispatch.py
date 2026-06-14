# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration: D2 anchor builders dispatched through the D1 dispatcher.

Builds real ``event_payload`` envelopes via
:mod:`kailash.trust.vault.anchors` (W2-D2) and dispatches them through the
REAL :class:`~kailash.trust.vault.dispatch.AuditDispatcher` (W2-D1) — real
per-tier :class:`~kailash.delegate.audit.AuditChainEngine`, real
:class:`~kailash.trust.chain.TrustLineageChain`, real Ed25519 signer +
:class:`~kailash.delegate.verifier.Ed25519Verifier`. NO mocks (Tier-2: real
infrastructure, no ``@patch`` / ``MagicMock`` / ``unittest.mock``).

Confirms the D2 builder output is a valid D1 dispatch input end-to-end:

- a ``vault_key_backup`` envelope dispatches to ``recovery`` and the receipt
  carries ``event_subtype == "vault_key_backup"`` (N12-AU-02 outcome → recovery);
- a denial envelope dispatches to ``safety`` (N12-AU-01 denial → safety).
"""

from __future__ import annotations

import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import DelegateEventType, content_signing_bytes
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.vault.anchors import build_backup_anchor, build_denial_anchor
from kailash.trust.vault.dispatch import (
    AuditDispatcher,
    AuditTier,
    require_receipt_or_abort,
)

_EVENT_TYPE = DelegateEventType.EXTERNAL_SIDE_EFFECT.value

# §12.1 fixed-input stand-ins for an end-to-end build+dispatch (the byte-pin
# is tested in the Tier-1 suite; here we only exercise the wiring).
_HOLDERS = ["holder:h1", "holder:h2", "holder:h3", "holder:h4", "holder:h5"]
_SHARD_COMMITMENTS = [
    "aa" * 32,
    "bb" * 32,
    "cc" * 32,
    "dd" * 32,
    "ee" * 32,
]
_SLIP39 = {
    "extendable": True,
    "iteration_exponent": 1,
    "group_threshold": 1,
    "master_secret_bits": 128,
}
_TS = "2026-06-12T00:00:00Z"


def _build_signer() -> tuple[DelegateIdentity, Ed25519Verifier, Callable[[bytes], str]]:
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-vault-anchor",
        role_binding_ref="rb-vault-anchor",
        genesis_ref="gen-vault-anchor",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


def _sign(signer, identity, payload) -> str:
    return signer(content_signing_bytes(_EVENT_TYPE, payload, identity.delegate_id))


@pytest.mark.integration
def test_backup_envelope_dispatches_to_recovery_with_subtype():
    """N12-AU-02 — a built backup envelope → recovery; receipt carries the subtype."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    payload = build_backup_anchor(
        alg_id="eatp-v1",
        k=3,
        n=5,
        holders=_HOLDERS,
        shard_count=5,
        vault_id="vault:fixture-0001",
        kek_generation=7,
        kek_identity_commitment="f3" * 32,
        kek_commitment_alg="eatp-v1",
        kcv="00051364b85b0a43",
        shard_commitments=_SHARD_COMMITMENTS,
        slip39_params=_SLIP39,
        principal="delegate:requester-01",
        timestamp=_TS,
        time_attested=True,
    )

    receipt = require_receipt_or_abort(
        dispatcher.dispatch(
            event_type=_EVENT_TYPE,
            event_payload=payload,
            signer_identity=identity,
            signature=_sign(signer, identity, payload),
            tier=AuditTier.RECOVERY.value,
        )
    )
    assert receipt.tier == "recovery"
    assert receipt.event_subtype == "vault_key_backup"
    assert receipt.previous_anchor_hash == ""  # genesis of the recovery chain
    assert len(receipt.anchor_hash) == 64
    assert dispatcher.head_hash(AuditTier.RECOVERY.value) == receipt.anchor_hash


@pytest.mark.integration
def test_denial_envelope_dispatches_to_safety():
    """N12-AU-01 — a built denial envelope → safety tier with the denial subtype."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    payload = build_denial_anchor(
        subtype="vault_key_restore_denied",
        principal="delegate:prober-99",
        missing_capability_or_scope="vault:restore",
        target_handle_ref="opaque:href-abcdef",
        timestamp=_TS,
        time_attested=True,
    )

    receipt = require_receipt_or_abort(
        dispatcher.dispatch(
            event_type=_EVENT_TYPE,
            event_payload=payload,
            signer_identity=identity,
            signature=_sign(signer, identity, payload),
            tier=AuditTier.SAFETY.value,
        )
    )
    assert receipt.tier == "safety"
    assert receipt.event_subtype == "vault_key_restore_denied"
    # recovery remained untouched (per-tier chains, N12-AU-01a)
    assert dispatcher.head_hash(AuditTier.RECOVERY.value) is None
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1
