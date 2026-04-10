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
