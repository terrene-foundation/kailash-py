# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 W6-X1-EMBED — Complete-level governance binding into the hot path (V8).

This is the V8 (Complete-level) conformance vector AND the closure of the Wave-5
LOW-1 wiring gap (journal/0010 G3): the X1 gates
(:func:`~kailash.trust.vault.complete.verify_governance_approval` /
:func:`~kailash.trust.vault.complete.verify_ceremony_witness`) are now WIRED into
``restore_vault_key`` / ``back_up_vault_key`` so the CL-03(c)/CL-05 "token bound
into the signed ``event_payload`` (covered by ``content_signing_bytes``)"
guarantee (spec §4.2 N12-CL-03(c)) is actually realized.

Exercised against the REAL substrate (real SLIP-0039, real Ed25519 ``verify_token``,
real D1 dispatcher, real D2 anchor builders, real SQLitePostureStore) — NO mocks
(``rules/testing.md`` Tier-2). Coverage:

* **Embed (N12-CL-03(c))** — a valid governance approval on a forced-stale restore
  succeeds AND lands under the dispatched ``vault_key_restore_forced_stale``
  anchor's ``event_payload["approval"]`` on BOTH the recovery + safety tiers, and
  the approval sub-object is byte-covered by ``content_signing_bytes`` (a missing/
  forged approval is therefore cryptographically detectable).
* **Mandatory (N12-SG-03)** — a missing approval on a Complete forced-stale restore
  is rejected ``missing-clearance`` with a ``vault_key_restore_denied`` denial to
  the safety tier and NO recovery anchor (fail-closed before the KEK materializes).
* **Fail-closed verify** — a forged approval signature, and a self-approval
  (approver == requester), are both rejected ``missing-clearance``.
* **Conformant byte-unchanged** — a Conformant forced-stale restore (no approval)
  succeeds and the anchor carries NO ``approval`` key (the §12.11 byte-pin holds).
* **Cooling-off HELD override (N12-CL-04 × CL-03)** — a 2nd materializing restore
  by a principal inside the 7-day cooling-off window is SUSPENDED, but a VERIFIED
  governance approval lifts the suspension; without it the op is denied.
* **Ceremony witness (N12-CL-05)** — a Complete backup requires an independent
  witness bound into the ``vault_key_backup`` anchor; a missing or self-witness is
  rejected ``missing-clearance``.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from kailash.delegate.audit import content_signing_bytes
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.posture.posture_store import SQLitePostureStore
from kailash.trust.vault.anchors import build_backup_anchor, build_kek_rotation_anchor
from kailash.trust.vault.backup import back_up_vault_key, restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.complete import (
    CeremonyWitness,
    ConformanceLevel,
    GovernanceApproval,
    approval_pre_image,
    witness_pre_image,
)
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.holder_registry import default_holder_registry
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.shamir import ShamirRitual, generate, serialize_shard
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KEK_OLD = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_GEN_OLD = 7
_GEN_NEW = 8
_KEY_ID = "kek-handle-x1"
_VAULT_ID = "vault-x1"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"
_HOLDERS = ["h1", "h2", "h3", "h4", "h5"]
_REQUESTER = "agent-x1"
_APPROVER = "approver-x1"
_WITNESS = "witness-x1"


# ---------------------------------------------------------------------------
# Real-infra harness (mirrors the stale-guard wiring suite; NO mocks)
# ---------------------------------------------------------------------------


def _shard_commitments(shards) -> list[str]:
    return [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]


class _Resolver:
    """Deployment-supplied trusted resolver (NOT a mock) returning the old KEK."""

    def __init__(self, *, secret: bytes = _KEK_OLD, generation: int = _GEN_OLD) -> None:
        self._secret = secret
        self._generation = generation

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=self._secret,
            key_class=KeyClass.KEK,
            kek_generation=self._generation,
            key_id=_KEY_ID,
            passphrase_provenance=_PROVENANCE,
            vault_tenant="t1",
            vault_domain="d1",
        )


def _build_signer() -> tuple[DelegateIdentity, Ed25519Verifier, Callable[[bytes], str]]:
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-x1",
        role_binding_ref="rb-x1",
        genesis_ref="gen-x1",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


class _TokenKeyring:
    """A real Ed25519 keyring + verify_token callable (the deployment verifier)."""

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


def _handle(generation: int = _GEN_OLD) -> VaultKeyHandle:
    return VaultKeyHandle(key_id=_KEY_ID, vault_id=_VAULT_ID, kek_generation=generation)


def _clearance(principal: str, *caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal=principal, tenant="t1", domain="d1", capabilities=tuple(caps)
    )


def _dispatch(dispatcher, identity, signer, payload, tier) -> None:
    pre = content_signing_bytes("external_side_effect", payload, identity.delegate_id)
    dispatcher.dispatch("external_side_effect", payload, identity, signer(pre), tier)


def _old_gen_commitment(secret: bytes = _KEK_OLD) -> str:
    return kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_OLD,
        master_secret=secret,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )


def _seed_old_gen_backup_anchor(
    dispatcher, identity, signer, *, shards, commitment, generation
) -> list[str]:
    commitments = _shard_commitments(shards)
    payload = build_backup_anchor(
        alg_id=_ALG,
        k=3,
        n=5,
        holders=_HOLDERS,
        shard_count=5,
        vault_id=_VAULT_ID,
        kek_generation=generation,
        kek_identity_commitment=commitment,
        kek_commitment_alg=_ALG,
        kcv="0" * 16,
        shard_commitments=commitments,
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": 256,
        },
        principal=_REQUESTER,
        timestamp="unverified",
        time_attested=False,
        side_channel_hardened=False,
    )
    _dispatch(dispatcher, identity, signer, payload, AuditTier.RECOVERY.value)
    return commitments


def _seed_rotation_to_new_gen(
    dispatcher, identity, signer, *, new_secret, new_shards
) -> None:
    new_commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_NEW,
        master_secret=new_secret,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    payload = build_kek_rotation_anchor(
        alg_id=_ALG,
        prior_kek_generation=_GEN_OLD,
        kek_generation=_GEN_NEW,
        vault_id=_VAULT_ID,
        k=3,
        n=5,
        holders=_HOLDERS,
        shard_count=5,
        shard_commitments=_shard_commitments(new_shards),
        kek_identity_commitment=new_commitment,
        kek_commitment_alg=_ALG,
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": 256,
        },
        for_cause=False,
        principal=_REQUESTER,
        timestamp="unverified",
        time_attested=False,
    )
    _dispatch(dispatcher, identity, signer, payload, AuditTier.RECOVERY.value)


def _seed_forced_stale_setup(dispatcher, identity, signer, registry):
    """Register the old-gen commitment + distribution anchor + a rotation to new gen.

    Returns the old-gen shards (the valid presenting set) + recorded commitments.
    """
    old_shards = generate(_KEK_OLD, ShamirRitual(threshold=3, total_shards=5))
    new_secret = bytes.fromhex("ff" * 32)
    new_shards = generate(new_secret, ShamirRitual(threshold=3, total_shards=5))
    commitment = _old_gen_commitment()
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_OLD,
        kek_commitment_alg=_ALG,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    old_commitments = _seed_old_gen_backup_anchor(
        dispatcher,
        identity,
        signer,
        shards=old_shards,
        commitment=commitment,
        generation=_GEN_OLD,
    )
    _seed_rotation_to_new_gen(
        dispatcher, identity, signer, new_secret=new_secret, new_shards=new_shards
    )
    return old_shards, old_commitments


@pytest.fixture
def posture_store():
    """A REAL SQLitePostureStore against a temp DB (Tier-2, NO mock)."""
    fd, path = tempfile.mkstemp(suffix="-x1-postures.db")
    os.close(fd)
    os.unlink(path)
    store = SQLitePostureStore(path)
    try:
        yield store
    finally:
        store.close()
        if os.path.exists(path):
            os.unlink(path)


@pytest.fixture(autouse=True)
def _isolate_default_singletons():
    from kailash.trust.vault.registry import default_commitment_registry
    from kailash.trust.vault.stale_guard import default_compromised_generation_denylist

    default_commitment_registry()._store.clear()
    default_compromised_generation_denylist()._revoked.clear()
    default_holder_registry()._registered.clear()
    default_holder_registry().register_all(_HOLDERS)
    yield
    default_commitment_registry()._store.clear()
    default_compromised_generation_denylist()._revoked.clear()
    default_holder_registry()._registered.clear()


def _signed_approval(
    keyring: _TokenKeyring,
    *,
    approver_delegate_id: str,
    requester_principal: str,
    operation: str,
    kek_generation: int,
    requester_delegate_id: str = "dlg-requester",
    approver_principal: str = _APPROVER,
    valid: bool = True,
) -> GovernanceApproval:
    priv = keyring.enroll(approver_delegate_id)
    pre = approval_pre_image(
        vault_id=_VAULT_ID,
        kek_generation=kek_generation,
        operation=operation,
        requester_principal=requester_principal,
        requester_delegate_id=requester_delegate_id,
    )
    sig = priv.sign(pre).hex()
    if not valid:
        # Flip the signature payload so verify_token rejects it (forged token).
        sig = priv.sign(b"different-message").hex()
    return GovernanceApproval(
        approver_principal=approver_principal,
        approver_delegate_id=approver_delegate_id,
        approval_signature=sig,
    )


# ===========================================================================
# V8 — forced-stale restore × governance approval (N12-CL-03 / SG-03)
# ===========================================================================


@pytest.mark.integration
def test_v8_complete_forced_stale_embeds_verified_approval(posture_store):
    """A valid approval on a Complete forced-stale restore embeds into the signed
    anchor on BOTH tiers AND is byte-covered by content_signing_bytes (N12-CL-03(c))."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    keyring = _TokenKeyring()
    old_shards, _ = _seed_forced_stale_setup(dispatcher, identity, signer, registry)

    approval = _signed_approval(
        keyring,
        approver_delegate_id="dlg-approver",
        requester_principal=_REQUESTER,
        operation="restore-forced-stale",
        kek_generation=_GEN_OLD,
    )

    receipt = restore_vault_key(
        old_shards[:3],
        _handle(_GEN_OLD),
        _clearance(_REQUESTER, "vault:restore", "vault:restore-stale"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        force_stale=True,
        conformance_level=ConformanceLevel.COMPLETE,
        approval=approval,
        approver_clearance=_clearance(_APPROVER, "vault:approve"),
        requester_delegate_id="dlg-requester",
        verify_token=keyring.verify_token,
    )
    assert receipt.forced_stale is True

    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    saf = dispatcher._engines[AuditTier.SAFETY.value].entries
    rec_forced = [
        e for e in rec if e.event_payload["subtype"] == "vault_key_restore_forced_stale"
    ]
    saf_forced = [
        e for e in saf if e.event_payload["subtype"] == "vault_key_restore_forced_stale"
    ]
    assert len(rec_forced) == 1 and len(saf_forced) == 1
    # The approval sub-object is embedded under event_payload["approval"].
    embedded = rec_forced[0].event_payload["approval"]
    assert embedded == {
        "approver_principal": _APPROVER,
        "approver_delegate_id": "dlg-approver",
        "approval_signature": approval.approval_signature,
    }
    # And it is byte-covered by content_signing_bytes (the signed pre-image): the
    # approver's signature literally appears in the canonical signed bytes.
    signed_bytes = content_signing_bytes(
        "external_side_effect", rec_forced[0].event_payload, identity.delegate_id
    )
    assert b'"approval"' in signed_bytes
    assert approval.approval_signature.encode() in signed_bytes
    # Dual-emit carries the SAME embedded approval on the safety tier.
    assert saf_forced[0].event_payload["approval"] == embedded


@pytest.mark.integration
def test_v8_complete_forced_stale_missing_approval_denied(posture_store):
    """A Complete forced-stale restore with NO approval is rejected missing-clearance
    + denial to safety, NO recovery anchor (N12-SG-03 mandatory, fail-closed)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    old_shards, _ = _seed_forced_stale_setup(dispatcher, identity, signer, registry)
    rec_before = len(dispatcher._engines[AuditTier.RECOVERY.value].entries)

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance(_REQUESTER, "vault:restore", "vault:restore-stale"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            force_stale=True,
            conformance_level=ConformanceLevel.COMPLETE,
            # approval omitted
        )
    assert exc.value.code == N12FT01Code.MISSING_CLEARANCE
    saf = dispatcher._engines[AuditTier.SAFETY.value].entries
    assert saf[-1].event_payload["subtype"] == "vault_key_restore_denied"
    # No NEW recovery anchor (the forced-stale outcome anchor was never built).
    rec_after = [
        e
        for e in dispatcher._engines[AuditTier.RECOVERY.value].entries
        if e.event_payload["subtype"] == "vault_key_restore_forced_stale"
    ]
    assert rec_after == []
    assert len(dispatcher._engines[AuditTier.RECOVERY.value].entries) == rec_before


@pytest.mark.integration
def test_v8_complete_forced_stale_forged_approval_denied(posture_store):
    """A forged approval signature is rejected missing-clearance (fail-closed verify)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    keyring = _TokenKeyring()
    old_shards, _ = _seed_forced_stale_setup(dispatcher, identity, signer, registry)
    forged = _signed_approval(
        keyring,
        approver_delegate_id="dlg-approver",
        requester_principal=_REQUESTER,
        operation="restore-forced-stale",
        kek_generation=_GEN_OLD,
        valid=False,
    )
    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance(_REQUESTER, "vault:restore", "vault:restore-stale"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            force_stale=True,
            conformance_level=ConformanceLevel.COMPLETE,
            approval=forged,
            approver_clearance=_clearance(_APPROVER, "vault:approve"),
            requester_delegate_id="dlg-requester",
            verify_token=keyring.verify_token,
        )
    assert exc.value.code == N12FT01Code.MISSING_CLEARANCE
    assert (
        dispatcher._engines[AuditTier.SAFETY.value].entries[-1].event_payload["subtype"]
        == "vault_key_restore_denied"
    )


@pytest.mark.integration
def test_v8_self_approval_rejected(posture_store):
    """An approver whose delegate_id == the requester's is rejected (no self-approval)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    keyring = _TokenKeyring()
    old_shards, _ = _seed_forced_stale_setup(dispatcher, identity, signer, registry)
    # Approver principal == requester principal (self-approval on the principal axis).
    self_approval = _signed_approval(
        keyring,
        approver_delegate_id="dlg-requester",
        requester_principal=_REQUESTER,
        operation="restore-forced-stale",
        kek_generation=_GEN_OLD,
        approver_principal=_REQUESTER,
    )
    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance(_REQUESTER, "vault:restore", "vault:restore-stale"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            force_stale=True,
            conformance_level=ConformanceLevel.COMPLETE,
            approval=self_approval,
            approver_clearance=_clearance(_REQUESTER, "vault:approve"),
            requester_delegate_id="dlg-requester",
            verify_token=keyring.verify_token,
        )
    assert exc.value.code == N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_v8_conformant_forced_stale_anchor_has_no_approval(posture_store):
    """A Conformant forced-stale restore (no approval) succeeds and the anchor carries
    NO approval key — the §12.11 byte-pin is preserved (Conformant byte-unchanged)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    old_shards, _ = _seed_forced_stale_setup(dispatcher, identity, signer, registry)

    receipt = restore_vault_key(
        old_shards[:3],
        _handle(_GEN_OLD),
        _clearance(_REQUESTER, "vault:restore", "vault:restore-stale"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        force_stale=True,
        # conformance_level defaults to CONFORMANT; no approval.
    )
    assert receipt.forced_stale is True
    forced = [
        e
        for e in dispatcher._engines[AuditTier.RECOVERY.value].entries
        if e.event_payload["subtype"] == "vault_key_restore_forced_stale"
    ][0]
    assert "approval" not in forced.event_payload


# ===========================================================================
# V8 — cooling-off HELD override (N12-CL-04 × CL-03)
# ===========================================================================


@pytest.mark.integration
def test_v8_cooling_off_held_override_lifts_suspension(posture_store):
    """A principal inside the 7-day cooling-off window is suspended, but a VERIFIED
    governance approval lifts it; without the approval the op is denied (N12-CL-04)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    keyring = _TokenKeyring()

    # Register the old-gen commitment + distribution so an ORDINARY restore at the
    # current generation passes the crypto gates.
    old_shards = generate(_KEK_OLD, ShamirRitual(threshold=3, total_shards=5))
    commitment = _old_gen_commitment()
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_OLD,
        kek_commitment_alg=_ALG,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    _seed_old_gen_backup_anchor(
        dispatcher,
        identity,
        signer,
        shards=old_shards,
        commitment=commitment,
        generation=_GEN_OLD,
    )

    # Put the principal INSIDE the cooling-off window: record a downgrade now.
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
    from kailash.trust.vault.stale_guard import trigger_d6_posture_downgrade

    trigger_d6_posture_downgrade(
        posture_store, principal=_REQUESTER, forced_stale=False, now=now
    )
    later = now + timedelta(days=1)  # still within the 7-day window

    # Without an approval → the suspended vault:restore token denies.
    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance(_REQUESTER, "vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            trust_anchored_now=later,
            conformance_level=ConformanceLevel.COMPLETE,
        )
    assert exc.value.code == N12FT01Code.MISSING_CLEARANCE

    # WITH a verified approval (operation="restore") → the HELD action lifts it.
    approval = _signed_approval(
        keyring,
        approver_delegate_id="dlg-approver",
        requester_principal=_REQUESTER,
        operation="restore",
        kek_generation=_GEN_OLD,
    )
    receipt = restore_vault_key(
        old_shards[:3],
        _handle(_GEN_OLD),
        _clearance(_REQUESTER, "vault:restore"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        trust_anchored_now=later,
        conformance_level=ConformanceLevel.COMPLETE,
        approval=approval,
        approver_clearance=_clearance(_APPROVER, "vault:approve"),
        requester_delegate_id="dlg-requester",
        verify_token=keyring.verify_token,
    )
    restore = [
        e
        for e in dispatcher._engines[AuditTier.RECOVERY.value].entries
        if e.event_payload["subtype"] == "vault_key_restore"
    ][-1]
    assert restore.event_payload["approval"]["approval_signature"] == (
        approval.approval_signature
    )
    assert receipt.kek_generation == _GEN_OLD


# ===========================================================================
# V8 — backup ceremony witness (N12-CL-05)
# ===========================================================================


def _signed_witness(
    keyring: _TokenKeyring,
    *,
    witness_delegate_id: str,
    requester_principal: str,
    kek_generation: int,
    requester_delegate_id: str = "dlg-requester",
    witness_principal: str = _WITNESS,
) -> CeremonyWitness:
    priv = keyring.enroll(witness_delegate_id)
    pre = witness_pre_image(
        vault_id=_VAULT_ID,
        kek_generation=kek_generation,
        operation="backup",
        requester_principal=requester_principal,
        requester_delegate_id=requester_delegate_id,
    )
    return CeremonyWitness(
        witness_principal=witness_principal,
        witness_delegate_id=witness_delegate_id,
        witness_signature=priv.sign(pre).hex(),
    )


def _backup(dispatcher, identity, signer, *, witness=None, **kw):
    return back_up_vault_key(
        _handle(_GEN_OLD),
        ShamirRitual(threshold=3, total_shards=5),
        _clearance(_REQUESTER, "vault:backup"),
        _HOLDERS,
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        witness=witness,
        **kw,
    )


@pytest.mark.integration
def test_v8_complete_backup_embeds_verified_witness():
    """A Complete backup binds an independent witness into the vault_key_backup
    anchor (covered by content_signing_bytes); a self-witness is rejected (N12-CL-05).
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    keyring = _TokenKeyring()
    witness = _signed_witness(
        keyring,
        witness_delegate_id="dlg-witness",
        requester_principal=_REQUESTER,
        kek_generation=_GEN_OLD,
    )
    _backup(
        dispatcher,
        identity,
        signer,
        witness=witness,
        conformance_level=ConformanceLevel.COMPLETE,
        witness_clearance=_clearance(_WITNESS, "vault:witness"),
        requester_delegate_id="dlg-requester",
        verify_token=keyring.verify_token,
    )
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    backup = [e for e in rec if e.event_payload["subtype"] == "vault_key_backup"][-1]
    assert backup.event_payload["witness"] == {
        "witness_principal": _WITNESS,
        "witness_delegate_id": "dlg-witness",
        "witness_signature": witness.witness_signature,
    }
    signed_bytes = content_signing_bytes(
        "external_side_effect", backup.event_payload, identity.delegate_id
    )
    assert b'"witness"' in signed_bytes


@pytest.mark.integration
def test_v8_complete_backup_missing_witness_denied():
    """A Complete backup with NO witness is rejected missing-clearance + safety denial."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    with pytest.raises(VaultBindingError) as exc:
        _backup(
            dispatcher,
            identity,
            signer,
            conformance_level=ConformanceLevel.COMPLETE,
        )
    assert exc.value.code == N12FT01Code.MISSING_CLEARANCE
    saf = dispatcher._engines[AuditTier.SAFETY.value].entries
    assert saf[-1].event_payload["subtype"] == "vault_key_backup_denied"
    assert not any(
        e.event_payload["subtype"] == "vault_key_backup"
        for e in dispatcher._engines[AuditTier.RECOVERY.value].entries
    )


@pytest.mark.integration
def test_v8_self_witness_rejected():
    """A witness whose delegate_id == the requester's is rejected (N12-CL-05)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    keyring = _TokenKeyring()
    self_witness = _signed_witness(
        keyring,
        witness_delegate_id="dlg-requester",
        requester_principal=_REQUESTER,
        kek_generation=_GEN_OLD,
        witness_principal=_REQUESTER,
    )
    with pytest.raises(VaultBindingError) as exc:
        _backup(
            dispatcher,
            identity,
            signer,
            witness=self_witness,
            conformance_level=ConformanceLevel.COMPLETE,
            witness_clearance=_clearance(_REQUESTER, "vault:witness"),
            requester_delegate_id="dlg-requester",
            verify_token=keyring.verify_token,
        )
    assert exc.value.code == N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_v8_conformant_backup_anchor_has_no_witness():
    """A Conformant backup carries NO witness key (byte-unchanged §12.4 pin)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    _backup(dispatcher, identity, signer)  # CONFORMANT default, no witness
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    backup = [e for e in rec if e.event_payload["subtype"] == "vault_key_backup"][-1]
    assert "witness" not in backup.event_payload
    assert "approver" not in backup.event_payload
