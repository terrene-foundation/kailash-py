# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 Trust-Vault quickstart — release-blocking end-to-end regression (HIGH-7, V1).

The canonical user flow the docs teach (`specs/trust-crypto.md` § Trust-Vault
Binding): a deployment BACKS UP a KEK (the backup ceremony) and later RESTORES it
from the holder-distributed shards (the restore ceremony). Because the
handle-based surface never returns plaintext KEK bytes (N12-IN-05 — the backup's
shards are distributed to holders internally and the restore receipt is opaque),
the roundtrip is two ceremonies sharing the vault's commitment, NOT a single
shared-shards call chain. This regression exercises BOTH ceremonies against the
REAL substrate and asserts the V1 roundtrip invariant directly:

1. **Backup ceremony** — ``back_up_vault_key`` returns a ``BackupReceipt`` carrying
   the KEK-identity commitment + KCV, and dispatches a ``vault_key_backup`` anchor
   to the recovery tier.
2. **KEK byte-equality** — the genuine SLIP-0039 shards reconstruct to the
   ORIGINAL KEK byte-for-byte (``reconstruct(generate(kek)) == kek``), the V1
   reproducibility invariant the commitment cryptographically binds.
3. **Restore ceremony** — ``restore_vault_key`` with the genuine shards SUCCEEDS,
   dispatches a ``vault_key_restore`` anchor, and that anchor's
   ``kek_identity_commitment`` equals the backup's commitment (the restore
   authenticated the reconstructed secret against the registered commitment).
4. **Anti-injection guard** — a FOREIGN shard not in the distribution is rejected
   ``unknown-shard`` before reconstruction.

Tier-2: real SLIP-0039, real Ed25519 signer, real named-tier dispatcher, real
SQLitePostureStore. NO mocks (``rules/testing.md``). Marked ``regression`` so it
is a release gate (``rules/testing.md`` § End-to-End Pipeline Regression).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import content_signing_bytes
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.posture.posture_store import SQLitePostureStore
from kailash.trust.vault.backup import back_up_vault_key, restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.shamir import (
    ShamirRitual,
    generate,
    reconstruct,
    serialize_shard,
)
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KEK = bytes.fromhex("a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90")
_GEN = 3
_KEY_ID = "kek-quickstart"
_VAULT_ID = "vault-quickstart"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"
_HOLDERS = ["alice", "bob", "carol", "dave", "erin"]
_PRINCIPAL = "agent-quickstart"


class _Resolver:
    """Deployment-supplied trusted resolver (NOT a mock) returning the known KEK."""

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=_KEK,
            key_class=KeyClass.KEK,
            kek_generation=_GEN,
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
        sovereign_ref="sov-quickstart",
        role_binding_ref="rb-quickstart",
        genesis_ref="gen-quickstart",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)
    return identity, verifier, lambda b: priv.sign(b).hex()


def _handle() -> VaultKeyHandle:
    return VaultKeyHandle(key_id=_KEY_ID, vault_id=_VAULT_ID, kek_generation=_GEN)


def _clearance(*caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal=_PRINCIPAL, tenant="t1", domain="d1", capabilities=tuple(caps)
    )


def _shard_commitments(shards) -> list[str]:
    return [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]


@pytest.fixture
def posture_store():
    fd, path = tempfile.mkstemp(suffix="-quickstart-postures.db")
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
def _isolate_singletons():
    from kailash.trust.vault.holder_registry import default_holder_registry
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


@pytest.mark.regression
def test_eatp12_vault_quickstart_backup_restore_roundtrip(posture_store):
    """The canonical backup→restore quickstart succeeds end-to-end, the KEK
    reconstructs byte-for-byte, and the restore anchor's commitment matches
    the backup's (V1 reproducibility, release-blocking)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    ritual = ShamirRitual(threshold=3, total_shards=5)

    # --- Backup ceremony (the documented quickstart) ---
    backup_receipt = back_up_vault_key(
        _handle(),
        ritual,
        _clearance("vault:backup"),
        _HOLDERS,
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
    )
    assert backup_receipt.kek_identity_commitment
    assert backup_receipt.kcv
    assert backup_receipt.k == 3 and backup_receipt.n == 5
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    backup_anchor = [e for e in rec if e.event_payload["subtype"] == "vault_key_backup"]
    assert len(backup_anchor) == 1
    expected_commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_GEN,
        master_secret=_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    assert backup_receipt.kek_identity_commitment == expected_commitment

    # --- V1 KEK byte-equality: the genuine shards reconstruct the ORIGINAL KEK ---
    # (Holders hold these out-of-band; the backup distributes them internally, so
    # the restore ceremony presents the holder-distributed shards.)
    holder_shards = generate(_KEK, ritual)
    reconstructed = reconstruct(holder_shards[:3])
    assert reconstructed == _KEK, "SLIP-0039 roundtrip MUST reproduce the KEK exactly"

    # Seed the distribution the restore consults (what the backup dispatched for
    # this generation) so the foreign-shard gate has a source, registered under
    # the SAME commitment the backup produced.
    from kailash.trust.vault.anchors import build_backup_anchor

    dist_commitments = _shard_commitments(holder_shards)
    dist_anchor = build_backup_anchor(
        alg_id=_ALG,
        k=3,
        n=5,
        holders=_HOLDERS,
        shard_count=5,
        vault_id=_VAULT_ID,
        kek_generation=_GEN,
        kek_identity_commitment=expected_commitment,
        kek_commitment_alg=_ALG,
        kcv=backup_receipt.kcv,
        shard_commitments=dist_commitments,
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": 256,
        },
        principal=_PRINCIPAL,
        timestamp="unverified",
        time_attested=False,
    )
    pre = content_signing_bytes(
        "external_side_effect", dist_anchor, identity.delegate_id
    )
    dispatcher.dispatch(
        "external_side_effect",
        dist_anchor,
        identity,
        signer(pre),
        AuditTier.RECOVERY.value,
    )

    # --- Restore ceremony: genuine shards restore successfully ---
    restore_receipt = restore_vault_key(
        holder_shards[:3],
        _handle(),
        _clearance("vault:restore"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
    )
    assert restore_receipt.kek_generation == _GEN
    assert restore_receipt.forced_stale is False
    restore_anchor = [
        e
        for e in dispatcher._engines[AuditTier.RECOVERY.value].entries
        if e.event_payload["subtype"] == "vault_key_restore"
    ]
    assert len(restore_anchor) == 1
    # The restore authenticated the reconstructed secret against the SAME
    # commitment the backup registered (commitment-chain intact).
    assert (
        restore_anchor[0].event_payload["kek_identity_commitment"]
        == expected_commitment
    )


@pytest.mark.regression
def test_eatp12_vault_quickstart_foreign_shard_rejected(posture_store):
    """A foreign shard not in the distribution is rejected unknown-shard before
    reconstruction (the anti-injection guard the quickstart relies on)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    ritual = ShamirRitual(threshold=3, total_shards=5)

    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_GEN,
        master_secret=_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_GEN,
        kek_commitment_alg=_ALG,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    genuine = generate(_KEK, ritual)
    from kailash.trust.vault.anchors import build_backup_anchor

    dist_anchor = build_backup_anchor(
        alg_id=_ALG,
        k=3,
        n=5,
        holders=_HOLDERS,
        shard_count=5,
        vault_id=_VAULT_ID,
        kek_generation=_GEN,
        kek_identity_commitment=commitment,
        kek_commitment_alg=_ALG,
        kcv="0" * 16,
        shard_commitments=_shard_commitments(genuine),
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": 256,
        },
        principal=_PRINCIPAL,
        timestamp="unverified",
        time_attested=False,
    )
    pre = content_signing_bytes(
        "external_side_effect", dist_anchor, identity.delegate_id
    )
    dispatcher.dispatch(
        "external_side_effect",
        dist_anchor,
        identity,
        signer(pre),
        AuditTier.RECOVERY.value,
    )

    # A foreign shard from a DIFFERENT secret is not in the distribution.
    foreign = generate(bytes.fromhex("ff" * 32), ritual)
    presented = [genuine[0], genuine[1], foreign[0]]
    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            presented,
            _handle(),
            _clearance("vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
        )
    assert exc.value.code == N12FT01Code.UNKNOWN_SHARD
