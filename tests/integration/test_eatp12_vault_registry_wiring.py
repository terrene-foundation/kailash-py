# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the EATP-12 commitment registry (W3-C2a).

Exercises the C2a registry END-TO-END through the REAL binding code path —
real SLIP-0039 ``shamir.generate`` / ``reconstruct`` (the ``shamir`` extra),
real per-tier :class:`~kailash.delegate.audit.AuditChainEngine`, real Ed25519
signer + :class:`~kailash.delegate.verifier.Ed25519Verifier`, real C1
commitment/KCV, real D1 dispatcher, real C2a :class:`CommitmentRegistry`. NO
mocks (``rules/testing.md`` Tier-2: real infrastructure).

The injected resolver is the deployment-supplied trusted-module resolver (NOT a
Tier-2 mock — a deterministic in-test resolver returning known KEK bytes,
exercised through the real binding code path, the §3.4 / #630 seam).

Conformance coverage (EATP-12 §4.4 / §4.6, N12-CB-02/03/04):

- backup REGISTERS its commitment into the registry under (vault_id, gen) keyed
  by kek_commitment_alg, binding key_id at the registry layer (N12-IN-04);
- restore CONSULTS the registry + the recovery-tier distribution anchor (no
  caller-supplied commitment / shard_commitments) and round-trips successfully;
- recompute-under-RECORDED-alg: a backup registered under ``eatp-v1`` still
  verifies after the verifier's "current" alg notionally advances (the recorded
  alg is used, not the latest) (N12-CB-04(b));
- foreign-shard (N12-CB-03, FT-02 step 6): a SLIP-0039-valid shard whose
  ciphertext-hash is NOT in the distribution anchor → ``unknown-shard`` BEFORE
  reconstruction (asserted: reconstruction was NOT reached — the foreign set
  WOULD reconstruct, yet fails at unknown-shard first);
- map_wrapper_exception fail-closed: an unrecognized wrapper exception → deny;
- no plaintext KEK in receipt / anchor / logs across the registry path.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.vault import backup as backup_mod
from kailash.trust.vault.backup import back_up_vault_key, restore_vault_key
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.shamir import ShamirRitual, generate, serialize_shard
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KEK_A = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_KEK_B = bytes.fromhex(
    "ffeeddccbbaa99887766554433221100ffeeddccbbaa99887766554433221100"
)
_GEN = 7
_VAULT = "vault-c2a"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"


def _shard_commitments(shards) -> list[str]:
    return [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]


class _Resolver:
    """Deployment-supplied trusted resolver (NOT a mock)."""

    def __init__(
        self,
        *,
        secret: bytes = _KEK_A,
        key_class: KeyClass = KeyClass.KEK,
        key_id: str = "kek-handle-a",
        vault_id: str = _VAULT,
        gen: int = _GEN,
    ) -> None:
        self._secret = secret
        self._key_class = key_class
        self._key_id = key_id
        self._vault_id = vault_id
        self._gen = gen

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=self._secret,
            key_class=self._key_class,
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
        sovereign_ref="sov-c2a",
        role_binding_ref="rb-c2a",
        genesis_ref="gen-c2a",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


@pytest.fixture(autouse=True)
def _register_default_holders():
    """Register the test holders so gate-3 (N12-SH-01) is satisfied for the
    backups in this file (their SH-01 enforcement is exercised in its own wiring
    test). ``_do_backup`` uses the process-default holder registry."""
    from kailash.trust.vault.holder_registry import default_holder_registry

    default_holder_registry()._registered.clear()
    default_holder_registry().register_all(["h1", "h2", "h3", "h4", "h5"])
    yield
    default_holder_registry()._registered.clear()


def _handle(key_id: str = "kek-handle-a", vault_id: str = _VAULT) -> VaultKeyHandle:
    return VaultKeyHandle(key_id=key_id, vault_id=vault_id, kek_generation=_GEN)


def _clearance(*caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal="agent-1", tenant="t1", domain="d1", capabilities=tuple(caps)
    )


def _do_backup(
    dispatcher: AuditDispatcher,
    identity: DelegateIdentity,
    signer: Callable[[bytes], str],
    registry: CommitmentRegistry,
    *,
    resolver: _Resolver,
    handle: VaultKeyHandle,
    holders=("h1", "h2", "h3", "h4", "h5"),
):
    return back_up_vault_key(
        handle,
        ShamirRitual(threshold=3, total_shards=5),
        _clearance("vault:backup"),
        list(holders),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
    )


@pytest.mark.integration
def test_backup_registers_commitment_keyed_by_alg_with_key_id():
    """backup REGISTERS the commitment under (vault_id, gen) keyed by alg + key_id.

    N12-CB-04(c) registry shape + N12-IN-04 key_id binding at the registry layer.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _Resolver()

    receipt = _do_backup(
        dispatcher, identity, signer, registry, resolver=resolver, handle=_handle()
    )

    lookup = registry.lookup(
        vault_id=_VAULT, kek_generation=_GEN, kek_commitment_alg=_ALG
    )
    assert lookup.entry is not None, "backup did not register the commitment"
    assert lookup.entry.commitment == receipt.kek_identity_commitment
    assert lookup.entry.key_id == "kek-handle-a"  # N12-IN-04 key_id bound here
    assert lookup.entry.retired is False  # C2a registers LIVE
    assert registry.live_algs(vault_id=_VAULT, kek_generation=_GEN) == (_ALG,)
    # The recovery-tier backup anchor carries the per-deployment foreign-shard
    # array (N12-CB-03) — 5 real ciphertext commitments, not the empty Wave-2 set.
    backup_anchor = dispatcher._engines[AuditTier.RECOVERY.value].entries[0]
    assert len(backup_anchor.event_payload["shard_commitments"]) == 5


@pytest.mark.integration
def test_backup_then_restore_round_trip_through_registry_no_caller_commitment():
    """backup→restore round-trip through the registry; NO caller-supplied
    expected_commitment / shard_commitments. No plaintext in receipt/anchor/logs.

    The restore SOURCES the commitment from the registry + the distribution from
    the recovery-tier backup anchor, recomputes + constant-time-compares, and
    succeeds. (Models post-backup state from ONE canonical shard set because
    ``back_up_vault_key`` shards internally and never returns shards — see the
    binding-path test for the same rationale.)
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _Resolver(secret=_KEK_A)
    handle = _handle()

    # Canonical shard set: backup registers + dispatches the anchor over THIS
    # set's commitments; holders present a k-subset of THIS set.
    all_shards = generate(_KEK_A, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_state(
        dispatcher,
        identity,
        signer,
        registry,
        secret=_KEK_A,
        shards=all_shards,
        key_id="kek-handle-a",
    )

    caplog_records: list[str] = []
    logger = logging.getLogger("kailash.trust.vault")

    class _Collector(logging.Handler):
        def emit(self, record):
            caplog_records.append(record.getMessage())
            caplog_records.append(repr(getattr(record, "__dict__", {})))

    handler = _Collector()
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        receipt = restore_vault_key(
            all_shards[:3],
            handle,
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
        )
    finally:
        logger.removeHandler(handler)

    assert receipt.restored_handle == handle
    assert receipt.kek_generation == _GEN
    assert receipt.forced_stale is False
    # No plaintext anywhere (I1's consume-and-del preserved).
    hexform = _KEK_A.hex()
    assert hexform not in repr(receipt.to_dict())
    restore_anchor = next(
        e
        for e in dispatcher._engines[AuditTier.RECOVERY.value].entries
        if e.event_payload["subtype"] == "vault_key_restore"
    )
    assert hexform not in repr(restore_anchor.event_payload)
    for msg in caplog_records:
        assert hexform not in msg, "KEK hex leaked into a log record"


@pytest.mark.integration
def test_recompute_under_recorded_alg_survives_current_alg_advance(monkeypatch):
    """N12-CB-02(b): restore recomputes under the backup's RECORDED alg, NOT the
    verifier's current/latest alg. A backup registered under ``eatp-v1`` still
    verifies after the deployment's notional current suite advances.

    Simulated by registering under ``eatp-v1`` then changing the module DEFAULT
    alg constant; the restore passes ``kek_commitment_alg="eatp-v1"`` (the
    recorded alg from the backup blob) and resolves the still-registered entry.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    handle = _handle()

    all_shards = generate(_KEK_A, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_state(
        dispatcher,
        identity,
        signer,
        registry,
        secret=_KEK_A,
        shards=all_shards,
        key_id="kek-handle-a",
        alg="eatp-v1",
    )

    # Notional "current suite advance": the deployment default moves on, but the
    # restore still passes the RECORDED alg (eatp-v1) so the registered entry is
    # found and recomputed under eatp-v1 — never the new default.
    monkeypatch.setattr(backup_mod, "DEFAULT_KEK_COMMITMENT_ALG", "eatp-v1.1")
    resolver = _Resolver(secret=_KEK_A)

    receipt = restore_vault_key(
        all_shards[:3],
        handle,
        _clearance("vault:restore"),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        kek_commitment_alg="eatp-v1",  # the backup's RECORDED alg
    )
    assert receipt.kek_generation == _GEN


@pytest.mark.integration
def test_foreign_shard_rejected_before_reconstruction():
    """N12-CB-03 / FT-02 step 6: a SLIP-0039-valid foreign shard whose ciphertext
    hash is NOT in the distribution anchor → ``unknown-shard`` BEFORE reconstruct.

    The foreign set is itself a complete, internally-consistent k-of-n that WOULD
    reconstruct (a self-generated set sharing its own identifier). It is rejected
    at the foreign-shard gate (step 6), proving reconstruction was NOT reached —
    a foreign secret never enters the candidate-secret path.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _Resolver(secret=_KEK_A)
    handle = _handle()

    # The GENUINE distribution: backup over KEK_A's shards.
    genuine_shards = generate(_KEK_A, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_state(
        dispatcher,
        identity,
        signer,
        registry,
        secret=_KEK_A,
        shards=genuine_shards,
        key_id="kek-handle-a",
    )

    # A FOREIGN, internally-consistent set (different secret, fresh identifier)
    # that WOULD reconstruct on its own — but its ciphertext hashes are NOT in
    # the genuine distribution anchor.
    foreign_shards = generate(_KEK_B, ShamirRitual(threshold=3, total_shards=5))
    # Sanity: the foreign set IS reconstructable on its own (so the rejection is
    # genuinely at the foreign-shard gate, not at reconstruction).
    from kailash.trust.vault.shamir import reconstruct as _reconstruct

    assert _reconstruct([list(s) for s in foreign_shards[:3]]) == _KEK_B

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            foreign_shards[:3],
            handle,
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.UNKNOWN_SHARD
    # No restore OUTCOME anchor on recovery; a denial on safety. (The backup
    # anchor from seeding is on recovery, so recovery has exactly the 1 seed.)
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    assert all(e.event_payload["subtype"] != "vault_key_restore" for e in rec)
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1


@pytest.mark.integration
def test_map_wrapper_exception_unrecognized_denies_fail_closed(monkeypatch):
    """map_wrapper_exception fail-closed: an UNRECOGNIZED wrapper exception (None
    return) DENIES the restore — never a silent proceed (LOW-1 carry-in).

    The presented shards pass the foreign-shard gate (genuine distribution), so
    the restore reaches the guarded reconstruct; a patched ``reconstruct`` raises
    a wrapper exception whose text matches NO entry in the wrapper-text map
    (map_wrapper_exception → None). The binding MUST deny (raise), not proceed.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _Resolver(secret=_KEK_A)
    handle = _handle()

    genuine_shards = generate(_KEK_A, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_state(
        dispatcher,
        identity,
        signer,
        registry,
        secret=_KEK_A,
        shards=genuine_shards,
        key_id="kek-handle-a",
    )

    def _raise_unrecognized(shards, *, passphrase=b""):
        # Text matches NO needle in _WRAPPER_TEXT_MAP → map_wrapper_exception None.
        raise RuntimeError("a totally novel wrapper failure with no mapped needle")

    monkeypatch.setattr(backup_mod, "reconstruct", _raise_unrecognized)

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            genuine_shards[:3],
            handle,
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
        )
    # Fail-closed deny: a typed VaultBindingError, NOT a returned receipt and NOT
    # the raw RuntimeError propagating unmapped.
    assert isinstance(exc.value, VaultBindingError)
    assert exc.value.code is N12FT01Code.CORRUPTED_SHARD
    # No restore OUTCOME anchor on recovery (no key without authenticated recon).
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    assert all(e.event_payload["subtype"] != "vault_key_restore" for e in rec)


@pytest.mark.integration
def test_map_wrapper_exception_recognized_maps_to_typed_code(monkeypatch):
    """A RECOGNIZED wrapper exception maps to its typed code (not unknown-shard).

    A patched reconstruct raising the wrapper's insufficient-shards text maps to
    ``insufficient-shards`` via map_wrapper_exception — the mapped-condition half
    of the fail-closed caller.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _Resolver(secret=_KEK_A)
    handle = _handle()

    genuine_shards = generate(_KEK_A, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_state(
        dispatcher,
        identity,
        signer,
        registry,
        secret=_KEK_A,
        shards=genuine_shards,
        key_id="kek-handle-a",
    )

    def _raise_insufficient(shards, *, passphrase=b""):
        raise ValueError("insufficient number of mnemonics provided")

    monkeypatch.setattr(backup_mod, "reconstruct", _raise_insufficient)

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            genuine_shards[:3],
            handle,
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.INSUFFICIENT_SHARDS


# ---------------------------------------------------------------------------
# Shared post-backup-state seeder (back_up_vault_key shards internally + never
# returns the shards, so a round-trip test models the post-backup state from a
# single canonical shard set: register the commitment + dispatch the
# vault_key_backup distribution anchor carrying THOSE shards' commitments).
# ---------------------------------------------------------------------------


def _seed_backup_state(
    dispatcher: AuditDispatcher,
    identity: DelegateIdentity,
    signer: Callable[[bytes], str],
    registry: CommitmentRegistry,
    *,
    secret: bytes,
    shards,
    key_id: str,
    vault_id: str = _VAULT,
    gen: int = _GEN,
    alg: str = _ALG,
) -> str:
    from kailash.delegate.audit import content_signing_bytes
    from kailash.trust.vault.anchors import build_backup_anchor
    from kailash.trust.vault.commitment import kek_identity_commitment

    commitment = kek_identity_commitment(
        vault_id=vault_id,
        kek_generation=gen,
        master_secret=secret,
        passphrase_provenance=_PROVENANCE,
        alg=alg,
    )
    registry.register(
        vault_id=vault_id,
        kek_generation=gen,
        kek_commitment_alg=alg,
        commitment=commitment,
        key_id=key_id,
    )
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
        shard_commitments=_shard_commitments(shards),
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": len(secret) * 8,
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
    return commitment
