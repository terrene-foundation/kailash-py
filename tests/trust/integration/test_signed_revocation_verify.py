# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2/3 integration tests for the AUTHORITATIVE signed-ledger revocation
verify + durable anti-rollback re-seed (#1842 shard 3).

Real crypto (Ed25519 via the shared signing primitives) + real persistence
(temp-dir JSON stores). NO mocking. Exercises:

* Store-tamper / revocation-resurrection is DETECTED — a persisted event set
  altered at rest changes the recomputed ledger tip → the owner-head signature
  no longer binds it → fail-closed DENY.
* A replayed lower-epoch head is REJECTED via the DURABLE anchor re-seed
  (contrast: a bare ``HeadCommitmentAnchor()`` with no re-seed would wrongly
  accept it — asserted).
* Fail-closed on an unverifiable ledger/head — never falling open to the
  unsigned ``revoked`` flag.
* The ``TrustOperations.verify`` path consults the signed ledger as the
  authoritative revocation source and DENIES a revoked delegation.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import AuthorityType, CapabilityType, VerificationLevel
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kailash.trust.revocation.head_commitment import (
    HeadCommitment,
    HeadCommitmentAnchor,
)
from kailash.trust.revocation.signed_ledger import (
    RevocationLedger,
    SignedRevocationEvent,
    revocation_ledger_tip,
)
from kailash.trust.revocation.verify import (
    HEAD_FILENAME,
    DurableHighWaterStore,
    RevocationVerificationError,
    SignedRevocationStore,
    SignedRevocationVerifier,
)
from kailash.trust.signing.crypto import generate_keypair

# ---------------------------------------------------------------------------
# Real Ed25519 keypair (raw seed + pubkey bytes for head signing)
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_keys() -> Tuple[bytes, bytes]:
    """A fresh Ed25519 keypair as raw (32-byte seed, 32-byte public key)."""
    priv_b64, pub_b64 = generate_keypair()
    return base64.b64decode(priv_b64), base64.b64decode(pub_b64)


def _rfc3339_ns() -> str:
    """An RFC-3339 timestamp with exactly 9 fractional (nanosecond) digits + Z."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond * 1000:09d}Z"


def _build_signed_head(
    seed: bytes,
    events: List[SignedRevocationEvent],
    *,
    epoch: int,
    block_count: int = 0,
    tip_hash: bytes | None = None,
) -> Tuple[HeadCommitment, str]:
    """Fold ``events`` into a ledger tip, wrap it in an owner-signed head.

    Returns ``(head, owner_signature_hex)``. ``tip_hash`` defaults to a
    deterministic 32-byte block-chain tip derived from ``epoch``.
    """
    ledger_tip = revocation_ledger_tip(events)
    if tip_hash is None:
        tip_hash = bytes([epoch & 0xFF]) * 32
    head = HeadCommitment(
        epoch=epoch,
        block_count=block_count,
        tip_hash=tip_hash,
        revocation_ledger_tip=ledger_tip,
        signed_at=_rfc3339_ns(),
    )
    return head, head.sign(seed)


def _make_verifier(
    store_dir: Path, pubkey: bytes
) -> Tuple[SignedRevocationVerifier, SignedRevocationStore, DurableHighWaterStore]:
    signed_store = SignedRevocationStore(store_dir)
    highwater_store = DurableHighWaterStore(store_dir, pubkey)
    verifier = SignedRevocationVerifier(pubkey, signed_store, highwater_store)
    return verifier, signed_store, highwater_store


# ---------------------------------------------------------------------------
# Core verifier — authoritative decision + store-tamper detection
# ---------------------------------------------------------------------------


def test_absent_store_is_genesis_not_revoked(tmp_path, owner_keys):
    """An ABSENT store is the legitimate empty-ledger case: nothing revoked."""
    _, pubkey = owner_keys
    verifier, _, _ = _make_verifier(tmp_path, pubkey)
    assert verifier.verified_revoked_set() == set()
    assert verifier.is_revoked("del-anything") is False


def test_signed_ledger_is_authoritative_revocation_source(tmp_path, owner_keys):
    """A delegation present in the owner-signed ledger reads as revoked."""
    seed, pubkey = owner_keys
    events = [
        SignedRevocationEvent("del-001", epoch=1, revoked_at=_rfc3339_ns()),
        SignedRevocationEvent("del-002", epoch=2, revoked_at=_rfc3339_ns()),
    ]
    head, sig = _build_signed_head(seed, events, epoch=2)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)

    assert verifier.is_revoked("del-001") is True
    assert verifier.is_revoked("del-002") is True
    assert verifier.is_revoked("del-003") is False


def test_resurrection_via_flipped_unsigned_flag_has_no_effect(tmp_path, owner_keys):
    """The verifier ignores any mutable unsigned ``revoked`` field: the signed
    ledger still shows the delegation revoked → verify DENIES.

    Simulates a store-writer adding an unsigned ``revoked: false`` alongside the
    signed record (a resurrection attempt). The signed event set is authoritative
    and its owner signature is untouched, so the delegation stays revoked.
    """
    seed, pubkey = owner_keys
    events = [SignedRevocationEvent("del-001", epoch=1, revoked_at=_rfc3339_ns())]
    head, sig = _build_signed_head(seed, events, epoch=1)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)

    # Attacker injects an unsigned resurrection flag into the persisted file.
    path = tmp_path / HEAD_FILENAME
    data = json.loads(path.read_text())
    data["revoked"] = False  # unsigned, not part of the signing pre-image
    data["events"][0]["revoked"] = False
    path.write_text(json.dumps(data))

    # The signed ledger remains authoritative — del-001 is STILL revoked.
    assert verifier.is_revoked("del-001") is True


def test_deleted_signed_event_is_detected_via_tip_mismatch(tmp_path, owner_keys):
    """A store-writer who DELETES a signed revocation event changes the
    recomputed tip → the owner-head signature no longer binds it → fail-closed.
    """
    seed, pubkey = owner_keys
    events = [
        SignedRevocationEvent("del-001", epoch=1, revoked_at=_rfc3339_ns()),
        SignedRevocationEvent("del-002", epoch=2, revoked_at=_rfc3339_ns()),
    ]
    head, sig = _build_signed_head(seed, events, epoch=2)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)

    # Attacker deletes del-001's event to "resurrect" it, leaving the (now stale)
    # owner-signed head in place.
    path = tmp_path / HEAD_FILENAME
    data = json.loads(path.read_text())
    data["events"] = [e for e in data["events"] if e["delegation_id"] != "del-001"]
    path.write_text(json.dumps(data))

    with pytest.raises(RevocationVerificationError) as exc:
        verifier.verified_revoked_set()
    assert "tamper" in str(exc.value).lower() or "tip" in str(exc.value).lower()


def test_bad_owner_signature_fails_closed(tmp_path, owner_keys):
    """An unverifiable owner signature DENIES (never falls open)."""
    seed, pubkey = owner_keys
    events = [SignedRevocationEvent("del-001", epoch=1, revoked_at=_rfc3339_ns())]
    head, _sig = _build_signed_head(seed, events, epoch=1)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    # Persist a bogus signature.
    signed_store.persist_head(events, head, "00" * 64)

    with pytest.raises(RevocationVerificationError) as exc:
        verifier.verified_revoked_set()
    assert "signature" in str(exc.value).lower()


def test_malformed_store_fails_closed(tmp_path, owner_keys):
    """A PRESENT but corrupt store is a tamper signal → fail-closed, not empty."""
    _, pubkey = owner_keys
    (tmp_path / HEAD_FILENAME).write_text("{ not valid json ")
    verifier, _, _ = _make_verifier(tmp_path, pubkey)
    with pytest.raises(RevocationVerificationError):
        verifier.verified_revoked_set()


# ---------------------------------------------------------------------------
# Durable anti-rollback re-seed
# ---------------------------------------------------------------------------


def test_durable_anchor_persists_and_reseeds_high_water(tmp_path, owner_keys):
    """After accepting an epoch-N head, the durable high-water survives a
    'process restart' (fresh store instances re-seed from disk)."""
    seed, pubkey = owner_keys
    events = [
        SignedRevocationEvent("del-001", epoch=5, revoked_at=_rfc3339_ns()),
    ]
    head, sig = _build_signed_head(seed, events, epoch=5, tip_hash=bytes([0xAA]) * 32)
    verifier, signed_store, hw_store = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)

    # First verify accepts the head and persists the high-water durably.
    assert verifier.is_revoked("del-001") is True
    reseeded = hw_store.load_anchor()
    assert reseeded.high_water_epoch == 5
    assert reseeded.high_water_tip_hash == bytes([0xAA]) * 32


def test_replayed_lower_epoch_head_is_rejected_via_durable_anchor(tmp_path, owner_keys):
    """Persist high-water at epoch N; simulate a restart by reconstructing the
    verifier FROM the durable store; feed an epoch < N head → REJECTED.

    Contrast: a bare ``HeadCommitmentAnchor()`` (no re-seed) would WRONGLY accept
    the lower epoch — asserted, proving the durable path is what closes it.
    """
    seed, pubkey = owner_keys

    # Phase 1: accept a high head at epoch 100, persisting the durable high-water.
    events_hi = [SignedRevocationEvent("del-hi", epoch=100, revoked_at=_rfc3339_ns())]
    head_hi, sig_hi = _build_signed_head(seed, events_hi, epoch=100)
    verifier1, signed_store1, _ = _make_verifier(tmp_path, pubkey)
    signed_store1.persist_head(events_hi, head_hi, sig_hi)
    assert verifier1.is_revoked("del-hi") is True  # advances + persists high-water

    # Phase 2: "process restart" — a store-writer replaces the persisted head with
    # a validly-owner-signed but STALE lower-epoch head (epoch 5).
    events_lo = [SignedRevocationEvent("del-lo", epoch=5, revoked_at=_rfc3339_ns())]
    head_lo, sig_lo = _build_signed_head(seed, events_lo, epoch=5)
    signed_store2 = SignedRevocationStore(tmp_path)
    signed_store2.persist_head(events_lo, head_lo, sig_lo)

    # Fresh verifier instances (the restart) RE-SEED the anchor from the durable
    # high-water (epoch 100) and REJECT the epoch-5 replay.
    verifier2, _, _ = _make_verifier(tmp_path, pubkey)
    with pytest.raises(RevocationVerificationError) as exc:
        verifier2.verified_revoked_set()
    assert "rollback" in str(exc.value).lower()

    # Contrast: a BARE anchor (the restart-WITHOUT-re-seed bug) would accept it.
    bare = HeadCommitmentAnchor()
    bare.accept(head_lo)  # no raise — this is exactly the vulnerability we close
    assert bare.high_water_epoch == 5


def test_malformed_high_water_store_fails_closed(tmp_path, owner_keys):
    """A present-but-corrupt durable high-water file DENIES (never silently
    resets the anti-rollback high-water to 0)."""
    from kailash.trust.revocation.verify import HIGHWATER_FILENAME

    _, pubkey = owner_keys
    (tmp_path / HIGHWATER_FILENAME).write_text('{"epoch": "not-an-int"}')
    hw_store = DurableHighWaterStore(tmp_path, pubkey)
    with pytest.raises(RevocationVerificationError):
        hw_store.load_anchor()


# ---------------------------------------------------------------------------
# Security-redteam regression cases (FIX 1 CRITICAL, FIX 2 HIGH, FIX 3 HIGH)
# ---------------------------------------------------------------------------


def test_R1_head_delete_with_high_water_is_detected(tmp_path, owner_keys):
    """FIX 1 (CRITICAL): deleting ONLY the signed-head store, leaving the durable
    high-water at epoch ≥ 1, is a resurrection attempt — verify RAISES, does NOT
    return an empty (nothing-revoked) set.
    """
    seed, pubkey = owner_keys
    events = [SignedRevocationEvent("del-01", epoch=5, revoked_at=_rfc3339_ns())]
    head, sig = _build_signed_head(seed, events, epoch=5)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)
    assert verifier.is_revoked("del-01") is True  # advances + persists high-water

    # Store-writer deletes ONLY revocation_head.json (high-water file remains).
    (tmp_path / HEAD_FILENAME).unlink()

    # A fresh verifier (restart) MUST NOT read "nothing revoked" — the retained
    # high-water at epoch 5 proves a head existed → fail-closed.
    verifier2, _, _ = _make_verifier(tmp_path, pubkey)
    with pytest.raises(RevocationVerificationError) as exc:
        verifier2.verified_revoked_set()
    assert (
        "resurrection" in str(exc.value).lower() or "deleted" in str(exc.value).lower()
    )


def test_R2_lower_epoch_persist_does_not_regress_high_water(tmp_path, owner_keys):
    """FIX 2 (HIGH): a lower-epoch accept after a higher one is rejected and does
    NOT lower the durable high-water.
    """
    seed, pubkey = owner_keys
    _, _, hw_store = _make_verifier(tmp_path, pubkey)

    head_hi, sig_hi = _build_signed_head(
        seed, [SignedRevocationEvent("d", epoch=10, revoked_at=_rfc3339_ns())], epoch=10
    )
    hw_store.accept_and_persist(head_hi, sig_hi)
    assert hw_store.load_anchor().high_water_epoch == 10

    head_lo, sig_lo = _build_signed_head(
        seed, [SignedRevocationEvent("d", epoch=7, revoked_at=_rfc3339_ns())], epoch=7
    )
    with pytest.raises(RevocationVerificationError):
        hw_store.accept_and_persist(head_lo, sig_lo)
    # High-water is UNCHANGED at 10 — no regression.
    assert hw_store.load_anchor().high_water_epoch == 10


def test_R2_concurrent_accepts_never_regress_high_water(tmp_path, owner_keys):
    """FIX 2 (HIGH): under concurrency, the compare-and-swap under a single file
    lock guarantees the durable high-water is monotonic — a racing lower-epoch
    accept can never lower it below a higher accepted epoch.
    """
    import threading

    seed, pubkey = owner_keys
    _, _, hw_store = _make_verifier(tmp_path, pubkey)
    head_hi, sig_hi = _build_signed_head(
        seed, [SignedRevocationEvent("d", epoch=10, revoked_at=_rfc3339_ns())], epoch=10
    )
    head_lo, sig_lo = _build_signed_head(
        seed, [SignedRevocationEvent("d", epoch=7, revoked_at=_rfc3339_ns())], epoch=7
    )
    barrier = threading.Barrier(2)

    def worker(commitment, signature):
        barrier.wait()
        try:
            hw_store.accept_and_persist(commitment, signature)
        except RevocationVerificationError:
            pass  # a lost race for the lower epoch legitimately raises

    threads = [
        threading.Thread(target=worker, args=(head_hi, sig_hi)),
        threading.Thread(target=worker, args=(head_lo, sig_lo)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Whatever the interleaving, the durable high-water settles at the MAX
    # accepted epoch (10) and never regresses to 7.
    assert hw_store.load_anchor().high_water_epoch == 10


def test_R3_forged_unsigned_high_water_fails_closed(tmp_path, owner_keys):
    """FIX 3 (HIGH): the durable high-water is owner-signed; a store-writer who
    forges a low-epoch high-water with a BOGUS signature cannot pass the
    signature check — load fails closed. (The documented RESIDUAL is replay of a
    previously-valid owner-signed head, which this signature binding does not
    claim to prevent.)
    """
    seed, pubkey = owner_keys
    _, _, hw_store = _make_verifier(tmp_path, pubkey)
    head_hi, sig_hi = _build_signed_head(
        seed, [SignedRevocationEvent("d", epoch=10, revoked_at=_rfc3339_ns())], epoch=10
    )
    hw_store.accept_and_persist(head_hi, sig_hi)

    # Attacker rewrites the high-water to a forged low-epoch head with a bad sig.
    forged_head, _ = _build_signed_head(
        seed, [SignedRevocationEvent("d", epoch=1, revoked_at=_rfc3339_ns())], epoch=1
    )
    path = tmp_path / "revocation_highwater.json"
    path.write_text(
        json.dumps({"head": forged_head.to_dict(), "head_signature": "00" * 64})
    )
    with pytest.raises(RevocationVerificationError) as exc:
        hw_store.load_anchor()
    assert "signature" in str(exc.value).lower() or "tamper" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# TrustOperations.verify consults the signed ledger authoritatively
# ---------------------------------------------------------------------------


class SimpleAuthorityRegistry:
    """Real in-memory authority registry (NOT a mock)."""

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            from kailash.trust.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority


@pytest.fixture
async def ops_factory(owner_keys):
    """Factory building an initialized TrustOperations with an optional signed
    revocation verifier, plus the established agent."""

    async def _build(verifier=None):
        chain_priv_b64, chain_pub_b64 = generate_keypair()
        authority = OrganizationalAuthority(
            id="org-acme",
            name="ACME",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=chain_pub_b64,
            signing_key_id="acme-key-001",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.GRANT_CAPABILITIES,
            ],
        )
        registry = SimpleAuthorityRegistry()
        registry.register(authority)
        km = TrustKeyManager()
        km.register_key("acme-key-001", chain_priv_b64)
        store = InMemoryTrustStore()
        await store.initialize()
        ops = TrustOperations(
            authority_registry=registry,
            key_manager=km,
            trust_store=store,
            revocation_verifier=verifier,
        )
        await ops.initialize()
        await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                )
            ],
        )
        return ops

    return _build


async def test_operations_verify_denies_revoked_agent_via_signed_ledger(
    tmp_path, owner_keys, ops_factory
):
    """TrustOperations.verify consults the signed ledger and DENIES when the
    agent is revoked there (authoritative), at STANDARD level."""
    seed, pubkey = owner_keys
    events = [SignedRevocationEvent("agent-001", epoch=1, revoked_at=_rfc3339_ns())]
    head, sig = _build_signed_head(seed, events, epoch=1)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)

    ops = await ops_factory(verifier=verifier)
    result = await ops.verify(
        agent_id="agent-001", action="analyze_data", level=VerificationLevel.STANDARD
    )
    assert result.valid is False
    assert "revoked" in result.reason.lower()


async def test_operations_verify_allows_when_not_in_signed_ledger(
    tmp_path, owner_keys, ops_factory
):
    """A signed ledger that does NOT list the agent lets verify proceed."""
    seed, pubkey = owner_keys
    events = [SignedRevocationEvent("other-agent", epoch=1, revoked_at=_rfc3339_ns())]
    head, sig = _build_signed_head(seed, events, epoch=1)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)

    ops = await ops_factory(verifier=verifier)
    result = await ops.verify(
        agent_id="agent-001", action="analyze_data", level=VerificationLevel.STANDARD
    )
    assert result.valid is True


async def test_operations_verify_fails_closed_on_unverifiable_ledger(
    tmp_path, owner_keys, ops_factory
):
    """An unverifiable signed ledger (bad owner signature) DENIES the whole
    verify — never falling open to the unsigned flag."""
    seed, pubkey = owner_keys
    events = [SignedRevocationEvent("agent-001", epoch=1, revoked_at=_rfc3339_ns())]
    head, _sig = _build_signed_head(seed, events, epoch=1)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, "11" * 64)  # bad signature

    ops = await ops_factory(verifier=verifier)
    result = await ops.verify(
        agent_id="agent-001", action="analyze_data", level=VerificationLevel.STANDARD
    )
    assert result.valid is False
    assert (
        "unverifiable" in result.reason.lower()
        or "fail-closed" in result.reason.lower()
    )


async def test_operations_verify_warns_once_when_verifier_absent(ops_factory, caplog):
    """FIX 4 (Check-2): with NO signed-ledger verifier wired, verify() emits ONE
    WARN that the authoritative resurrection/rollback layer is OFF (observability),
    and does NOT hard-fail (backward-compatible default).
    """
    import logging

    ops = await ops_factory(verifier=None)
    with caplog.at_level(logging.WARNING):
        r1 = await ops.verify(agent_id="agent-001", action="analyze_data")
        r2 = await ops.verify(agent_id="agent-001", action="analyze_data")
    assert r1.valid is True and r2.valid is True  # not hard-failed
    warns = [
        rec
        for rec in caplog.records
        if rec.levelno == logging.WARNING and "signed-revocation" in rec.getMessage()
    ]
    assert len(warns) == 1  # emitted exactly ONCE, not per-verify


def test_ledger_append_only_ordering_matches_persisted_events(tmp_path, owner_keys):
    """Sanity: the RevocationLedger append-only fold equals the persisted event
    fold, so a verifier recomputing the tip agrees with the ledger."""
    seed, pubkey = owner_keys
    ledger = RevocationLedger()
    events = []
    for i in range(1, 4):
        ev = SignedRevocationEvent(f"del-{i:03d}", epoch=i, revoked_at=_rfc3339_ns())
        ledger.append(ev)
        events.append(ev)
    assert ledger.tip() == revocation_ledger_tip(events)

    head, sig = _build_signed_head(seed, events, epoch=3)
    verifier, signed_store, _ = _make_verifier(tmp_path, pubkey)
    signed_store.persist_head(events, head, sig)
    assert verifier.verified_revoked_set() == {"del-001", "del-002", "del-003"}
