# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK PROVISIONAL tripwire vectors for the EATP-12 D5 signed
RevocationEvent pre-image + Ed25519 signature AND the append-only
revocation-ledger tip fold.

kailash-rs LEADS and authored the reference bytes (rs#1849 / rs#1763 OPEN — these
vectors are PROVISIONAL; re-pin in lockstep if rs changes them, per
``cross-sdk-inspection.md`` Rule 4b). These assert the Python production path
reproduces the pinned rs bytes BYTE-FOR-BYTE:

* ``RevocationEvent`` (RE0-RE3): pre-image string + Ed25519 signature hex, incl.
  the RE3 nanosecond-fidelity boundary vector.
* Ledger tip fold (LT0-LT3): LT0 all-zero empty tip, LT1 single, LT2 two ascending,
  LT3 two reversed (a DIFFERENT tip — pins order-dependence).

The vectors are vendored (per ``cross-sdk-inspection.md`` Rule 4a) into
``tests/test-vectors/`` from the rs-authored reference set. Real crypto, no
mocking (testing.md Tier 2/3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kailash.trust.revocation.signed_ledger import (
    GENESIS_TIP,
    RevocationLedger,
    RevocationLedgerError,
    SignedRevocationEvent,
    revocation_ledger_tip,
)

pytestmark = pytest.mark.regression

_REF_DIR = Path(__file__).resolve().parents[1] / "test-vectors"
_EVENT_VECTORS = json.loads(
    (_REF_DIR / "revocation-event-vectors.json").read_text(encoding="utf-8")
)
_TIP_VECTORS = json.loads(
    (_REF_DIR / "revocation-ledger-tip-vectors.json").read_text(encoding="utf-8")
)

# RFC 8032 §7.1 Test 1 keypair (cross-SDK byte-shape fixtures only; never live signing).
_SECRET_SEED = bytes.fromhex(_EVENT_VECTORS["keypair"]["secret_key_hex"])
_PUBLIC_KEY = bytes.fromhex(_EVENT_VECTORS["keypair"]["public_key_hex"])


def _event_from_vector(vec: dict) -> SignedRevocationEvent:
    return SignedRevocationEvent(
        delegation_id=vec["input"]["delegation_id"],
        epoch=vec["input"]["epoch"],
        revoked_at=vec["input"]["revoked_at"],
    )


# --- RevocationEvent pre-image + signature (RE0-RE3) -------------------------


@pytest.mark.parametrize(
    "vec", _EVENT_VECTORS["vectors"], ids=[v["id"] for v in _EVENT_VECTORS["vectors"]]
)
def test_revocation_event_preimage_matches_pinned(vec: dict) -> None:
    """The canonical JCS pre-image string EQUALS the pinned rs bytes."""
    event = _event_from_vector(vec)
    preimage = event.signing_preimage()
    assert preimage == vec["expected_canonical_preimage"], (
        f"{vec['id']}: pre-image diverged from pinned rs bytes\n"
        f"  got:      {preimage!r}\n"
        f"  expected: {vec['expected_canonical_preimage']!r}"
    )


@pytest.mark.parametrize(
    "vec", _EVENT_VECTORS["vectors"], ids=[v["id"] for v in _EVENT_VECTORS["vectors"]]
)
def test_revocation_event_signature_matches_pinned(vec: dict) -> None:
    """Ed25519 signature (hex) over the pre-image EQUALS the pinned rs bytes."""
    event = _event_from_vector(vec)
    signature_hex = event.sign(_SECRET_SEED)
    assert signature_hex == vec["expected_signature_hex"], (
        f"{vec['id']}: signature diverged from pinned rs bytes\n"
        f"  got:      {signature_hex}\n"
        f"  expected: {vec['expected_signature_hex']}"
    )
    # Round-trip: the pinned signature verifies against the pinned public key.
    assert event.verify(vec["expected_signature_hex"], _PUBLIC_KEY)


def test_re3_nanosecond_fidelity_preserved() -> None:
    """RE3 pins that the 9-digit nanosecond tail is STRING-PRESERVED, not
    microsecond-truncated — the pre-image + signature only match if the full
    nanosecond timestamp survives verbatim."""
    re3 = next(v for v in _EVENT_VECTORS["vectors"] if v["id"].startswith("RE3"))
    event = _event_from_vector(re3)
    # The nanosecond tail is carried verbatim (9 fractional digits).
    assert event.revoked_at == "2026-07-17T12:34:56.123456789Z"
    assert "123456789" in event.signing_preimage()
    assert event.sign(_SECRET_SEED) == re3["expected_signature_hex"]


# --- Ledger tip fold (LT0-LT3) ----------------------------------------------


@pytest.mark.parametrize(
    "vec", _TIP_VECTORS["vectors"], ids=[v["id"] for v in _TIP_VECTORS["vectors"]]
)
def test_revocation_ledger_tip_matches_pinned(vec: dict) -> None:
    """The folded tip EQUALS the pinned rs tip hex (LT0 empty all-zero,
    LT1 single, LT2 two ascending, LT3 two reversed)."""
    events = [
        SignedRevocationEvent(
            delegation_id=e["delegation_id"],
            epoch=e["epoch"],
            revoked_at=e["revoked_at"],
        )
        for e in vec["events"]
    ]
    tip_hex = revocation_ledger_tip(events).hex()
    assert tip_hex == vec["expected_tip_hex"], (
        f"{vec['id']}: ledger tip diverged from pinned rs bytes\n"
        f"  got:      {tip_hex}\n"
        f"  expected: {vec['expected_tip_hex']}"
    )


def test_lt0_empty_ledger_is_all_zero_tip() -> None:
    """LT0: an empty ledger folds to the 32-zero-byte genesis tip."""
    lt0 = next(v for v in _TIP_VECTORS["vectors"] if v["id"].startswith("LT0"))
    assert revocation_ledger_tip([]) == GENESIS_TIP
    assert GENESIS_TIP.hex() == lt0["expected_tip_hex"]
    assert RevocationLedger().tip() == GENESIS_TIP


def test_lt3_order_dependence_reversed_differs_from_ascending() -> None:
    """LT3 vs LT2: the SAME two events in reversed order fold to a DIFFERENT
    tip — the fold is order-dependent (reorder/delete detection)."""
    lt2 = next(v for v in _TIP_VECTORS["vectors"] if v["id"].startswith("LT2"))
    lt3 = next(v for v in _TIP_VECTORS["vectors"] if v["id"].startswith("LT3"))

    def _fold(vec: dict) -> str:
        events = [
            SignedRevocationEvent(
                delegation_id=e["delegation_id"],
                epoch=e["epoch"],
                revoked_at=e["revoked_at"],
            )
            for e in vec["events"]
        ]
        return revocation_ledger_tip(events).hex()

    ascending = _fold(lt2)
    reversed_ = _fold(lt3)
    assert ascending != reversed_, "fold MUST be order-dependent (LT2 != LT3)"
    assert ascending == lt2["expected_tip_hex"]
    assert reversed_ == lt3["expected_tip_hex"]


# --- Append-only enforcement -------------------------------------------------


def test_ledger_append_enforces_strictly_ascending_epoch() -> None:
    """The ledger rejects a non-ascending epoch on append (no reorder/replay);
    the canonical ascending path reproduces the LT2 tip."""
    ledger = RevocationLedger()
    ledger.append(
        SignedRevocationEvent("del-0001", 2, "2026-07-17T00:00:00.000000000Z")
    )
    # Replaying / reordering a lower-or-equal epoch is a fail-closed violation.
    with pytest.raises(RevocationLedgerError, match="append-only violation"):
        ledger.append(
            SignedRevocationEvent("del-0001", 2, "2026-07-17T00:00:00.000000000Z")
        )
    ledger.append(
        SignedRevocationEvent("del-0002", 3, "2026-07-17T00:00:00.000000000Z")
    )
    lt2 = next(v for v in _TIP_VECTORS["vectors"] if v["id"].startswith("LT2"))
    assert ledger.tip_hex() == lt2["expected_tip_hex"]


def test_malformed_event_fails_closed() -> None:
    """Malformed events are rejected at construction (fail-closed)."""
    with pytest.raises(RevocationLedgerError):
        SignedRevocationEvent("", 0, "2026-07-17T00:00:00.000000000Z")
    with pytest.raises(RevocationLedgerError):
        SignedRevocationEvent("del-x", -1, "2026-07-17T00:00:00.000000000Z")
    with pytest.raises(RevocationLedgerError):
        # microsecond (6-digit) timestamp — would truncate nanosecond fidelity.
        SignedRevocationEvent("del-x", 0, "2026-07-17T00:00:00.000000Z")
    with pytest.raises(RevocationLedgerError):
        # bool epoch must not slip through the int check.
        SignedRevocationEvent("del-x", True, "2026-07-17T00:00:00.000000000Z")
