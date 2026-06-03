# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK canonical JSON parsing tests (SPEC-09 S8.2).

Verifies that ``canonical_json_loads`` rejects duplicate keys (matching
Rust's ``serde_json`` default behavior) and that ``canonical_json_dumps``
produces deterministic sorted-key output for cross-SDK byte-equivalence.
"""

from __future__ import annotations

import json

import pytest

from kailash.trust._json import (
    DuplicateKeyError,
    canonical_json_dumps,
    canonical_json_loads,
)


def test_duplicate_key_rejected():
    """Top-level duplicate key raises ``DuplicateKeyError``.

    Python's stdlib ``json.loads`` silently uses last-wins for duplicate
    keys. ``canonical_json_loads`` MUST reject them so both Python and
    Rust parsers agree on every input (SPEC-09 S8.2 mitigation 4).
    """
    with pytest.raises(DuplicateKeyError, match="duplicate key.*'a'"):
        canonical_json_loads('{"a": 1, "a": 2}')


def test_nested_duplicate_rejected():
    """Nested duplicate key is also rejected.

    The ``object_pairs_hook`` applies at every nesting level during
    ``json.loads``, so nested duplicates are caught automatically.
    """
    with pytest.raises(DuplicateKeyError, match="duplicate key.*'x'"):
        canonical_json_loads('{"outer": {"x": 1, "x": 2}}')


def test_valid_json_parses_identically():
    """Valid JSON parses to the same result as ``json.loads``.

    ``canonical_json_loads`` MUST not alter the semantics of valid JSON
    — only reject inputs that would create parser differentials.
    """
    text = '{"b": 2, "a": [1, {"c": 3}]}'
    canonical = canonical_json_loads(text)
    stdlib = json.loads(text)
    assert canonical == stdlib


def test_sorted_serialization():
    """``canonical_json_dumps`` produces sorted keys with no whitespace.

    The output is deterministic and matches the canonical encoder order
    required by SPEC-09 S8.2 for cross-SDK byte-equivalence.
    """
    obj = {"z": 1, "a": {"y": 2, "b": 3}, "m": [1, 2]}
    result = canonical_json_dumps(obj)
    assert result == '{"a":{"b":3,"y":2},"m":[1,2],"z":1}'


def test_canonical_round_trip():
    """Dumps then loads produces the original object."""
    obj = {"name": "test", "values": [1, 2, 3], "nested": {"key": "val"}}
    text = canonical_json_dumps(obj)
    restored = canonical_json_loads(text)
    assert restored == obj


def test_strict_mode_rejects_control_characters():
    """``canonical_json_loads`` uses ``strict=True`` per SPEC-09 S8.2.

    Raw control characters inside JSON strings are rejected to match
    Rust's ``serde_json`` strict mode behavior.
    """
    with pytest.raises(json.JSONDecodeError):
        canonical_json_loads('{"key": "value\nwith newline"}')


# ---------------------------------------------------------------------------
# Issue #1243 — encoder/decoder round-trip symmetry.
#
# ``canonical_json_loads`` rejects NaN/Infinity (RFC 8259); the encoder MUST
# reject the same values rather than emitting non-JSON tokens (``NaN``,
# ``Infinity``) that its own paired decoder — and Rust ``serde_json`` — refuse.
# It MUST also reject non-string object keys, which the wire form cannot carry
# without silently stringifying them (breaking round-trip with the decoder,
# whose output keys are always strings).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_dumps_rejects_non_finite_floats(bad):
    """The encoder rejects NaN/Infinity/-Infinity, symmetric with the decoder.

    Before the fix, ``canonical_json_dumps({"x": float("nan")})`` returned the
    non-JSON string ``'{"x":NaN}'`` which ``canonical_json_loads`` then refused
    to parse — the encode/decode pair was not round-trip-consistent.
    """
    with pytest.raises(ValueError):
        canonical_json_dumps({"x": bad})


def test_dumps_rejects_nested_non_finite_float():
    """Non-finite floats nested inside arrays/objects are also rejected."""
    with pytest.raises(ValueError):
        canonical_json_dumps({"outer": {"vals": [1.0, float("inf")]}})


def test_dumps_rejects_top_level_non_finite_float():
    """A bare non-finite float (not wrapped in a container) is rejected."""
    with pytest.raises(ValueError):
        canonical_json_dumps(float("nan"))


@pytest.mark.parametrize("key", [1, 2**53, 3.14, True, None])
def test_dumps_rejects_non_string_object_key(key):
    """Non-string object keys are rejected, not silently stringified.

    ``json.dumps`` coerces int/float/bool/None keys to strings
    (``{1: "a"}`` -> ``'{"1":"a"}'``); the canonical encoder MUST reject them
    so the encode/decode pair round-trips (the decoder always yields string
    keys).
    """
    with pytest.raises(ValueError):
        canonical_json_dumps({key: "value"})


def test_dumps_rejects_nested_non_string_object_key():
    """Non-string keys nested below the top level are also rejected."""
    with pytest.raises(ValueError):
        canonical_json_dumps({"outer": {1: "value"}})


def test_dumps_round_trip_symmetry_property():
    """For every value the decoder rejects, the encoder rejects too.

    This is the load-bearing invariant of issue #1243: the canonical
    encode/decode pair must agree on the value domain. The encoder must never
    produce bytes its own paired decoder cannot read back.
    """
    # NaN/Infinity: decoder rejects (parse_constant) -> encoder must reject.
    for non_finite in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            canonical_json_dumps({"x": non_finite})


def test_dumps_allows_large_integers():
    """Integers beyond the JS-safe range are NOT rejected (Py<->Rust scope).

    The canonical encoder's documented parity scope is Python and Rust
    (``serde_json``), both of which carry 64-bit+ integers losslessly. Common
    signing payloads (e.g. nanosecond timestamps ~1.78e18 > 2**53) rely on
    this. JS-consumer 2**53 safety is explicitly out of scope per issue #1243
    acceptance criterion 3 ("(Consider) ... when JS consumers are in scope").
    """
    assert canonical_json_dumps({"n": 2**53}) == '{"n":9007199254740992}'
    assert canonical_json_dumps({"n": 2**63 + 1}) == '{"n":9223372036854775809}'
