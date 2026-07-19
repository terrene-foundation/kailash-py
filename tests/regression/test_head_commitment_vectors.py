# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK PROVISIONAL tripwire vectors for the EATP-12 D5 owner-signed
``HeadCommitment`` epoch anchor pre-image + Ed25519 signature, plus the
anti-rollback high-water anchor.

kailash-rs LEADS and authored the reference bytes (rs#1849 / rs#1763 OPEN — these
vectors are PROVISIONAL; re-pin in lockstep if rs changes them, per
``cross-sdk-inspection.md`` Rule 4b). These assert the Python production path
reproduces the pinned rs bytes BYTE-FOR-BYTE:

* ``HeadCommitment`` (HC0-HC3): the JCS pre-image string + Ed25519 signature hex,
  incl. the HC3 nanosecond-fidelity boundary vector (a 9-digit fractional second
  that MUST be string-preserved, not microsecond-truncated).
* Anti-rollback: a persisted head whose epoch is LOWER than a retained high-water
  is rejected fail-closed (replay defense); equal/greater epochs advance the anchor.

The vectors are vendored (per ``cross-sdk-inspection.md`` Rule 4a) into
``tests/test-vectors/head-commitment-vectors.json`` from the rs-authored reference
set. Real crypto, no mocking (testing.md Tier 2/3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kailash.trust.revocation.head_commitment import (
    HeadCommitment,
    HeadCommitmentAnchor,
    HeadCommitmentError,
)

pytestmark = pytest.mark.regression

_REF_DIR = Path(__file__).resolve().parents[1] / "test-vectors"
_HC_VECTORS = json.loads(
    (_REF_DIR / "head-commitment-vectors.json").read_text(encoding="utf-8")
)

# RFC 8032 §7.1 Test 1 keypair (cross-SDK byte-shape fixtures only; never live signing).
_SECRET_SEED = bytes.fromhex(_HC_VECTORS["keypair"]["secret_key_hex"])
_PUBLIC_KEY = bytes.fromhex(_HC_VECTORS["keypair"]["public_key_hex"])


def _head_from_vector(vec: dict) -> HeadCommitment:
    i = vec["input"]
    return HeadCommitment(
        epoch=i["epoch"],
        block_count=i["block_count"],
        tip_hash=bytes.fromhex(i["tip_hash"]),
        revocation_ledger_tip=bytes.fromhex(i["revocation_ledger_tip"]),
        signed_at=i["signed_at"],
    )


# --- HeadCommitment pre-image + signature (HC0-HC3) --------------------------


@pytest.mark.parametrize(
    "vec", _HC_VECTORS["vectors"], ids=[v["id"] for v in _HC_VECTORS["vectors"]]
)
def test_head_commitment_preimage_matches_pinned(vec: dict) -> None:
    """The canonical JCS pre-image string EQUALS the pinned rs bytes."""
    head = _head_from_vector(vec)
    preimage = head.signing_preimage()
    assert preimage == vec["expected_canonical_preimage"], (
        f"{vec['id']}: pre-image diverged from pinned rs bytes\n"
        f"  got:      {preimage!r}\n"
        f"  expected: {vec['expected_canonical_preimage']!r}"
    )


@pytest.mark.parametrize(
    "vec", _HC_VECTORS["vectors"], ids=[v["id"] for v in _HC_VECTORS["vectors"]]
)
def test_head_commitment_signature_matches_pinned(vec: dict) -> None:
    """Owner Ed25519 signature (hex) over the pre-image EQUALS the pinned rs bytes."""
    head = _head_from_vector(vec)
    signature_hex = head.sign(_SECRET_SEED)
    assert signature_hex == vec["expected_signature_hex"], (
        f"{vec['id']}: signature diverged from pinned rs bytes\n"
        f"  got:      {signature_hex}\n"
        f"  expected: {vec['expected_signature_hex']}"
    )
    # Round-trip: the pinned signature verifies against the pinned public key.
    assert head.verify(vec["expected_signature_hex"], _PUBLIC_KEY)


def test_hc3_nanosecond_fidelity_preserved() -> None:
    """HC3 pins that the 9-digit nanosecond tail is STRING-PRESERVED, not
    microsecond-truncated — the pre-image + owner signature only match if the full
    nanosecond timestamp survives verbatim."""
    hc3 = next(v for v in _HC_VECTORS["vectors"] if v["id"].startswith("HC3"))
    head = _head_from_vector(hc3)
    # The nanosecond tail is carried verbatim (9 fractional digits).
    assert head.signed_at == "2026-07-17T12:34:56.123456789Z"
    assert "123456789" in head.signing_preimage()
    assert head.sign(_SECRET_SEED) == hc3["expected_signature_hex"]


def test_hc0_genesis_all_zero_tips() -> None:
    """HC0: the genesis head (epoch 0, block_count 0) binds all-zero tips for BOTH
    the chain tip and the (empty-ledger) revocation-ledger tip."""
    hc0 = next(v for v in _HC_VECTORS["vectors"] if v["id"].startswith("HC0"))
    head = _head_from_vector(hc0)
    assert head.epoch == 0 and head.block_count == 0
    assert head.tip_hash == bytes(32)
    assert head.revocation_ledger_tip == bytes(32)
    assert head.signing_preimage() == hc0["expected_canonical_preimage"]


# --- Anti-rollback high-water anchor -----------------------------------------


def test_anti_rollback_lower_epoch_replay_rejected() -> None:
    """A persisted head whose epoch is LOWER than the retained high-water is
    rejected fail-closed (replay/rollback defense) — the core anti-rollback test."""
    anchor = HeadCommitmentAnchor()
    hc2 = _head_from_vector(
        next(v for v in _HC_VECTORS["vectors"] if v["id"].startswith("HC2"))
    )  # epoch 2
    hc1 = _head_from_vector(
        next(v for v in _HC_VECTORS["vectors"] if v["id"].startswith("HC1"))
    )  # epoch 1

    anchor.accept(hc2)  # advance high-water to epoch 2
    assert anchor.high_water_epoch == 2

    # Replaying the earlier epoch-1 head against the retained high-water is a rollback.
    with pytest.raises(HeadCommitmentError, match="anti-rollback violation"):
        anchor.accept(hc1)
    # The high-water is NOT rolled back by the rejected replay.
    assert anchor.high_water_epoch == 2


def test_anti_rollback_equal_and_greater_epochs_accepted() -> None:
    """An epoch EQUAL to the high-water (re-reading the current head) is accepted;
    a strictly-greater epoch advances the high-water. The high-water never decreases."""
    heads = {v["id"][:3]: _head_from_vector(v) for v in _HC_VECTORS["vectors"]}
    anchor = HeadCommitmentAnchor()

    anchor.accept(heads["HC0"])  # epoch 0
    assert anchor.high_water_epoch == 0
    anchor.accept(heads["HC0"])  # equal epoch re-read → accepted, no rollback
    assert anchor.high_water_epoch == 0
    anchor.accept(heads["HC1"])  # epoch 1 → advance
    anchor.accept(heads["HC2"])  # epoch 2 → advance
    anchor.accept(heads["HC3"])  # epoch 3 → advance
    assert anchor.high_water_epoch == 3
    # Re-reading the current (highest) head is still accepted.
    anchor.accept(heads["HC3"])
    assert anchor.high_water_epoch == 3


# --- Fail-closed construction + hardening ------------------------------------


def test_malformed_head_fails_closed() -> None:
    """Malformed fields are rejected at construction (fail-closed)."""
    ok = {
        "epoch": 1,
        "block_count": 1,
        "tip_hash": bytes(32),
        "revocation_ledger_tip": bytes(32),
        "signed_at": "2026-07-17T00:00:00.000000000Z",
    }
    # Wrong-length hash slot.
    with pytest.raises(HeadCommitmentError, match="32 bytes"):
        HeadCommitment(**{**ok, "tip_hash": bytes(31)})
    with pytest.raises(HeadCommitmentError, match="32 bytes"):
        HeadCommitment(**{**ok, "revocation_ledger_tip": bytes(33)})
    # microsecond (6-digit) timestamp — would truncate nanosecond fidelity.
    with pytest.raises(HeadCommitmentError, match="signed_at"):
        HeadCommitment(**{**ok, "signed_at": "2026-07-17T00:00:00.000000Z"})
    # bool epoch / block_count must not slip through the int check.
    with pytest.raises(HeadCommitmentError, match="epoch must be an int"):
        HeadCommitment(**{**ok, "epoch": True})
    with pytest.raises(HeadCommitmentError, match="block_count must be an int"):
        HeadCommitment(**{**ok, "block_count": False})


def test_epoch_u64_range_enforced_fail_closed() -> None:
    """A u64 epoch is fail-closed at both bounds: ``2**64`` (out of range) raises;
    ``2**64 - 1`` (max u64) is accepted. An oversized epoch would serialize as a JSON
    number rs cannot parse into a u64, making the signed pre-image unreproducible
    cross-SDK."""
    base = {
        "block_count": 1,
        "tip_hash": bytes(32),
        "revocation_ledger_tip": bytes(32),
        "signed_at": "2026-07-17T00:00:00.000000000Z",
    }
    with pytest.raises(HeadCommitmentError, match="u64 range"):
        HeadCommitment(epoch=2**64, **base)
    ok = HeadCommitment(epoch=2**64 - 1, **base)
    assert ok.epoch == 2**64 - 1


def test_verify_fails_closed_on_malformed_signature_hex() -> None:
    """``verify()`` returns False (never raises) on malformed / short / non-hex
    signature input — fail-closed, not an off-contract ValueError."""
    head = HeadCommitment(
        epoch=1,
        block_count=1,
        tip_hash=bytes(32),
        revocation_ledger_tip=bytes(32),
        signed_at="2026-07-17T00:00:00.000000000Z",
    )
    assert head.verify("not-hex-!!", _PUBLIC_KEY) is False
    assert head.verify("dead", _PUBLIC_KEY) is False  # valid hex, wrong length
    assert head.verify("", _PUBLIC_KEY) is False
    assert head.verify("abc", _PUBLIC_KEY) is False  # odd-length hex


def test_to_from_dict_round_trip() -> None:
    """``from_dict(to_dict())`` round-trips; a missing field raises the typed error
    naming the field, and a malformed hex hash raises the typed error (not a bare
    ValueError)."""
    head = _head_from_vector(
        next(v for v in _HC_VECTORS["vectors"] if v["id"].startswith("HC2"))
    )
    data = head.to_dict()
    assert HeadCommitment.from_dict(data) == head
    # The signed head still verifies after a dict round-trip (bytes preserved).
    hc2 = next(v for v in _HC_VECTORS["vectors"] if v["id"].startswith("HC2"))
    assert HeadCommitment.from_dict(data).verify(
        hc2["expected_signature_hex"], _PUBLIC_KEY
    )
    for missing in data:
        partial = {k: v for k, v in data.items() if k != missing}
        with pytest.raises(HeadCommitmentError, match=missing):
            HeadCommitment.from_dict(partial)
    with pytest.raises(HeadCommitmentError, match="malformed hex"):
        HeadCommitment.from_dict({**data, "tip_hash": "zz"})
