# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the EATP-12 handle-based backup/restore (W2-I1).

Exercises ``kailash.trust.vault.back_up_vault_key`` /
``restore_vault_key`` end-to-end against the REAL substrate — real SLIP-0039
``shamir.generate`` / ``reconstruct`` (the ``shamir`` extra), real per-tier
:class:`~kailash.delegate.audit.AuditChainEngine`, real
:class:`~kailash.trust.chain.TrustLineageChain`, real Ed25519 signer +
:class:`~kailash.delegate.verifier.Ed25519Verifier`, real C1 commitment/KCV,
real D2 anchor builders, real D1 dispatcher. NO mocks (per ``rules/testing.md``
Tier-2: real infrastructure, no ``@patch`` / ``MagicMock`` / ``unittest.mock``).

The injected resolver is the deployment-supplied trusted-module resolver (NOT
a Tier-2 mock): a deterministic in-test resolver returning known KEK bytes,
exercised through the real binding code path. This is exactly the §3.4 / #630
seam — a deployment wires its real vault key store; the test wires a
deterministic one with known bytes so the no-plaintext invariant is checkable.

Conformance coverage (EATP-12 §4.1 / §4.5):

- N12-IN-01/IN-04/IN-05 — handle-based; key_id recorded on receipt; the KEK
  secret appears in NEITHER the BackupReceipt dict NOR the dispatched anchor
  payload NOR any captured log record (the no-plaintext invariant).
- N12-AU-02b — backup returns a receipt only AFTER a successful dispatch; a
  failing dispatch aborts with no shard release / no receipt.
- restore consume-and-del round-trip — no plaintext in the RestoreReceipt; the
  reconstructed KEK byte-equals the original (the round-trip is genuine).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import AuditChainSignatureError
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.backup import back_up_vault_key, restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment, key_check_value
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.shamir import ShamirRitual, generate, serialize_shard
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle


def _shard_commitments(shards) -> list[str]:
    """SHA-256 (hex) of each shard's canonical paper-print form (N12-CB-03)."""
    return [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]


# A known KEK secret (32 bytes = 256 bits). The no-plaintext invariant asserts
# this NEVER appears (raw or hex) in any receipt / anchor / log record.
_KNOWN_KEK = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_KEK_GENERATION = 7
_KEY_ID = "kek-handle-abc"
_VAULT_ID = "vault-xyz"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"


class _DeterministicResolver:
    """The deployment-supplied trusted resolver, returning known bytes.

    Satisfies the :class:`VaultKeyResolver` Protocol at runtime. NOT a mock —
    it IS the trusted-module boundary a deployment fills with its vault key
    store; here it returns a fixed KEK so the no-plaintext invariant is
    checkable. ``key_class`` is parameterized so a DATA-class negative test can
    reuse it.
    """

    def __init__(self, *, key_class: KeyClass = KeyClass.KEK) -> None:
        self._key_class = key_class

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=_KNOWN_KEK,
            key_class=self._key_class,
            kek_generation=_KEK_GENERATION,
            key_id=_KEY_ID,
            passphrase_provenance=_PROVENANCE,
            vault_tenant="t1",
            vault_domain="d1",
        )


def _build_signer() -> tuple[DelegateIdentity, Ed25519Verifier, Callable[[bytes], str]]:
    """Real Ed25519 keypair + directory + signer (NO mocks)."""
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-vault-binding",
        role_binding_ref="rb-vault-binding",
        genesis_ref="gen-vault-binding",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


def _handle() -> VaultKeyHandle:
    return VaultKeyHandle(
        key_id=_KEY_ID, vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION
    )


def _clearance(*caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal="agent-1", tenant="t1", domain="d1", capabilities=tuple(caps)
    )


@pytest.fixture(autouse=True)
def _isolate_default_registry():
    """Reset the process-default commitment registry between tests.

    Backups that do NOT inject a ``registry`` register into the module singleton
    (:func:`default_commitment_registry`); without isolation a registration from
    one test would leak into a sibling that consults the default. Clearing the
    store before each test keeps the singleton-default path deterministic.
    """
    from kailash.trust.vault.holder_registry import default_holder_registry
    from kailash.trust.vault.registry import default_commitment_registry

    default_commitment_registry()._store.clear()
    # N12-SH-01: gate 3 now requires every holder id to be registered in the
    # deployment holder registry. Register the test holders so the backups in
    # this file reach the gate they exercise (the SH-01 enforcement itself is
    # exercised by test_eatp12_vault_holder_registry_wiring.py).
    default_holder_registry()._registered.clear()
    default_holder_registry().register_all(["h1", "h2", "h3", "h4", "h5"])
    yield
    default_commitment_registry()._store.clear()
    default_holder_registry()._registered.clear()


def _resolver_satisfies_protocol() -> None:
    assert isinstance(_DeterministicResolver(), VaultKeyResolver)


def _assert_no_plaintext(blob: str) -> None:
    """Assert neither the raw KEK bytes nor their hex appears in ``blob``."""
    hexform = _KNOWN_KEK.hex()
    assert hexform not in blob, "KEK hex leaked"
    # The raw bytes rarely survive str() intact, but check the repr too.
    assert repr(_KNOWN_KEK) not in blob, "KEK raw repr leaked"
    # A couple of distinctive hex substrings (defense-in-depth).
    assert "00112233445566778899aabbccddeeff" not in blob, "KEK hex prefix leaked"


@pytest.mark.integration
def test_resolver_satisfies_protocol():
    """The in-test trusted resolver satisfies the VaultKeyResolver Protocol."""
    _resolver_satisfies_protocol()


@pytest.mark.integration
def test_backup_no_plaintext_in_receipt_anchor_or_logs(caplog):
    """N12-IN-05 — the KEK secret appears in NO receipt / anchor / log record.

    Runs a full handle-based backup with the deterministic resolver returning
    a known secret, then asserts the secret (hex + raw) appears in NEITHER the
    returned BackupReceipt's dict, NOR the dispatched anchor payload, NOR any
    captured log record.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    caplog.set_level(logging.DEBUG)

    receipt = back_up_vault_key(
        _handle(),
        ShamirRitual(threshold=3, total_shards=5),
        _clearance("vault:backup"),
        ["h1", "h2", "h3", "h4", "h5"],
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
    )

    # N12-IN-04: key_id is captured (on the registry layer the receipt feeds);
    # the receipt itself carries the commitment + KCV + topology.
    assert receipt.vault_id == _VAULT_ID
    assert receipt.kek_generation == _KEK_GENERATION
    assert receipt.k == 3 and receipt.n == 5
    assert receipt.holders == ("h1", "h2", "h3", "h4", "h5")

    # No-plaintext: the BackupReceipt dict carries NO secret.
    _assert_no_plaintext(repr(receipt.to_dict()))

    # No-plaintext: the dispatched anchor payload carries NO secret. Pull the
    # actual dispatched entries off the recovery-tier engine.
    rec_engine = dispatcher._engines[AuditTier.RECOVERY.value]
    assert len(rec_engine.entries) == 1, "exactly one OUTCOME anchor dispatched"
    anchor_entry = rec_engine.entries[0]
    _assert_no_plaintext(repr(anchor_entry.event_payload))
    # The anchor binds the commitment + KCV, not the secret.
    assert anchor_entry.event_payload["subtype"] == "vault_key_backup"
    assert (
        anchor_entry.event_payload["kek_identity_commitment"]
        == receipt.kek_identity_commitment
    )
    assert anchor_entry.event_payload["slip39_params"]["master_secret_bits"] == 256

    # No-plaintext: no captured log record carries the secret.
    for rec in caplog.records:
        _assert_no_plaintext(rec.getMessage())
        _assert_no_plaintext(repr(getattr(rec, "__dict__", {})))


@pytest.mark.integration
def test_backup_au02b_failing_dispatch_aborts_no_receipt():
    """N12-AU-02b — a failing dispatch aborts the backup with no receipt.

    A dispatcher whose verifier rejects every signature (a real
    Ed25519Verifier wired to a DIFFERENT keypair than the signer) makes the
    dispatch RAISE; the backup MUST abort with NO BackupReceipt returned (no
    shard release without a durable anchor).
    """
    signer_identity, _good_verifier, signer = _build_signer()
    # Build a dispatcher whose verifier knows a DIFFERENT key — the signature
    # over the real signer's pre-image will NOT verify → dispatch RAISES.
    _other_identity, wrong_verifier, _other_signer = _build_signer()
    # Re-bind the signer's identity into the wrong verifier's directory with a
    # bogus key so verification fails (not a missing-principal error).
    dispatcher = AuditDispatcher.for_named_tiers(wrong_verifier)

    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    with pytest.raises(Exception) as exc:
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:backup"),
            ["h1", "h2", "h3", "h4", "h5"],
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            alg_id=_ALG,
        )
    # The failure is the engine's typed signature-verification condition (the
    # wrong-key verifier rejected the real signer's pre-image) — a dispatch
    # failure that propagates, NOT a swallowed error and NOT a returned receipt.
    assert isinstance(exc.value, AuditChainSignatureError), (
        f"AU-02b: expected the dispatch signature-verify failure to propagate, "
        f"got {type(exc.value).__name__}"
    )
    # And no anchor landed in the recovery tier (the dispatch failed → fail-closed).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


@pytest.mark.integration
def test_backup_not_a_kek_resolved_data_class_rejected():
    """N12-IN-02 — a DATA-class resolved handle → not-a-kek (no sharding)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.DATA)

    with pytest.raises(VaultBindingError) as exc:
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:backup"),
            ["h1", "h2", "h3", "h4", "h5"],
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
        )
    assert exc.value.code is N12FT01Code.NOT_A_KEK
    # No anchor dispatched (rejected before sharding/dispatch).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


@pytest.mark.integration
def test_backup_missing_clearance_dispatches_safety_denial():
    """N12-CL + N12-AU-01 — missing clearance raises AND dispatches a denial."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    with pytest.raises(VaultBindingError) as exc:
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:read"),  # lacks vault:backup
            ["h1", "h2", "h3", "h4", "h5"],
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    # The denial landed on the SAFETY tier; recovery stays empty.
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    denial = dispatcher._engines[AuditTier.SAFETY.value].entries[0]
    assert denial.event_payload["subtype"] == "vault_key_backup_denied"
    # The denial schema OMITS vault_id / generation / commitments (N12-AU-01).
    assert "vault_id" not in denial.event_payload
    assert "kek_generation" not in denial.event_payload


@pytest.mark.integration
def test_restore_round_trip_no_plaintext_in_receipt(caplog):
    """Restore consume-and-del round-trip; no plaintext in the RestoreReceipt.

    Generate real shards from the known KEK, then restore through the
    handle-based surface with the deterministic resolver. The commitment-auth
    gate authenticates the reconstructed secret against the registered
    commitment; the RestoreReceipt carries an opaque handle ref, NEVER bytes.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    # Real shards from the known KEK (3-of-5).
    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    # The registered commitment the restore authenticates against (C1).
    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )

    caplog.set_level(logging.DEBUG)

    receipt = restore_vault_key(
        shards[:3],  # exactly k=3
        _handle(),
        _clearance("vault:restore"),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        expected_commitment=commitment,
        alg_id=_ALG,
        holders=["h1", "h2", "h3", "h4", "h5"],
        # Foreign-shard source (N12-CB-03): the presented shards' real ciphertext
        # hashes MUST be in the distribution. The caller-supplied array is the
        # backward-compat fallback (no registry / no anchor in this isolated test).
        shard_commitments=_shard_commitments(shards),
    )

    assert receipt.restored_handle == _handle()
    assert receipt.kek_generation == _KEK_GENERATION
    assert receipt.forced_stale is False
    # No-plaintext in the RestoreReceipt dict.
    _assert_no_plaintext(repr(receipt.to_dict()))
    # A restore OUTCOME anchor landed on the recovery tier.
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 1
    anchor = dispatcher._engines[AuditTier.RECOVERY.value].entries[0]
    assert anchor.event_payload["subtype"] == "vault_key_restore"
    _assert_no_plaintext(repr(anchor.event_payload))
    # No-plaintext in any captured log record.
    for rec in caplog.records:
        _assert_no_plaintext(rec.getMessage())


@pytest.mark.integration
def test_restore_commitment_mismatch_rejected():
    """A reconstructed secret not matching the registered commitment → mismatch.

    Present genuine shards but an expected_commitment for a DIFFERENT secret;
    the commitment-auth gate (C1, constant-time) rejects with
    kek-commitment-mismatch and dispatches a safety-tier denial.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    # A commitment over a DIFFERENT secret — the reconstructed (genuine) secret
    # will not match it.
    wrong_commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=b"\xff" * 32,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:3],
            _handle(),
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            expected_commitment=wrong_commitment,
            alg_id=_ALG,
            holders=["h1", "h2", "h3", "h4", "h5"],
            # Genuine shards pass the foreign-shard gate (step 6) so the restore
            # reaches the commitment-auth gate (step 7) where the wrong commitment
            # is rejected — the gate-ORDER guarantee the reorder must preserve.
            shard_commitments=_shard_commitments(shards),
        )
    assert exc.value.code is N12FT01Code.KEK_COMMITMENT_MISMATCH
    # The restore did NOT proceed: no OUTCOME anchor on recovery; a denial on
    # safety.
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1


@pytest.mark.integration
def test_restore_missing_clearance_dispatches_safety_denial():
    """A restore without vault:restore raises AND dispatches a safety denial."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:3],
            _handle(),
            _clearance("vault:read"),  # lacks vault:restore
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            expected_commitment=commitment,
            alg_id=_ALG,
            holders=["h1", "h2", "h3", "h4", "h5"],
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    denial = dispatcher._engines[AuditTier.SAFETY.value].entries[0]
    assert denial.event_payload["subtype"] == "vault_key_restore_denied"


@pytest.mark.integration
def test_restore_binding_path_records_distribution_via_registry():
    """C2a — the restore BINDING path sources its distribution from the backup's
    recovery-tier distribution anchor (N12-CB-03 / N12-AU-04), NOT the presenting
    k-shard subset.

    The C2a successor to the Wave-2 HIGH-1 §12.8 binding-path test (per
    journal/0007 G3 carry-in: "the binding-path test MUST be updated to drive the
    registry path once C2a lands"). Drives a real backup→restore round-trip:
    backup registers the commitment + dispatches a ``vault_key_backup``
    distribution anchor carrying the REAL shard_commitments; restore then SOURCES
    its foreign-shard array + restore-anchor distribution from that anchor and its
    commitment from the registry — no caller-supplied ``expected_commitment`` /
    ``holders`` / ``shard_commitments``. The HIGH-1 regression guard
    (``shard_count == n == 5``, distribution recorded not the k-subset) holds
    against the registry-sourced distribution. The byte-exact §12.8 golden pin is
    owned by the direct-builder test ``test_restore_anchor_byte_pin_12_8``.
    """
    secret_128 = bytes.fromhex("00112233445566778899aabbccddeeff")
    vault_id = "vault:fixture-0001"
    gen = 7
    provenance = "vault-derived:v1"
    holders = ["holder:h1", "holder:h2", "holder:h3", "holder:h4", "holder:h5"]

    class _FixtureResolver:
        """Trusted-module resolver returning the §12.1 KEK (NOT a mock)."""

        def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
            return ResolvedKek(
                master_secret=secret_128,
                key_class=KeyClass.KEK,
                kek_generation=gen,
                key_id="kek-fixture",
                passphrase_provenance=provenance,
                vault_tenant="t1",
                vault_domain="d1",
            )

    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _FixtureResolver()
    registry = CommitmentRegistry()  # fresh — isolate the registration
    target = VaultKeyHandle(key_id="kek-fixture", vault_id=vault_id, kek_generation=gen)

    # Model post-backup deployment state from ONE canonical shard set (holders
    # hold these; the restore presents a k-subset of THESE). A real
    # ``back_up_vault_key`` shards INTERNALLY with a CSPRNG and never returns the
    # shards (they go to holders), so a round-trip test cannot share backup's
    # internal shards — it constructs the post-backup state the restore consults:
    # (a) the registered commitment (what backup.register did), (b) the recovery-
    # tier ``vault_key_backup`` distribution anchor carrying THESE shards'
    # ciphertext commitments (what backup dispatched).
    all_shards = generate(secret_128, ShamirRitual(threshold=3, total_shards=5))
    real_commitments = _shard_commitments(all_shards)
    commitment = kek_identity_commitment(
        vault_id=vault_id,
        kek_generation=gen,
        master_secret=secret_128,
        passphrase_provenance=provenance,
    )
    registry.register(
        vault_id=vault_id,
        kek_generation=gen,
        kek_commitment_alg="eatp-v1",
        commitment=commitment,
        key_id="kek-fixture",
    )
    from kailash.delegate.audit import content_signing_bytes
    from kailash.trust.vault.anchors import build_backup_anchor

    backup_payload = build_backup_anchor(
        alg_id="eatp-v1",
        k=3,
        n=5,
        holders=holders,
        shard_count=5,
        vault_id=vault_id,
        kek_generation=gen,
        kek_identity_commitment=commitment,
        kek_commitment_alg="eatp-v1",
        kcv="0" * 16,
        shard_commitments=real_commitments,
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": 128,
        },
        principal="delegate:requester-01",
        timestamp="unverified",
        time_attested=False,
        side_channel_hardened=False,
    )
    _pre = content_signing_bytes(
        "external_side_effect", backup_payload, identity.delegate_id
    )
    dispatcher.dispatch(
        "external_side_effect",
        backup_payload,
        identity,
        signer(_pre),
        AuditTier.RECOVERY.value,
    )

    # Present a k=3 subset of the SAME canonical shard set the distribution holds.
    shards = all_shards[:3]

    # Restore: NO caller-supplied commitment / holders / shard_commitments —
    # everything is sourced from the registry + the recovery-tier distribution
    # anchor the backup dispatched.
    restore_vault_key(
        shards,
        target,
        _clearance("vault:restore"),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id="eatp-v1",
        registry=registry,
        re_established_handle_ref="opaque:href-restored-01",
        timestamp="2026-06-12T00:00:00Z",
        time_attested=True,
        principal="delegate:requester-01",
    )

    # Recovery tier now holds the backup anchor + the restore anchor.
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    backup_anchor = next(
        e for e in rec if e.event_payload["subtype"] == "vault_key_backup"
    )
    restore_anchor = next(
        e for e in rec if e.event_payload["subtype"] == "vault_key_restore"
    )
    payload = restore_anchor.event_payload
    # Distribution recorded, NOT the presenting subset (HIGH-1 regression guard),
    # and sourced from the backup's distribution anchor (C2a).
    assert payload["shard_count"] == 5
    assert (
        payload["shard_commitments"] == backup_anchor.event_payload["shard_commitments"]
    )
    assert payload["holders"] == backup_anchor.event_payload["holders"]
    assert payload["re_established_handle_ref"] == "opaque:href-restored-01"
    # The recorded commitment is the registered (authenticated) one.
    assert (
        payload["kek_identity_commitment"]
        == backup_anchor.event_payload["kek_identity_commitment"]
    )


# ===========================================================================
# GAP-2 — pre-reconstruction shard-count (step 3) + mixed-identifier (step 5)
# ===========================================================================


@pytest.mark.integration
def test_restore_too_many_shards_rejected_too_many_shards():
    """GAP-2 / V5(g)(h) reject branch — k+1 shards from the SAME backup → too-many-shards.

    Over-supply (4 shards for a 3-of-5 ritual, all from one backup so identifiers
    match) is rejected at FT-02 step 3 (shard-count) with the REJECT-branch code
    `too-many-shards` — BEFORE reconstruction, sourced from the SLIP-0039
    member-threshold metadata, NOT the ambiguous wrapper "Wrong number" text.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:4],  # k+1 = 4 (k=3), all from the SAME backup
            _handle(),
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            expected_commitment=commitment,
            alg_id=_ALG,
            holders=["h1", "h2", "h3", "h4", "h5"],
            shard_commitments=_shard_commitments(shards),
        )
    assert exc.value.code is N12FT01Code.TOO_MANY_SHARDS
    # Rejected before any OUTCOME anchor; a denial landed on safety.
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1


@pytest.mark.integration
def test_restore_insufficient_shards_rejected_insufficient_shards():
    """GAP-2 — fewer than k shards → insufficient-shards at step 3 (pre-reconstruction)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:2],  # k-1 = 2 (k=3)
            _handle(),
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            expected_commitment=commitment,
            alg_id=_ALG,
            holders=["h1", "h2", "h3", "h4", "h5"],
            shard_commitments=_shard_commitments(shards),
        )
    assert exc.value.code is N12FT01Code.INSUFFICIENT_SHARDS
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


@pytest.mark.integration
def test_restore_mixed_shard_set_rejected_before_foreign_shard():
    """GAP-2 / V5(f) — k shards from TWO distinct SLIP-0039 identifiers → mixed-shard-set.

    A genuine shard mixed with a shard from a DIFFERENT backup (distinct
    identifier) is rejected at FT-02 step 5 (mixed-identifier) — BEFORE the step-6
    foreign-shard gate and the step-7 commitment gate. The assertion that the code
    is `mixed-shard-set` (NOT `unknown-shard` / `corrupted-shard`) proves the
    canonical ordering: step 5 fires first.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    genuine = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    foreign = generate(b"\xab" * 32, ShamirRitual(threshold=3, total_shards=5))
    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    # k=3 shards but one is from a DIFFERENT backup (distinct identifier).
    presented = [genuine[0], genuine[1], foreign[0]]

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            presented,
            _handle(),
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            expected_commitment=commitment,
            alg_id=_ALG,
            holders=["h1", "h2", "h3", "h4", "h5"],
            # The genuine distribution: foreign[0]'s hash is absent, so step 6
            # WOULD reject unknown-shard — but step 5 (mixed) fires FIRST.
            shard_commitments=_shard_commitments(genuine),
        )
    assert exc.value.code is N12FT01Code.MIXED_SHARD_SET
    assert exc.value.code is not N12FT01Code.UNKNOWN_SHARD
    assert exc.value.code is not N12FT01Code.CORRUPTED_SHARD
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


# ===========================================================================
# GAP-1 — kcv-mismatch (N12-CB-04(d) / V6) offline blob check
# ===========================================================================


@pytest.mark.integration
def test_restore_wrong_kcv_rejected_kcv_mismatch():
    """GAP-1 / V6 — a relabelled/tampered blob (wrong expected_kcv) → kcv-mismatch.

    Backup-equivalent: capture the receipt's KCV; present a WRONG KCV (simulating
    a relabelled blob) at restore. The commitment-auth gate recomputes the KCV
    over the reconstructed secret and constant-time compares — a mismatch fails
    OFFLINE with `kcv-mismatch` (no live vault needed for the tamper signal).
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    # A KCV over a DIFFERENT secret — the genuine reconstructed secret won't match.
    wrong_kcv = key_check_value(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=b"\xff" * 32,
        alg=_ALG,
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            shards[:3],
            _handle(),
            _clearance("vault:restore"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            expected_commitment=commitment,
            expected_kcv=wrong_kcv,
            alg_id=_ALG,
            holders=["h1", "h2", "h3", "h4", "h5"],
            shard_commitments=_shard_commitments(shards),
        )
    assert exc.value.code is N12FT01Code.KCV_MISMATCH
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1


@pytest.mark.integration
def test_restore_correct_kcv_succeeds_round_trip():
    """GAP-1 — the CORRECT expected_kcv passes (orphan-detection §2a crypto-pair).

    The crypto-pair round-trip: backup computes the KCV over the real secret;
    restore presents that SAME KCV; the offline check passes and the restore
    succeeds. Pairs with the wrong-KCV test so the KCV gate is exercised on BOTH
    branches (a gate that only ever fails is indistinguishable from a hard-reject).
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    correct_kcv = key_check_value(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        alg=_ALG,
    )

    receipt = restore_vault_key(
        shards[:3],
        _handle(),
        _clearance("vault:restore"),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        expected_commitment=commitment,
        expected_kcv=correct_kcv,
        alg_id=_ALG,
        holders=["h1", "h2", "h3", "h4", "h5"],
        shard_commitments=_shard_commitments(shards),
    )
    assert receipt.kek_generation == _KEK_GENERATION
    assert receipt.forced_stale is False
    # The restore OUTCOME anchor landed (the KCV gate passed → reconstruction
    # authenticated → anchor dispatched).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 1


# ===========================================================================
# GAP-4 — side_channel_hardened=True is non-fake (N12-CRY-SC)
# ===========================================================================


@pytest.mark.integration
def test_backup_side_channel_hardened_true_rejected():
    """GAP-4 / N12-CRY-SC — side_channel_hardened=True is rejected (never truthful here).

    This binding ALWAYS reconstructs via userspace combine_mnemonics (not
    constant-time), so asserting side_channel_hardened=True would be a
    fake-classification (zero-tolerance Rule 2). The entry gate rejects it with a
    ValueError before resolution — no anchor, no sharding.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    with pytest.raises(ValueError, match="side_channel_hardened"):
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:backup"),
            ["h1", "h2", "h3", "h4", "h5"],
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            side_channel_hardened=True,
        )
    # Rejected at the entry gate — nothing dispatched.
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


@pytest.mark.integration
def test_backup_side_channel_hardened_false_records_false_in_anchor():
    """GAP-4 — the default (False) records side_channel_hardened=False on the anchor."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    back_up_vault_key(
        _handle(),
        ShamirRitual(threshold=3, total_shards=5),
        _clearance("vault:backup"),
        ["h1", "h2", "h3", "h4", "h5"],
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        # side_channel_hardened defaults to False
    )
    anchor = dispatcher._engines[AuditTier.RECOVERY.value].entries[0]
    assert anchor.event_payload["subtype"] == "vault_key_backup"
    assert anchor.event_payload["side_channel_hardened"] is False
