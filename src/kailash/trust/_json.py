# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical JSON utilities for cross-SDK parity validation.

Per SPEC-09 S8.2, Python's ``json.loads()`` silently uses last-wins for
duplicate keys, creating a parser differential with Rust's ``serde_json``
which rejects duplicates by default. This module provides
``canonical_json_loads`` which raises ``DuplicateKeyError`` on duplicate
keys, and ``canonical_json_dumps`` which produces deterministic sorted-key
output.

Used by all cross-SDK deserialization paths to ensure both Python and Rust
parsers reach the same conclusion on every input.
"""

from __future__ import annotations

import json
from typing import Any


class DuplicateKeyError(ValueError):
    """Raised when a JSON object contains duplicate keys.

    Per SPEC-09 S8.2, duplicate keys produce parser-differential
    vulnerabilities between Python (last-wins) and Rust (reject).
    Canonical parsing rejects duplicates in both SDKs.
    """

    def __init__(self, key: str, path: str = "") -> None:
        location = f" at {path}" if path else ""
        super().__init__(f"duplicate key {key!r}{location}")
        self.key = key
        self.path = path


def _make_duplicate_checker(path: str = "") -> Any:
    """Create an ``object_pairs_hook`` that rejects duplicate keys."""

    def check_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DuplicateKeyError(key, path)
            result[key] = value
        return result

    return check_duplicates


def _walk_and_check(obj: Any, path: str = "$") -> Any:
    """Recursively check for duplicate keys in nested objects.

    The ``object_pairs_hook`` only detects duplicates at the level it is
    called. For nested objects, we need to parse with the hook to catch
    all levels. Since ``json.loads`` with ``object_pairs_hook`` applies
    the hook at every nesting level, a single parse call handles all
    depths.
    """
    # The hook is applied by json.loads at every object level, so
    # recursive checking is handled by the parser itself.
    return obj


def canonical_json_loads(text: str) -> Any:
    """Parse JSON with strict mode and duplicate key rejection.

    Args:
        text: JSON string to parse.

    Returns:
        Parsed Python object.

    Raises:
        DuplicateKeyError: If any JSON object contains duplicate keys.
        json.JSONDecodeError: If the JSON is malformed.
    """
    return json.loads(
        text,
        strict=True,
        object_pairs_hook=_make_duplicate_checker(),
    )


def canonical_json_dumps(obj: Any) -> str:
    """Serialize to canonical JSON with sorted keys and no extra whitespace.

    The output is deterministic: keys are sorted alphabetically at every
    nesting level, and no trailing whitespace or newlines are emitted.
    This matches the canonical encoder order required by SPEC-09 S8.2.

    Args:
        obj: Python object to serialize.

    Returns:
        Canonical JSON string.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
