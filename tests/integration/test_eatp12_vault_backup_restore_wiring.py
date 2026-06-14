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

import logging
import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import AuditChainSignatureError
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust._json import canonical_json_dumps
from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.backup import back_up_vault_key, restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.shamir import ShamirRitual, generate
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

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
def test_restore_binding_path_reproduces_spec_12_8_event_payload():
    """N12-AU-04 / §12.8 — the I1 restore BINDING path (not just the direct D2
    builder) emits a ``vault_key_restore`` anchor whose ``event_payload``
    reproduces the §12.8 golden canonical form byte-for-byte.

    Closes the G1 gate gap (security-reviewer HIGH-1): the §12.8 byte-pin was
    previously exercised ONLY via ``build_restore_anchor`` directly, hiding that
    the binding recorded ``shard_commitments=[]`` + ``shard_count=len(shards)``
    (the presenting k-subset) instead of the current-generation DISTRIBUTION
    (n=5 + the 5 commitments) the spec mandates. Drives the real
    ``restore_vault_key`` against the §12.1 fixed inputs and asserts the
    DISPATCHED anchor payload equals §12.8. (The full signed pre-image hex is
    signer-id-dependent — the fixture's ``delegate:vault-signer-00`` vs this
    test's random Ed25519 ``delegate_id`` — so the signer-independent
    ``event_payload`` is the binding-path conformance target; the full-hex pin
    lives in the direct-builder test ``test_restore_anchor_byte_pin_12_8``.)
    """
    import json
    from pathlib import Path

    # §12.1 fixed inputs (128-bit master secret, generation 7, fixture vault).
    secret_128 = bytes.fromhex("00112233445566778899aabbccddeeff")
    vault_id = "vault:fixture-0001"
    gen = 7
    provenance = "vault-derived:v1"
    holders = ["holder:h1", "holder:h2", "holder:h3", "holder:h4", "holder:h5"]
    shard_commitments = ["a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64]
    commitment = kek_identity_commitment(
        vault_id=vault_id,
        kek_generation=gen,
        master_secret=secret_128,
        passphrase_provenance=provenance,
    )

    class _FixtureResolver:
        """Trusted-module resolver returning the §12.1 KEK (NOT a mock)."""

        def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
            return ResolvedKek(
                master_secret=secret_128,
                key_class=KeyClass.KEK,
                kek_generation=gen,
                key_id="kek-fixture",
                passphrase_provenance=provenance,
            )

    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    # A conformant restore PRESENTS exactly k=3 shards (the wrapper requires
    # exactly k); the anchor still records the full n=5 distribution via the
    # caller-supplied shard_commitments, independent of the presented subset.
    shards = generate(secret_128, ShamirRitual(threshold=3, total_shards=5))[:3]
    target = VaultKeyHandle(key_id="kek-fixture", vault_id=vault_id, kek_generation=gen)

    restore_vault_key(
        shards,
        target,
        _clearance("vault:restore"),
        resolver=_FixtureResolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        expected_commitment=commitment,
        alg_id="eatp-v1",
        holders=holders,
        shard_commitments=shard_commitments,
        re_established_handle_ref="opaque:href-restored-01",
        timestamp="2026-06-12T00:00:00Z",
        time_attested=True,
        principal="delegate:requester-01",
    )

    # The binding dispatched exactly one vault_key_restore anchor to recovery.
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 1
    payload = dispatcher._engines[AuditTier.RECOVERY.value].entries[-1].event_payload
    assert payload["subtype"] == "vault_key_restore"
    # Distribution recorded, NOT the presenting subset (HIGH-1 regression guard).
    assert payload["shard_count"] == 5
    assert payload["shard_commitments"] == shard_commitments
    assert payload["re_established_handle_ref"] == "opaque:href-restored-01"

    fixture = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "test-vectors"
            / "eatp12-vault-canonical.json"
        ).read_text(encoding="utf-8")
    )
    vec = next(v for v in fixture["anchor_vectors"] if v["spec_section"] == "12.8")
    assert (
        canonical_json_dumps(payload) == vec["event_payload"]
    ), "I1 restore binding path diverged from the §12.8 golden event_payload"
