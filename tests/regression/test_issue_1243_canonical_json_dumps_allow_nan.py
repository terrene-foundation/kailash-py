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
