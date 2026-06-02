# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for #1209 — SignedActionEnvelope carries observed_at.

Before #1209, :class:`AttestedReadReceipt` exposed ``observed_at`` as a
first-class field (so a read receipt is independently verifiable from the
receipt object alone), but :class:`SignedActionEnvelope` did NOT — the
signed timestamp was committed inside ``canonical_bytes`` yet could not be
read off the envelope object. A caller verifying a write envelope therefore
had to supply ``observed_at`` out-of-band; it could not be re-derived from
the envelope the way the read path re-derives it from ``receipt.observed_at``.

These tests pin the fix:

1. **Structural symmetry** — ``SignedActionEnvelope`` carries an
   ``observed_at: datetime`` field, matching ``AttestedReadReceipt``.
2. **Re-derivable verification** — a write envelope is verifiable using
   ONLY the envelope object: the verifier reconstructs ``canonical_bytes``
   from ``envelope.observed_at`` + ``envelope.payload`` with no out-of-band
   timestamp parameter.
3. **Round-trip** — sign (timestamp committed into ``canonical_bytes``) →
   verify-from-envelope-alone succeeds; tampering ``observed_at`` makes the
   re-derived ``canonical_bytes`` diverge so verification fails.

This is a behavioral regression test per ``rules/testing.md`` § "Behavioral
Regression Tests Over Source-Grep": it exercises the envelope shape + the
re-derivation contract, not a source-grep for the field name.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.dispatch import AttestedReadReceipt, SignedActionEnvelope


def _canonical_action_bytes(payload: dict, observed_at: datetime) -> bytes:
    """A connector's action-canonical encoding: payload + signed timestamp.

    The timestamp IS committed into the signed bytes (the cryptographic
    soundness the issue notes is already present). #1209 makes the same
    timestamp re-derivable from the envelope object via ``observed_at``.
    """
    return json.dumps(
        {"payload": payload, "observed_at": observed_at.isoformat()},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sign(canonical_bytes: bytes) -> bytes:
    return hashlib.sha256(b"k-" + canonical_bytes).digest()


def _make_envelope(payload: dict, observed_at: datetime) -> SignedActionEnvelope:
    canonical_bytes = _canonical_action_bytes(payload, observed_at)
    return SignedActionEnvelope(
        action_id=uuid.uuid4(),
        canonical_bytes=canonical_bytes,
        signature=_sign(canonical_bytes),
        signer_delegate_id="delegate-1209",
        observed_at=observed_at,
        payload=payload,
    )


def _verify_from_envelope_alone(env: SignedActionEnvelope) -> bool:
    """Re-derive canonical_bytes from the envelope; verify — NO out-of-band ts.

    This is the contract #1209 enables: the verifier reads ``observed_at``
    off the envelope rather than requiring the caller to already know the
    exact timestamp that was baked into ``canonical_bytes``.
    """
    rederived = _canonical_action_bytes(env.payload, env.observed_at)
    return rederived == env.canonical_bytes and env.signature == _sign(rederived)


@pytest.mark.regression
def test_action_envelope_has_observed_at_field_symmetric_with_receipt() -> None:
    action_fields = {f.name for f in dataclasses.fields(SignedActionEnvelope)}
    receipt_fields = {f.name for f in dataclasses.fields(AttestedReadReceipt)}

    # The asymmetry the issue's minimal repro asserted is now closed.
    assert "observed_at" in receipt_fields  # pre-existing (read path)
    assert "observed_at" in action_fields  # #1209 (write path)

    action_type = {f.name: f.type for f in dataclasses.fields(SignedActionEnvelope)}[
        "observed_at"
    ]
    receipt_type = {f.name: f.type for f in dataclasses.fields(AttestedReadReceipt)}[
        "observed_at"
    ]
    assert action_type == receipt_type  # both annotate `datetime`


@pytest.mark.regression
def test_write_envelope_verifies_from_envelope_alone() -> None:
    observed_at = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    env = _make_envelope({"op": "transfer", "amount": 100}, observed_at)

    # Re-derive observed_at off the envelope object — no out-of-band param.
    assert env.observed_at == observed_at
    assert _verify_from_envelope_alone(env) is True


@pytest.mark.regression
def test_tampered_observed_at_fails_rederived_verification() -> None:
    observed_at = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    env = _make_envelope({"op": "transfer", "amount": 100}, observed_at)

    # An envelope whose exposed observed_at disagrees with the timestamp
    # committed into canonical_bytes must fail re-derived verification —
    # the field is load-bearing, not decorative.
    tampered = dataclasses.replace(
        env, observed_at=datetime(2026, 6, 1, 13, 0, 0, tzinfo=timezone.utc)
    )
    assert _verify_from_envelope_alone(tampered) is False


@pytest.mark.regression
def test_observed_at_is_required_no_silent_default() -> None:
    # observed_at carries no default: an envelope cannot be constructed
    # without the timestamp, preserving independent verifiability.
    with pytest.raises(TypeError):
        SignedActionEnvelope(  # type: ignore[call-arg]
            action_id=uuid.uuid4(),
            canonical_bytes=b"x",
            signature=b"y",
            signer_delegate_id="d",
        )
