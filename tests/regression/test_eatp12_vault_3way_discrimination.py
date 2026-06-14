# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: EATP-12 C2a 3-way commitment-auth discrimination (N12-CB-02).

The restore commitment-auth gate (FT-02 step 7) MUST discriminate THREE distinct
codes — collapsing any pair is a non-conformance (§4.6 "MUST NOT collapse these
into a single generic error"):

* ``commitment-alg-mismatch`` — NO commitment registered for ``(target_handle,
  captured gen)`` under the backup's RECORDED ``kek_commitment_alg`` (the alg was
  never registered / recommitted for that vault/gen). NOT injection, NOT a mere
  difference from the current/latest alg (N12-CB-04(b)).
* ``kek-commitment-mismatch`` — a commitment IS registered under that alg but the
  restore's recompute does NOT equal it (injection / wrong passphrase /
  relabelled-gen whose ciphertexts reached step 7) (N12-CB-02(c)).
* ``key-identity-mismatch`` — the target handle's captured ``key_id`` differs from
  the registered ``key_id`` (intra-vault two-KEK-same-generation / cross-vault
  re-install) (N12-CB-02(d)). ``key_id`` is bound at the registry layer
  (N12-IN-04), NOT in the §12.2 commitment pre-image, so this is the control that
  catches the case the ``vault_id``-keyed commitment cannot.

All three are exercised through the REAL ``restore_vault_key`` binding path
against real SLIP-0039 reconstruction + a real C2a registry — no mocks. Each case
seeds a genuine distribution anchor so the presented shards pass the foreign-shard
gate (step 6) and the restore reaches step 7, isolating the discrimination logic.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import content_signing_bytes
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.anchors import build_backup_anchor
from kailash.trust.vault.backup import restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.shamir import ShamirRitual, generate, serialize_shard
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KEK_GENUINE = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_KEK_OTHER = bytes.fromhex(
    "ffeeddccbbaa99887766554433221100ffeeddccbbaa99887766554433221100"
)
_GEN = 7
_VAULT = "vault-3way"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"


class _Resolver:
    def __init__(self, *, secret: bytes, key_id: str, gen: int = _GEN) -> None:
        self._secret = secret
        self._key_id = key_id
        self._gen = gen

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=self._secret,
            key_class=KeyClass.KEK,
            kek_generation=self._gen,
            key_id=self._key_id,
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
        sovereign_ref="sov-3way",
        role_binding_ref="rb-3way",
        genesis_ref="gen-3way",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    return identity, Ed25519Verifier(directory=directory), lambda b: priv.sign(b).hex()


def _clearance() -> ClearanceContext:
    return ClearanceContext(
        principal="agent-1", tenant="t1", domain="d1", capabilities=("vault:restore",)
    )


def _seed_distribution_anchor(
    dispatcher: AuditDispatcher,
    identity: DelegateIdentity,
    signer: Callable[[bytes], str],
    *,
    commitment: str,
    shards,
    vault_id: str = _VAULT,
    gen: int = _GEN,
    alg: str = _ALG,
) -> None:
    """Dispatch a genuine ``vault_key_backup`` distribution anchor over ``shards``.

    Models the post-backup recovery-tier state restore reads (N12-CB-03), so the
    presented shards pass the foreign-shard gate (step 6) and the restore reaches
    the commitment-auth gate (step 7) under test.
    """
    commitments = [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]
    payload = build_backup_anchor(
        alg_id=_ALG,
        k=3,
        n=5,
        holders=["h1", "h2", "h3", "h4", "h5"],
        shard_count=5,
        vault_id=vault_id,
        kek_generation=gen,
        kek_identity_commitment=commitment,
        kek_commitment_alg=alg,
        kcv="0" * 16,
        shard_commitments=commitments,
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": 256,
        },
        principal="agent-1",
        timestamp="unverified",
        time_attested=False,
        side_channel_hardened=False,
    )
    pre = content_signing_bytes("external_side_effect", payload, identity.delegate_id)
    dispatcher.dispatch(
        "external_side_effect", payload, identity, signer(pre), AuditTier.RECOVERY.value
    )


@pytest.mark.regression
def test_3way_commitment_alg_mismatch_when_alg_never_registered():
    """commitment-alg-mismatch: the recorded alg has NO registered commitment for
    (vault, gen) AND no caller-supplied expected_commitment fallback.

    The genuine shards pass the foreign-shard gate (distribution seeded); the
    commitment-auth gate looks up the registry under the recorded alg, finds
    NOTHING (an alg never registered for this vault/gen), and raises the
    never-registered code — distinct from injection.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()  # EMPTY — nothing registered
    resolver = _Resolver(secret=_KEK_GENUINE, key_id="kek-genuine")
    handle = VaultKeyHandle(key_id="kek-genuine", vault_id=_VAULT, kek_generation=_GEN)

    shards = generate(_KEK_GENUINE, ShamirRitual(threshold=3, total_shards=5))
    genuine_commitment = kek_identity_commitment(
        vault_id=_VAULT,
        kek_generation=_GEN,
        master_secret=_KEK_GENUINE,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    # Distribution anchor exists (foreign-shard passes) but the registry has NO
    # entry for the recorded alg → commitment-alg-mismatch.
    _seed_distribution_anchor(
        dispatcher, identity, signer, commitment=genuine_commitment, shards=shards
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:3],
            handle,
            _clearance(),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            # No expected_commitment fallback → never-registered, not mismatch.
        )
    assert exc.value.code is N12FT01Code.COMMITMENT_ALG_MISMATCH


@pytest.mark.regression
def test_3way_kek_commitment_mismatch_when_registered_but_recompute_differs():
    """kek-commitment-mismatch: a commitment IS registered under the recorded alg
    but the recompute (over the genuine reconstructed secret) does NOT equal it.

    Injection model: the registry entry commits to a DIFFERENT secret (_KEK_OTHER)
    than the shards reconstruct (_KEK_GENUINE). The shards pass foreign-shard, the
    recompute over the genuine secret diverges from the registered (wrong-secret)
    commitment → injection code, NOT never-registered.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _Resolver(secret=_KEK_GENUINE, key_id="kek-genuine")
    handle = VaultKeyHandle(key_id="kek-genuine", vault_id=_VAULT, kek_generation=_GEN)

    shards = generate(_KEK_GENUINE, ShamirRitual(threshold=3, total_shards=5))
    # Register a commitment over the WRONG secret under the recorded alg, keyed to
    # the SAME key_id the target handle resolves to (so key-identity PASSES and the
    # mismatch is isolated to the recompute compare).
    wrong_commitment = kek_identity_commitment(
        vault_id=_VAULT,
        kek_generation=_GEN,
        master_secret=_KEK_OTHER,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    registry.register(
        vault_id=_VAULT,
        kek_generation=_GEN,
        kek_commitment_alg=_ALG,
        commitment=wrong_commitment,
        key_id="kek-genuine",
    )
    # The distribution anchor is over the genuine shards (foreign-shard passes).
    _seed_distribution_anchor(
        dispatcher, identity, signer, commitment=wrong_commitment, shards=shards
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:3],
            handle,
            _clearance(),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.KEK_COMMITMENT_MISMATCH


@pytest.mark.regression
def test_3way_key_identity_mismatch_intra_vault_two_kek_same_generation():
    """key-identity-mismatch: the target handle's captured key_id differs from the
    registered key_id at the same (vault_id, generation) — intra-vault two-KEK.

    Two KEKs share (vault_id, generation) but have distinct key_ids. The §12.2
    commitment is vault_id-keyed (OMITS key_id), so the commitment alone CANNOT
    distinguish them; the registry-layer key_id binding (N12-IN-04) is the control.
    Register key_id="kek-A"; resolve the target to key_id="kek-B"; the shards
    reconstruct + pass foreign-shard, then the key-identity gate fires BEFORE the
    commitment compare.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    # Target handle resolves to key_id "kek-B" — but the registry entry is "kek-A".
    resolver = _Resolver(secret=_KEK_GENUINE, key_id="kek-B")
    handle = VaultKeyHandle(key_id="kek-B", vault_id=_VAULT, kek_generation=_GEN)

    shards = generate(_KEK_GENUINE, ShamirRitual(threshold=3, total_shards=5))
    commitment = kek_identity_commitment(
        vault_id=_VAULT,
        kek_generation=_GEN,
        master_secret=_KEK_GENUINE,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    # Registered under a DIFFERENT key_id ("kek-A") at the same (vault, gen).
    registry.register(
        vault_id=_VAULT,
        kek_generation=_GEN,
        kek_commitment_alg=_ALG,
        commitment=commitment,
        key_id="kek-A",
    )
    _seed_distribution_anchor(
        dispatcher, identity, signer, commitment=commitment, shards=shards
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:3],
            handle,
            _clearance(),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
        )
    # key-identity fires (NOT kek-commitment-mismatch: the commitment WOULD match
    # the genuine secret; the divergence is the key_id, which the vault_id-keyed
    # commitment cannot see — exactly why N12-IN-04 binds it at the registry).
    assert exc.value.code is N12FT01Code.KEY_IDENTITY_MISMATCH


@pytest.mark.regression
def test_3way_codes_are_distinct_enum_members():
    """The three codes are distinct closed-enum members (no collapse, §4.6)."""
    codes = {
        N12FT01Code.COMMITMENT_ALG_MISMATCH,
        N12FT01Code.KEK_COMMITMENT_MISMATCH,
        N12FT01Code.KEY_IDENTITY_MISMATCH,
    }
    assert len(codes) == 3
    assert N12FT01Code.RETIRED_COMMITMENT_ALG not in codes  # C2b's, distinct again
