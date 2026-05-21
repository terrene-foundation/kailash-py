# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash.delegate.audit`` (S4, #1035).

Mirrors kailash-rs ``kailash-delegate-audit`` (M4) per Option A (rs-shipped
impl is the de facto spec). Covers AuditChainEngine, AuditChainEntry,
WitnessedCrossAnchor, and the three typed-error classes.

Tier classification: all assertions here are STRUCTURAL (frozen-dataclass
guard, tz-aware enforcement, hex validation, monotonic sequence, raw-byte
SHA-256 equality, isinstance type checks) — no semantic verification of
prose output. Per ``probe-driven-verification.md`` MUST Rule 3, structural
assertions remain regex/check-based; the rule's BLOCKED class is regex over
PROSE output, not exact-string equality on canonical bytes.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import (
    AuditChainEmissionError,
    AuditChainEngine,
    AuditChainEntry,
    AuditChainSignatureError,
    CrossAnchorIntegrityError,
    DelegateEventType,
    WitnessedCrossAnchor,
)
from kailash.delegate.types import DelegateIdentity
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain

# ---------------------------------------------------------------------------
# Helpers (factories — keep tests focused on the behavior under test)
# ---------------------------------------------------------------------------


def _build_chain(agent_id: str = "agent-tier1") -> TrustLineageChain:
    """Substrate chain factory — frozen-time, no I/O."""
    return TrustLineageChain(
        genesis=GenesisRecord(
            id=f"g-{agent_id}",
            agent_id=agent_id,
            authority_id=f"auth-{agent_id}",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
            signature="a" * 128,
        )
    )


def _build_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-tier1",
        role_binding_ref="rb-tier1",
        genesis_ref="g-agent-tier1",
    )


# ---------------------------------------------------------------------------
# AuditChainEntry — Tier 1 invariants (frozen, tz-aware, hex-validated)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audit_chain_entry_is_frozen_dataclass() -> None:
    """The entry MUST refuse post-construction mutation (frozen=True)."""
    entry = AuditChainEntry(
        sequence=0,
        previous_hash="",
        event_type=DelegateEventType.LIFECYCLE_TRANSITION,
        event_payload={"from": "proposed", "to": "instantiated"},
        signer_delegate_id=uuid.uuid4(),
        signed_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="b" * 128,
    )
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        entry.sequence = 99  # type: ignore[misc]


@pytest.mark.unit
def test_audit_chain_entry_genesis_requires_empty_previous_hash() -> None:
    """Sequence 0 (genesis) MUST carry empty previous_hash."""
    with pytest.raises(AuditChainEmissionError, match="empty string at sequence=0"):
        AuditChainEntry(
            sequence=0,
            previous_hash="a" * 64,  # non-empty at genesis
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            event_payload={},
            signer_delegate_id=uuid.uuid4(),
            signed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
            signature="c" * 128,
        )


@pytest.mark.unit
def test_audit_chain_entry_non_genesis_requires_previous_hash() -> None:
    """Sequence > 0 MUST carry a 64-char hex previous_hash."""
    with pytest.raises(AuditChainEmissionError, match="non-empty at sequence=1"):
        AuditChainEntry(
            sequence=1,
            previous_hash="",
            event_type=DelegateEventType.POSTURE_RATCHET,
            event_payload={},
            signer_delegate_id=uuid.uuid4(),
            signed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
            signature="d" * 128,
        )


@pytest.mark.unit
def test_audit_chain_entry_rejects_naive_datetime() -> None:
    """tz-aware datetime enforced — cross-SDK wire-format parity."""
    with pytest.raises(AuditChainEmissionError, match="timezone-aware"):
        AuditChainEntry(
            sequence=0,
            previous_hash="",
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            event_payload={},
            signer_delegate_id=uuid.uuid4(),
            signed_at=datetime(2026, 5, 21, 12, 0, 0),  # naive
            signature="e" * 128,
        )


@pytest.mark.unit
def test_audit_chain_entry_rejects_unknown_event_type() -> None:
    """Event type must be one of the DelegateEventType sentinels."""
    with pytest.raises(AuditChainEmissionError, match="not a known DelegateEventType"):
        AuditChainEntry(
            sequence=0,
            previous_hash="",
            event_type="kaizen.agent.thinking",  # not a delegate event
            event_payload={},
            signer_delegate_id=uuid.uuid4(),
            signed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
            signature="f" * 128,
        )


@pytest.mark.unit
def test_audit_chain_entry_rejects_non_uuid_signer() -> None:
    """signer_delegate_id MUST be uuid.UUID (post-Option-A restructure)."""
    with pytest.raises(AuditChainEmissionError, match="MUST be a uuid.UUID"):
        AuditChainEntry(
            sequence=0,
            previous_hash="",
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            event_payload={},
            signer_delegate_id="delegate-string-id",  # type: ignore[arg-type]
            signed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
            signature="a" * 128,
        )


@pytest.mark.unit
def test_audit_chain_entry_rejects_bad_hex_signature() -> None:
    """Signature MUST be exactly 128 lowercase-hex chars (Ed25519)."""
    with pytest.raises(ValueError, match="128 hex chars"):
        AuditChainEntry(
            sequence=0,
            previous_hash="",
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            event_payload={},
            signer_delegate_id=uuid.uuid4(),
            signed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
            signature="abcd",  # wrong length
        )


@pytest.mark.unit
def test_audit_chain_entry_canonical_dict_byte_stable() -> None:
    """Two constructions with identical inputs emit byte-identical JSON.

    Cross-SDK fixture parity (per ``cross-sdk-inspection.md`` Rule 4)
    depends on byte-canonical output through ``canonical_json_dumps``.
    """
    sid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    when = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)

    def build() -> AuditChainEntry:
        return AuditChainEntry(
            sequence=0,
            previous_hash="",
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            event_payload={"from": "proposed", "to": "instantiated"},
            signer_delegate_id=sid,
            signed_at=when,
            signature="9" * 128,
        )

    j1 = canonical_json_dumps(build().to_canonical_dict())
    j2 = canonical_json_dumps(build().to_canonical_dict())
    assert j1 == j2
    # Signature appears in canonical (transport) form.
    assert '"signature":' in j1
    # Signing dict EXCLUDES signature (F7 split).
    j_sign = canonical_json_dumps(build().to_signing_dict())
    assert '"signature":' not in j_sign


# ---------------------------------------------------------------------------
# AuditChainEngine — monotonic sequence + previous-hash linkage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_engine_requires_real_trust_lineage_chain() -> None:
    """facade-manager-detection.md MUST Rule 3 — explicit framework dep."""
    with pytest.raises(AuditChainEmissionError, match="TrustLineageChain instance"):
        AuditChainEngine(chain="not-a-chain")  # type: ignore[arg-type]


@pytest.mark.unit
def test_engine_emit_event_genesis_starts_at_zero() -> None:
    """First emitted event MUST be sequence=0, previous_hash=''."""
    engine = AuditChainEngine(chain=_build_chain())
    entry = engine.emit_event(
        event_type=DelegateEventType.LIFECYCLE_TRANSITION,
        payload={"from": "proposed", "to": "instantiated"},
        signer_identity=_build_identity(),
        signature="a" * 128,
    )
    assert entry.sequence == 0
    assert entry.previous_hash == ""


@pytest.mark.unit
def test_engine_emit_event_monotonic_sequence() -> None:
    """Subsequent events MUST increment sequence by exactly 1."""
    engine = AuditChainEngine(chain=_build_chain())
    signer = _build_identity()
    e1 = engine.emit_event(
        event_type=DelegateEventType.LIFECYCLE_TRANSITION,
        payload={},
        signer_identity=signer,
        signature="b" * 128,
    )
    e2 = engine.emit_event(
        event_type=DelegateEventType.POSTURE_RATCHET,
        payload={"from": 1, "to": 2},
        signer_identity=signer,
        signature="c" * 128,
    )
    e3 = engine.emit_event(
        event_type=DelegateEventType.CASCADE_EMISSION,
        payload={"child_id": "child-1"},
        signer_identity=signer,
        signature="d" * 128,
    )
    assert (e1.sequence, e2.sequence, e3.sequence) == (0, 1, 2)


@pytest.mark.unit
def test_engine_previous_hash_chains_correctly() -> None:
    """Entry N+1.previous_hash == SHA-256(canonical_json(entry N))."""
    engine = AuditChainEngine(chain=_build_chain())
    signer = _build_identity()
    e1 = engine.emit_event(
        event_type=DelegateEventType.LIFECYCLE_TRANSITION,
        payload={"step": 1},
        signer_identity=signer,
        signature="e" * 128,
    )
    e2 = engine.emit_event(
        event_type=DelegateEventType.LIFECYCLE_TRANSITION,
        payload={"step": 2},
        signer_identity=signer,
        signature="f" * 128,
    )
    expected = hashlib.sha256(
        canonical_json_dumps(e1.to_canonical_dict()).encode("utf-8")
    ).hexdigest()
    assert e2.previous_hash == expected


@pytest.mark.unit
def test_engine_emit_event_raises_signature_error_on_bad_hex() -> None:
    """Pre-validates signature surface; raises typed AuditChainSignatureError.

    Distinct from AuditChainEmissionError (chain-structure failure class).
    """
    engine = AuditChainEngine(chain=_build_chain())
    with pytest.raises(AuditChainSignatureError, match="128 hex chars"):
        engine.emit_event(
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            payload={},
            signer_identity=_build_identity(),
            signature="not-hex",
        )


@pytest.mark.unit
def test_engine_emit_event_raises_emission_error_on_non_identity_signer() -> None:
    """signer MUST be DelegateIdentity; non-identity raises emission error."""
    engine = AuditChainEngine(chain=_build_chain())
    with pytest.raises(AuditChainEmissionError, match="MUST be a DelegateIdentity"):
        engine.emit_event(
            event_type=DelegateEventType.LIFECYCLE_TRANSITION,
            payload={},
            signer_identity="not-an-identity",  # type: ignore[arg-type]
            signature="0" * 128,
        )


@pytest.mark.unit
def test_engine_entries_property_returns_immutable_tuple() -> None:
    """entries MUST be a tuple snapshot, not the internal list."""
    engine = AuditChainEngine(chain=_build_chain())
    engine.emit_event(
        event_type=DelegateEventType.LIFECYCLE_TRANSITION,
        payload={},
        signer_identity=_build_identity(),
        signature="9" * 128,
    )
    snapshot = engine.entries
    assert isinstance(snapshot, tuple)
    assert len(snapshot) == 1
    # tuples are immutable — cannot append.
    with pytest.raises(AttributeError):
        snapshot.append("forbidden")  # type: ignore[attr-defined]


@pytest.mark.unit
def test_engine_head_hash_empty_chain_returns_none() -> None:
    """Empty chain → head_hash() is None (used by cross-anchor seal)."""
    engine = AuditChainEngine(chain=_build_chain())
    assert engine.head_hash() is None


@pytest.mark.unit
def test_engine_head_hash_matches_canonical_sha256_of_tail() -> None:
    """head_hash MUST equal SHA-256(canonical_json(last_entry))."""
    engine = AuditChainEngine(chain=_build_chain())
    signer = _build_identity()
    engine.emit_event(
        event_type=DelegateEventType.LIFECYCLE_TRANSITION,
        payload={},
        signer_identity=signer,
        signature="1" * 128,
    )
    tail = engine.emit_event(
        event_type=DelegateEventType.GRANT_CONSUMPTION,
        payload={"grant_id": "g-1"},
        signer_identity=signer,
        signature="2" * 128,
    )
    expected = hashlib.sha256(
        canonical_json_dumps(tail.to_canonical_dict()).encode("utf-8")
    ).hexdigest()
    assert engine.head_hash() == expected


# ---------------------------------------------------------------------------
# WitnessedCrossAnchor — salted SHA-256 + tz-aware + UUID-keyed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_witnessed_cross_anchor_is_frozen() -> None:
    """Frozen dataclass — residency-boundary contract is structurally locked."""
    anchor = WitnessedCrossAnchor(
        anchor_chain_id=uuid.uuid4(),
        witness_chain_id=uuid.uuid4(),
        anchor_sequence=0,
        witness_sequence=0,
        cross_anchor_hash="0" * 64,
        witnessed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        anchor.cross_anchor_hash = "1" * 64  # type: ignore[misc]


@pytest.mark.unit
def test_witnessed_cross_anchor_rejects_same_chain_id() -> None:
    """A chain cannot witness itself — residency boundary requires two tiers."""
    same_id = uuid.uuid4()
    with pytest.raises(CrossAnchorIntegrityError, match="MUST differ"):
        WitnessedCrossAnchor(
            anchor_chain_id=same_id,
            witness_chain_id=same_id,
            anchor_sequence=0,
            witness_sequence=0,
            cross_anchor_hash="a" * 64,
            witnessed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        )


@pytest.mark.unit
def test_witnessed_cross_anchor_rejects_naive_datetime() -> None:
    """tz-aware datetime enforced for wire-format parity."""
    with pytest.raises(CrossAnchorIntegrityError, match="timezone-aware"):
        WitnessedCrossAnchor(
            anchor_chain_id=uuid.uuid4(),
            witness_chain_id=uuid.uuid4(),
            anchor_sequence=0,
            witness_sequence=0,
            cross_anchor_hash="b" * 64,
            witnessed_at=datetime(2026, 5, 21, 12, 0, 0),  # naive
        )


@pytest.mark.unit
def test_witnessed_cross_anchor_rejects_negative_sequence() -> None:
    with pytest.raises(CrossAnchorIntegrityError, match="non-negative"):
        WitnessedCrossAnchor(
            anchor_chain_id=uuid.uuid4(),
            witness_chain_id=uuid.uuid4(),
            anchor_sequence=-1,
            witness_sequence=0,
            cross_anchor_hash="c" * 64,
            witnessed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        )


@pytest.mark.unit
def test_witnessed_cross_anchor_rejects_bad_hex() -> None:
    with pytest.raises(CrossAnchorIntegrityError, match="64 hex chars"):
        WitnessedCrossAnchor(
            anchor_chain_id=uuid.uuid4(),
            witness_chain_id=uuid.uuid4(),
            anchor_sequence=0,
            witness_sequence=0,
            cross_anchor_hash="abc",  # wrong length
            witnessed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        )


@pytest.mark.unit
def test_compute_anchor_hash_rejects_non_32_byte_salt() -> None:
    """rs M4-02 contract: salt is 256-bit residency-boundary secret."""
    with pytest.raises(CrossAnchorIntegrityError, match="32 bytes"):
        WitnessedCrossAnchor.compute_anchor_hash(b"\x00" * 16, "a" * 64)


@pytest.mark.unit
def test_compute_anchor_hash_is_deterministic() -> None:
    """SHA-256(salt || anchor_head) — pure function, deterministic."""
    salt = b"\x42" * 32
    head = "f" * 64
    d1 = WitnessedCrossAnchor.compute_anchor_hash(salt, head)
    d2 = WitnessedCrossAnchor.compute_anchor_hash(salt, head)
    assert d1 == d2
    # Sanity: it's actually SHA-256(salt || raw_head_bytes).
    expected = hashlib.sha256(salt + bytes.fromhex(head)).hexdigest()
    assert d1 == expected


@pytest.mark.unit
def test_verify_seam_succeeds_on_correct_witness_pair() -> None:
    """Untampered seam verifies (mirrors rs untampered_seam_verifies test)."""
    salt = secrets.token_bytes(32)
    head = hashlib.sha256(b"anchor-head-data").hexdigest()
    digest = WitnessedCrossAnchor.compute_anchor_hash(salt, head)
    anchor = WitnessedCrossAnchor(
        anchor_chain_id=uuid.uuid4(),
        witness_chain_id=uuid.uuid4(),
        anchor_sequence=5,
        witness_sequence=2,
        cross_anchor_hash=digest,
        witnessed_at=datetime.now(timezone.utc),
    )
    # No exception → seam holds.
    anchor.verify_seam(salt, head)


@pytest.mark.unit
def test_verify_seam_fails_on_tampered_anchor_head() -> None:
    """A single-bit change to the anchor head MUST fail the seam check."""
    salt = secrets.token_bytes(32)
    head = "a" * 64
    digest = WitnessedCrossAnchor.compute_anchor_hash(salt, head)
    anchor = WitnessedCrossAnchor(
        anchor_chain_id=uuid.uuid4(),
        witness_chain_id=uuid.uuid4(),
        anchor_sequence=0,
        witness_sequence=0,
        cross_anchor_hash=digest,
        witnessed_at=datetime.now(timezone.utc),
    )
    tampered_head = "b" + head[1:]
    with pytest.raises(CrossAnchorIntegrityError, match="seam verification failed"):
        anchor.verify_seam(salt, tampered_head)


@pytest.mark.unit
def test_verify_seam_fails_on_wrong_salt() -> None:
    """Without the correct salt the witness cannot confirm the anchor head."""
    salt = secrets.token_bytes(32)
    head = "c" * 64
    digest = WitnessedCrossAnchor.compute_anchor_hash(salt, head)
    anchor = WitnessedCrossAnchor(
        anchor_chain_id=uuid.uuid4(),
        witness_chain_id=uuid.uuid4(),
        anchor_sequence=0,
        witness_sequence=0,
        cross_anchor_hash=digest,
        witnessed_at=datetime.now(timezone.utc),
    )
    other_salt = secrets.token_bytes(32)
    with pytest.raises(CrossAnchorIntegrityError):
        anchor.verify_seam(other_salt, head)


@pytest.mark.unit
def test_witnessed_cross_anchor_canonical_signing_split() -> None:
    """canonical_dict includes cross_anchor_hash; signing_dict excludes it."""
    salt = secrets.token_bytes(32)
    head = "d" * 64
    digest = WitnessedCrossAnchor.compute_anchor_hash(salt, head)
    anchor = WitnessedCrossAnchor(
        anchor_chain_id=uuid.uuid4(),
        witness_chain_id=uuid.uuid4(),
        anchor_sequence=3,
        witness_sequence=1,
        cross_anchor_hash=digest,
        witnessed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    canonical = anchor.to_canonical_dict()
    signing = anchor.to_signing_dict()
    assert "cross_anchor_hash" in canonical
    assert "cross_anchor_hash" not in signing
    # signing dict's keys ⊂ canonical dict's keys.
    assert set(signing.keys()) <= set(canonical.keys())


# ---------------------------------------------------------------------------
# Cross-SDK byte parity stub (S7 vendoring — deferred)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "S7 vendoring: cross-SDK byte-parity test requires vendored "
        "kailash-rs kailash-delegate-audit reference vectors. The "
        "assertion shape is pinned here so the gap is greppable: "
        "py-emitted AuditChainEntry canonical-JSON MUST byte-equal "
        "rs-emitted AuditChainRecord serde_json output for the same "
        "(event_type, payload, signer, signed_at, signature) inputs."
    )
)
@pytest.mark.unit
def test_audit_chain_cross_sdk_byte_parity() -> None:
    """Cross-SDK byte parity stub — vendored under S7.

    Acceptance criterion: ``canonical_json_dumps(py_entry.to_canonical_dict())``
    MUST byte-equal the JSON produced by the rs verifier for the same
    inputs. Vendoring path: ``tests/fixtures/delegate/audit-vectors/``.
    """
    # When S7 lands the vendored fixtures, replace this skip with:
    #   fixture = json.loads(Path("tests/fixtures/delegate/audit-vectors/"
    #                              "DV-M4-001.json").read_text())
    #   py_entry = AuditChainEntry(**fixture["inputs"])
    #   py_json = canonical_json_dumps(py_entry.to_canonical_dict())
    #   assert py_json == fixture["rs_canonical_bytes"]
    raise AssertionError("unreachable — see @pytest.mark.skip reason")
