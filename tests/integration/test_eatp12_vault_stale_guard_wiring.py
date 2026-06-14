# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the EATP-12 stale-generation guard (W3-C3).

Exercises ``kailash.trust.vault.restore_vault_key``'s FT-02 step-8
``ordinal-generation`` gate (N12-SG-02/03/05) + the N12-RT-05 D6 posture trigger
end-to-end against the REAL substrate — real SLIP-0039 ``shamir.generate``, real
per-tier :class:`~kailash.delegate.audit.AuditChainEngine`, real Ed25519 signer +
:class:`~kailash.delegate.verifier.Ed25519Verifier`, real C1 commitment, real D2
anchor builders (incl. ``build_kek_rotation_anchor`` for the advanced-generation
setup + ``build_restore_forced_stale_anchor``), real D1 dispatcher, real
:class:`~kailash.trust.posture.posture_store.SQLitePostureStore` against a temp
DB. NO mocks (``rules/testing.md`` Tier-2: real infrastructure).

The injected resolver is the deployment-supplied trusted-module resolver (NOT a
mock): a deterministic in-test resolver returning known KEK bytes for a chosen
captured generation, exercised through the real binding code path.

Conformance coverage (EATP-12 §6 / §5.4 / §4.6):

- N12-SG-02 — default stale refusal: seed an advanced current generation N+1 via
  a dispatched ``vault_kek_rotation`` anchor; restore an old-gen N backup with
  ``force_stale=False`` → ``stale-generation``, no KEK re-established.
- N12-SG-03 — ``force_stale`` step-8-only: same setup + ``force_stale=True`` +
  ``vault:restore-stale`` → SUCCEEDS, dual-emits a ``vault_key_restore_forced_stale``
  anchor to BOTH recovery AND safety, ``receipt.forced_stale is True``; AND
  ``force_stale`` does NOT bypass step 7 (a commitment mismatch under
  ``force_stale`` still fails ``kek-commitment-mismatch``).
- N12-SG-03 missing-capability — ``force_stale=True`` with only ``vault:restore``
  → ``missing-clearance``.
- N12-SG-05 — denylist: revoke gen N; restore gen N (even when N==current) →
  ``revoked-generation``; ``force_stale`` does NOT override the denylist.
- N12-RT-05 — after a successful ordinary restore the principal's posture in the
  PostureStore is SUPERVISED + the 7-day cooling-off start is recorded.
- N12-FT-02 8-step ordering — a crafted input failing multiple gates returns the
  FIRST per ``RESTORE_GATE_ORDER`` (unknown-shard at step 6 before
  stale-generation at step 8).
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
from kailash.trust.posture.postures import TrustPosture
from kailash.trust.vault.anchors import build_backup_anchor, build_kek_rotation_anchor
from kailash.trust.vault.backup import restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.shamir import ShamirRitual, generate, serialize_shard
from kailash.trust.vault.stale_guard import (
    COOLING_OFF_DAYS,
    CompromisedGenerationDenylist,
)
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KEK_OLD = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_GEN_OLD = 7
_GEN_NEW = 8  # the advanced current generation seeded via a rotation anchor
_KEY_ID = "kek-handle-c3"
_VAULT_ID = "vault-c3"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"
_HOLDERS = ["h1", "h2", "h3", "h4", "h5"]


def _shard_commitments(shards) -> list[str]:
    return [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]


class _Resolver:
    """The deployment-supplied trusted resolver (NOT a mock) returning the old KEK.

    Resolves the target handle to the OLD generation's KEK bytes + ``key_class``
    + ``kek_generation`` — the captured generation the restore authenticates and
    ordinal-compares.
    """

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
        )


def _build_signer() -> tuple[DelegateIdentity, Ed25519Verifier, Callable[[bytes], str]]:
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-c3",
        role_binding_ref="rb-c3",
        genesis_ref="gen-c3",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


def _handle(generation: int = _GEN_OLD) -> VaultKeyHandle:
    return VaultKeyHandle(key_id=_KEY_ID, vault_id=_VAULT_ID, kek_generation=generation)


def _clearance(*caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal="agent-c3", tenant="t1", domain="d1", capabilities=tuple(caps)
    )


def _dispatch(dispatcher, identity, signer, payload, tier) -> None:
    pre = content_signing_bytes("external_side_effect", payload, identity.delegate_id)
    dispatcher.dispatch("external_side_effect", payload, identity, signer(pre), tier)


def _seed_old_gen_backup_anchor(
    dispatcher, identity, signer, *, shards, commitment, generation
) -> list[str]:
    """Dispatch a ``vault_key_backup`` distribution anchor at ``generation``.

    Returns the shard_commitments array recorded (the foreign-shard source the
    restore consults for that generation). Mirrors what ``back_up_vault_key``
    dispatched at backup time (the test cannot share backup's internal CSPRNG
    shards, so it constructs the post-backup distribution state).
    """
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
        principal="agent-c3",
        timestamp="unverified",
        time_attested=False,
        side_channel_hardened=False,
    )
    _dispatch(dispatcher, identity, signer, payload, AuditTier.RECOVERY.value)
    return commitments


def _seed_rotation_to_new_gen(
    dispatcher, identity, signer, *, new_secret, new_shards
) -> None:
    """Dispatch a ``vault_kek_rotation`` anchor advancing the vault to _GEN_NEW.

    This is what makes ``current_generation_from_chain`` derive _GEN_NEW as the
    current generation (N12-RT-06). The rotation re-shards under a fresh KEK; the
    new generation's distribution rides this anchor.
    """
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
        principal="agent-c3",
        timestamp="unverified",
        time_attested=False,
    )
    _dispatch(dispatcher, identity, signer, payload, AuditTier.RECOVERY.value)


@pytest.fixture(autouse=True)
def _isolate_default_singletons():
    """Reset the process-default registry + denylist between tests."""
    from kailash.trust.vault.registry import default_commitment_registry
    from kailash.trust.vault.stale_guard import default_compromised_generation_denylist

    default_commitment_registry()._store.clear()
    default_compromised_generation_denylist()._revoked.clear()
    yield
    default_commitment_registry()._store.clear()
    default_compromised_generation_denylist()._revoked.clear()


@pytest.fixture
def posture_store():
    """A REAL SQLitePostureStore against a temp DB (Tier-2, NO mock)."""
    fd, path = tempfile.mkstemp(suffix="-c3-postures.db")
    os.close(fd)
    os.unlink(path)  # let the store create it with 0o600
    store = SQLitePostureStore(path)
    try:
        yield store
    finally:
        store.close()
        if os.path.exists(path):
            os.unlink(path)


def _old_gen_commitment(secret: bytes = _KEK_OLD) -> str:
    return kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_OLD,
        master_secret=secret,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )


# ---------------------------------------------------------------------------
# N12-SG-02 — default stale refusal
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stale_generation_refused_by_default(posture_store):
    """N12-SG-02 — old-gen backup restored against an advanced current gen → stale."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

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
    # The old-gen distribution (so step 6 passes against the CAPTURED gen anchor).
    _seed_old_gen_backup_anchor(
        dispatcher,
        identity,
        signer,
        shards=old_shards,
        commitment=commitment,
        generation=_GEN_OLD,
    )
    # Advance the current generation to _GEN_NEW via an audited rotation anchor.
    _seed_rotation_to_new_gen(
        dispatcher, identity, signer, new_secret=new_secret, new_shards=new_shards
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance("vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            force_stale=False,
        )
    assert exc.value.code is N12FT01Code.STALE_GENERATION
    # No KEK re-established: no restore OUTCOME anchor, a denial on safety.
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    assert not any(
        e.event_payload["subtype"]
        in ("vault_key_restore", "vault_key_restore_forced_stale")
        for e in rec
    )
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1
    # D6 NOT triggered (no materialized KEK): posture stays at the default.
    assert posture_store.get_posture("agent-c3") == TrustPosture.SUPERVISED
    assert posture_store.get_history("agent-c3") == []


# ---------------------------------------------------------------------------
# N12-SG-03 — force_stale step-8-only override
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_force_stale_succeeds_dual_emits_forced_anchor(posture_store):
    """N12-SG-03 — force_stale + vault:restore-stale restores; dual-emits to both tiers."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

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

    receipt = restore_vault_key(
        old_shards[:3],
        _handle(_GEN_OLD),
        _clearance("vault:restore", "vault:restore-stale"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        force_stale=True,
    )
    assert receipt.forced_stale is True
    assert receipt.kek_generation == _GEN_OLD

    # Forced-stale anchor dual-emitted to BOTH recovery AND safety.
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    saf = dispatcher._engines[AuditTier.SAFETY.value].entries
    rec_forced = [
        e for e in rec if e.event_payload["subtype"] == "vault_key_restore_forced_stale"
    ]
    saf_forced = [
        e for e in saf if e.event_payload["subtype"] == "vault_key_restore_forced_stale"
    ]
    assert len(rec_forced) == 1, "forced-stale anchor on recovery"
    assert len(saf_forced) == 1, "forced-stale anchor dual-emitted to safety"
    p = rec_forced[0].event_payload
    assert p["restored_generation"] == _GEN_OLD
    assert p["overridden_current_generation"] == _GEN_NEW
    assert p["kek_generation"] == _GEN_OLD
    # CAPTURED (old-gen) distribution recorded (fix [2]), NOT the current gen's.
    assert p["shard_commitments"] == old_commitments
    assert p["shard_count"] == 5
    # NO ordinary vault_key_restore anchor was emitted (forced path is distinct).
    assert not any(e.event_payload["subtype"] == "vault_key_restore" for e in rec)

    # N12-RT-05 fired on the forced-stale (materializing) restore.
    assert posture_store.get_posture("agent-c3") == TrustPosture.SUPERVISED
    history = posture_store.get_history("agent-c3")
    assert len(history) == 1
    assert history[0].metadata.get("forced_stale") is True
    assert "cooling_off_start" in history[0].metadata


@pytest.mark.integration
def test_force_stale_does_not_bypass_commitment_auth(posture_store):
    """N12-SG-03 — force_stale overrides ONLY step 8; a step-7 mismatch still fails."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

    old_shards = generate(_KEK_OLD, ShamirRitual(threshold=3, total_shards=5))
    new_secret = bytes.fromhex("ff" * 32)
    new_shards = generate(new_secret, ShamirRitual(threshold=3, total_shards=5))

    # Register a commitment over a DIFFERENT secret: the genuine reconstructed
    # old KEK will NOT match it → step-7 kek-commitment-mismatch, EVEN under
    # force_stale (which overrides only step 8).
    wrong_commitment = kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_OLD,
        master_secret=b"\xaa" * 32,
        passphrase_provenance=_PROVENANCE,
        alg=_ALG,
    )
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_OLD,
        kek_commitment_alg=_ALG,
        commitment=wrong_commitment,
        key_id=_KEY_ID,
    )
    # Distribution carries the genuine old shards so step 6 PASSES (the foreign-
    # shard gate is not the one under test); step 7 is where it must fail.
    _seed_old_gen_backup_anchor(
        dispatcher,
        identity,
        signer,
        shards=old_shards,
        commitment=wrong_commitment,
        generation=_GEN_OLD,
    )
    _seed_rotation_to_new_gen(
        dispatcher, identity, signer, new_secret=new_secret, new_shards=new_shards
    )

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance("vault:restore", "vault:restore-stale"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            force_stale=True,
        )
    assert exc.value.code is N12FT01Code.KEK_COMMITMENT_MISMATCH
    # No forced-stale anchor emitted (the restore aborted at step 7).
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    assert not any(
        e.event_payload["subtype"] == "vault_key_restore_forced_stale" for e in rec
    )
    # D6 NOT fired (no materialization).
    assert posture_store.get_history("agent-c3") == []


@pytest.mark.integration
def test_force_stale_without_capability_missing_clearance(posture_store):
    """N12-SG-03 / F-AUTHZ-9 — force_stale with only vault:restore → missing-clearance."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    old_shards = generate(_KEK_OLD, ShamirRitual(threshold=3, total_shards=5))

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance("vault:restore"),  # lacks vault:restore-stale
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            force_stale=True,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    # Denied before any key material touched: a denial on safety, none on recovery.
    assert dispatcher.sequence_length(AuditTier.SAFETY.value) == 1
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    denial = dispatcher._engines[AuditTier.SAFETY.value].entries[0]
    assert denial.event_payload["subtype"] == "vault_key_restore_denied"
    assert denial.event_payload["missing_capability_or_scope"] == "vault:restore-stale"
    assert posture_store.get_history("agent-c3") == []


# ---------------------------------------------------------------------------
# N12-SG-05 — compromised-generation denylist
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_revoked_generation_refused_even_when_current(posture_store):
    """N12-SG-05 — a denylisted gen is refused EVEN WHEN it equals current."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    denylist = CompromisedGenerationDenylist()

    old_shards = generate(_KEK_OLD, ShamirRitual(threshold=3, total_shards=5))
    commitment = _old_gen_commitment()
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_GEN_OLD,
        kek_commitment_alg=_ALG,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    # No rotation anchor → _GEN_OLD IS current. Distribution at _GEN_OLD so step 6
    # passes; the denylist (step 8a) fires even though N == current.
    _seed_old_gen_backup_anchor(
        dispatcher,
        identity,
        signer,
        shards=old_shards,
        commitment=commitment,
        generation=_GEN_OLD,
    )
    denylist.revoke(vault_id=_VAULT_ID, kek_generation=_GEN_OLD)

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance("vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            denylist=denylist,
            posture_store=posture_store,
            force_stale=False,
        )
    assert exc.value.code is N12FT01Code.REVOKED_GENERATION
    assert posture_store.get_history("agent-c3") == []


@pytest.mark.integration
def test_denylist_not_overridable_by_force_stale(posture_store):
    """N12-SG-05 — force_stale does NOT override the denylist."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    denylist = CompromisedGenerationDenylist()

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
    _seed_old_gen_backup_anchor(
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
    denylist.revoke(vault_id=_VAULT_ID, kek_generation=_GEN_OLD)

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            old_shards[:3],
            _handle(_GEN_OLD),
            _clearance("vault:restore", "vault:restore-stale"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            denylist=denylist,
            posture_store=posture_store,
            force_stale=True,  # MUST NOT override the denylist
        )
    assert exc.value.code is N12FT01Code.REVOKED_GENERATION
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    assert not any(
        e.event_payload["subtype"] == "vault_key_restore_forced_stale" for e in rec
    )
    assert posture_store.get_history("agent-c3") == []


# ---------------------------------------------------------------------------
# N12-RT-05 — D6 trigger on ordinary restore
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rt05_d6_downgrade_on_ordinary_restore(posture_store):
    """N12-RT-05 — a successful ordinary restore downgrades posture + starts cooling-off."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

    # Single-generation surface (no rotation anchor): restore at the current gen.
    shards = generate(_KEK_OLD, ShamirRitual(threshold=3, total_shards=5))
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
        shards=shards,
        commitment=commitment,
        generation=_GEN_OLD,
    )

    # Pre-seed the principal at a HIGHER posture so the downgrade is observable.
    posture_store.set_posture("agent-c3", TrustPosture.AUTONOMOUS)

    receipt = restore_vault_key(
        shards[:3],
        _handle(_GEN_OLD),
        _clearance("vault:restore"),
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
        posture_store=posture_store,
        force_stale=False,
    )
    assert receipt.forced_stale is False
    # The ordinary restore materialized the KEK → D6 fired.
    assert posture_store.get_posture("agent-c3") == TrustPosture.SUPERVISED
    history = posture_store.get_history("agent-c3")
    assert len(history) == 1
    md = history[0].metadata
    assert md["trigger"] == "vault_restore_materialized_kek"
    assert md["cooling_off_days"] == COOLING_OFF_DAYS
    assert "cooling_off_start" in md and "cooling_off_end" in md
    assert history[0].from_posture == TrustPosture.AUTONOMOUS
    assert history[0].to_posture == TrustPosture.SUPERVISED


# ---------------------------------------------------------------------------
# N12-FT-02 — 8-step ordering (first-failing)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ft02_unknown_shard_step6_beats_stale_step8(posture_store):
    """N12-FT-02 — unknown-shard (step 6) fires BEFORE stale-generation (step 8)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

    old_shards = generate(_KEK_OLD, ShamirRitual(threshold=3, total_shards=5))
    # A DIFFERENT shard set whose ciphertext hashes are NOT in the distribution —
    # presenting these foreign shards trips step 6 (unknown-shard).
    foreign_shards = generate(b"\xcc" * 32, ShamirRitual(threshold=3, total_shards=5))
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
    # Distribution carries the GENUINE old shards; the presented foreign shards
    # are absent from it → step 6 fires. The vault is ALSO stale (gen N < N+1),
    # so step 8 WOULD fire — the test proves step 6 wins.
    _seed_old_gen_backup_anchor(
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

    with pytest.raises(VaultBindingError) as exc:
        restore_vault_key(
            foreign_shards[:3],  # foreign → step-6 unknown-shard
            _handle(_GEN_OLD),
            _clearance("vault:restore"),
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=registry,
            posture_store=posture_store,
            force_stale=False,
        )
    # First-failing per RESTORE_GATE_ORDER: step 6 (unknown-shard), NOT step 8.
    assert exc.value.code is N12FT01Code.UNKNOWN_SHARD
    assert posture_store.get_history("agent-c3") == []
