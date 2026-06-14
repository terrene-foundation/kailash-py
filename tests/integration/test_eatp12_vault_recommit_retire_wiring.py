# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for EATP-12 W3-C2b recommit + retire (N12-CB-04(c)/(e)).

Exercises ``kailash.trust.vault.registry_ops.recommit_vault_kek`` /
``retire_vault_kek_alg`` end-to-end against the REAL substrate — real C1
commitment helpers, real C2a :class:`CommitmentRegistry`, real D2 anchor
builders (``build_kek_recommit_anchor`` / ``build_kek_retire_anchor``), real D1
per-tier :class:`AuditDispatcher` with a real Ed25519 signer +
:class:`Ed25519Verifier`, and the real restore commitment-auth gate
(``restore_vault_key``) that reads the ``retired`` marker. NO mocks (per
``rules/testing.md`` Tier-2). The injected resolver is the deployment-supplied
trusted-module resolver returning known bytes (a Protocol-satisfying
deterministic adapter, NOT a mock).

Conformance coverage:

- N12-CB-04(c) recommit — ADDITIVE: recommit ``eatp-v1`` → ``eatp-v1.1`` ADDS
  ``C_Y`` without deleting ``C_X``; BOTH a restore under ``eatp-v1`` AND under
  ``eatp-v1.1`` verify (both entries live, V6(e)). Recommit dispatches a
  ``vault_kek_recommit`` recovery anchor recording the from-to pair; does NOT
  alter ``kek_generation`` / ``vault_id``.
- N12-CB-04(e) retire — after recommit, retiring ``eatp-v1`` marks the entry
  non-verifiable; a restore presenting the ``eatp-v1`` backup fails
  ``retired-commitment-alg`` (distinct from ``kek-commitment-mismatch`` +
  ``commitment-alg-mismatch``). Dispatches a ``vault_kek_retire`` recovery anchor.
- Recoverability guard — retiring the ONLY live entry (no superseding ``C_Y``)
  is REFUSED.
- N12-FT-03 first-failing order — a recommit violating ≥2 gates surfaces the
  FIRST gate's code (generation-altered before binding-mismatch).
- Clearance — recommit/retire without the required capability → missing-clearance.
- AU-02b — each op dispatches its anchor to recovery; a failing dispatch aborts
  the op with NO registry mutation.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import AuditChainSignatureError
from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.backup import restore_vault_key
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.registry_ops import recommit_vault_kek, retire_vault_kek_alg
from kailash.trust.vault.shamir import ShamirRitual, generate, serialize_shard
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KNOWN_KEK = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_KEK_GENERATION = 7
_KEY_ID = "kek-handle-abc"
_VAULT_ID = "vault-xyz"
_PROVENANCE = "vault-derived:v1"
_ALG_V1 = "eatp-v1"
_ALG_V11 = "eatp-v1.1"


class _DeterministicResolver:
    """Deployment-supplied trusted resolver returning the known KEK (NOT a mock)."""

    def __init__(
        self,
        *,
        key_class: KeyClass = KeyClass.KEK,
        kek_generation: int = _KEK_GENERATION,
    ) -> None:
        self._key_class = key_class
        self._gen = kek_generation

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=_KNOWN_KEK,
            key_class=self._key_class,
            kek_generation=self._gen,
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


def _shard_commitments(shards) -> list[str]:
    return [
        hashlib.sha256(serialize_shard(list(s)).encode("utf-8")).hexdigest()
        for s in shards
    ]


def _commitment(alg: str) -> str:
    return kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=alg,
    )


def _seed_registry_with_v1(registry: CommitmentRegistry) -> str:
    """Register the initial ``eatp-v1`` commitment (models a prior backup)."""
    commitment = _commitment(_ALG_V1)
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        kek_commitment_alg=_ALG_V1,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    return commitment


def _restore(
    *,
    dispatcher: AuditDispatcher,
    identity,
    signer,
    registry: CommitmentRegistry,
    shards,
    alg: str,
):
    """Drive a restore under ``alg`` against ``registry`` (no caller commitment).

    The recovery-tier distribution anchor for ``(vault_id, gen)`` is seeded by
    the backup-distribution helper below so foreign-shard sourcing succeeds.
    """
    return restore_vault_key(
        shards[:3],
        _handle(),
        _clearance("vault:restore"),
        resolver=_DeterministicResolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=alg,
        registry=registry,
        kek_commitment_alg=alg,
        holders=["h1", "h2", "h3", "h4", "h5"],
        shard_commitments=_shard_commitments(shards),
    )


@pytest.mark.integration
def test_recommit_keeps_old_alg_verifiable_both_live():
    """N12-CB-04(c) V6(e) — recommit ADDS C_Y; BOTH eatp-v1 and eatp-v1.1 verify."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _DeterministicResolver()

    c_x = _seed_registry_with_v1(registry)
    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))

    new_entry = recommit_vault_kek(
        _handle(),
        _clearance("vault:backup"),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG_V1,
        prior_kek_commitment_alg=_ALG_V1,
        prior_kek_identity_commitment=c_x,
        new_kek_commitment_alg=_ALG_V11,
        registry=registry,
    )

    # ADDITIVE: both algs live; the new C_Y differs from C_X (different hash).
    assert new_entry.retired is False
    assert new_entry.commitment == _commitment(_ALG_V11)
    assert new_entry.commitment != c_x
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V1,
        _ALG_V11,
    )
    # The prior entry is untouched (not deleted).
    prior = registry.lookup(
        vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION, kek_commitment_alg=_ALG_V1
    ).entry
    assert prior is not None and prior.commitment == c_x and prior.retired is False

    # The recovery tier holds a vault_kek_recommit anchor recording the from-to pair.
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    recommit_anchor = next(
        e for e in rec if e.event_payload["subtype"] == "vault_kek_recommit"
    )
    p = recommit_anchor.event_payload
    assert p["prior_kek_commitment_alg"] == _ALG_V1
    assert p["prior_kek_identity_commitment"] == c_x
    assert p["new_kek_commitment_alg"] == _ALG_V11
    assert p["new_kek_identity_commitment"] == new_entry.commitment
    # MUST NOT alter generation / vault.
    assert p["kek_generation"] == _KEK_GENERATION
    assert p["vault_id"] == _VAULT_ID

    # Seed the distribution anchor so both restores can source foreign-shards.
    _seed_distribution_anchor(dispatcher, identity, signer, shards)

    # BOTH restores verify — eatp-v1 (the old, still-live alg) AND eatp-v1.1.
    r_old = _restore(
        dispatcher=dispatcher,
        identity=identity,
        signer=signer,
        registry=registry,
        shards=shards,
        alg=_ALG_V1,
    )
    assert r_old.kek_generation == _KEK_GENERATION
    r_new = _restore(
        dispatcher=dispatcher,
        identity=identity,
        signer=signer,
        registry=registry,
        shards=shards,
        alg=_ALG_V11,
    )
    assert r_new.kek_generation == _KEK_GENERATION


def _seed_distribution_anchor(dispatcher, identity, signer, shards) -> None:
    """Dispatch a vault_key_backup distribution anchor (foreign-shard source)."""
    from kailash.delegate.audit import content_signing_bytes
    from kailash.trust.vault.anchors import build_backup_anchor

    payload = build_backup_anchor(
        alg_id=_ALG_V1,
        k=3,
        n=5,
        holders=["h1", "h2", "h3", "h4", "h5"],
        shard_count=5,
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        kek_identity_commitment=_commitment(_ALG_V1),
        kek_commitment_alg=_ALG_V1,
        kcv="0" * 16,
        shard_commitments=_shard_commitments(shards),
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


@pytest.mark.integration
def test_retire_old_alg_then_restore_fails_retired_commitment_alg():
    """N12-CB-04(e) — retire eatp-v1 (after recommit to C_Y) → restore fails retired."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _DeterministicResolver()

    c_x = _seed_registry_with_v1(registry)
    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_distribution_anchor(dispatcher, identity, signer, shards)

    # Recommit to a strong C_Y first (so recoverability holds at retire time).
    recommit_vault_kek(
        _handle(),
        _clearance("vault:backup"),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG_V1,
        prior_kek_commitment_alg=_ALG_V1,
        prior_kek_identity_commitment=c_x,
        new_kek_commitment_alg=_ALG_V11,
        registry=registry,
    )

    # Retire eatp-v1 — requires the distinct vault:retire-alg capability.
    retired_entry = retire_vault_kek_alg(
        _handle(),
        _clearance("vault:retire-alg"),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG_V1,
        retired_kek_commitment_alg=_ALG_V1,
        retired_kek_identity_commitment=c_x,
        registry=registry,
    )
    assert retired_entry.retired is True
    # eatp-v1 is no longer a LIVE alg; eatp-v1.1 remains live.
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V11,
    )

    # A vault_kek_retire anchor landed on recovery.
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    retire_anchor = next(
        e for e in rec if e.event_payload["subtype"] == "vault_kek_retire"
    )
    assert retire_anchor.event_payload["retired_kek_commitment_alg"] == _ALG_V1
    assert retire_anchor.event_payload["retired_kek_identity_commitment"] == c_x

    # A restore presenting the eatp-v1 backup now fails retired-commitment-alg —
    # distinct from kek-commitment-mismatch + commitment-alg-mismatch.
    with pytest.raises(VaultBindingError) as exc:
        _restore(
            dispatcher=dispatcher,
            identity=identity,
            signer=signer,
            registry=registry,
            shards=shards,
            alg=_ALG_V1,
        )
    assert exc.value.code is N12FT01Code.RETIRED_COMMITMENT_ALG
    assert exc.value.code is not N12FT01Code.KEK_COMMITMENT_MISMATCH
    assert exc.value.code is not N12FT01Code.COMMITMENT_ALG_MISMATCH

    # The still-live eatp-v1.1 alg restores cleanly (corpus is recoverable).
    r_new = _restore(
        dispatcher=dispatcher,
        identity=identity,
        signer=signer,
        registry=registry,
        shards=shards,
        alg=_ALG_V11,
    )
    assert r_new.kek_generation == _KEK_GENERATION


@pytest.mark.integration
def test_retire_only_live_entry_is_refused_recoverability_guard():
    """N12-CB-04(e)(4) — retiring the ONLY live entry (no C_Y) is REFUSED."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

    c_x = _seed_registry_with_v1(registry)  # eatp-v1 is the ONLY live entry

    with pytest.raises(VaultBindingError) as exc:
        retire_vault_kek_alg(
            _handle(),
            _clearance("vault:retire-alg"),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            retired_kek_commitment_alg=_ALG_V1,
            retired_kek_identity_commitment=c_x,
            registry=registry,
        )
    # Recoverability refusal is a missing-clearance-class typed error.
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    # The entry stays LIVE (the retire was refused; the corpus is not stranded).
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V1,
    )
    entry = registry.lookup(
        vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION, kek_commitment_alg=_ALG_V1
    ).entry
    assert entry is not None and entry.retired is False
    # No vault_kek_retire anchor was dispatched (refused BEFORE the anchor, the
    # gate ran first; AU-02b means anchor-before-mutation, but the gate failed
    # before either).
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    assert not any(e.event_payload["subtype"] == "vault_kek_retire" for e in rec)


@pytest.mark.integration
def test_recommit_first_failing_order_generation_before_binding():
    """N12-FT-03 — a recommit violating ≥2 gates surfaces the FIRST gate's code.

    Craft a recommit whose resolved generation differs from the handle's captured
    generation (gate 2 → recommit-generation-altered) AND whose prior commitment
    is bogus (gate 3 → unknown-prior-commitment). The FIRST gate (generation)
    MUST surface, never the later binding/prior gate.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    # Resolver returns a DIFFERENT generation than the handle's captured 7.
    resolver = _DeterministicResolver(kek_generation=_KEK_GENERATION + 1)

    _seed_registry_with_v1(registry)

    with pytest.raises(VaultBindingError) as exc:
        recommit_vault_kek(
            _handle(),  # captured generation 7
            _clearance("vault:backup"),
            resolver=resolver,  # resolves generation 8 → altered
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment="ff"
            * 32,  # bogus prior (gate 3 would fail too)
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
        )
    # Gate 2 (generation-altered) is BEFORE gate 3 (prior) + gate 4 (binding).
    assert exc.value.code is N12FT01Code.RECOMMIT_GENERATION_ALTERED
    # No anchor dispatched + no registry mutation (gate failed before AU-02b).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V1,
    )


@pytest.mark.integration
def test_recommit_unknown_prior_commitment_when_prior_bogus():
    """N12-FT-03 gate 3 — a recommit naming a bogus prior commitment → unknown-prior."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _DeterministicResolver()

    _seed_registry_with_v1(registry)

    with pytest.raises(VaultBindingError) as exc:
        recommit_vault_kek(
            _handle(),
            _clearance("vault:backup"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment="ab" * 32,  # no live entry equals this
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.UNKNOWN_PRIOR_COMMITMENT
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


@pytest.mark.integration
def test_recommit_missing_clearance():
    """Clearance — recommit without vault:backup → missing-clearance."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _DeterministicResolver()
    c_x = _seed_registry_with_v1(registry)

    with pytest.raises(VaultBindingError) as exc:
        recommit_vault_kek(
            _handle(),
            _clearance("vault:read"),  # lacks vault:backup
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment=c_x,
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


@pytest.mark.integration
def test_retire_missing_retire_alg_capability():
    """Clearance — retire WITHOUT vault:retire-alg → missing-clearance.

    Ordinary vault:restore / vault:backup MUST NOT authorize a retire
    (N12-CB-04(e)(2)).
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _DeterministicResolver()
    c_x = _seed_registry_with_v1(registry)
    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_distribution_anchor(dispatcher, identity, signer, shards)
    recommit_vault_kek(
        _handle(),
        _clearance("vault:backup"),
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG_V1,
        prior_kek_commitment_alg=_ALG_V1,
        prior_kek_identity_commitment=c_x,
        new_kek_commitment_alg=_ALG_V11,
        registry=registry,
    )

    # vault:backup + vault:restore but NOT vault:retire-alg → refused.
    with pytest.raises(VaultBindingError) as exc:
        retire_vault_kek_alg(
            _handle(),
            _clearance("vault:backup", "vault:restore"),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            retired_kek_commitment_alg=_ALG_V1,
            retired_kek_identity_commitment=c_x,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    # eatp-v1 stays live (retire refused at the clearance gate).
    assert _ALG_V1 in registry.live_algs(
        vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION
    )


@pytest.mark.integration
def test_recommit_au02b_failing_dispatch_aborts_no_registry_mutation():
    """AU-02b — a failing recommit dispatch aborts with NO new registry entry."""
    signer_identity, _good_verifier, signer = _build_signer()
    _other_identity, wrong_verifier, _other_signer = _build_signer()
    # Dispatcher whose verifier knows a DIFFERENT key → dispatch RAISES.
    dispatcher = AuditDispatcher.for_named_tiers(wrong_verifier)
    registry = CommitmentRegistry()
    resolver = _DeterministicResolver()
    c_x = _seed_registry_with_v1(registry)

    with pytest.raises(Exception) as exc:
        recommit_vault_kek(
            _handle(),
            _clearance("vault:backup"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment=c_x,
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
        )
    assert isinstance(exc.value, AuditChainSignatureError)
    # AU-02b: the new alg was NEVER registered (dispatch failed → no mutation).
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V1,
    )
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0


@pytest.mark.integration
def test_retire_au02b_failing_dispatch_aborts_entry_stays_live():
    """AU-02b — a failing retire dispatch aborts; the entry stays LIVE."""
    signer_identity, _good_verifier, signer = _build_signer()
    _other_identity, wrong_verifier, _other_signer = _build_signer()
    good_dispatcher = AuditDispatcher.for_named_tiers(_good_verifier)
    resolver = _DeterministicResolver()
    registry = CommitmentRegistry()
    c_x = _seed_registry_with_v1(registry)
    shards = generate(_KNOWN_KEK, ShamirRitual(threshold=3, total_shards=5))
    _seed_distribution_anchor(good_dispatcher, signer_identity, signer, shards)
    recommit_vault_kek(
        _handle(),
        _clearance("vault:backup"),
        resolver=resolver,
        dispatcher=good_dispatcher,
        signer=signer,
        signer_identity=signer_identity,
        alg_id=_ALG_V1,
        prior_kek_commitment_alg=_ALG_V1,
        prior_kek_identity_commitment=c_x,
        new_kek_commitment_alg=_ALG_V11,
        registry=registry,
    )

    # Now attempt the retire through a WRONG-key dispatcher → dispatch RAISES.
    wrong_dispatcher = AuditDispatcher.for_named_tiers(wrong_verifier)
    with pytest.raises(AuditChainSignatureError):
        retire_vault_kek_alg(
            _handle(),
            _clearance("vault:retire-alg"),
            dispatcher=wrong_dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            alg_id=_ALG_V1,
            retired_kek_commitment_alg=_ALG_V1,
            retired_kek_identity_commitment=c_x,
            registry=registry,
        )
    # eatp-v1 stays LIVE (dispatch failed before the entry was replaced).
    entry = registry.lookup(
        vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION, kek_commitment_alg=_ALG_V1
    ).entry
    assert entry is not None and entry.retired is False


# ===========================================================================
# LOW-1 — recommit-binding-mismatch (FT-03 gate 4 "new-commitment-binds-secret")
# ===========================================================================


class _SecretFlipResolved(ResolvedKek):
    """A ResolvedKek whose ``master_secret`` differs between its first and second
    read — modelling a resolver whose backing secret is not stable across the
    gate-4 compute-then-verify window.

    Protocol-satisfying deterministic adapter (NOT a mock): the FIRST read of
    ``master_secret`` returns ``first``, every subsequent read returns ``second``.
    Gate 4 computes ``C_Y`` over the first read and then re-verifies the bind over
    the second read — with two distinct secrets the recomputed commitment does NOT
    bind, surfacing ``recommit-binding-mismatch`` genuinely (no monkeypatching of
    the system-under-test).
    """

    def __init__(self, *, first: bytes, second: bytes) -> None:
        super().__init__(
            master_secret=first,
            key_class=KeyClass.KEK,
            kek_generation=_KEK_GENERATION,
            key_id=_KEY_ID,
            passphrase_provenance=_PROVENANCE,
            vault_tenant="t1",
            vault_domain="d1",
        )
        # Store the flip state out-of-band; the property below owns the reads.
        object.__setattr__(self, "_first", first)
        object.__setattr__(self, "_second", second)
        object.__setattr__(self, "_reads", 0)

    @property  # type: ignore[override]
    def master_secret(self) -> bytes:
        reads = object.__getattribute__(self, "_reads")
        object.__setattr__(self, "_reads", reads + 1)
        return (
            object.__getattribute__(self, "_first")
            if reads == 0
            else object.__getattribute__(self, "_second")
        )

    @master_secret.setter
    def master_secret(self, value: bytes) -> None:
        # The parent dataclass __init__ assigns master_secret; route it to the
        # backing field. zeroize() uses object.__setattr__ so it bypasses this.
        object.__setattr__(self, "_first", value)


class _SecretFlipResolver:
    """Deployment-supplied resolver returning a _SecretFlipResolved (NOT a mock)."""

    def __init__(self, *, first: bytes, second: bytes) -> None:
        self._first = first
        self._second = second

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return _SecretFlipResolved(first=self._first, second=self._second)


@pytest.mark.integration
def test_recommit_binding_mismatch_when_new_commitment_does_not_bind_secret():
    """LOW-1 / N12-FT-03 gate 4 — a new commitment that does NOT bind the resolved
    secret → recommit-binding-mismatch.

    Gate 4 (``new-commitment-binds-secret``) recomputes ``C_Y`` over the resolved
    secret and constant-time verifies it binds that secret. When the resolved
    secret is not stable across the compute-then-verify window (modelled by a
    resolver whose master_secret flips between reads), ``C_Y`` (over secret-A) does
    NOT bind secret-B → ``recommit-binding-mismatch`` — the control reachable but
    previously untested.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    resolver = _SecretFlipResolver(first=_KNOWN_KEK, second=b"\xab" * 32)

    # A LIVE prior eatp-v1 entry MUST exist so gate 3 passes and gate 4 runs. The
    # prior commitment is computed over the FIRST secret (_KNOWN_KEK) — but the
    # prior-commitment gate (step 3) does not read the resolved secret, so this is
    # just the standard prior registration.
    c_x = _seed_registry_with_v1(registry)

    with pytest.raises(VaultBindingError) as exc:
        recommit_vault_kek(
            _handle(),
            _clearance("vault:backup"),
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment=c_x,
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.RECOMMIT_BINDING_MISMATCH
    # Gate 4 failed before any anchor dispatch / registry mutation (AU-02b).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    # The new alg was NOT registered (recommit aborted at the gate).
    assert (
        registry.lookup(
            vault_id=_VAULT_ID,
            kek_generation=_KEK_GENERATION,
            kek_commitment_alg=_ALG_V11,
        ).entry
        is None
    )
