# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the EATP-12 Complete-level knobs (W5-X1, §4.2 / §4.3).

Exercises the X1 Complete-level gates END-TO-END through real cryptography —
real Ed25519 approver/witness signatures verified through a real
:class:`~cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PublicKey`
``verify_token`` callable, real HMAC per-holder wrapping. NO mocks
(``rules/testing.md`` Tier-2: real infrastructure).

Conformance coverage (EATP-12 §4.2 / §4.3, N12-CL-03/CL-03(c)/CL-05/SH-02 — the
4 Complete-optional IDs):

- **N12-CL-03 governance-approver** (``verify_governance_approval``):
  (a) requires ``vault:approve`` scoped to the vault tenant/domain;
  (b) forbids self-approval on BOTH the principal AND the ``delegate_id`` axis
      (a second credential under the same actor does NOT satisfy distinctness);
  (c) verifies the approver's signed token over the canonical approval pre-image;
  (d) fail-closed ``missing-clearance`` on any failure; returns the to-embed
      payload (the V8/Wave-6 anchor-embedding consumes it);
- **N12-CL-05 ceremony witness** (``verify_ceremony_witness``): requires
  ``vault:witness``, witness distinct from requester AND from any configured
  approver, signed witness token verified; self-witness fails;
- **N12-SH-02 per-holder wrapping** (``wrap_shard_for_holder`` /
  ``unwrap_shard_for_holder``): HMAC wrap round-trips; a revoked holder fails
  ``revoked-holder``; a tampered wrap / wrong passphrase fails ``corrupted-shard``
  (integrity-only, never conflated with foreign-shard ``unknown-shard``).
"""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.complete import (
    APPROVE_CAPABILITY,
    WITNESS_CAPABILITY,
    CeremonyWitness,
    GovernanceApproval,
    HolderRevocationRegistry,
    approval_pre_image,
    unwrap_shard_for_holder,
    verify_ceremony_witness,
    verify_governance_approval,
    witness_pre_image,
    wrap_shard_for_holder,
)
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek
from kailash.trust.vault.types import ClearanceContext

_VAULT = "vault-x1"
_GEN = 7
_OP = "restore-forced-stale"


def _resolved() -> ResolvedKek:
    return ResolvedKek(
        master_secret=bytes(32),
        key_class=KeyClass.KEK,
        kek_generation=_GEN,
        key_id="kek-handle-x1",
        passphrase_provenance="vault-derived:v1",
        vault_tenant="t1",
        vault_domain="d1",
    )


def _clearance(principal: str, *caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal=principal, tenant="t1", domain="d1", capabilities=tuple(caps)
    )


class _SignerPair:
    """A real Ed25519 keypair + a verify_token callable bound to its registry."""

    def __init__(self) -> None:
        self._keys: dict[str, Ed25519PublicKey] = {}

    def enroll(self, delegate_id: str) -> Ed25519PrivateKey:
        priv = Ed25519PrivateKey.generate()
        self._keys[delegate_id] = priv.public_key()
        return priv

    def verify_token(
        self, pre_image: bytes, signature_hex: str, delegate_id: str
    ) -> bool:
        pub = self._keys.get(delegate_id)
        if pub is None:
            return False
        try:
            pub.verify(bytes.fromhex(signature_hex), pre_image)
            return True
        except (InvalidSignature, ValueError):
            return False


# ---------------------------------------------------------------------------
# N12-CL-03 — governance-approver HELD gate
# ---------------------------------------------------------------------------


def _signed_approval(
    priv: Ed25519PrivateKey,
    *,
    approver_principal,
    approver_delegate_id,
    requester_principal,
):
    sig = priv.sign(
        approval_pre_image(
            vault_id=_VAULT,
            kek_generation=_GEN,
            operation=_OP,
            requester_principal=requester_principal,
        )
    ).hex()
    return GovernanceApproval(
        approver_principal=approver_principal,
        approver_delegate_id=approver_delegate_id,
        approval_signature=sig,
    )


@pytest.mark.integration
def test_governance_approval_valid_returns_embeddable_payload():
    """N12-CL-03: a distinct approver with vault:approve + valid signed token passes."""
    pair = _SignerPair()
    apriv = pair.enroll("delg-approver")
    approval = _signed_approval(
        apriv,
        approver_principal="approver-1",
        approver_delegate_id="delg-approver",
        requester_principal="agent-1",
    )

    payload = verify_governance_approval(
        approval,
        vault_id=_VAULT,
        requester_principal="agent-1",
        requester_delegate_id="delg-requester",
        approver_clearance=_clearance("approver-1", APPROVE_CAPABILITY),
        resolved=_resolved(),
        operation=_OP,
        verify_token=pair.verify_token,
    )
    # The returned payload is the sub-object embedded under event_payload["approval"]
    # (covered by content_signing_bytes when the anchor is signed — N12-CL-03(c)).
    assert payload["approver_principal"] == "approver-1"
    assert payload["approver_delegate_id"] == "delg-approver"
    assert payload["approval_signature"] == approval.approval_signature


@pytest.mark.integration
def test_self_approval_rejected_on_principal_axis():
    """N12-CL-03(b): approver principal == requester → missing-clearance."""
    pair = _SignerPair()
    apriv = pair.enroll("delg-approver")
    approval = _signed_approval(
        apriv,
        approver_principal="agent-1",  # SAME as requester
        approver_delegate_id="delg-approver",
        requester_principal="agent-1",
    )
    with pytest.raises(VaultBindingError) as ei:
        verify_governance_approval(
            approval,
            vault_id=_VAULT,
            requester_principal="agent-1",
            requester_delegate_id="delg-requester",
            approver_clearance=_clearance("agent-1", APPROVE_CAPABILITY),
            resolved=_resolved(),
            operation=_OP,
            verify_token=pair.verify_token,
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_self_approval_rejected_on_delegate_id_axis():
    """N12-CL-03(b): a SECOND credential under the same actor (same delegate_id) fails."""
    pair = _SignerPair()
    apriv = pair.enroll("delg-shared")  # same delegate_id as requester
    approval = _signed_approval(
        apriv,
        approver_principal="approver-1",
        approver_delegate_id="delg-shared",
        requester_principal="agent-1",
    )
    with pytest.raises(VaultBindingError) as ei:
        verify_governance_approval(
            approval,
            vault_id=_VAULT,
            requester_principal="agent-1",
            requester_delegate_id="delg-shared",  # SAME delegate_id
            approver_clearance=_clearance("approver-1", APPROVE_CAPABILITY),
            resolved=_resolved(),
            operation=_OP,
            verify_token=pair.verify_token,
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_approval_without_vault_approve_capability_rejected():
    """N12-CL-03(a): approver lacking vault:approve → missing-clearance."""
    pair = _SignerPair()
    apriv = pair.enroll("delg-approver")
    approval = _signed_approval(
        apriv,
        approver_principal="approver-1",
        approver_delegate_id="delg-approver",
        requester_principal="agent-1",
    )
    with pytest.raises(VaultBindingError) as ei:
        verify_governance_approval(
            approval,
            vault_id=_VAULT,
            requester_principal="agent-1",
            requester_delegate_id="delg-requester",
            approver_clearance=_clearance(
                "approver-1", "vault:restore"
            ),  # no vault:approve
            resolved=_resolved(),
            operation=_OP,
            verify_token=pair.verify_token,
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_forged_approval_signature_rejected_fail_closed():
    """N12-CL-03(c)/(d): a forged/wrong signature is rejected fail-closed."""
    pair = _SignerPair()
    pair.enroll("delg-approver")
    # Sign with a DIFFERENT (unenrolled) key — the registered key won't verify it.
    forger = Ed25519PrivateKey.generate()
    approval = _signed_approval(
        forger,
        approver_principal="approver-1",
        approver_delegate_id="delg-approver",
        requester_principal="agent-1",
    )
    with pytest.raises(VaultBindingError) as ei:
        verify_governance_approval(
            approval,
            vault_id=_VAULT,
            requester_principal="agent-1",
            requester_delegate_id="delg-requester",
            approver_clearance=_clearance("approver-1", APPROVE_CAPABILITY),
            resolved=_resolved(),
            operation=_OP,
            verify_token=pair.verify_token,
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_approval_wrong_tenant_rejected():
    """N12-CL-03(a): approver bound to a different tenant → missing-clearance."""
    pair = _SignerPair()
    apriv = pair.enroll("delg-approver")
    approval = _signed_approval(
        apriv,
        approver_principal="approver-1",
        approver_delegate_id="delg-approver",
        requester_principal="agent-1",
    )
    wrong_tenant = ClearanceContext(
        principal="approver-1",
        tenant="t2",
        domain="d1",
        capabilities=(APPROVE_CAPABILITY,),
    )
    with pytest.raises(VaultBindingError) as ei:
        verify_governance_approval(
            approval,
            vault_id=_VAULT,
            requester_principal="agent-1",
            requester_delegate_id="delg-requester",
            approver_clearance=wrong_tenant,
            resolved=_resolved(),
            operation=_OP,
            verify_token=pair.verify_token,
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


# ---------------------------------------------------------------------------
# N12-CL-05 — ceremony witness gate
# ---------------------------------------------------------------------------


def _signed_witness(
    priv,
    *,
    witness_principal,
    witness_delegate_id,
    requester_principal,
    operation="backup",
):
    sig = priv.sign(
        witness_pre_image(
            vault_id=_VAULT,
            kek_generation=_GEN,
            operation=operation,
            requester_principal=requester_principal,
        )
    ).hex()
    return CeremonyWitness(
        witness_principal=witness_principal,
        witness_delegate_id=witness_delegate_id,
        witness_signature=sig,
    )


@pytest.mark.integration
def test_ceremony_witness_valid_returns_embeddable_payload():
    """N12-CL-05: a distinct witness with vault:witness + valid token passes."""
    pair = _SignerPair()
    wpriv = pair.enroll("delg-witness")
    witness = _signed_witness(
        wpriv,
        witness_principal="witness-1",
        witness_delegate_id="delg-witness",
        requester_principal="agent-1",
    )
    payload = verify_ceremony_witness(
        witness,
        vault_id=_VAULT,
        requester_principal="agent-1",
        requester_delegate_id="delg-requester",
        resolved=_resolved(),
        operation="backup",
        verify_token=pair.verify_token,
        witness_clearance=_clearance("witness-1", WITNESS_CAPABILITY),
        approver_principal="approver-1",
        approver_delegate_id="delg-approver",
    )
    assert payload["witness_principal"] == "witness-1"
    assert payload["witness_signature"] == witness.witness_signature


@pytest.mark.integration
def test_self_witness_rejected():
    """N12-CL-05: witness == requester → missing-clearance."""
    pair = _SignerPair()
    wpriv = pair.enroll("delg-witness")
    witness = _signed_witness(
        wpriv,
        witness_principal="agent-1",  # SAME as requester
        witness_delegate_id="delg-witness",
        requester_principal="agent-1",
    )
    with pytest.raises(VaultBindingError) as ei:
        verify_ceremony_witness(
            witness,
            vault_id=_VAULT,
            requester_principal="agent-1",
            requester_delegate_id="delg-requester",
            resolved=_resolved(),
            operation="backup",
            verify_token=pair.verify_token,
            witness_clearance=_clearance("agent-1", WITNESS_CAPABILITY),
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_witness_equal_to_approver_rejected():
    """N12-CL-05: witness MUST be independent of the configured approver."""
    pair = _SignerPair()
    wpriv = pair.enroll("delg-witness")
    witness = _signed_witness(
        wpriv,
        witness_principal="approver-1",  # SAME as approver
        witness_delegate_id="delg-witness",
        requester_principal="agent-1",
    )
    with pytest.raises(VaultBindingError) as ei:
        verify_ceremony_witness(
            witness,
            vault_id=_VAULT,
            requester_principal="agent-1",
            requester_delegate_id="delg-requester",
            resolved=_resolved(),
            operation="backup",
            verify_token=pair.verify_token,
            witness_clearance=_clearance("approver-1", WITNESS_CAPABILITY),
            approver_principal="approver-1",
            approver_delegate_id="delg-approver",
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


# ---------------------------------------------------------------------------
# N12-SH-02 — per-holder wrapping
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_per_holder_wrap_round_trips():
    """N12-SH-02: wrap then unwrap under the same passphrase returns the shard."""
    shard = "word1 word2 word3 word4"
    wrapped = wrap_shard_for_holder(shard, holder_id="h1", holder_passphrase=b"pw-h1")
    assert wrapped["holder_id"] == "h1"
    assert len(wrapped["wrap_mac"]) == 64
    out = unwrap_shard_for_holder(wrapped, holder_passphrase=b"pw-h1")
    assert out == shard


@pytest.mark.integration
def test_per_holder_wrap_revoked_holder_fails_revoked_holder():
    """N12-SH-02: a revoked holder's wrapped shard fails revoked-holder on unwrap."""
    shard = "word1 word2 word3 word4"
    wrapped = wrap_shard_for_holder(shard, holder_id="h1", holder_passphrase=b"pw-h1")
    reg = HolderRevocationRegistry()
    reg.revoke("h1")
    with pytest.raises(VaultBindingError) as ei:
        unwrap_shard_for_holder(
            wrapped, holder_passphrase=b"pw-h1", revocation_registry=reg
        )
    assert ei.value.code is N12FT01Code.REVOKED_HOLDER


@pytest.mark.integration
def test_per_holder_wrap_tamper_fails_corrupted_shard_not_unknown_shard():
    """N12-SH-02: a tampered wrap / wrong passphrase is corrupted-shard, NOT unknown-shard.

    Integrity failure (tamper / wrong passphrase) MUST surface as corrupted-shard
    — distinct from the foreign-shard unknown-shard code (N12-CB-03), which means
    'not in the distribution', a different failure class."""
    shard = "word1 word2 word3 word4"
    wrapped = wrap_shard_for_holder(shard, holder_id="h1", holder_passphrase=b"pw-h1")
    with pytest.raises(VaultBindingError) as ei:
        unwrap_shard_for_holder(wrapped, holder_passphrase=b"wrong-passphrase")
    assert ei.value.code is N12FT01Code.CORRUPTED_SHARD
    assert ei.value.code is not N12FT01Code.UNKNOWN_SHARD
