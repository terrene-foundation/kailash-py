# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the EATP-12 rotation trigger (W5-R1, §5).

Exercises the R1 rotation surfaces END-TO-END through the REAL binding code
path — real SLIP-0039 ``shamir.generate`` / ``rotate_holders`` (the ``shamir``
extra), real per-tier :class:`~kailash.delegate.audit.AuditChainEngine`, real
Ed25519 signer + :class:`~kailash.delegate.verifier.Ed25519Verifier`, real D1
dispatcher, real C2a :class:`CommitmentRegistry`, real B2 holder registry +
k-floor guard, real C3 ``current_generation_from_chain``. NO mocks
(``rules/testing.md`` Tier-2: real infrastructure).

Conformance coverage (EATP-12 §5 / §4.3, N12-RT-01/02/03/04/06, N12-SH-04,
N12-TH-01, N12-CL-01):

- **V4(a) amicable holder rotation** (N12-RT-01/02): ``rotate_vault_holders``
  composes the shipped ``shamir.rotate_holders`` (no reimpl) and writes a
  ``vault_holder_rotation`` anchor with ``for_cause=False`` and the generation
  UNCHANGED (N12-RT-03);
- **V4(c) for-cause generation-advance** (N12-SH-04 / N12-RT-06):
  ``revoke_holder_for_cause`` advances the generation ``g -> g+1``, writes a
  ``vault_kek_rotation`` anchor with ``for_cause=True`` + the new distribution,
  and REGISTERS the new-generation commitment;
- **C3 stale-guard LIVE** (N12-RT-06): after the for-cause rotation,
  ``current_generation_from_chain`` returns ``g+1`` (R1 writes the anchor C3
  reads) — the old-generation shards are now stale;
- **k-floor refusal** (N12-SH-03, B2): a for-cause revocation that would drop
  the un-revoked holder set below ``k`` is REFUSED ``revoked-holder``
  (rotation-required) — composes ``check_revocation_k_floor``, no reimpl;
- **N12-CL-01 clearance**: a caller lacking ``vault:rotate`` is rejected
  ``missing-clearance`` on BOTH surfaces;
- **N12-TH-01 floor**: a new ritual outside ``2<=k<=n<=9`` is ``invalid-ritual``;
- **N12-RT-04 Mode-A only**: the rotation surface takes a single ``ShamirRitual``
  (single-group) — there is no Mode-B (multi-group) parameter;
- no plaintext KEK in the receipt or any dispatched anchor.
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
from kailash.trust.vault.dispatch import AuditDispatcher
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.holder_registry import default_holder_registry
from kailash.trust.vault.input_gates import ResolvedKek
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.rotation import revoke_holder_for_cause, rotate_vault_holders
from kailash.trust.vault.shamir import ShamirRitual, generate
from kailash.trust.vault.stale_guard import current_generation_from_chain
from kailash.trust.vault.types import ClearanceContext, RotationReceipt, VaultKeyHandle

_KEK = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
_GEN = 7
_VAULT = "vault-r1"
_PROVENANCE = "vault-derived:v1"
_ALG = "eatp-v1"
_ALL_HOLDERS = ["h1", "h2", "h3", "h4", "h5", "n1", "n2", "n3", "n4", "n5"]


class _Resolver:
    """Deployment-supplied trusted resolver (NOT a mock)."""

    def __init__(
        self,
        *,
        secret: bytes = _KEK,
        key_class: KeyClass = KeyClass.KEK,
        key_id: str = "kek-handle-r1",
        gen: int = _GEN,
    ) -> None:
        self._secret = secret
        self._key_class = key_class
        self._key_id = key_id
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
        sovereign_ref="sov-r1",
        role_binding_ref="rb-r1",
        genesis_ref="gen-r1",
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
def _register_holders():
    """Register the test holders so gate-3 (N12-SH-01) is satisfied. The rotation
    surfaces use the process-default holder registry when none is injected."""
    default_holder_registry()._registered.clear()
    default_holder_registry().register_all(_ALL_HOLDERS)
    yield
    default_holder_registry()._registered.clear()


def _handle() -> VaultKeyHandle:
    return VaultKeyHandle(key_id="kek-handle-r1", vault_id=_VAULT, kek_generation=_GEN)


def _clearance(*caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal="agent-1", tenant="t1", domain="d1", capabilities=tuple(caps)
    )


def _old_shards(k: int = 3, n: int = 5):
    """Exactly ``k`` real SLIP-0039 shards of _KEK under the (k, n) ritual.

    ``shamir.reconstruct`` (and therefore ``rotate_holders``) requires EXACTLY
    ``threshold`` mnemonics — the non-revoked holders supply exactly ``k`` of the
    ``n`` shards. Returns the first ``k`` shards of a fresh (k, n) split."""
    return generate(_KEK, ShamirRitual(threshold=k, total_shards=n))[:k]


def _recovery_entries(dispatcher: AuditDispatcher):
    engine = dispatcher._engines.get("recovery")
    return list(engine.entries) if engine is not None else []


# ---------------------------------------------------------------------------
# V4(a) — amicable holder rotation (N12-RT-01/02/03)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_amicable_holder_rotation_writes_anchor_generation_unchanged():
    """Amicable rotation writes vault_holder_rotation (for_cause=False), gen UNCHANGED."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    receipt = rotate_vault_holders(
        _handle(),
        _old_shards(3, 5),
        ShamirRitual(threshold=3, total_shards=5),
        ShamirRitual(threshold=2, total_shards=4),
        _clearance("vault:rotate"),
        ["h1", "h2", "n1", "n2"],
        departing_holder="h5",
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
    )

    assert isinstance(receipt, RotationReceipt)
    assert receipt.for_cause is False
    assert receipt.kek_generation == _GEN  # N12-RT-03: unchanged
    assert receipt.prior_kek_generation == _GEN
    assert (
        receipt.kek_identity_commitment is None
    )  # commitment unchanged, none registered
    assert receipt.k == 2 and receipt.n == 4
    assert receipt.holders == ("h1", "h2", "n1", "n2")
    assert len(receipt.shard_commitments) == 4  # new (k=2,n=4) distribution

    # The anchor landed on the recovery tier with the right discriminator + flag.
    entries = _recovery_entries(dispatcher)
    rot = [
        e for e in entries if e.event_payload.get("subtype") == "vault_holder_rotation"
    ]
    assert len(rot) == 1
    p = rot[0].event_payload
    assert p["for_cause"] is False
    assert p["kek_generation"] == _GEN
    assert p["departing_holder"] == "h5"
    assert p["k"] == {"old": {"k": 3, "n": 5}, "new": {"k": 2, "n": 4}}
    assert p["holders"] == ["h1", "h2", "n1", "n2"]
    # No plaintext / secret material on the anchor.
    assert "master_secret" not in p and "secret" not in p


# ---------------------------------------------------------------------------
# V4(c) — for-cause generation-advancing rotation (N12-SH-04 / N12-RT-06)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_for_cause_revocation_advances_generation_and_registers_commitment():
    """For-cause revocation advances g->g+1, writes vault_kek_rotation, registers C_{g+1}."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()

    receipt = revoke_holder_for_cause(
        _handle(),
        _old_shards(3, 5),  # non-revoked holders' shards
        ShamirRitual(threshold=3, total_shards=5),  # current ritual
        ShamirRitual(threshold=3, total_shards=5),  # new ritual
        _clearance("vault:rotate"),
        current_holders=["h1", "h2", "h3", "h4", "h5"],
        revoked_holders=["h5"],
        new_holders=["h1", "h2", "h3", "n1", "n2"],
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=registry,
    )

    assert receipt.for_cause is True
    assert receipt.prior_kek_generation == _GEN
    assert receipt.kek_generation == _GEN + 1  # N12-SH-04: generation advanced
    assert receipt.kek_identity_commitment is not None
    assert len(receipt.kek_identity_commitment) == 64  # SHA-256 hex

    # The new-generation commitment is REGISTERED for (vault_id, g+1).
    lookup = registry.lookup(
        vault_id=_VAULT, kek_generation=_GEN + 1, kek_commitment_alg=_ALG
    )
    assert lookup.entry is not None
    assert lookup.entry.commitment == receipt.kek_identity_commitment
    assert lookup.entry.key_id == "kek-handle-r1"

    # The vault_kek_rotation anchor carries for_cause=True + prior/new generation.
    entries = _recovery_entries(dispatcher)
    rot = [e for e in entries if e.event_payload.get("subtype") == "vault_kek_rotation"]
    assert len(rot) == 1
    p = rot[0].event_payload
    assert p["for_cause"] is True
    assert p["prior_kek_generation"] == _GEN
    assert p["kek_generation"] == _GEN + 1
    assert p["holders"] == ["h1", "h2", "h3", "n1", "n2"]
    assert p["kek_identity_commitment"] == receipt.kek_identity_commitment
    assert "master_secret" not in p and "secret" not in p


@pytest.mark.integration
def test_for_cause_rotation_makes_c3_stale_guard_live():
    """N12-RT-06: after for-cause rotation, current_generation_from_chain reads g+1.

    R1 WRITES the vault_kek_rotation anchor that C3 READS — the old-generation
    (g) shards a departed holder retained are now STALE (g < g+1)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    # Before the rotation, no rotation anchor exists → captured gen is current.
    assert (
        current_generation_from_chain(
            dispatcher, vault_id=_VAULT, captured_generation=_GEN
        )
        == _GEN
    )

    revoke_holder_for_cause(
        _handle(),
        _old_shards(3, 5),
        ShamirRitual(threshold=3, total_shards=5),
        ShamirRitual(threshold=3, total_shards=5),
        _clearance("vault:rotate"),
        current_holders=["h1", "h2", "h3", "h4", "h5"],
        revoked_holders=["h5"],
        new_holders=["h1", "h2", "h3", "n1", "n2"],
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG,
        registry=CommitmentRegistry(),
    )

    # After the rotation, the audited chain's current generation is g+1 — a
    # captured-gen-g restore is now stale per the §6 ordinal guard.
    assert (
        current_generation_from_chain(
            dispatcher, vault_id=_VAULT, captured_generation=_GEN
        )
        == _GEN + 1
    )


# ---------------------------------------------------------------------------
# k-floor refusal (N12-SH-03, B2 — composed, not reimplemented)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_for_cause_revocation_below_k_floor_is_refused():
    """N12-SH-03: revoking would drop the un-revoked set below k → revoked-holder."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    with pytest.raises(VaultBindingError) as ei:
        revoke_holder_for_cause(
            _handle(),
            _old_shards(3, 5),
            ShamirRitual(threshold=3, total_shards=5),  # k=3
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:rotate"),
            current_holders=["h1", "h2", "h3", "h4", "h5"],
            revoked_holders=["h3", "h4", "h5"],  # 5 - 3 = 2 remaining < k=3
            new_holders=["h1", "h2", "n1", "n2", "n3"],
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=CommitmentRegistry(),
        )
    assert ei.value.code is N12FT01Code.REVOKED_HOLDER
    assert ei.value.details.get("disposition") == "rotation-required"
    # No rotation anchor was written (refused before any re-shard).
    rot = [
        e
        for e in _recovery_entries(dispatcher)
        if e.event_payload.get("subtype") == "vault_kek_rotation"
    ]
    assert rot == []


# ---------------------------------------------------------------------------
# Clearance + ritual-floor gates (N12-CL-01, N12-TH-01)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_amicable_rotation_without_vault_rotate_is_missing_clearance():
    """N12-CL-01: a caller lacking vault:rotate is rejected missing-clearance."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    with pytest.raises(VaultBindingError) as ei:
        rotate_vault_holders(
            _handle(),
            _old_shards(3, 5),
            ShamirRitual(threshold=3, total_shards=5),
            ShamirRitual(threshold=2, total_shards=4),
            _clearance("vault:backup"),  # NOT vault:rotate
            ["h1", "h2", "n1", "n2"],
            departing_holder="h5",
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_for_cause_rotation_without_vault_rotate_is_missing_clearance():
    """N12-CL-01: for-cause path also requires vault:rotate."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    with pytest.raises(VaultBindingError) as ei:
        revoke_holder_for_cause(
            _handle(),
            _old_shards(3, 5),
            ShamirRitual(threshold=3, total_shards=5),
            ShamirRitual(threshold=3, total_shards=5),
            _clearance("vault:restore"),  # NOT vault:rotate
            current_holders=["h1", "h2", "h3", "h4", "h5"],
            revoked_holders=["h5"],
            new_holders=["h1", "h2", "h3", "n1", "n2"],
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
            registry=CommitmentRegistry(),
        )
    assert ei.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.integration
def test_amicable_rotation_new_ritual_below_floor_is_invalid_ritual():
    """N12-TH-01: a new ritual outside 2<=k<=n<=9 is invalid-ritual."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)

    with pytest.raises(VaultBindingError) as ei:
        rotate_vault_holders(
            _handle(),
            _old_shards(3, 5),
            ShamirRitual(threshold=3, total_shards=5),
            ShamirRitual(threshold=1, total_shards=1),  # 1-of-1 forbidden
            _clearance("vault:rotate"),
            ["h1"],
            departing_holder="h5",
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG,
        )
    assert ei.value.code is N12FT01Code.INVALID_RITUAL


# ---------------------------------------------------------------------------
# N12-RT-04 — Mode-A only (structural: single-group ritual, no Mode-B param)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rotation_is_mode_a_single_group_only():
    """N12-RT-04: both rotation surfaces take a single ShamirRitual (single-group).

    There is NO Mode-B (multi-group) parameter — the shipped wrapper is
    single-group (group_threshold=1). This structural invariant test asserts the
    rotation signatures admit only single-group rituals; if a future refactor
    grows a multi-group parameter, this fails and forces a Mode-B conformance
    re-audit (MED-5)."""
    import inspect

    for fn in (rotate_vault_holders, revoke_holder_for_cause):
        sig = inspect.signature(fn)
        ritual_params = [
            name
            for name, p in sig.parameters.items()
            if p.annotation is ShamirRitual or name.endswith("ritual")
        ]
        # Every ritual parameter is a single ShamirRitual; none is a sequence/group.
        for name in ritual_params:
            ann = sig.parameters[name].annotation
            assert ann in (ShamirRitual, "ShamirRitual"), (
                f"{fn.__name__}.{name} is not a single ShamirRitual "
                f"(Mode-B multi-group is out of scope, N12-RT-04): {ann!r}"
            )
        assert "groups" not in sig.parameters
        assert "group_rituals" not in sig.parameters
