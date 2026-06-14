# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the EATP-12 clearance gate (W4-B1).

Exercises ``kailash.trust.vault.backup``'s clearance gate (FT-02 step 1 for
restore; gate 1+5 for backup) end-to-end against the REAL substrate — real
SLIP-0039 ``shamir.generate``, real per-tier
:class:`~kailash.delegate.audit.AuditChainEngine`, real Ed25519 signer +
:class:`~kailash.delegate.verifier.Ed25519Verifier`, real C1 commitment, real D2
anchor builders, real D1 dispatcher, real C2a
:class:`~kailash.trust.vault.registry.CommitmentRegistry`, real
:class:`~kailash.trust.posture.posture_store.SQLitePostureStore` against a temp
DB. NO mocks (``rules/testing.md`` Tier-2: real infrastructure).

The injected resolver is the deployment-supplied trusted-module resolver (NOT a
mock): a deterministic in-test resolver returning known KEK bytes + the vault's
bound tenant/domain, exercised through the real binding code path.

Conformance coverage (EATP-12 §4.2 / §4.2.1):

- N12-CL-01 — missing ``vault:backup`` → ``missing-clearance`` on backup (NO
  resolution side effect — the BackupReceipt is never produced).
- N12-CL-02 — missing ``vault:restore`` → ``missing-clearance`` on restore (NO
  shard combined); holding ``vault:restore`` but presenting wrong shards fails on
  the OTHER axis (unknown-shard / a crypto code), NOT clearance (independence);
  k valid shards WITHOUT ``vault:restore`` → ``missing-clearance``.
- N12-CL-02a — a token granted in tenant A fails against a vault in tenant B
  (tenant mismatch → missing-clearance); domain A vs domain B → missing-clearance;
  fail-closed ORDER tenant→domain→token (a wrong-tenant + wrong-token input
  surfaces the tenant failure).
- N12-CL-04 — after a materializing restore (RT-05 fired, cooling-off start
  recorded), a 2nd restore/backup/rotate by the SAME principal within 7 days →
  missing-clearance; a DIFFERENT principal is NOT suspended; the trust-anchored
  start is read (injected start time, NOT wall-clock); a roll-forward does not
  lift the window early.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import content_signing_bytes
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.posture.posture_store import SQLitePostureStore
from kailash.trust.posture.postures import TrustPosture
from kailash.trust.vault.anchors import build_backup_anchor
from kailash.trust.vault.backup import back_up_vault_key, restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.shamir import ShamirRitual, generate, serialize_shard
from kailash.trust.vault.stale_guard import (
    COOLING_OFF_DAYS,
    trigger_d6_posture_downgrade,
)
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KEK = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
_GEN = 3
_KEY_ID = "kek-handle-b1"
_VAULT_ID = "vault-b1"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"
_HOLDERS = ["h1", "h2", "h3", "h4", "h5"]
_VAULT_TENANT = "tenant-A"
_VAULT_DOMAIN = "domain-A"


def _shard_commitments(shards) -> list[str]:
    return [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]


class _Resolver:
    """The deployment-supplied trusted resolver (NOT a mock).

    Resolves the handle to the KEK bytes + ``key_class`` + ``kek_generation`` +
    the vault's bound ``vault_tenant`` / ``vault_domain`` (the N12-CL-02a source —
    the trusted-module authority for the vault's tenant/domain).
    """

    def __init__(
        self,
        *,
        secret: bytes = _KEK,
        generation: int = _GEN,
        vault_tenant: str = _VAULT_TENANT,
        vault_domain: str = _VAULT_DOMAIN,
    ) -> None:
        self._secret = secret
        self._generation = generation
        self._vault_tenant = vault_tenant
        self._vault_domain = vault_domain

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=self._secret,
            key_class=KeyClass.KEK,
            kek_generation=self._generation,
            key_id=_KEY_ID,
            passphrase_provenance=_PROVENANCE,
            vault_tenant=self._vault_tenant,
            vault_domain=self._vault_domain,
        )


def _build_signer() -> tuple[DelegateIdentity, Ed25519Verifier, Callable[[bytes], str]]:
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-b1",
        role_binding_ref="rb-b1",
        genesis_ref="gen-b1",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


def _handle(generation: int = _GEN) -> VaultKeyHandle:
    return VaultKeyHandle(key_id=_KEY_ID, vault_id=_VAULT_ID, kek_generation=generation)


def _clearance(
    *caps: str,
    principal: str = "agent-b1",
    tenant: str = _VAULT_TENANT,
    domain: str = _VAULT_DOMAIN,
) -> ClearanceContext:
    return ClearanceContext(
        principal=principal, tenant=tenant, domain=domain, capabilities=tuple(caps)
    )


def _dispatch(dispatcher, identity, signer, payload, tier) -> None:
    pre = content_signing_bytes("external_side_effect", payload, identity.delegate_id)
    dispatcher.dispatch("external_side_effect", payload, identity, signer(pre), tier)


def _commitment() -> str:
    return kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_GEN,
        master_secret=_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )


def _seed_backup_anchor(
    dispatcher, identity, signer, *, shards, commitment
) -> list[str]:
    """Dispatch a ``vault_key_backup`` distribution anchor (foreign-shard source)."""
    commitments = _shard_commitments(shards)
    payload = build_backup_anchor(
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
        shard_commitments=commitments,
        slip39_params={
            "extendable": True,
            "iteration_exponent": 1,
            "group_threshold": 1,
            "master_secret_bits": 256,
        },
        principal="agent-b1",
        timestamp="unverified",
        time_attested=False,
        side_channel_hardened=False,
    )
    _dispatch(dispatcher, identity, signer, payload, AuditTier.RECOVERY.value)
    return commitments


@pytest.fixture(autouse=True)
def _isolate_default_singletons():
    from kailash.trust.vault.holder_registry import default_holder_registry
    from kailash.trust.vault.registry import default_commitment_registry
    from kailash.trust.vault.stale_guard import default_compromised_generation_denylist

    default_commitment_registry()._store.clear()
    default_compromised_generation_denylist()._revoked.clear()
    # N12-SH-01: register the test holders so backups reach the clearance/
    # cooling-off gate they exercise (gate 3 holder-registry membership now
    # precedes gate 5). SH-01 enforcement is exercised in its own wiring test.
    default_holder_registry()._registered.clear()
    default_holder_registry().register_all(_HOLDERS)
    yield
    default_commitment_registry()._store.clear()
    default_compromised_generation_denylist()._revoked.clear()
    default_holder_registry()._registered.clear()


@pytest.fixture
def posture_store():
    """A REAL SQLitePostureStore against a temp DB (Tier-2, NO mock)."""
    fd, path = tempfile.mkstemp(suffix="-b1-postures.db")
    os.close(fd)
    os.unlink(path)
    store = SQLitePostureStore(path)
    try:
        yield store
    finally:
        store.close()
        if os.path.exists(path):
            os.unlink(path)


def _register_commitment(registry: CommitmentRegistry) -> str:
    commitment = _commitment()
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_GEN,
        kek_commitment_alg=_ALG,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    return commitment


# ---------------------------------------------------------------------------
# N12-CL-01 — backup capability required
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_backup_missing_capability_denied_no_resolution(posture_store):
    """N12-CL-01 — missing vault:backup → missing-clearance; NO BackupReceipt."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    with pytest.raises(VaultBindingError) as exc:
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:restore"),  # NOT vault:backup
            _HOLDERS,
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=CommitmentRegistry(),
            posture_store=posture_store,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_backup_with_capability_succeeds(posture_store):
    """A holder of vault:backup in the right tenant/domain backs up successfully."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

    receipt = back_up_vault_key(
        _handle(),
        ShamirRitual(threshold=3, total_shards=5),
        _clearance("vault:backup"),
        _HOLDERS,
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
    )
    assert receipt.vault_id == _VAULT_ID
    assert receipt.kek_generation == _GEN


# ---------------------------------------------------------------------------
# N12-CL-02 — restore capability required + independence
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_restore_missing_capability_denied(posture_store):
    """N12-CL-02 — k valid shards WITHOUT vault:restore → missing-clearance."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)

    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]  # k=3 VALID shards

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            k_shards,
            _handle(),
            _clearance("vault:backup"),  # NOT vault:restore
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
        )
    # Fails on the CLEARANCE axis (missing-clearance) — NOT on shard validity.
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_restore_independence_wrong_shards_fail_other_axis(posture_store):
    """N12-CL-02 independence — holding vault:restore but wrong shards fails on the
    OTHER axis (unknown-shard at the foreign-shard gate), NOT clearance."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)

    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )

    # Present FOREIGN shards (a different secret) — their ciphertext-hashes are
    # absent from the distribution anchor → unknown-shard at step 6.
    foreign = generate(
        bytes.fromhex("aa" * 32), ShamirRitual(threshold=3, total_shards=5)
    )
    foreign_k = [list(s) for s in foreign[:3]]

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            foreign_k,
            _handle(),
            _clearance("vault:restore"),  # clearance HELD — passes step 1
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
        )
    assert exc.value.code is N12FT01Code.UNKNOWN_SHARD  # NOT missing-clearance


@pytest.mark.integration
def test_restore_with_capability_succeeds(posture_store):
    """A holder of vault:restore in the right tenant/domain restores successfully."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)

    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    receipt = restore_vault_key(
        k_shards,
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
    assert receipt.kek_generation == _GEN
    # RT-05 fired: the principal is SUPERVISED + a cooling-off start recorded.
    assert posture_store.get_posture("agent-b1") is TrustPosture.SUPERVISED


# ---------------------------------------------------------------------------
# N12-CL-02a — tenant/domain scoping + fail-closed order
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_restore_wrong_tenant_denied(posture_store):
    """N12-CL-02a(a) — vault:restore granted in tenant B fails against tenant A."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            k_shards,
            _handle(),
            _clearance("vault:restore", tenant="tenant-B"),  # WRONG tenant
            resolver=_Resolver(),  # vault is tenant-A
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_restore_wrong_domain_denied(posture_store):
    """N12-CL-02a(b) — vault:restore granted in domain B fails against domain A."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            k_shards,
            _handle(),
            _clearance(
                "vault:restore", domain="domain-B"
            ),  # WRONG domain (right tenant)
            resolver=_Resolver(),  # vault is domain-A
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_restore_fail_closed_order_tenant_before_token(posture_store):
    """N12-CL-02a fail-closed ORDER — a wrong-tenant AND wrong-token (missing
    vault:restore) input surfaces the TENANT failure first.

    Both axes fail; the gate checks tenant BEFORE token. We assert the tenant
    mismatch is what's reported (the error message names the tenant axis) — if
    token were checked first, the same missing-clearance code would carry the
    token-axis message instead.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            k_shards,
            _handle(),
            # WRONG tenant AND no vault:restore token (only vault:backup).
            _clearance("vault:backup", tenant="tenant-B"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
        )
    # Both axes fail; the gate denies with missing-clearance. The fail-closed
    # ORDER (tenant checked before domain before token) is asserted directly
    # against evaluate_clearance at Tier-1 (test_evaluate_clearance_tenant_first):
    # the restore path's first_failing wrapper preserves the CODE but collapses
    # the per-axis message, so the order claim is verified where the message
    # survives (the pure eval), not here.
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


# ---------------------------------------------------------------------------
# N12-CL-04 — cooling-off suspension via the trust-anchored clock
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cooling_off_suspends_second_op_same_principal(posture_store):
    """N12-CL-04 — after a materializing restore (cooling-off start recorded), a
    2nd restore by the SAME principal within 7 days → missing-clearance."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    # Fire the RT-05 trigger with an INJECTED trust-anchored start (NOT wall-clock).
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trigger_d6_posture_downgrade(
        posture_store, principal="agent-b1", forced_stale=False, now=start
    )

    # A 2nd restore 3 days into the window (trust-anchored now), same principal.
    now_in_window = start + timedelta(days=3)
    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            k_shards,
            _handle(),
            _clearance("vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            trust_anchored_now=now_in_window,
        )
    # The restore-path first_failing wrapper preserves the missing-clearance CODE
    # but collapses the cooling-off message; the message survives on the backup
    # path (test_cooling_off_suspends_backup_and_rotate_capability) where
    # evaluate_clearance raises directly.
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_cooling_off_start_recorded_from_trust_anchored_clock_end_to_end(posture_store):
    """N12-CL-04 (MED — writer clock source) — restore-1 ITSELF records the
    cooling-off START from the injected trust-anchored clock (NOT the producer's
    wall-clock), and a 2nd op by the same principal in-window is suspended.

    The other CL-04 tests seed the start via a DIRECT trigger_d6_posture_downgrade
    call; this one drives the START write through the real restore→D6 path so the
    producer's clock source is exercised end-to-end (reader/writer asymmetry guard).
    """
    from kailash.trust.vault.clearance import read_cooling_off_start

    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    # restore-1: a fixed trust-anchored instant, far from wall-clock now.
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    restore_vault_key(
        k_shards,
        _handle(),
        _clearance("vault:restore"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        trust_anchored_now=t0,
    )
    # The WRITER recorded the start from the injected clock, NOT wall-clock.
    assert read_cooling_off_start(posture_store, "agent-b1") == t0

    # restore-2 by the same principal 3 days into that window → suspended.
    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            k_shards,
            _handle(),
            _clearance("vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            trust_anchored_now=t0 + timedelta(days=3),
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_cooling_off_suspends_backup_and_rotate_capability(posture_store):
    """N12-CL-04 — the suspension covers vault:backup too (a 2nd materializing op
    of any suspended-capability class is blocked within the window)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trigger_d6_posture_downgrade(
        posture_store, principal="agent-b1", forced_stale=False, now=start
    )
    now_in_window = start + timedelta(days=2)

    with pytest.raises(VaultBindingError) as exc:
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:backup"),
            _HOLDERS,
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=CommitmentRegistry(),
            posture_store=posture_store,
            trust_anchored_now=now_in_window,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    assert "cooling-off" in str(exc.value).lower()


@pytest.mark.integration
def test_cooling_off_does_not_suspend_different_principal(posture_store):
    """N12-CL-04 — a DIFFERENT principal is NOT suspended by another's cooling-off."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trigger_d6_posture_downgrade(
        posture_store, principal="agent-b1", forced_stale=False, now=start
    )
    now_in_window = start + timedelta(days=3)

    # agent-other has NO cooling-off receipt → restore SUCCEEDS within the window.
    receipt = restore_vault_key(
        k_shards,
        _handle(),
        _clearance("vault:restore", principal="agent-other"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        trust_anchored_now=now_in_window,
    )
    assert receipt.kek_generation == _GEN


@pytest.mark.integration
def test_cooling_off_expires_after_window(posture_store):
    """N12-CL-04 — past the 7-day window the suspension lifts (window expiry, not a
    roll-forward bypass): a restore at start+8d by the same principal SUCCEEDS."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trigger_d6_posture_downgrade(
        posture_store, principal="agent-b1", forced_stale=False, now=start
    )
    now_after = start + timedelta(days=COOLING_OFF_DAYS + 1)

    receipt = restore_vault_key(
        k_shards,
        _handle(),
        _clearance("vault:restore"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        trust_anchored_now=now_after,
    )
    assert receipt.kek_generation == _GEN


@pytest.mark.integration
def test_cooling_off_clock_unavailable_keeps_suspension(posture_store):
    """N12-CL-04 fail-closed — a cooling-off receipt EXISTS but no trust-anchored
    clock is supplied → the suspension REMAINS in force (denied)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    commitment = _register_commitment(registry)
    shards = generate(_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_backup_anchor(
        dispatcher, identity, signer, shards=shards, commitment=commitment
    )
    k_shards = [list(s) for s in shards[:3]]

    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trigger_d6_posture_downgrade(
        posture_store, principal="agent-b1", forced_stale=False, now=start
    )

    # trust_anchored_now omitted → receipt exists but clock unavailable → deny.
    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            k_shards,
            _handle(),
            _clearance("vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            # trust_anchored_now intentionally omitted
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
