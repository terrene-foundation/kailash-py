# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #1243.

``kailash.trust._json.canonical_json_dumps`` emitted the non-JSON tokens
``NaN`` / ``Infinity`` (it omitted ``allow_nan=False``) and silently
stringified non-string object keys — producing canonical signing pre-images
that its OWN paired decoder ``canonical_json_loads`` rejects, and that Rust
``serde_json`` / JS verifiers cannot read back. The encode/decode pair was not
round-trip-consistent within the same module.

The fix makes the encoder reject the same value domain the decoder rejects.
"""

from __future__ import annotations

import json
import math

import pytest

from kailash.trust._json import canonical_json_dumps, canonical_json_loads


@pytest.mark.regression
@pytest.mark.parametrize(
    ("non_finite", "token"),
    [
        (float("nan"), "NaN"),
        (float("inf"), "Infinity"),
        (float("-inf"), "-Infinity"),
    ],
)
def test_issue_1243_dumps_rejects_non_finite_symmetric_with_loads(non_finite, token):
    """The encoder rejects exactly what the decoder rejects (NaN/Infinity).

    Before the fix the encoder emitted ``'{"x":NaN}'`` while the decoder
    raised ``ValueError`` on that same string — a round-trip break.
    """
    # Sanity: the parametrized value really is the non-finite float `token` names.
    assert math.isnan(non_finite) or math.isinf(non_finite)

    # Decoder rejects the literal form (the pre-fix encoder output).
    with pytest.raises(ValueError):
        canonical_json_loads(f'{{"x":{token}}}')

    # Encoder MUST now reject the value too (the fix), rather than emit it.
    with pytest.raises(ValueError):
        canonical_json_dumps({"x": non_finite})


@pytest.mark.regression
def test_issue_1243_dumps_rejects_non_string_keys():
    """Non-string object keys are rejected, not silently stringified.

    ``{1: "a"}`` previously encoded to ``'{"1":"a"}'``; decoding that yields
    ``{"1": "a"}`` (string key) != the original int-keyed dict — a round-trip
    break the canonical signing path cannot tolerate.
    """
    for bad_key in (1, 3.14, True, None):
        with pytest.raises(ValueError):
            canonical_json_dumps({bad_key: "a"})


@pytest.mark.regression
def test_issue_1243_finite_payloads_round_trip_unchanged():
    """Valid finite payloads still encode + decode byte-for-byte (no regression).

    The fix must reject only the non-representable value domain; every legal
    canonical payload — including large integers outside the JS-safe range —
    must continue to round-trip.
    """
    obj = {
        "agent": "a-1",
        "nonce_ns": 1_780_000_000_000_000_001,  # > 2**53; Py<->Rust lossless
        "scores": [1, 2.5, -3],
        "nested": {"b": True, "c": None, "deep": {"z": "ok"}},
    }
    encoded = canonical_json_dumps(obj)
    assert canonical_json_loads(encoded) == obj
    # Deterministic sorted-key output preserved.
    assert encoded == json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


@pytest.mark.regression
def test_issue_1243_dumps_rejects_circular_reference_as_valueerror():
    """Cyclic input raises ValueError (not RecursionError).

    The producer-side key guard recurses before ``json.dumps``; a cyclic
    structure must raise ``ValueError`` (caught by the signing call sites'
    ``except (TypeError, ValueError)`` taxonomy at dispatch.py / audit.py),
    NOT an uncaught ``RecursionError`` (a ``RuntimeError`` subclass) that
    would escape those wrappers.
    """
    cyclic: dict = {"a": 1}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="[Cc]ircular"):
        canonical_json_dumps(cyclic)


@pytest.mark.regression
def test_issue_1243_dumps_allows_shared_dag_substructure():
    """A shared (non-cyclic) substructure is NOT a cycle and must encode.

    The cycle guard tracks the ancestor path only (markers add-on-entry /
    discard-on-exit), so the same dict referenced by two sibling keys is
    accepted, exactly like ``json.dumps``.
    """
    shared = {"x": 1}
    obj = {"a": shared, "b": shared}
    assert canonical_json_dumps(obj) == '{"a":{"x":1},"b":{"x":1}}'


# ---------------------------------------------------------------------------
# Issue #1243 (HIGH-1, surfaced at security review): the LIVE Ed25519/HMAC
# signing pre-image `serialize_for_signing` is a sibling canonical encoder
# that had the identical `allow_nan` hole — on the more critical, cross-SDK
# (Rust serde_json / W3C-VC) signing path. Same bug class, fixed in this PR.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_issue_1243_serialize_for_signing_rejects_non_finite(non_finite):
    """The live signing pre-image rejects NaN/Infinity rather than emitting them.

    Before the fix, ``serialize_for_signing({"x": float("nan")})`` returned the
    non-JSON string ``'{"x":NaN}'`` into the Ed25519/HMAC-signed bytes — a
    pre-image Rust ``serde_json`` and W3C-VC verifiers cannot reconstruct.
    """
    from kailash.trust.signing.crypto import serialize_for_signing

    with pytest.raises(ValueError):
        serialize_for_signing({"x": non_finite})


@pytest.mark.regression
def test_issue_1243_serialize_for_signing_finite_payload_unchanged():
    """Finite signing payloads still serialize deterministically (no regression).

    The fix must only reject the non-finite domain; the canonical sorted-key
    output for legal payloads — including big-int nonces — is unchanged, so
    existing signatures over finite payloads remain valid.
    """
    from kailash.trust.signing.crypto import serialize_for_signing

    payload = {"b": 2, "a": 1, "nonce_ns": 1_780_000_000_000_000_001}
    assert (
        serialize_for_signing(payload) == '{"a":1,"b":2,"nonce_ns":1780000000000000001}'
    )
