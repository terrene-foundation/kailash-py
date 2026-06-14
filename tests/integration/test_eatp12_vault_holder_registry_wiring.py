# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the EATP-12 holder registry (W4-B2, N12-SH-01 / N12-SH-03).

Exercises the deployment-controlled holder registry end-to-end through the REAL
``back_up_vault_key`` binding (real SLIP-0039 ``shamir.generate``, real Ed25519
signer + verifier, real D1 dispatcher, real D2 anchor builders) — NO mocks (per
``rules/testing.md`` Tier-2). The injected resolver is the deployment-supplied
trusted-module resolver (a deterministic in-test resolver returning known KEK
bytes, NOT a Tier-2 mock — the §3.4 / #630 seam).

Conformance coverage (EATP-12 §4.3):

- **N12-SH-01 (holder attribution against a registry)** — gate 3 rejects a
  backup whose holder set carries an UNregistered id with ``unregistered-holder``
  BEFORE any sharding (asserts NO recovery-tier anchor dispatched + NO receipt
  produced); an all-registered backup SUCCEEDS; the dispatched audit envelope's
  ``holders`` field records the registry ids (NOT shard contents).
- **N12-SH-03 (revocation does not weaken threshold below k)** —
  :func:`~kailash.trust.vault.holder_registry.check_revocation_k_floor` raises a
  typed ``revoked-holder`` error with a ``rotation-required`` disposition when a
  revocation would leave fewer than ``k`` un-revoked holders; allows the
  revocation when ``>= k`` un-revoked holders remain. (Tier-1 — the guard is
  pure.)
"""

from __future__ import annotations

import uuid
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.backup import back_up_vault_key
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.holder_registry import (
    HolderRegistry,
    check_revocation_k_floor,
    default_holder_registry,
    require_registered_holders,
)
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import CommitmentRegistry, default_commitment_registry
from kailash.trust.vault.shamir import ShamirRitual
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

_KNOWN_KEK = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_KEK_GENERATION = 7
_KEY_ID = "kek-handle-abc"
_VAULT_ID = "vault-xyz"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"
_HOLDERS = ["holder:h1", "holder:h2", "holder:h3", "holder:h4", "holder:h5"]


class _DeterministicResolver:
    """Deployment-supplied trusted resolver (NOT a mock); satisfies the Protocol."""

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
def _isolate_default_singletons():
    """Reset the process-default commitment + holder registries between tests."""
    default_commitment_registry()._store.clear()
    default_holder_registry()._registered.clear()
    yield
    default_commitment_registry()._store.clear()
    default_holder_registry()._registered.clear()


def _registered_holder_registry() -> HolderRegistry:
    reg = HolderRegistry()
    reg.register_all(_HOLDERS)
    return reg


# ---------------------------------------------------------------------------
# N12-SH-01 — holder attribution against a deployment registry
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_sh01_unregistered_holder_rejected_before_sharding():
    """A backup with an UNregistered holder id → unregistered-holder BEFORE sharding.

    Asserts NO recovery-tier anchor was dispatched (no shard release) and NO
    receipt was produced — gate 3 fires before the KEK is ever resolved/sharded.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)
    holder_registry = _registered_holder_registry()

    # One id ("holder:rogue") is NOT in the registry — an attacker-controlled
    # holder the caller tried to smuggle in (F-AUTHZ-6).
    holders = ["holder:h1", "holder:h2", "holder:rogue", "holder:h4", "holder:h5"]

    with pytest.raises(VaultBindingError) as exc:
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:backup"),
            holders,
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            holder_registry=holder_registry,
        )

    assert exc.value.code is N12FT01Code.UNREGISTERED_HOLDER
    assert exc.value.details["holder_id"] == "holder:rogue"
    assert exc.value.details["index"] == 2

    # No shards released: NO recovery-tier OUTCOME anchor was dispatched (gate 3
    # fired before sharding + before the OUTCOME dispatch).
    rec_engine = dispatcher._engines.get(AuditTier.RECOVERY.value)
    assert (
        rec_engine is None or len(rec_engine.entries) == 0
    ), "no OUTCOME anchor may be dispatched when gate 3 rejects a holder"
    # No commitment registered (the register step runs only after a successful
    # OUTCOME dispatch).
    assert (
        default_commitment_registry()
        .lookup(
            vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION, kek_commitment_alg=_ALG
        )
        .entry
        is None
    )


@pytest.mark.integration
def test_sh01_all_registered_holders_succeed_and_anchor_records_registry_ids():
    """A backup with ALL-registered holders SUCCEEDS; the audit envelope records
    the registry ids (by stable id, never shard contents — N12-SH-01 / N12-AU-01)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)
    holder_registry = _registered_holder_registry()

    receipt = back_up_vault_key(
        _handle(),
        ShamirRitual(threshold=3, total_shards=5),
        _clearance("vault:backup"),
        _HOLDERS,
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        holder_registry=holder_registry,
    )

    # The receipt records the registry ids (verbatim order).
    assert receipt.holders == tuple(_HOLDERS)

    # Exactly one OUTCOME anchor dispatched; its holders field records the
    # SAME registry ids the gate validated — never shard contents.
    rec_engine = dispatcher._engines[AuditTier.RECOVERY.value]
    assert len(rec_engine.entries) == 1
    payload = rec_engine.entries[0].event_payload
    assert payload["subtype"] == "vault_key_backup"
    assert payload["holders"] == _HOLDERS
    # The envelope records ids (strings), NOT shard mnemonics / bytes.
    assert all(isinstance(h, str) for h in payload["holders"])
    # No shard contents on the envelope — shard_count is a count, shard_commitments
    # are one-way ciphertext hashes (N12-AU-01 contents-exclusion).
    assert payload["shard_count"] == 5
    assert "shards" not in payload and "mnemonics" not in payload


@pytest.mark.integration
def test_sh01_default_singleton_is_empty_and_fail_closed():
    """The process-default holder registry starts EMPTY + FAIL-CLOSED.

    Without injecting a holder_registry (so the default singleton is used) and
    with NO holder registered, a backup is rejected unregistered-holder — a
    deployment MUST register its holders first."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    resolver = _DeterministicResolver(key_class=KeyClass.KEK)

    # default_holder_registry() is empty (the autouse fixture cleared it).
    with pytest.raises(VaultBindingError) as exc:
        back_up_vault_key(
            _handle(),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:backup"),
            _HOLDERS,
            resolver=resolver,
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            # holder_registry omitted → uses the empty default singleton.
        )
    assert exc.value.code is N12FT01Code.UNREGISTERED_HOLDER

    # After registering into the singleton, the same backup succeeds.
    default_holder_registry().register_all(_HOLDERS)
    receipt = back_up_vault_key(
        _handle(),
        ShamirRitual(threshold=3, total_shards=5),
        _clearance("vault:backup"),
        _HOLDERS,
        resolver=resolver,
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
    )
    assert receipt.holders == tuple(_HOLDERS)


@pytest.mark.integration
def test_sh01_empty_holder_array_still_rejected():
    """The basic presence check is preserved — an empty holder array fails."""
    with pytest.raises(VaultBindingError) as exc:
        require_registered_holders([], _registered_holder_registry())
    assert exc.value.code is N12FT01Code.UNREGISTERED_HOLDER


@pytest.mark.integration
def test_sh01_non_string_holder_entry_rejected():
    """A non-string / empty-string holder entry fails the presence check."""
    with pytest.raises(VaultBindingError) as exc:
        require_registered_holders(
            ["holder:h1", "", "holder:h3"], _registered_holder_registry()
        )
    assert exc.value.code is N12FT01Code.UNREGISTERED_HOLDER
    assert exc.value.details["index"] == 1


# ---------------------------------------------------------------------------
# N12-SH-03 — revocation MUST NOT weaken the threshold below k
# ---------------------------------------------------------------------------


def test_sh03_revocation_below_k_floor_requires_rotation():
    """Revoking holders such that un-revoked < k → rotation-required typed error."""
    # k=3, 5 holders. Revoking 3 of them leaves 2 un-revoked < k=3.
    with pytest.raises(VaultBindingError) as exc:
        check_revocation_k_floor(
            ritual_k=3,
            holders=_HOLDERS,
            revoked=["holder:h1", "holder:h2", "holder:h3"],
        )
    assert exc.value.code is N12FT01Code.REVOKED_HOLDER
    assert exc.value.details["disposition"] == "rotation-required"
    assert exc.value.details["remaining_holders"] == 2
    assert exc.value.details["ritual_k"] == 3


def test_sh03_revocation_at_exactly_k_allowed():
    """Revoking holders such that un-revoked == k is allowed (no silent drop below)."""
    # k=3, 5 holders. Revoking 2 leaves exactly 3 un-revoked == k → allowed.
    check_revocation_k_floor(
        ritual_k=3,
        holders=_HOLDERS,
        revoked=["holder:h1", "holder:h2"],
    )  # no raise


def test_sh03_revocation_above_k_allowed():
    """Revoking holders such that un-revoked > k is allowed."""
    # k=2, 5 holders. Revoking 1 leaves 4 un-revoked > k=2 → allowed.
    check_revocation_k_floor(
        ritual_k=2,
        holders=_HOLDERS,
        revoked=["holder:h1"],
    )  # no raise


def test_sh03_revoking_id_not_in_set_has_no_threshold_effect():
    """Revoking an id NOT in the current holder set does not reduce the un-revoked count."""
    # k=5, 5 holders. Revoking an id outside the set leaves all 5 → allowed.
    check_revocation_k_floor(
        ritual_k=5,
        holders=_HOLDERS,
        revoked=["holder:not-a-current-holder"],
    )  # no raise

    # But revoking a REAL current holder when k == n drops to 4 < 5 → refused.
    with pytest.raises(VaultBindingError) as exc:
        check_revocation_k_floor(
            ritual_k=5,
            holders=_HOLDERS,
            revoked=["holder:h1"],
        )
    assert exc.value.code is N12FT01Code.REVOKED_HOLDER
    assert exc.value.details["disposition"] == "rotation-required"


def test_sh03_duplicate_revocation_ids_deduplicated():
    """Duplicate revoked ids do not double-count against the threshold."""
    # k=3, 5 holders. Revoking h1 twice + h2 → 2 distinct revoked, 3 remain == k.
    check_revocation_k_floor(
        ritual_k=3,
        holders=_HOLDERS,
        revoked=["holder:h1", "holder:h1", "holder:h2"],
    )  # no raise
