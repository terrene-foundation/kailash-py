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


def canonical_json_loads(text: str) -> Any:
    """Parse JSON with strict mode and duplicate key rejection.

    Rejects NaN, Infinity, and -Infinity literals which are not valid
    JSON per RFC 8259 but accepted by Python's ``json.loads`` default.

    Args:
        text: JSON string to parse.

    Returns:
        Parsed Python object.

    Raises:
        DuplicateKeyError: If any JSON object contains duplicate keys.
        json.JSONDecodeError: If the JSON is malformed.
        ValueError: If NaN or Infinity literals are present.
    """
    result = json.loads(
        text,
        strict=True,
        object_pairs_hook=_make_duplicate_checker(),
        parse_constant=_reject_nan_inf,
    )
    return result


def _reject_nan_inf(constant: str) -> None:
    """Reject NaN/Infinity which are not valid JSON per RFC 8259."""
    raise ValueError(
        f"Invalid JSON constant {constant!r} — NaN and Infinity "
        f"are not permitted in canonical JSON (RFC 8259)"
    )


def _reject_non_string_keys(obj: Any, path: str = "$") -> None:
    """Reject non-string object keys before canonical serialization.

    ``json.dumps`` silently coerces ``int`` / ``float`` / ``bool`` / ``None``
    object keys to strings (``{1: "a"}`` -> ``'{"1":"a"}'``). The canonical
    wire form assumes string keys (RFC 8259 object members), and
    ``canonical_json_loads`` always yields string keys — so silent coercion
    breaks round-trip symmetry between the encode/decode pair. We reject
    non-string keys at the producer boundary instead, recursively, so the
    failure surfaces at the signing site rather than as a verification
    mismatch on another implementation.

    Raises:
        ValueError: If any object key (at any nesting depth) is not a ``str``.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"non-string object key {key!r} ({type(key).__name__}) at "
                    f"{path} — canonical JSON requires string keys (RFC 8259 "
                    f"object members); coercing would break round-trip symmetry "
                    f"with canonical_json_loads"
                )
            _reject_non_string_keys(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _reject_non_string_keys(value, f"{path}[{index}]")


def canonical_json_dumps(obj: Any) -> str:
    """Serialize to canonical JSON with sorted keys and no extra whitespace.

    The output is deterministic: keys are sorted alphabetically at every
    nesting level, and no trailing whitespace or newlines are emitted.
    This matches the canonical encoder order required by SPEC-09 S8.2.

    This encoder is symmetric with :func:`canonical_json_loads` on the value
    domain it accepts: it rejects (raises) ``NaN`` / ``Infinity`` /
    ``-Infinity`` (via ``allow_nan=False``) — which are not valid JSON per
    RFC 8259 and which the paired decoder already refuses — and it rejects
    non-string object keys rather than silently stringifying them. This
    guarantees the encoder never produces signing pre-images that its own
    decoder, Rust ``serde_json``, or any RFC-8259 verifier cannot read back.

    Note: integers outside the JS-safe range (``±(2**53 - 1)``) are NOT
    rejected. The canonical parity scope is Python and Rust (``serde_json``),
    both of which carry 64-bit+ integers losslessly; common signing payloads
    (e.g. nanosecond timestamps) depend on this. JS-consumer ``2**53`` safety
    is out of scope (issue #1243 acceptance criterion 3).

    Args:
        obj: Python object to serialize.

    Returns:
        Canonical JSON string.

    Raises:
        ValueError: If ``obj`` contains ``NaN`` / ``Infinity`` / ``-Infinity``
            float values, or any non-string object key.
    """
    _reject_non_string_keys(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
