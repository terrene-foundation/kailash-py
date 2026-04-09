# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK ConstraintEnvelope round-trip tests (SPEC-07 §5, SPEC-09 §2.4).

These tests instantiate the canonical ``ConstraintEnvelope`` frozen
dataclass from ``kailash.trust.envelope`` and verify that its
``to_canonical_json()`` output exactly matches the fixture file that
``kailash-rs``'s ``eatp::constraints::ConstraintEnvelope`` consumes for
cross-SDK parity validation (EATP D6).

Spec-compliance v2 CRITICAL #8 failure class this file guards against:

1. Previous version used ``json.dumps(input_obj, sort_keys=True, ...)``
   on a plain dict and never instantiated ``ConstraintEnvelope``. Passed
   even when the envelope's ``to_canonical_json`` had drift bugs.
2. Previous version hardcoded an absolute developer path to
   ``src/kailash/trust/envelope.py`` -- the test only ran on one machine
   and broke on CI. This version uses the installed import, no
   path-based ``importlib.util``.
3. Previous version did not exercise intersection or HMAC signing --
   both are required for SPEC-07 cross-SDK parity.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import os

import pytest

from kailash.trust.envelope import (
    ConstraintEnvelope,
    EnvelopeValidationError,
    SecretRef,
    sign_envelope,
    verify_envelope,
)

# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "envelope_minimal.json",
        "envelope_with_posture_ceiling.json",
    ],
)
def test_envelope_canonical_round_trip(load_vector, filename):
    """``ConstraintEnvelope`` produces fixture-exact canonical JSON.

    Instantiates via ``ConstraintEnvelope.from_dict(input)``, calls
    ``to_canonical_json()``, asserts byte equality with
    ``expected_canonical_json``, then parses the canonical JSON back and
    asserts the reconstructed instance is equal (frozen dataclass
    structural equality).
    """
    vector = load_vector("envelope", filename)
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    # Build the canonical class from the fixture dict -- the whole point
    # of the test is to exercise ConstraintEnvelope, not to re-serialize
    # a plain dict.
    envelope = ConstraintEnvelope.from_dict(input_obj)

    actual = envelope.to_canonical_json()
    assert actual == expected, (
        f"Canonical JSON mismatch for {filename}:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )

    # Round-trip: parse the canonical JSON back into an envelope.
    round_tripped = ConstraintEnvelope.from_dict(json.loads(expected, strict=True))
    assert round_tripped == envelope, (
        f"Round-trip inequality for {filename}:\n"
        f"  original:    {envelope}\n"
        f"  round-trip:  {round_tripped}"
    )

    # Second canonical emission MUST also match (idempotence).
    assert round_tripped.to_canonical_json() == expected


def test_envelope_hash_is_stable_across_instances(load_vector):
    """The ``envelope_hash`` field is deterministic for identical inputs.

    Two independently constructed envelopes with the same constraint
    content MUST produce the same ``envelope_hash``. This is the
    cross-SDK tamper-detection invariant per SPEC-07 §6.
    """
    vector = load_vector("envelope", "envelope_with_posture_ceiling.json")
    a = ConstraintEnvelope.from_dict(vector["input"])
    b = ConstraintEnvelope.from_dict(vector["input"])
    assert a.envelope_hash() == b.envelope_hash()
    # The hash MUST appear in the canonical JSON.
    assert a.envelope_hash() in a.to_canonical_json()


# ---------------------------------------------------------------------------
# Monotonic intersection (SPEC-07 §5.3)
# ---------------------------------------------------------------------------


def test_envelope_intersection_matches_fixture(load_vector):
    """``intersect`` produces the exact cross-SDK canonical intersection.

    The Rust ``eatp::constraints::ConstraintEnvelope::intersect`` MUST
    produce the same canonical JSON from the same two inputs. This test
    is the contract.
    """
    vector = load_vector("envelope", "envelope_with_intersection.json")
    left = ConstraintEnvelope.from_dict(vector["left"])
    right = ConstraintEnvelope.from_dict(vector["right"])

    assert left.to_canonical_json() == vector["expected_left_canonical_json"]
    assert right.to_canonical_json() == vector["expected_right_canonical_json"]

    intersected = left.intersect(right)
    assert (
        intersected.to_canonical_json()
        == vector["expected_intersection_canonical_json"]
    ), (
        f"Intersection canonical JSON mismatch:\n"
        f"  expected: {vector['expected_intersection_canonical_json']}\n"
        f"  actual:   {intersected.to_canonical_json()}"
    )

    # Commutativity: intersect is order-independent for the canonical form.
    reversed_intersection = right.intersect(left)
    assert reversed_intersection.to_canonical_json() == intersected.to_canonical_json()

    # Monotonic tightening: the intersection is at least as tight as each
    # input on every dimension.
    assert intersected.is_tighter_than(left)
    assert intersected.is_tighter_than(right)


# ---------------------------------------------------------------------------
# HMAC signing (SPEC-07 §5.4 / §6)
# ---------------------------------------------------------------------------


def test_envelope_hmac_signature_matches_fixture(load_vector, monkeypatch):
    """HMAC-SHA256 over the canonical JSON matches the fixture.

    The Rust SDK MUST compute the same HMAC digest over the byte-stable
    canonical form -- this is the wire contract between the two SDKs for
    envelope attestation per SPEC-07 §6.
    """
    vector = load_vector("envelope", "envelope_signed.json")
    envelope = ConstraintEnvelope.from_dict(vector["input"])

    # Canonical JSON byte-equality (the payload the HMAC signs).
    actual_canonical = envelope.to_canonical_json()
    assert actual_canonical == vector["expected_canonical_json"]

    hmac_spec = vector["hmac"]
    # Inject the deterministic test key into the environment via the
    # ``env`` SecretRef provider. ``monkeypatch`` auto-restores on teardown.
    monkeypatch.setenv(hmac_spec["key_id"], hmac_spec["key_value"])
    secret = SecretRef(
        key_id=hmac_spec["key_id"],
        provider="env",
        algorithm=hmac_spec["algorithm"],
    )

    actual_signature = sign_envelope(envelope, secret)
    assert actual_signature == hmac_spec["expected_signature_hex"], (
        f"HMAC signature mismatch:\n"
        f"  expected: {hmac_spec['expected_signature_hex']}\n"
        f"  actual:   {actual_signature}"
    )

    # verify_envelope MUST accept the freshly computed signature.
    assert verify_envelope(envelope, actual_signature, secret) is True

    # Tampering: flipping one byte of the canonical payload breaks the
    # signature. Construct a tampered envelope and assert verify rejects.
    tampered = ConstraintEnvelope.from_dict(
        {
            **vector["input"],
            "metadata": {"agent_id": "impersonator"},  # different agent
        }
    )
    assert verify_envelope(tampered, actual_signature, secret) is False


def test_envelope_hmac_independent_recompute(load_vector, monkeypatch):
    """Manual HMAC recomputation matches ``sign_envelope``.

    Cross-check against Python's stdlib ``hmac`` module directly so that a
    regression in ``sign_envelope`` (e.g. changing the payload encoding)
    surfaces here independently of the canonical class's own helper.
    """
    vector = load_vector("envelope", "envelope_signed.json")
    envelope = ConstraintEnvelope.from_dict(vector["input"])
    hmac_spec = vector["hmac"]

    monkeypatch.setenv(hmac_spec["key_id"], hmac_spec["key_value"])
    secret = SecretRef(key_id=hmac_spec["key_id"], provider="env")

    manual = hmac_mod.new(
        hmac_spec["key_value"].encode("utf-8"),
        envelope.to_canonical_json().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    via_helper = sign_envelope(envelope, secret)
    assert manual == via_helper == hmac_spec["expected_signature_hex"]


# ---------------------------------------------------------------------------
# Structural validation failure modes
# ---------------------------------------------------------------------------


def test_envelope_rejects_unknown_top_level_field():
    """``from_dict`` rejects unknown top-level fields.

    This is the SPEC-09 §8.3 wire-format drift mitigation: a new field
    added in one SDK MUST NOT be silently dropped by the other.
    """
    with pytest.raises(Exception) as excinfo:
        ConstraintEnvelope.from_dict({"unknown_field": "value"})
    # Accept either UnknownEnvelopeFieldError (subclass of EnvelopeValidationError)
    # or the base class -- both are structural violations.
    assert (
        "unknown_field" in str(excinfo.value).lower()
        or "unknown fields" in str(excinfo.value).lower()
    )


def test_envelope_rejects_invalid_posture_ceiling():
    """An unrecognized ``posture_ceiling`` value is a structural error."""
    with pytest.raises(EnvelopeValidationError, match="posture_ceiling"):
        ConstraintEnvelope(posture_ceiling="definitely_not_a_valid_posture")


def test_envelope_is_importable_from_canonical_module():
    """``ConstraintEnvelope`` is importable from ``kailash.trust.envelope``.

    Guards against module relocation without a re-export shim. Uses a
    relative import (no hardcoded absolute paths on any machine).
    """
    from kailash.trust import envelope as canonical_module

    assert hasattr(canonical_module, "ConstraintEnvelope")
    assert canonical_module.ConstraintEnvelope is ConstraintEnvelope
    # Sanity: the class lives in the kailash.trust namespace.
    assert ConstraintEnvelope.__module__ == "kailash.trust.envelope"
